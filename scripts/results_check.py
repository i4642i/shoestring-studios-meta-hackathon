"""Focused checks for agents/_frame/results.py (Step 1). Stdlib only.

Run: python scripts/results_check.py. Writes only to a temp dir.
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agents._frame import results

fails = 0


def ok(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails += 1


def raises(fn, msg):
    try:
        fn()
    except RuntimeError:
        ok(True, msg)
        return
    ok(False, msg)


REQ = {"order_id": "o1",
       "client_answers": {"audience": "a", "length": "b", "depth": "c",
                         "theme": "d", "source": "e"},
       "source_summary": "s", "production_notes": ["n"],
       "open_questions": []}

reg = results.registry()
ok(set(reg) == {"brief", "source", "request", "structure", "video"},
   "registry has 5 incl video")
ok(all(reg[c]["version"] == 1 for c in reg), "all v1")

r = results.make_result("sales_sam", "o1", "r1", {"request": dict(REQ)})
ok(r["status"] == "unverified" and r["format_version"] == 1
   and r["categories"]["request"]["version"] == 1, "make_result wraps")
ok(results.check_result(r) == [], "fresh result validates")
raises(lambda: results.make_result("x", "o", "r", {"nope": {}}),
       "unknown category raises")
raises(lambda: results.make_result("x", "o", "r", {"request": []}),
       "non-dict data raises")

bad = dict(r)
del bad["run_id"]
ok(any("run_id" in e for e in results.check_result(bad)),
   "missing header key caught")
bad = dict(r, format_version=2)
ok(any("format_version" in e for e in results.check_result(bad)),
   "bad format_version caught")
bad = dict(r, status="maybe")
ok(any("status" in e for e in results.check_result(bad)),
   "bad status caught")
bad = {"producer": "x", "format_version": 1, "order_id": "o",
       "run_id": "r", "created_at": "t", "status": "unverified",
       "reviewed_by": None, "reviewed_at": None,
       "verified_by": None, "verified_at": None,
       "categories": {"request": {"version": 2, "data": dict(REQ)}}}
ok(any("not in accepted" in e for e in results.check_result(bad)),
   "version mismatch refuses")
ok(results.check_result(bad, {"request": [1, 2]}) == [],
   "accepted versions honored")
bad2 = dict(REQ)
del bad2["production_notes"]
r2 = results.make_result("sales_sam", "o1", "r1", {"request": bad2})
ok(any("production_notes" in e for e in results.check_result(r2)),
   "bad payload caught")

results.promote_checked(r)
ok(r["status"] == "checked", "promote to checked")
results.promote_checked(r)
ok(r["status"] == "checked", "promote idempotent")
results.set_reviewed(r, "board_vera")
ok(r["status"] == "reviewed" and r["reviewed_by"] == "board_vera"
   and r["reviewed_at"], "reviewed stamps reviewer")
raises(lambda: results.promote_checked(r), "promote reviewed refuses")
raises(lambda: results.set_reviewed(
    results.make_result("x", "o", "r", {"request": dict(REQ)}), "v"),
    "review unverified refuses")
raises(lambda: results.set_verified(r, "sales_sam"),
       "non-developer verify refuses")
raises(lambda: results.set_verified(
    results.make_result("x", "o", "r", {"request": dict(REQ)}), "developer"),
    "verify unverified refuses")
results.set_verified(r, "developer")
ok(r["status"] == "verified" and r["verified_by"] == "developer"
   and r["verified_at"], "developer verify stamps")
raises(lambda: results.set_verified(r, "developer"), "re-verify refuses")
ok(any("reviewed_by" in e for e in results.check_result(
    dict(r, reviewed_by=None))), "verified needs reviewed_by")

tmp = tempfile.mkdtemp(prefix="rescheck_")
p = results.save_result(tmp, r)
ok(os.path.basename(p) == "result.json"
   and results.load_result(p)["status"] == "verified", "save/load roundtrip")
raises(lambda: results.save_result(tmp, dict(r, status="checked")),
       "overwrite verified refuses")

if fails:
    print("%d FAILURES" % fails)
    sys.exit(1)
print("ALL PASS")
