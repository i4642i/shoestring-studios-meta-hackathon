# Shoestring Studios

AI-agent video team: dense source material in, publish-grade narrated explainer video out. Built during the Meta Global AI Developer Hackathon 2026 (Indie Developer track, Build for Your World).

All code in this repository was written during the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026).

## Run it (first time)

Prereqs: Python 3.10+, Git, an LLM key (see `.env` below).

1. `pip install -r requirements.txt` (includes the LightRAG knowledge backend; first install downloads ~1GB of ML packages)
2. Copy `.env.example` to `.env` next to this file and fill it in (never commit it). Keys the app reads:
   - `BASETEN_API_KEY` — LLM calls for every crew agent (they all use `meta-models/*`, routed to Baseten).
   - `MODEL_API_KEY` — only for non-`meta-models/*` models (Meta Model API). `META_API_KEY` still works as a legacy alias.
   - `TAVILY_API_KEY` — web research for Cleo/Rex picks. Optional: without it, search tools report "not configured".
   - `EMBED_PROFILE` — `jetson` (default, LAN server) or `local` (embed on your own PC; or pick Local in the Settings tab).
   - `JETSON_EMBED_URL`, `EMBED_REMOTE_TOKEN` — only for the `jetson` profile: where the LAN embed server lives and its token.
3. Double-click `start_server.bat` (or run `python scripts/server.py`).
4. Open the printed URL (usually http://localhost:8000) → Crew tab → click Marty.
5. Video toolchain (optional — real slide PNGs + local voiceover only; without it the app runs and records honest "unavailable" notes): install Node.js 16+ and ffmpeg, then run `powershell -ExecutionPolicy Bypass -File tools/setup_video.ps1` (installs the Remotion renderer in `video/remotion/`). For local TTS: install espeak-ng, then `pip install "kokoro>=0.9.4"` (see docs/PLAN_V8_VIDEO_EN.md §1b).

## Layout

- `index.html` — homepage (Order / Crew / Studio / Gallery / PC / Settings / Flow / About).
- `agents/` — one folder per AI employee (`_frame/` is the shared runtime).
- `scripts/server.py` — stdlib backend + crew API; `run_agent.py` — run one employee; `validate_agent.py` — validate one employee folder.
- `docs/` — planning docs and meeting minutes (English).
- `requirements.txt` — install list (`pdfplumber` + frozen LightRAG pins; the server code itself is Python stdlib).

## Third-party software and services

Our code imports pdfplumber, lightrag-hku, sentence-transformers, numpy and Pillow directly; the rest arrive as their dependencies (pinned versions in `requirements.txt`, installed versions/licenses verified with `python scripts/list_licenses.py`):

| Package | Version | License | Used for |
|---|---|---|---|
| pdfplumber | 0.11.10 | MIT | PDF text+image extraction |
| lightrag-hku | 1.5.7 | MIT | knowledge-graph index |
| sentence-transformers | 6.2.0 | Apache-2.0 | local embeddings |
| numpy | 2.4.6 | BSD-3-Clause | embedding math |
| Pillow | 13.0.0 (installed, unpinned) | MIT-CMU | figure thumbnails |
| torch (CPU) | 2.14.1+cpu | BSD-3-Clause | tensors behind sentence-transformers |
| transformers | 5.21.0 | Apache-2.0 | model loading behind sentence-transformers |
| pdfminer.six | 20260107 (installed, unpinned) | MIT | PDF parsing behind pdfplumber |
| networkx | 3.6.1 | BSD-3-Clause | graph store behind LightRAG |
| nano-vectordb | 0.0.4.3 | MIT | vector store behind LightRAG |
| tiktoken | 0.14.0 | MIT | token counting behind LightRAG |
| scikit-learn | 1.9.1 | BSD-3-Clause | behind sentence-transformers |
| huggingface_hub | 2.3.0 | Apache-2.0 | model download behind sentence-transformers |
| python-dotenv | 1.2.4 (pinned, not imported) | BSD-3-Clause | unused: our code loads `.env` with its own stdlib loader |
| Remotion | 4.0.539 (via npm, never bundled) | PROPRIETARY Free License (free for ≤3 people) | cut-slide PNG stills |
| KaTeX | 0.19.1 (via npm, never bundled) | MIT | formula rendering in the Remotion composition |
| React (+ react-dom) | 19.2.3 (via npm, never bundled) | MIT | UI library behind the Remotion composition |

Models (licenses read from their Hugging Face model cards): all-MiniLM-L6-v2 (Apache-2.0, local profile) and BAAI/bge-m3 (MIT, Jetson profile).

Bundled assets: Three.js 0.186.1 (MIT, vendored with its license in `vendor/three/`) and Kenney Mini Characters + Furniture Kit (CC0, no attribution required).

External services used at runtime (not open source): Meta Model API (Muse Spark — LLM for non-`meta-models/*` models), Baseten (OpenAI-compatible hosting for `meta-models/muse-spark-open-1026` — every crew agent), Tavily (basic web search + extract for Cleo/Rex picks).

Per-item credits with links live in `data/third_party.json` (source of truth; `THIRD_PARTY.md` and the About page card are generated from it by `scripts/gen_credits.py`).
