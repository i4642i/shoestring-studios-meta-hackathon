"""Order confirm-and-start checks (stdlib only).

Run: python scripts/order_check.py. Pure-function checks for the in-chat
confirm flow: readiness is decided by code (missing list), Sam's ready
question is an exact server-side string, and PDF sections are built by
rule, not by the model. No sockets, no model calls, no writes.
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)
import intake  # noqa: E402

FAILS = []


def ok(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


# ---- readiness: the missing list decides, not the model ----
ok(intake.INTAKE_KEYS == ("audience", "length", "depth", "theme"),
   "4 intake keys")
ok(intake.missing_of({}, {}) == ["audience", "length", "depth", "theme",
                                 "source PDF"],
   "empty order misses all 4 + PDF")
ok(intake.missing_of({"audience": "x", "length": "y", "depth": "z",
                      "theme": "w"}, {"source": "source.pdf"}) == [],
   "complete answers + stored PDF is ready")
ok(intake.missing_of({"audience": "x"}, {}) == ["length", "depth", "theme",
                                               "source PDF"],
   "partial answers still missing")
ok(intake.missing_of({"audience": "x", "length": "y", "depth": "z",
                      "theme": "w"}, {}) == ["source PDF"],
   "answers without PDF miss only the PDF")
ok(intake.missing_of({"audience": "  "}, {"source": "source.pdf"})
   == ["audience", "length", "depth", "theme"],
   "blank answer counts as missing")

ok(bool(intake.DECLINE_ACK.strip()) and len(intake.DECLINE_ACK) <= 200,
   "decline ack is short")
ok("start" not in intake.DECLINE_ACK.lower()
   or "not" in intake.DECLINE_ACK.lower(),
   "decline ack promises no start")

# ---- sections: numbered headings become markdown headings ----
SAMPLE = "\n".join([
    "# Parsed source: book.pdf", "",
    "## Page 1", "", "Preface text here.", "",
    "## Page 2", "", "1.1 Getting started", "Some intro.", "",
    "1.1.1 First steps", "Details here.", "",
    "## Page 3", "", "1.2 Moving on", "More text.",
    "A line with 2.51 numbers stays text.", ""])
md, heads = intake.build_sections(SAMPLE)
ok(heads == ["1.1 Getting started", "1.1.1 First steps",
             "1.2 Moving on"],
   "numbered headings found in order")
ok("## 1.1 Getting started" in md and "### 1.1.1 First steps" in md
   and "## 1.2 Moving on" in md,
   "heading depth follows dot count")
ok("*p. 1*" in md and "*p. 2*" in md and "*p. 3*" in md,
   "page numbers kept as notes")
ok("## Page 2" not in md, "page markers converted to notes")
ok("A line with 2.51 numbers stays text." in md,
   "mid-line numbers stay plain text")
ok("Preface text here." in md, "unheaded text kept")

md2, heads2 = intake.build_sections("## Page 1\n\nJust prose, no numbers.\n")
ok(heads2 == [] and "Just prose, no numbers." in md2,
   "no headings passes text through")

# ---- chat reply envelope: missing rides with every reply (J4) ----
p = intake.chat_reply_payload("hi", False, ["source PDF"])
ok(p == {"reply": "hi", "ready": False, "missing": ["source PDF"]},
   "chat payload carries reply+ready+missing")
ok(intake.chat_reply_payload("ok", True, [])["missing"] == [],
   "ready payload has empty missing")
ok(intake.chat_reply_payload("x", False, None)["missing"] == [],
   "missing None becomes []")

# ---- received state: started orders lock the consultation (J25) ----
ok(intake.STARTED == ("complete", "in_production"),
   "started statuses are complete + in_production")
ok(intake.RECEIVED_LINE
   == "Thanks! Your order is in. The crew has started.",
   "received line is exact")
_ui = open(os.path.join(ROOT, "index.html"),
           encoding="utf-8").read()
ok("Thanks! Your order is in. The crew has started." in _ui,
   "UI writes the fixed received line")
ok("Order received" in _ui and "olockdim" in _ui
   and "oreceived" in _ui and "__recepLock" in _ui,
   "UI has the received card, dim and room lock")
ok("already started" in open(os.path.join(ROOT, "scripts",
                                          "server.py"),
                             encoding="utf-8").read(),
   "server refuses turns on started orders")

# ---- reply cleaning: imitated control/function blocks go, text stays ----
RAW = ("<|start|>assistant to=commentary<|message|>Got it! I will help.<|eom|>"
       '<|start|>assistant to=pc_send_source<|message|><function name="pc_send_source"></function><|eot|> trailing.')
ok(intake.clean_chat_reply(RAW) == "Got it! I will help. trailing.",
   "control + function blocks stripped, plain text kept")
ok(intake.clean_chat_reply("plain text stays") == "plain text stays",
   "clean reply leaves plain text alone")
ok(intake.clean_chat_reply('<function name="x"></function>') == "",
   "tool-only reply cleans to empty")
ok(intake.clean_chat_reply('a <function name="x"/> b') == "a b",
   "self-closing function tag stripped")
ok(intake.CHAT_UNREADABLE == "Sam's reply could not be read, please send again.",
   "unreadable error line is exact")
_srv = open(os.path.join(ROOT, "scripts", "server.py"),
             encoding="utf-8").read()
ok("clean_chat_reply" in _srv and "CHAT_UNREADABLE" in _srv,
   "chat endpoint cleans every reply, errors when empty")
ok('rec["raw"]' in _srv,
   "chat log keeps the raw reply for audit")
# ---- one tool loop: the model decides, the server follows ----
ok(_srv.count("self._sam_turn(") == 1,
   "every chat turn goes through the single tool loop")
ok("confirm_step(" not in _srv and "_judge_confirm" not in _srv
   and "extract_form_block" not in _srv and "FORM_PROMPT" not in _srv
   and "looks_like_question" not in _srv,
   "no keyword path, no separate judge, no extraction, no router")
ok(not hasattr(intake, "classify_confirm")
   and not hasattr(intake, "confirm_step")
   and not hasattr(intake, "looks_like_question")
   and not hasattr(intake, "extract_form_block")
   and not hasattr(intake, "merge_form"),
   "no user-reading helpers left in intake")
ok("finalize_and_send" in _srv and "update_form" in _srv
   and "search_knowledge" in _srv and "tool_call_id" in _srv,
   "the server only does what the tool calls say")
ok("SAM_CHAT_TOOLS" in _srv,
   "chat offers only the three tools, never the runner writer")
ok("o-confirm" not in _ui and "o-yes" not in _ui and "showConfirm" not in _ui,
   "confirm buttons and their wiring are gone")
ok("_handover" in _srv and "handed_over" in _srv,
   "chat-yes finalizes at once, no second start call")
ok("start_result.json" in _srv and "starting" in _srv,
   "start clears its flag and keeps its result for reload")
ok("/progress" in _srv or "order_progress" in _srv,
   "progress endpoint serves the card lines")
ok("beginStarting" in _ui and "o-startcard" in _ui,
   "order tab dims the room with a progress card")
ok("Say 'start' to try again." in _ui,
   "failed start tells the client how to retry")
ok(intake.ACCEPT_LINE.startswith("Order received"),
   "accept line names the received state")
ok(intake.retry_line("boom") == "Something went wrong while "
   "starting: boom. Say 'start' to try again.",
   "retry line carries the reason")
_tl = [{"at": "2026-11-01 22:01:28", "source": "sam",
        "ev": "start", "summary": "x"},
       {"at": "2026-11-01 22:01:34", "source": "pc_worker",
        "ev": "start", "summary": "y"},
       {"at": "2026-11-01 22:02:18", "source": "pc_worker",
        "ev": "failed", "summary": "name 'secs' is not defined"}]
_el = [{"at": "2026-11-01T22:01:33", "ev": "ingested", "pages": 18},
       {"at": "2026-11-01T22:02:10", "ev": "transcribe_call",
        "kind": "table", "page": 8, "error": ""}]
_pl, _pf, _pr = intake.progress_lines(_tl, _el)
ok(_pl == ["Sam is writing the production request",
           "Reading your PDF (18 pages)",
           "Reading the table on page 8",
           "Problem: name 'secs' is not defined"],
   "progress lines read like the live order")
ok(_pf is True and _pr == "name 'secs' is not defined",
   "failed event surfaces with its reason")
ok(intake.progress_lines([], []) == ([], False, ""),
   "empty logs give empty progress")
# ---- Sam looks things up by calling search_knowledge ----
from agents._frame import tools as _tools
_samdir = os.path.join(ROOT, "agents", "sales_sam")
_g = _tools.get_tools(_samdir)
ok(all(k in _g and callable(_g[k][0])
       and isinstance(_g[k][1], str) and isinstance(_g[k][2], dict)
       for k in ("search_knowledge", "update_form",
                 "finalize_and_send")),
   "the three tools load with descriptions + schemas")
ok(json.load(open(os.path.join(_samdir, "agent.json"),
                  encoding="utf-8"))["tools"]
   == ["search_knowledge", "update_form", "finalize_and_send",
       "write_request"],
   "agent.json keeps the chat tools + the runner writer")
ok(_tools.search_knowledge({"agent_dir": _samdir}, {})
   .get("error", "").startswith("give query"),
   "search_knowledge needs a query")
_sk = _tools.search_knowledge({"agent_dir": ""}, {"query": "hi"})
ok(isinstance(_sk, dict) and ("answer" in _sk or "error" in _sk),
   "search_knowledge always answers as a dict")
# ---- parse is its own stage with % progress ----
_tl2 = [{"at": "2026-11-01 22:01:28", "source": "sam",
         "ev": "start", "summary": "x"},
        {"at": "2026-11-01 22:01:40", "source": "sam",
         "ev": "parse", "summary": "Parsing your PDF\u2026 12%"},
        {"at": "2026-11-01 22:02:05", "source": "sam",
         "ev": "parse", "summary": "Parsing your PDF\u2026 45%"},
        {"at": "2026-11-01 22:03:11", "source": "sam",
         "ev": "parse", "summary": "Parsing your PDF\u2026 100%"}]
_pl2, _, _ = intake.progress_lines(_tl2, [])
ok(_pl2 == ["Sam is writing the production request",
            "Parsing your PDF\u2026 100%"],
   "parse % lines collapse into the latest one")
import pc_worker
ok(pc_worker.stage_pct("transcribe", 0, 10) == 5
   and pc_worker.stage_pct("transcribe", 10, 10) == 45
   and pc_worker.stage_pct("describe", 1, 4) == 48
   and pc_worker.stage_pct("map", 3, 3) == 85
   and pc_worker.stage_pct("index", 0, 0) == 100
   and pc_worker.stage_pct("bogus", 1, 2) == 50,
   "parse % bands are monotonic inside each stage")
from agents._frame import runner as _runner
_old_chat = _runner._chat


def _boom(*a, **k):
    raise TimeoutError("timed out")


_runner._chat = _boom
try:
    _rd = tempfile.mkdtemp(prefix="sam_timeout_")
    _res = _runner.run(os.path.join(ROOT, "agents", "pd_marty"),
                       _rd, {"order_id": "fixture-ord",
                             "answers": {}}, "# fixture inputs")
finally:
    _runner._chat = _old_chat
    shutil.rmtree(_rd, ignore_errors=True)
ok(_res.get("ok") is False, "a model timeout fails the run")
_rfails = [e for e in _res.get("events", [])
           if e.get("ev") == "run_fail"]
ok(_rfails and "timed out" in _rfails[-1].get("reason", "")
   and "kept" in _rfails[-1].get("reason", ""),
   "timeout reason says the parse results are kept")
_flaky_calls = []


def _flaky(*a, **k):
    _flaky_calls.append(1)
    if len(_flaky_calls) < 3:
        raise ConnectionError("EOF occurred in violation of protocol")
    raise TimeoutError("stop after retries")


_runner._chat = _flaky
_old_sleep = _runner.CHAT_RETRY_SLEEP
_runner.CHAT_RETRY_SLEEP = 0
try:
    _rd3 = tempfile.mkdtemp(prefix="sam_transport_")
    _res3 = _runner.run(os.path.join(ROOT, "agents", "pd_marty"),
                        _rd3, {"order_id": "fixture-ord",
                               "answers": {}}, "# fixture inputs")
finally:
    _runner._chat = _old_chat
    _runner.CHAT_RETRY_SLEEP = _old_sleep
    shutil.rmtree(_rd3, ignore_errors=True)
ok(len(_flaky_calls) == 3 and _res3.get("ok") is False,
   "transient transport errors retry the model call, then fail clean")
_fatal_calls = []


def _fatal(*a, **k):
    _fatal_calls.append(1)
    raise ValueError("bad key")


_runner._chat = _fatal
try:
    _rd4 = tempfile.mkdtemp(prefix="sam_fatal_")
    _res4 = _runner.run(os.path.join(ROOT, "agents", "pd_marty"),
                        _rd4, {"order_id": "fixture-ord",
                               "answers": {}}, "# fixture inputs")
finally:
    _runner._chat = _old_chat
    shutil.rmtree(_rd4, ignore_errors=True)
_rfails4 = [e for e in _res4.get("events", [])
            if e.get("ev") == "run_fail"]
ok(len(_fatal_calls) == 1 and _res4.get("ok") is False
   and _rfails4 and "ValueError" in _rfails4[-1].get("reason", ""),
   "non-transport errors fail the stage without retry")
ok("_finalize_order" in _srv and "finalize_and_send" in _srv
   and "_try_fill_answers" not in _srv and "_extract_intake" not in _srv
   and "_run_parse_stage" not in _srv,
   "finalize replaces the extraction call and the blocking parse")
_seen = []


def _cap(*a, **k):
    _seen.append((a, k))
    raise TimeoutError("stop")


_runner._chat = _cap
try:
    _rd2 = tempfile.mkdtemp(prefix="sam_input_")
    _fp = os.path.join(_rd2, "INPUTS.md")
    open(_fp, "w", encoding="utf-8").write("# bundle body here")
    _runner.run(os.path.join(ROOT, "agents", "pd_marty"), _rd2,
                {"order_id": "fixture-ord", "answers": {}}, _fp)
    _runner.run(os.path.join(ROOT, "agents", "pd_marty"), _rd2,
                {"order_id": "fixture-ord", "answers": {}},
                "# raw body here")
finally:
    _runner._chat = _old_chat
    shutil.rmtree(_rd2, ignore_errors=True)
ok(any("# bundle body here" in str(m)
       for a, k in _seen for m in a[1]),
   "input file path is inlined into the prompt")
ok(any("# raw body here" in str(m)
       for a, k in _seen for m in a[1]),
   "raw input text still passes through")
# ---- the chat-filled form is the source of truth ----
_td = tempfile.mkdtemp(prefix="sam_form_")
json.dump({"id": "fixture-ord", "assignee": "sales_sam",
           "status": "consulting", "answers": {}, "files": {}},
          open(os.path.join(_td, "meta.json"), "w", encoding="utf-8"))
_fx = {"producer": "sales_sam", "order_id": "fixture-ord",
       "agent_dir": _samdir, "order_dir": _td}
_ur = _tools.update_form(_fx, {"audience": "beginners"})
ok(_ur.get("ok") is True and _ur.get("changed") == ["audience"]
   and json.load(open(os.path.join(_td, "form.json"),
                      encoding="utf-8"))["audience"] == "beginners",
   "update_form saves what the turn revealed")
_ur2 = _tools.update_form(_fx, {"audience": "",
                               "length": "10 minutes"})
ok(_ur2.get("changed") == ["length"]
   and _tools._load_form(_td, {})["audience"] == "beginners",
   "a blank update never wipes a filled field")
_fr = _tools.finalize_and_send(
    {"producer": "sales_sam", "order_id": "fixture-ord",
     "agent_dir": _samdir, "order_dir": _td}, {})
ok(_fr.get("error") == "intake incomplete"
   and "depth" in _fr.get("missing", []),
   "finalize refuses an incomplete form without any model call")
shutil.rmtree(_td, ignore_errors=True)
ok(intake.form_complete({"audience": "a", "length": "b",
                         "depth": "c", "theme": "d"})
   and not intake.form_complete({"audience": "a"}),
   "completeness is decided by code, not the model")
_pr = _tools.final_request_prompt("ord-9", {"audience": "beginners",
                                            "length": "10 min",
                                            "depth": "key", "theme": "ex"},
                                  "book.pdf", 12)
ok("ord-9" in _pr and "beginners" in _pr and "book.pdf" in _pr,
   "final request is written from the form")
_pay = intake.chat_reply_payload("hi", True, [],
                                 {"audience": "a", "length": "b",
                                  "depth": "c", "theme": "d"})
ok(_pay["form"] == {"audience": "a", "length": "b", "depth": "c",
                     "theme": "d"}
   and _pay["form_complete"] is True,
   "every reply carries the form for the panel")
_el2 = [{"at": "2026-11-01T22:04:01", "ev": "progress", "pct": 12},
        {"at": "2026-11-01T22:04:40", "ev": "progress", "pct": 45}]
_pl3, _, _ = intake.progress_lines([], _el2)
ok(_pl3 == ["Parsing your PDF\u2026 45%"],
   "worker % rows collapse into the latest line")
# ---- every LLM call is logged in full, keys never ----
import json as _json
import urllib.request as _urlreq
from agents._frame import llmlog as _llmlog
_nested = {"authorization": "Bearer sk-live", "ok": 1,
           "deep": {"api_key": "x", "text": "keep me"}}
_out = _llmlog.scrub(_nested)
ok("authorization" not in _out and "api_key" not in _out["deep"]
   and _out["deep"]["text"] == "keep me" and _out["ok"] == 1,
   "key-shaped fields are dropped, text kept")
_old_env = os.environ.get("BASETEN_API_KEY")
os.environ["BASETEN_API_KEY"] = "sk-test-secret-12345"
try:
    _s = _llmlog.scrub({"msg": "key sk-test-secret-12345 here"})
finally:
    if _old_env is None:
        del os.environ["BASETEN_API_KEY"]
    else:
        os.environ["BASETEN_API_KEY"] = _old_env
ok(_s == {"msg": "key *** here"},
   "configured key values are redacted from text")
_img = {"role": "user", "content": [
    {"type": "text", "text": "look"},
    {"type": "image_url", "image_url": {
        "url": "data:image/png;base64," + "QUJD" * 100}}]}
_dropped = _llmlog.drop_images([_img])
_u = _dropped[0]["content"][1]["image_url"]["url"]
ok("base64," not in _u and "bytes" in _u
   and _dropped[0]["content"][0]["text"] == "look",
   "image bytes become a byte count, text kept")


class _FakeResp:
    def __init__(self, payload):
        self._p = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return _json.dumps(self._p).encode()


_real_open = _urlreq.urlopen


def _fake_open(req, timeout=None):
    return _FakeResp({"choices": [{"message": {"content": "hi there"}}],
                      "usage": {"prompt_tokens": 10,
                                "completion_tokens": 3}})


_urlreq.urlopen = _fake_open
_old_key = os.environ.get("BASETEN_API_KEY")
os.environ["BASETEN_API_KEY"] = "test-dummy-key"
try:
    _ld = tempfile.mkdtemp(prefix="llmlog_")
    _lp = os.path.join(_ld, "llm_calls.jsonl")
    _msgs = [{"role": "system", "content": "be sam"},
             {"role": "user", "content": "hello"}]
    _tools = [{"type": "function",
               "function": {"name": "f", "parameters": {}}}]
    _got = _runner._chat("meta-models/muse-spark-open-1026", _msgs,
                         _tools, caller="sam:test", log_path=_lp)
    _line = open(_lp, encoding="utf-8").read()
    _rec = _json.loads(_line.strip().splitlines()[-1])
finally:
    _urlreq.urlopen = _real_open
    if _old_key is None:
        del os.environ["BASETEN_API_KEY"]
    else:
        os.environ["BASETEN_API_KEY"] = _old_key
    shutil.rmtree(_ld, ignore_errors=True)
ok(_got["choices"][0]["message"]["content"] == "hi there",
   "logged call still returns the reply")
ok(_rec["caller"] == "sam:test"
   and _rec["model"] == "meta-models/muse-spark-open-1026"
   and _rec["prompt_tokens"] == 10 and _rec["completion_tokens"] == 3
   and _rec["messages"] == _msgs and _rec["tools"] == _tools
   and _rec["reply"] == {"content": "hi there"}
   and isinstance(_rec["seconds"], (int, float))
   and "Bearer" not in _line,
   "one JSONL line holds the full request and reply, no keys")


def _boom_open(req, timeout=None):
    raise TimeoutError("timed out")


_urlreq.urlopen = _boom_open
_old_key2 = os.environ.get("BASETEN_API_KEY")
os.environ["BASETEN_API_KEY"] = "test-dummy-key"
try:
    _ld2 = tempfile.mkdtemp(prefix="llmlog_err_")
    _lp2 = os.path.join(_ld2, "llm_calls.jsonl")
    try:
        _runner._chat("meta-models/muse-spark-open-1026",
                      [{"role": "user", "content": "x"}],
                      None, caller="sam:err", log_path=_lp2)
        _raised = False
    except TimeoutError:
        _raised = True
    _rec2 = _json.loads(open(_lp2, encoding="utf-8").read().strip())
finally:
    _urlreq.urlopen = _real_open
    if _old_key2 is None:
        del os.environ["BASETEN_API_KEY"]
    else:
        os.environ["BASETEN_API_KEY"] = _old_key2
    shutil.rmtree(_ld2, ignore_errors=True)
ok(_raised and _rec2["reply"] is None
   and "timed out" in (_rec2.get("error") or "")
   and _rec2["caller"] == "sam:err",
   "failed calls are logged too, then raised")
ok("sales_sam:chat" in _srv and "llm_calls.jsonl" in _srv,
   "sam chat turns land in the order log")
# ---- crew listing never depends on the process cwd (J42) ----
from agents._frame import tools as _tools
_aroot_bare = _tools._agents_root({})
ok(os.path.isfile(os.path.join(_aroot_bare, "sales_sam",
                               "agent.json"))
   and os.path.isfile(os.path.join(_aroot_bare, "pd_marty",
                                   "agent.json")),
   "recipient check resolves the agents folder without agent_dir")
ok(_tools._agents_root(
    {"agent_dir": os.path.join(ROOT, "agents", "sales_sam")})
   == _aroot_bare,
   "recipient check with agent_dir resolves the same folder")
ok(_tools._agents_root(
    {"agent_dir": os.path.join("no", "such", "dir")})
   == _aroot_bare,
   "recipient check falls back when agent_dir is bogus")
ok('"agent_dir": agent_dir' in _srv,
   "server-side crew listing passes its agent dir")
ok("self._json(200, bad)" in _srv and "CHAT_UNREADABLE" in _srv,
   "a failed chat accept still answers 200 so Sam speaks + retry")


print("FAILURES: %d" % len(FAILS) if FAILS else "ALL PASS")
sys.exit(1 if FAILS else 0)
