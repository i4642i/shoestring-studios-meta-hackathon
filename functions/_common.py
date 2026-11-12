"""Shared helpers of this project's functions and tools (not a function block: the name starts with '_')."""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONT = r"C:\Windows\Fonts\malgun.ttf"          # Korean font (Malgun Gothic)
FONT_BOLD = r"C:\Windows\Fonts\malgunbd.ttf"
UA = "naw-shoestring/0.2"

EDGE_VOICE = "en-US-AvaNeural"                  # spare voice (Microsoft neural, via edge-tts); also gives word timings
MINIMAX_MODEL = "fal-ai/minimax/speech-02-hd"   # paid voice (fal.ai), key FAL_KEY; not used by the narrator now
MINIMAX_VOICE = "Wise_Woman"
# The narrator's voice: Kokoro (local, free), American English female. It runs in this project's Python
# (requirements-voice.txt); set KOKORO_PYTHON in .env to use another Python that has kokoro.
KOKORO_PYTHON = sys.executable
KOKORO_VOICE = "af_heart"


def pick(inputs: dict, suffix: str):
    """The value of the input whose key ends with suffix ('pd/brief', 'editor@2/timeline' -> 'timeline')."""
    for k, v in inputs.items():
        if k == suffix or k.endswith("/" + suffix):
            return v
    raise KeyError(f"no input ending with {suffix!r} (got {sorted(inputs)})")


def pick_opt(inputs: dict, suffix: str, default=None):
    try:
        return pick(inputs, suffix)
    except KeyError:
        return default


def env(name: str) -> str:
    """A key from the environment or the project's .env (never printed)."""
    if os.environ.get(name):
        return os.environ[name]
    f = ROOT / ".env"
    if f.is_file():
        for line in f.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                if k.strip() == name:
                    return v.strip().strip('"').strip("'")
    return ""


def write_json(path: pathlib.Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def http_json(url: str, payload: dict | None = None, headers: dict | None = None, timeout: int = 120) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    h = {"User-Agent": UA, **({"Content-Type": "application/json"} if data else {}), **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=h, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def download(url: str, out: pathlib.Path, timeout: int = 60, max_bytes: int = 25_000_000) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " + UA,
                                               "Accept": "image/*,*/*;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("file too large")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return len(data)


def ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg is not installed")
    return exe


def media_seconds(path: str | pathlib.Path) -> float:
    r = subprocess.run([ffmpeg(), "-i", str(path)], capture_output=True, text=True, encoding="utf-8", errors="ignore")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
    if not m:
        raise RuntimeError(f"cannot read the length of {pathlib.Path(path).name}")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


# ---------------------------------------------------------------- voices

async def _edge(text: str, voice: str, out: pathlib.Path) -> list[dict]:
    import edge_tts
    words = []
    comm = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    with open(out, "wb") as f:
        async for ch in comm.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                s = ch["offset"] / 1e7
                words.append({"text": ch["text"], "start": round(s, 3), "end": round(s + ch["duration"] / 1e7, 3)})
    return words


def speak_edge(text: str, out: pathlib.Path) -> tuple[float, list[dict]]:
    """Free draft voice: MP3 + word timings."""
    out.parent.mkdir(parents=True, exist_ok=True)
    words = asyncio.run(_edge(text, EDGE_VOICE, out))
    return media_seconds(out), words


def speak_minimax(text: str, out: pathlib.Path) -> tuple[float, list[dict]]:
    """Paid final voice (fal.ai MiniMax). Word timings: the edge timings of the same text, stretched to this length."""
    key = env("FAL_KEY")
    if not key:
        raise RuntimeError("FAL_KEY is not set in .env (needed for the final voice)")
    try:
        r = http_json(f"https://fal.run/{MINIMAX_MODEL}",
                      {"text": text, "voice_setting": {"voice_id": MINIMAX_VOICE, "speed": 1.0},
                       "language_boost": "English", "output_format": "url"},
                      {"Authorization": f"Key {key}"}, timeout=240)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"fal.ai error {e.code}: {e.read(300).decode('utf-8', 'replace')}") from None
    url = (r.get("audio") or {}).get("url") or ""
    if not url:
        raise RuntimeError(f"MiniMax reply has no audio address: {str(r)[:200]}")
    download(url, out, timeout=120)
    secs = media_seconds(out)
    ref = out.with_suffix(".ref.mp3")
    try:
        rsecs, w = speak_edge(text, ref)
        k = secs / rsecs if rsecs else 1
        words = [{"text": x["text"], "start": round(x["start"] * k, 3), "end": round(x["end"] * k, 3)} for x in w]
    except Exception:            # no timings: spread the words by length
        toks = text.split()
        tot, t, words = sum(len(x) for x in toks) or 1, 0.0, []
        for x in toks:
            d = secs * len(x) / tot
            words.append({"text": x, "start": round(t, 3), "end": round(t + d, 3)})
            t += d
    finally:
        ref.unlink(missing_ok=True)
    return secs, words


def speak_kokoro_many(lines: list[tuple[str, pathlib.Path]], voice: str = KOKORO_VOICE) -> list[tuple[float, list[dict]]]:
    """The narrator's voice: Kokoro (local, free). lines = [(text, out.mp3)]; the model loads once for all of them.
    Returns (seconds, word timings) per line, in order. Raises RuntimeError when Kokoro cannot run."""
    import tempfile
    py = env("KOKORO_PYTHON") or KOKORO_PYTHON
    if not pathlib.Path(py).is_file():
        raise RuntimeError(f"Kokoro's Python is not found: {py} (set KOKORO_PYTHON in .env)")
    helper = ROOT / "tools" / "_kokoro_say.py"
    jobs = [{"text": t, "wav": str(out.with_suffix(".wav").resolve())} for t, out in lines]
    for _t, out in lines:
        out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        jf = pathlib.Path(td) / "jobs.json"
        jf.write_text(json.dumps({"voice": voice, "lines": jobs}, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([py, str(helper), str(jf)], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=1800)
    got = {}
    for ln in r.stdout.splitlines():
        if ln.startswith("{"):
            d = json.loads(ln)
            got[d["wav"]] = d
    if r.returncode != 0 and not got:
        raise RuntimeError("Kokoro failed: " + (r.stderr or "").strip()[-400:])
    res = []
    for job, (_t, out) in zip(jobs, lines):
        d = got.get(job["wav"])
        if not d:
            raise RuntimeError(f"Kokoro did not voice {out.name}: " + (r.stderr or "").strip()[-300:])
        wav = pathlib.Path(job["wav"])
        subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "128k", str(out)], check=True)
        wav.unlink(missing_ok=True)
        res.append((media_seconds(out), d["words"]))
    return res


# ---------------------------------------------------------------- file server files

def image_ext(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return None
