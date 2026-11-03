# Shoestring Studios

AI-agent video team: dense source material in, publish-grade narrated explainer video out. Built during the Meta Global AI Developer Hackathon 2026 (Indie Developer track, Build for Your World).

All code in this repository was written during the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026).

## Run it (first time)

Prereqs: Python 3.10+, Git, **Node.js 16+** (LTS from nodejs.org; needed to render slides), an LLM key (see `.env` below).

1. Nothing to install by hand: `start_server.bat` (step 3) creates `.venv` and installs everything on first run — `requirements.txt` (LightRAG knowledge backend, ~1GB), `requirements-video.txt` (Kokoro voice, espeak-ng and ffmpeg as pip packages) and the Remotion slide renderer (`npm install` in `video/remotion/`). Without the bat: `pip install -r requirements.txt -r requirements-video.txt` and `npm install` in `video/remotion/`.
2. Copy `.env.example` to `.env` next to this file and fill it in (never commit it). Keys the app reads:
   - `MODEL_API_KEY` — Meta Model API key. Every crew agent and the knowledge-build worker use `muse-spark-1.3` through it. `META_API_KEY` still works as a legacy alias.
   - `BASETEN_API_KEY` — only if you switch an employee to a `meta-models/*` model (Baseten hosting); not needed by default.
   - `TAVILY_API_KEY` — web research for Cleo/Rex picks. Optional: without it, search tools report "not configured".
   - `EMBED_PROFILE` — `local` (default: embeds on your own PC with BAAI/bge-m3 — the same model as the Jetson server, ~2.2 GB downloaded on first use, CPU is fine but slow) or `jetson` (our LAN embed server; needs the two settings below). On a new PC leave it `local`.
   - `JETSON_EMBED_URL`, `EMBED_REMOTE_TOKEN` — only for the `jetson` profile: where the LAN embed server lives and its token.
3. Double-click `start_server.bat` (or run `python scripts/server.py`).
4. Open the printed URL (usually http://localhost:8000) → Crew tab → click Marty.
5. Video toolchain check: `powershell -ExecutionPolicy Bypass -File tools/setup_video.ps1` prints what is installed. A full PDF-to-MP4 run needs the voice packages and the Remotion renderer (both installed by the bat); first use also downloads the Kokoro voice (~400 MB) and Remotion's headless browser.

## Layout

- `index.html` — homepage (Order / Crew / Studio / Gallery / PC / Settings / Flow / About).
- `agents/` — one folder per AI employee (`_frame/` is the shared runtime).
- `scripts/server.py` — stdlib backend + crew API; `run_agent.py` — run one employee; `validate_agent.py` — validate one employee folder.
- `docs/` — planning docs and meeting minutes (English).
- `requirements.txt` — install list (`pdfplumber` + frozen LightRAG pins; the server code itself is Python stdlib).

## License

Our code is licensed under the PolyForm Noncommercial License 1.0.0
(see `LICENSE`): free to read, run and modify for noncommercial
purposes; commercial use needs permission from the author.
Third-party files keep their own licenses: Three.js (MIT, `vendor/three/`),
Kenney assets (CC0, `vendor/kenney/`); Python and npm packages are
installed, not bundled (see the table above / `THIRD_PARTY.md`).

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
| @remotion/google-fonts → Inter | 4.0.539 (via npm, never bundled) | Remotion license (package); SIL OFL 1.1 (Inter font) | slide typeface |
| kokoro | 0.9.4 | Apache-2.0 | Wren's local text-to-speech voice |
| Kokoro-82M (voice model) | downloaded on first use | Apache-2.0 | voice model weights |
| misaki | 0.9.4 | Apache-2.0 | text-to-phoneme behind Kokoro |
| spaCy + en_core_web_sm | 3.8.18 / 3.8.0 | MIT | English sentence analysis behind misaki |
| phonemizer-fork | 3.3.2 | GPL-3.0-or-later | phonemizer behind misaki's fallback (pip-installed, not bundled) |
| espeakng-loader (with eSpeak NG) | 0.2.4 | eSpeak NG GPL-3.0-or-later; loader license not stated in its metadata | words Kokoro cannot spell (pip-installed, not bundled) |
| soundfile | 0.14.0 | BSD-3-Clause | WAV output |
| imageio-ffmpeg (with FFmpeg) | 0.7.0 | BSD-2-Clause; FFmpeg binary LGPL/GPL depending on its build | MP4 assembly when no system ffmpeg |

Models (licenses read from their Hugging Face model cards): BAAI/bge-m3 (MIT; both profiles — on the Jetson server or on this PC through sentence-transformers).

Bundled assets: Three.js 0.186.1 (MIT, vendored with its license in `vendor/three/`) and Kenney Mini Characters + Furniture Kit (CC0, no attribution required).

External services used at runtime (not open source): Meta Model API — Muse Spark 1.3 for every crew agent and the knowledge-build worker, Muse Image 1.0 for Gene's pictures (needs `MODEL_API_KEY`); Tavily (web search + extract for Cleo/Rex picks, optional, `TAVILY_API_KEY`); Wikimedia Commons and Openverse (Pia's photo search — each picture keeps its own license, stored with its source page link; non-commercial licenses are refused); Baseten (optional hosting for `meta-models/muse-spark-open-1026`, not used by default).

GPL note: phonemizer-fork and eSpeak NG (inside espeakng-loader) are GPL-3.0-or-later. They are installed by pip from `requirements-video.txt` and are never copied into this repository.

Per-item credits with links live in `data/third_party.json` (source of truth; `THIRD_PARTY.md` and the About page card are generated from it by `scripts/gen_credits.py`).
