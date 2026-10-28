"""Meta Model API smoke test: tiny Spark call + one PD portrait.

Key handling: reads MODEL_API_KEY (or META_API_KEY) from the environment or a
local .env file. The key value is NEVER printed. Usage: python scripts/meta_smoke.py
"""
import base64
import json
import os
import sys
import urllib.request

BASE_URL = "https://api.meta.ai/v1"


def load_dotenv(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def api_post(path, payload, key):
    req = urllib.request.Request(
        BASE_URL + path,
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def main():
    load_dotenv()
    key = os.environ.get("MODEL_API_KEY") or os.environ.get("META_API_KEY")
    if not key:
        print("KEY: MISSING (set MODEL_API_KEY env var or .env file)")
        return 1

    # Test 1: tiny chat call
    chat = api_post("/chat/completions", {
        "model": "muse-spark-1.3",
        "messages": [{"role": "user", "content": "Reply with exactly: SPARK_OK"}],
        "max_tokens": 200,
    }, key)
    msg = chat["choices"][0]["message"]
    if not isinstance(msg.get("content"), str):
        print("CHAT: unexpected shape, raw:")
        print(json.dumps(chat, ensure_ascii=False)[:1500])
        return 1
    print("CHAT:", msg["content"].strip())
    if chat.get("usage"):
        print("USAGE:", chat["usage"])

    # Test 2: one PD portrait (pixel-art, per D16)
    img = api_post("/images/generations", {
        "model": "muse-image-1.0",
        "prompt": ("16-bit pixel art portrait, friendly Korean woman documentary "
                   "director in her 30s, medium brown skin, teal blazer, headset, "
                   "game character avatar, centered bust, solid dark background"),
        "size": "1024x1024",
        "response_format": "b64_json",
    }, key)
    datum = img["data"][0]
    os.makedirs("output", exist_ok=True)
    out = os.path.join("output", "pd_test.webp")
    if datum.get("b64_json"):
        raw = base64.b64decode(datum["b64_json"])
    elif datum.get("url"):
        with urllib.request.urlopen(datum["url"], timeout=120) as r:
            raw = r.read()
    else:
        print("IMAGE: unexpected response keys:", sorted(datum.keys()))
        return 1
    with open(out, "wb") as f:
        f.write(raw)
    print("IMAGE: saved", out, len(raw), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
