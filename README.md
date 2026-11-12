# Shoestring Studios

AI-agent video team: dense source material in, publish-grade narrated explainer video out. Built during the Meta Global AI Developer Hackathon 2026 (Indie Developer track, Build for Your World).

All code in this repository was written during the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026).

## Author

- Sangho KIM, NexTopologix (Changwon, South Korea)
- Open to job offers, contract projects and collaborations on AI agents.
- Website: https://nextopologix.com
- GitHub: https://github.com/i4642i
- LinkedIn: https://www.linkedin.com/in/sangho-kim-839a4799/

## Run it (first time)

Prereqs: Windows, Python 3.11, Git, **Node.js 18+** (nodejs.org; renders the slides), FFmpeg on PATH.

1. `git clone` this repository.
2. Copy `.env.example` to `.env` and fill it in (never commit `.env`). Each key says what uses it.
3. Set your own servers in `project.json` (this repository has ours, which only work on our LAN):
   - `adapters.llm.default.options.base_url`: an OpenAI-compatible LLM server (key `LOCAL_LLM_API_KEY`), and the
     model name under `models` (ours: `qwen3.8-flash-next`, with vision).
   - Embeddings for the LightRAG knowledge index (indexing and search): `adapters.index.lightrag.options.embed`
     is `"cpu"`: BAAI/bge-m3 on your own PC (~2.2 GB downloaded on first use; slower, no extra server). `"jetson"`
     is our LAN embedding server (`adapters.embed.jetson`, key `EMBED_TOKEN`); point its URL at your own server
     to use one. Studio > SETTINGS > EMBED & INDEX changes both. `adapters.index.lightrag.options.base_url` is the
     LLM the index uses (the same server as above by default).
4. Double-click `start_server.bat`. On the first run it creates `.venv` and installs everything:
   - `requirements.txt`: `nextop` (the framework, from PyPI), LightRAG and the rest,
   - `requirements-voice.txt` (the narrator's voice: Kokoro with torch CPU; the first voice run downloads the
     Kokoro-82M model, ~330 MB),
   - `npm install` in `remotion/` (the slide renderer; the first render downloads its headless browser).
5. Open http://localhost:8000 (the bat opens it): Order to start a video, Studio to see the flow.

## Layout

- `index.html` - the site (Order / Board / Studio / Crew / ...); `scripts/server.py` serves it and starts
  `nextop studio` on an internal port.
- `project.json` - the nextop project: models, adapters (LLM, embeddings, knowledge index).
- `flows/main.json` - the flow: workers, functions and the `check_layout` switch block.
- `workers/<id>/` - one folder per worker (`worker.json`, `persona.md`, `mission.md`, `checks.py`).
- `functions/` - function blocks (`split_parts`, `check_layout`, `render_part`, `assemble_video`, ...).
- `tools/` - the workers' tools (layout fit, image generation and search, voice, ...).
- `file_servers/` - shared file servers (sources, materials, voice, ...).
- `remotion/` - the Remotion slide templates; `layouts/` - the screen layouts.
- `office_3d.html` + `vendor/` - the 3D office view (three.js, Kenney models).

## License

Our code is licensed under the PolyForm Noncommercial License 1.0.0
(see `LICENSE`): free to read, run and modify for noncommercial
purposes; commercial use needs permission from the author.
Third-party files keep their own licenses: Three.js (MIT, `vendor/three/`),
Kenney assets (CC0, `vendor/kenney/`); Python and npm packages are
installed, not bundled (see the table above / `THIRD_PARTY.md`).

## Third-party software and services

Copyright and licenses, kept apart:

