"""Ask the same questions through lite and LightRAG, side by side.

Usage (from repo root): .venv-lightrag/Scripts/python experiments/lightrag/run_compare.py agents/pd_marty
Builds the lite index if missing; the LightRAG index must already exist
(see run_index.py). Saves the comparison to experiments/lightrag/logs/.
"""
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

QUESTIONS = [
    "How many beats does each scene carry, and what is a beat?",
    "What must every scene list as a source?",
    "What ends every draft?",
]


def main(agent_dir):
    from agents._frame import graph
    lite_idx = os.path.join(agent_dir, "graph_index", "lite.json")
    if not os.path.isfile(lite_idx):
        print("building lite index...")
        print(graph.index_corpus(agent_dir, backend="lite"))
    lines = ["# lite vs LightRAG — %s (%s)"
             % (os.path.basename(agent_dir),
                datetime.date.today().isoformat()), ""]
    for i, q in enumerate(questions(), 1):
        os.environ["RAG_BACKEND"] = "lite"
        lite = graph.query(agent_dir, q, top_k=1)
        os.environ["RAG_BACKEND"] = "lightrag"
        lr = graph.query(agent_dir, q)
        lite_txt = lite["chunks"][0]["text"] if lite["chunks"] else "(no hit)"
        lines += ["## Q%d: %s" % (i, q), "",
                  "### lite (retrieved chunk)", "",
                  lite_txt, "",
                  "### LightRAG (answer)", "",
                  lr.get("answer", "(none)"), ""]
        print("Q%d done" % i)
    outdir = os.path.join(ROOT, "experiments", "lightrag", "logs")
    os.makedirs(outdir, exist_ok=True)
    outp = os.path.join(outdir, "compare_%s_%s.md"
                        % (os.path.basename(agent_dir),
                           datetime.date.today().isoformat()))
    with open(outp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("saved:", os.path.relpath(outp, ROOT))


def questions():
    return QUESTIONS


if __name__ == "__main__":
    main(sys.argv[1])
