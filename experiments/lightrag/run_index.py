"""Index an employee handbook with the LightRAG backend.

Usage (from repo root): .venv\\Scripts\\python experiments/lightrag/run_index.py agents/pd_marty [profile]
Profile defaults to the active one (data/settings.json, else .env
EMBED_PROFILE, else "local"). Logs every LLM call to
storage/<eid>/<profile>/llm_log.jsonl. Refuses to start when
--stop-tokens would already be exceeded (spend guard; Meta publishes no
per-token price, so the guard counts estimated tokens: chars/4).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

STOP_TOKENS = 100000  # >> expected ~10k for one handbook file


def main(agent_dir, profile=None):
    from agents._frame import graph
    eid = os.path.basename(os.path.normpath(agent_dir))
    prof = profile or graph._adapter().embed_settings()["profile"]
    est = _logged_tokens(eid, prof)
    if est >= STOP_TOKENS:
        raise SystemExit("stop: logged estimate already %d tokens" % est)
    res = graph.index_corpus(agent_dir, profile)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    print("log:", os.path.join("experiments", "lightrag", "storage", eid,
                               res["profile"], "llm_log.jsonl"))


def _logged_tokens(eid, profile):
    p = os.path.join(ROOT, "experiments", "lightrag", "storage",
                     eid, profile, "llm_log.jsonl")
    if not os.path.isfile(p):
        return 0
    total = 0
    with open(p, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            total += (r.get("prompt_chars", 0) + r.get("reply_chars", 0)) // 4
    return total


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
