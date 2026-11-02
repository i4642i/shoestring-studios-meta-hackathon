"""One-shot: drop slide_remy approvals so step_run re-runs Remy."""
import json

p = "runs/flow-20261102-122459-0471/STATUS.json"
s = json.load(open(p, encoding="utf-8"))
before = list(s.get("approved", []))
s["approved"] = [a for a in before if not a.startswith("slide_remy")]
json.dump(s, open(p, "w", encoding="utf-8"), ensure_ascii=False,
          indent=1)
print("dropped:", [a for a in before if a.startswith("slide_remy")])
