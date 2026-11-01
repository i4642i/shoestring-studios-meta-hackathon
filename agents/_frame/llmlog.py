"""Full LLM call log (one JSONL per order/run/entry).

Every record carries time, caller, model, tokens, seconds, the exact
request (messages, tools) and the full reply. Secrets never land here:
key-shaped fields are dropped and any configured key value found in
text is replaced with "***". Image bytes are replaced with a byte
count (the PNGs themselves live on disk). Appending never raises.
Stdlib only.
"""
import json
import os
import time

_KEY_VARS = ("BASETEN_API_KEY", "MODEL_API_KEY", "META_API_KEY",
             "EMBED_REMOTE_TOKEN", "TAVILY_API_KEY")
_KEY_FIELDS = ("authorization", "api_key", "api-key", "x-api-key",
               "token", "secret", "bearer", "password", "api_token")


def _secret_values():
    vals = []
    for var in _KEY_VARS:
        v = os.environ.get(var, "")
        if isinstance(v, str) and len(v) >= 8:
            vals.append(v)
    return vals


def _scrub_str(s, secrets):
    for sec in secrets:
        if sec and sec in s:
            s = s.replace(sec, "***")
    return s


def scrub(obj, secrets=None):
    """Drop key-shaped fields, redact configured key values."""
    secs = _secret_values() if secrets is None else list(secrets or [])
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in _KEY_FIELDS:
                continue
            out[k] = scrub(v, secs)
        return out
    if isinstance(obj, list):
        return [scrub(v, secs) for v in obj]
    if isinstance(obj, str):
        return _scrub_str(obj, secs)
    return obj


def _image_bytes(url):
    try:
        b64 = url.split("base64,", 1)[1]
        return len(b64) * 3 // 4
    except (IndexError, AttributeError, TypeError):
        return -1


def drop_images(messages):
    """Copy of messages with inline image data replaced by byte counts."""
    if not isinstance(messages, list):
        return messages
    out = []
    for m in messages:
        if not isinstance(m, dict):
            out.append(m)
            continue
        content = m.get("content")
        if not isinstance(content, list):
            out.append(m)
            continue
        parts = []
        for p in content:
            if not isinstance(p, dict):
                parts.append(p)
                continue
            iu = p.get("image_url")
            if isinstance(iu, dict) and isinstance(iu.get("url"), str) \
                    and iu["url"].startswith("data:"):
                n = _image_bytes(iu["url"])
                q = dict(p)
                q["image_url"] = {"url": "<inline image, %d bytes, "
                                        "not stored in log>" % n}
                parts.append(q)
            else:
                parts.append(p)
        q = dict(m)
        q["content"] = parts
        out.append(q)
    return out


def append(path, record):
    """Append one scrubbed record as a JSON line. Never raises."""
    try:
        if not path:
            return False
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(scrub(record), ensure_ascii=False)
                    + "\n")
        return True
    except (OSError, ValueError, TypeError):
        return False


def stamp():
    return time.strftime("%Y-%m-%d %H:%M:%S")
