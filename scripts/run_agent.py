"""CLI dev harness: run one employee on one input.

Usage:
  python scripts/run_agent.py --agent agents/pd_marty --input <md> --brief <json>
      --run-id <id>
Writes output/runs/<id>/{brief.json,input.md,events.jsonl,draft.json}.
Key from MODEL_API_KEY env or .env (never printed).
"""
import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agents._frame import runner  # noqa: E402


def load_dotenv(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="agents/pd_marty")
    ap.add_argument("--input", required=True)
    ap.add_argument("--brief", required=True)
    ap.add_argument("--run-id", required=True)
    a = ap.parse_args()
    load_dotenv(os.path.join(ROOT, ".env"))
    run_dir = os.path.join(ROOT, "output", "runs", a.run_id)
    os.makedirs(run_dir, exist_ok=True)
    input_md = os.path.join(run_dir, "input.md")
    shutil.copyfile(a.input, input_md)
    with open(a.brief, encoding="utf-8") as f:
        brief = json.load(f)
    with open(os.path.join(run_dir, "brief.json"), "w", encoding="utf-8") as f:
        json.dump(brief, f, ensure_ascii=False, indent=2)
    result = runner.run(a.agent, run_dir, brief, input_md)
    print("OK" if result["ok"] else "FAIL")
    print("USAGE:", result["usage"])
    print("RUN:", run_dir)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