- **Shoestring Studios 2** (this repository: workers, missions, flows, functions, tools, the site and the 3D office) — Copyright Sangho KIM (NexTopologix), PolyForm Noncommercial License 1.0.0 (`LICENSE`). Noncommercial use only; commercial use needs written permission: ksh4642@nextopologix.com.
- **Nextop Agentic Workers (nextop)** — the framework this project runs on; a separate product, Copyright NexTopologix (Sangho KIM), PolyForm Small Business License 1.0.0, installed from PyPI (`nextop>=0.2.0`), not part of this repository. https://nextop.nextopologix.com
- **Third-party software and services** — each under its own license or terms. The full table (version, license, what it is used for, link) is in `THIRD_PARTY.md` and on the site's ABOUT tab.

What Shoestring 2 uses (versions and licenses read from the installed packages):

| Item | Version | License | Used for |
|---|---|---|---|
| PyMuPDF | 2.1 | **AGPL-3.0** or Artifex commercial (dual) | PDF order intake (imported by our code) |
| Pillow | 13.0.0 | MIT-CMU | image checks, crops, preview sheets |
| numpy | 2.4.6 | BSD-3-Clause (+ 0BSD, MIT, Zlib, CC0 parts) | embedding math in the LightRAG adapter |
| lightrag-hku (+ networkx, nano-vectordb, tiktoken) | 1.5.7 (3.6.1, 0.0.4.3, 0.14.0) | MIT (networkx BSD-3-Clause) | knowledge-graph index of the SOURCE file server |
| qwen3.8-flash-next (local server) | — | not stated | all LLM work |
| BAAI/bge-m3 (on our Jetson embedding server) | — | MIT (model card) | embeddings for the LightRAG index |
| Remotion (remotion, @remotion/cli, renderer, bundler) | 4.0.535 | Remotion License (proprietary, Free License for up to 3 employees) | slide stills (npm, never bundled) |
| @remotion/three, three, @react-three/fiber, React, KaTeX | 4.0.535, 0.169.0, 8.17.10, 18.3.1, 0.16.11 | MIT | slide templates (npm, never bundled) |
| Pretendard fonts (`remotion/public/fonts`) | not stated | SIL Open Font License (project page; no license file stored with the fonts) | slide typeface |
| Kokoro + Kokoro-82M, misaki, torch, spaCy, soundfile | 0.9.4, 0.9.4, 2.15.0+cpu, 3.8.18, 0.14.0 | Apache-2.0 / permissive | narrator voice, in `.venv` from `requirements-voice.txt` (`KOKORO_PYTHON` can point elsewhere) |
| phonemizer-fork, eSpeak NG (espeakng-loader 0.2.4) | 3.3.2 | **GPL-3.0-or-later** (loader: not stated) | phonemes behind misaki (pip-installed, never bundled) |
| FFmpeg (system install) | 9.0.2 gyan.dev full build | **GPL-3.0-or-later** (this build) | MP4 assembly, audio conversion (on PATH, never bundled) |
| Three.js (`vendor/three/`) | 0.186.1 | MIT | 3D office (vendored with its license) |
| Kenney Mini Characters 1.0 + Furniture Kit 2.0 (`vendor/kenney/`) | — | CC0 | crew avatars, office furniture |

Services used at runtime (not open source): Meta Model API — Muse Image 1.0 for Gene's pictures (`MODEL_API_KEY`); Tavily news search for Cleo and Rex (`TAVILY_API_KEY`); Serper.dev Google Images search for Pia (`SERPER_API_KEY`; fallback Google Custom Search, `GOOGLE_API_KEY` + `GOOGLE_CSE_ID`) — the pictures found keep their source address, but their licenses are not checked by the code; our Jetson embedding server (`EMBED_TOKEN`).

Copyleft note: PyMuPDF (AGPL-3.0), phonemizer-fork and eSpeak NG (GPL-3.0-or-later) and the FFmpeg build (GPL) are installed separately and never copied into this repository.

`THIRD_PARTY.md` and the ABOUT tables are kept by hand from the installed packages; `data/third_party.json` belongs to the hackathon edition and is out of date (its generator, `scripts/gen_credits.py`, is not in this repository).
