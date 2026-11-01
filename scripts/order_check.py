"""Order confirm-and-start checks (stdlib only).

Run: python scripts/order_check.py. Pure-function checks for the in-chat
confirm flow: readiness is decided by code (missing list), Sam's ready
question is an exact server-side string, and PDF sections are built by
rule, not by the model. No sockets, no model calls, no writes.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
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
ok(all(v in intake.NO_PROMISE_RULE.lower()
       for v in ("start", "pars", "upload", "writ", "runn")),
   "no-promise rule names every action")
ok("never promise" in intake.NO_PROMISE_RULE.lower(),
   "no-promise rule forbids promising")

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
# ---- chat wording is model-driven, decisions are code ----
ok(_srv.count("self._sam_turn(") == 3,
   "keep, ask and chat turns share one model-worded turn")
ok("CONFIRM_AGAIN" not in _srv.split("def _api_order_chat")[1]
   .split("def _sam_turn")[0],
   "no fixed line left in the confirm turns")

# ---- conversation-only start: no buttons, yes/no by text ----
for _y in ("yes, start", "Yes, start.", "go ahead", "ok", "START", "please start",
         "ok let's start", "sure, go ahead", "start please", "let's go"):
    ok(intake.classify_confirm(_y) == "yes",
       "clear yes: %r" % (_y,))
for _n in ("No, not yet.", "not yet", "wait"):
    ok(intake.classify_confirm(_n) == "no",
       "clear no: %r" % (_n,))
for _u in ("", "maybe later", "yes, but change the theme", "what happens next?"):
    ok(intake.classify_confirm(_u) is None,
       "unclear stays unclear: %r" % (_u,))
ok(intake.confirm_step(False, "yes, start") == "chat",
   "not ready: normal model turn")
ok(intake.confirm_step(True, "yes, start") == "start",
   "ready + yes starts (ord-20261101-245 regression)")
ok(intake.confirm_step(True, "ok let's start") == "start",
   "ready + ok-let-start starts (ord-20261101-271 regression)")
ok(intake.confirm_step(True, "No, not yet.") == "keep",
   "ready + no keeps the consultation open")
ok(intake.confirm_step(True, "hmm?") == "ask",
   "ready + unclear asks once more")
ok(intake.parse_confirm_word("YES") == "yes"
   and intake.parse_confirm_word("  no\n") == "no"
   and intake.parse_confirm_word("UNCLEAR") is None
   and intake.parse_confirm_word("Yes, start!") is None,
   "one-word verdict parses strictly")
ok("_judge_confirm" in _srv and "JUDGE_PROMPT" in open(
   os.path.join(ROOT, "scripts", "intake.py"), encoding="utf-8").read(),
   "unclear ready turns get a one-word LLM verdict")
ok("o-confirm" not in _ui and "o-yes" not in _ui and "showConfirm" not in _ui,
   "confirm buttons and their wiring are gone")
ok("_do_chat_accept" in _srv and "accepted" in _srv,
   "chat-yes confirms now, the client then calls start")
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
# ---- user questions are answered from the LightRAG index ----
for _q in ("What video lengths do you support?",
           "How long does production take?",
           "Can I change the theme later?"):
    ok(intake.looks_like_question(_q),
       "question detected: %r" % (_q,))
for _s in ("beginners", "10 minutes", "yes, start", ""):
    ok(not intake.looks_like_question(_s),
       "statement left alone: %r" % (_s,))
ok("graph.query" in _srv,
   "sam turns consult the LightRAG index on questions")
ok("rag lookup skipped" in _srv,
   "a dead index never breaks the turn")


print("FAILURES: %d" % len(FAILS) if FAILS else "ALL PASS")
sys.exit(1 if FAILS else 0)
