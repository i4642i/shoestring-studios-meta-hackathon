"""Smoke: Meta Model API through LightRAG's OpenAI-compatible func.

Reads MODEL_API_KEY/META_API_KEY from repo .env (never printed).
Usage (from repo root): .venv-lightrag/Scripts/python experiments/lightrag/smoke_meta.py
"""
import asyncio
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


def load_key():
    vals = {}
    with open(os.path.join(ROOT, ".env"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip("'\"")
    key = vals.get("MODEL_API_KEY") or vals.get("META_API_KEY") or ""
    if not key:
        raise SystemExit("no key in .env")
    return key


async def main():
    from lightrag.llm.openai import openai_complete_if_cache
    t0 = time.time()
    out = await openai_complete_if_cache(
        "muse-spark-1.3",
        "Reply with exactly this token and nothing else: META-OK",
        system_prompt=None,
        history_messages=[],
        api_key=load_key(),
        base_url="https://api.meta.ai/v1",
    )
    print("reply:", (out or "").strip()[:60])
    print("seconds: %.1f" % (time.time() - t0))
    print("SMOKE:", "PASS" if "META-OK" in (out or "") else "UNEXPECTED")


if __name__ == "__main__":
    asyncio.run(main())
