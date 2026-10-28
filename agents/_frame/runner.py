"""Bounded ReAct runner (D11). One model call -> tool calls -> results, until
write_draft succeeds or max_steps runs out. Stdlib only."""
import json
import os
import time
import urllib.request

BASE_URL = "https://api.meta.ai/v1"
MAX_TOKENS = 8000  # Spark spends heavily on reasoning; budget generously


def _key():
    key = os.environ.get("MODEL_API_KEY") or os.environ.get("META_API_KEY")
    if not key:
        raise RuntimeError("MODEL_API_KEY missing")
    return key


def _chat(model, messages, tools):
    body = {"model": model, "messages": messages, "max_tokens": MAX_TOKENS}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    req = urllib.request.Request(
        BASE_URL + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + _key(),
                "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode())


def run(agent_dir, run_dir, brief, input_md):
    from . import tools as reg
    os.makedirs(run_dir, exist_ok=True)
    events_path = os.path.join(run_dir, "events.jsonl")
    events = []

    def emit(ev):
        ev["t"] = time.strftime("%H:%M:%S")
        events.append(ev)
        with open(events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    with open(os.path.join(agent_dir, "agent.json"), encoding="utf-8") as f:
        agent = json.load(f)
    with open(os.path.join(agent_dir, "persona.md"), encoding="utf-8") as f:
        persona = f.read()
    available = reg.get_tools(agent_dir)
    missing = [n for n in agent["tools"] if n not in available]
    if missing:
        emit({"ev": "run_fail",
              "reason": "unknown tools: " + ",".join(missing)})
        return {"ok": False, "events": events, "usage": total}
    play = {n: available[n] for n in agent["tools"]}
    oai = [{"type": "function",
            "function": {"name": n, "description": d, "parameters": s}}
           for n, (_, d, s) in play.items()]
    ctx = {"run_dir": run_dir, "agent_dir": agent_dir, "input_md": input_md}
    messages = [
        {"role": "system", "content": persona},
        {"role": "user", "content":
         "BRIEF:\n" + json.dumps(brief, ensure_ascii=False)
         + "\n\nINPUT FILE:\n" + input_md
         + "\n\nDo the job. Use tools. Read before writing. "
           "Finish by calling write_draft with the complete draft object."},
    ]
    emit({"ev": "run_start", "agent": agent["id"], "model": agent["model"]})
    total = {"prompt": 0, "completion": 0}
    for step in range(1, agent["bounds"]["max_steps"] + 1):
        resp = _chat(agent["model"], messages, oai)
        usage = resp.get("usage", {})
        total["prompt"] += usage.get("prompt_tokens", 0)
        total["completion"] += usage.get("completion_tokens", 0)
        msg = resp["choices"][0]["message"]
        messages.append(msg)
        calls = msg.get("tool_calls") or []
        emit({"ev": "llm", "step": step,
              "tool_calls": [c["function"]["name"] for c in calls],
              "usage": usage})
        if not calls:
            emit({"ev": "run_fail", "reason": "model stopped without tool call",
                  "text": (msg.get("content") or "")[:300]})
            return {"ok": False, "events": events, "usage": total}
        finished = False
        for call in calls:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except ValueError:
                args = {}
            if name not in play:
                result = {"error": "unknown tool: " + name}
            else:
                try:
                    result = play[name][0](ctx, args)
                except Exception as exc:  # noqa: BLE001 - surfaced to the model
                    result = {"error": "%s: %s" % (type(exc).__name__, exc)}
            ok = result.get("ok", "error" not in result)
            tool_ev = {"ev": "tool", "step": step, "tool": name, "ok": bool(ok)}
            if "errors" in result:
                tool_ev["errors"] = result["errors"]
            emit(tool_ev)
            messages.append({"role": "tool", "tool_call_id": call["id"],
                             "content": json.dumps(result, ensure_ascii=False)[:4000]})
            if name == "write_draft" and result.get("ok"):
                finished = True
        if finished:
            emit({"ev": "run_done", "usage": total})
            return {"ok": True, "events": events, "usage": total}
    emit({"ev": "run_fail", "reason": "max_steps exhausted", "usage": total})
    return {"ok": False, "events": events, "usage": total}
