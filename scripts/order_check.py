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

# ---- exact server-side strings (contract with the chat UI) ----
ok(intake.READY_QUESTION == "I have everything I need. Anything else "
   "you'd like to add? Shall I start?",
   "ready question is exact")
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

print("FAILURES: %d" % len(FAILS) if FAILS else "ALL PASS")
sys.exit(1 if FAILS else 0)
