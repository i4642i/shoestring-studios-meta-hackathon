"""Generate a chibi full-body crew sprite via Muse Image.

Usage: python scripts/gen_chibi.py
Saves to output/pd_chibi.png. Key from MODEL_API_KEY env or .env (never printed).
"""
import base64
import json
import os
import sys
import urllib.request

BASE_URL = "https://api.meta.ai/v1"
PROMPT = ("3-head-tall chibi game character, full body, friendly Korean woman "
          "documentary director in her 30s, medium brown skin, black hair, teal "
          "blazer, headset with microphone, 16-bit pixel art style, standing pose "
          "facing front, feet visible, solid bright green background, no shadow, "
          "no text")


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


def main():
    load_dotenv()
    key = os.environ.get("MODEL_API_KEY") or os.environ.get("META_API_KEY")
    if not key:
        print("KEY: MISSING")
        return 1
    req = urllib.request.Request(
        BASE_URL + "/images/generations",
        data=json.dumps({
            "model": "muse-image-1.0",
            "prompt": PROMPT,
            "size": "1024x1024",
            "response_format": "b64_json",
        }).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        img = json.loads(resp.read().decode())
    datum = img["data"][0]
    if datum.get("b64_json"):
        raw = base64.b64decode(datum["b64_json"])
    elif datum.get("url"):
        with urllib.request.urlopen(datum["url"], timeout=180) as r:
            raw = r.read()
    else:
        print("IMAGE: unexpected keys:", sorted(datum.keys()))
        return 1
    os.makedirs("output", exist_ok=True)
    out = os.path.join("output", "pd_chibi.webp")
    with open(out, "wb") as f:
        f.write(raw)
    print("IMAGE: saved", out, len(raw), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
