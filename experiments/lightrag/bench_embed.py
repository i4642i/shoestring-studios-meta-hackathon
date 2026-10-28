"""Embedding bake-off: small English vs multilingual bge-m3 on this PC.

Downloads go to experiments/lightrag/models/ (gitignored).
Usage (from repo root): .venv-lightrag/Scripts/python experiments/lightrag/bench_embed.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["SENTENCE_TRANSFORMERS_HOME"] = os.path.join(ROOT, "experiments", "lightrag", "models")
os.environ["HF_HUB_OFFLINE"] = "0"
sys.path.insert(0, ROOT)

SENTS = [
    "Each scene carries 2-4 narration beats.",
    "Every scene lists at least one verbatim source.",
    "The draft ends with a coverage list of left-out points.",
    "A hook opens with a concrete puzzle or number.",
    "Key ideas become one scene each, in order.",
    "New terms get a same-sentence gloss.",
    "Trim quotes with [...] only at the edges.",
    "Cut the beat when no passage supports it.",
    "Beats use words a curious adult knows.",
    "The payoff shows what the viewer can now do.",
] * 2  # 20 sentences


def dir_mb(path):
    total = 0
    for dp, _, fns in os.walk(path):
        for fn in fns:
            try:
                total += os.path.getsize(os.path.join(dp, fn))
            except OSError:
                pass
    return total / 1e6


def bench(model_id):
    from sentence_transformers import SentenceTransformer
    t0 = time.time()
    m = SentenceTransformer(model_id, device="cpu")
    load_s = time.time() - t0
    t0 = time.time()
    v = m.encode(SENTS, batch_size=8, show_progress_bar=False,
                 normalize_embeddings=True)
    enc_s = time.time() - t0
    home = os.environ["SENTENCE_TRANSFORMERS_HOME"]
    print("model:", model_id)
    print("  dim:", v.shape[1])
    print("  load_s: %.1f  enc20_s: %.1f  per_sent_ms: %.0f"
          % (load_s, enc_s, enc_s / len(SENTS) * 1000))
    print("  cache_mb: %.0f" % dir_mb(home))
    return v.shape[1]


if __name__ == "__main__":
    bench("sentence-transformers/all-MiniLM-L6-v2")
    bench("BAAI/bge-m3")
