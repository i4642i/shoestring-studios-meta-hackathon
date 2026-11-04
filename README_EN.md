# Shoestring Studios (English)

AI-agent video team: dense source material in, publish-grade narrated
explainer video out. Built during the Meta Global AI Developer
Hackathon 2026, Oct 27 – Nov 4 (Indie Developer track, Build for
Your World). All of our code in this repository was written during
the hackathon; everything we did not write is listed under
Third-party below.

## Author

Sangho KIM, NexTopologix (Changwon, South Korea)
Open to job offers, contract projects and collaborations on AI agents.
Website: https://nextopologix.com
GitHub: https://github.com/i4642i
LinkedIn: https://www.linkedin.com/in/sangho-kim-839a4799/

## What was built

- **Nextop Agentic Workers (NAW)** — the multi-agent framework in
  `agents/_frame/`: each employee is a folder (`agent.json` with
  model/tools/bounds, `persona.md`, handbooks), the runner executes
  bounded tool-using turns, and the flow engine (`data/flows/`)
  moves an order through the crew with per-stage approval.
- **The video team** — 12 employees covering the whole pipeline
  from a client PDF to a subtitled 720p MP4: intake, structure,
  research, planning, narration + voice, storyboard, photo /
  generated / animation candidates, slide planning, slide rendering
  (Remotion), and programmed assembly (ffmpeg).
- **Knowledge PCs** — Source / Theory / Article stores with a
  LightRAG knowledge-graph index, plus Image / Generated / Voice
  material stores with per-order recipient grants.
- **Studio site** — `index.html` + `scripts/server.py`: order,
  crew, flow, gallery, and PC views over the same runtime.

## How to run: PDF order to MP4

Prereqs: Python 3.10+, Git, Node.js 16+, an LLM key (copy
`.env.example` to `.env`; all 12 crew agents call `muse-spark-1.3`
on the Meta Model API via `MODEL_API_KEY` — Baseten credits ran
out on 2026-11-03, so final runs use `muse-spark-1.3`;
Cleo/Rex web research needs `TAVILY_API_KEY`).
First install: double-click `start_server.bat` — it creates `.venv`
and installs `requirements.txt`, `requirements-video.txt` (Kokoro
voice; espeak-ng and ffmpeg come as pip packages) and the Remotion
renderer (`npm install` in `video/remotion/`). Node.js is the only
system install. Check with
`powershell -ExecutionPolicy Bypass -File tools/setup_video.ps1`.

1. Start the server (`start_server.bat` or `python scripts/server.py`)
   and open the printed URL (usually http://localhost:8000).
2. Order tab: create an order from the client PDF (Sam consults and
   takes the order; the PDF is ingested into the Source PC).
3. Flow tab: run the stages in order, approving each one
   (Sam → Marty → Cleo → Rex → Ash → Wren → Penn → split →
   Pia / Gene / Max → Vera → Remy → video_production → final).
   Re-runs start from the changed employee; approved upstream
   results are reused.
4. video_production writes `assembly.json` + `captions.srt`;
   assemble builds `video.mp4` (voice-timed segments, 0.5 s
   crossfades), served in the Gallery tab.
5. Headless (same pipeline, no browser):
   `python scripts/stage2_run.py --src-order <id> --new-order <id>`
   runs every stage, approves, assembles, and logs to the run
   folder (`runs/<run_id>/driver.log`); `--resume <run> --from <node>`
   continues after a fix.

## The employees

| Employee | Role |
|---|---|
| Sam (`sales_sam`) | Sales representative, frontline — takes the order |
| Marty (`pd_marty`) | Structure writer — maps the source into parts |
| Cleo (`explain_cleo`) | Concept explainer — theory picks |
| Rex (`case_rex`) | Case researcher — article picks |
| Ash (`plan_ash`) | Planning PD — scenes per part |
| Wren (`voice_wren`) | Narration writer — cuts + voiceover |
| Penn (`board_penn`) | Storyboard writer — screens + style guide |
| Pia (`photo_pia`) | Photo researcher — licensed stills |
| Gene (`image_gene`) | Image generator — concept art |
| Max (`anim_max`) | Animation planner — tables/formulas/steps |
| Vera (`board_vera`) | Slide planner — per-cut layouts |
| Remy (`slide_remy`) | Slide builder — renders every cut |

## License

Our code is licensed under the PolyForm Noncommercial License 1.0.0
(see `LICENSE`): free to read, run and modify for noncommercial
purposes; commercial use needs permission from the author.
Third-party files keep their own licenses: Three.js (MIT, `vendor/three/`),
Kenney assets (CC0, `vendor/kenney/`); Python and npm packages are
installed, not bundled (see the table above / `THIRD_PARTY.md`).

## Third-party software and services

Our code calls these; we did not write them (`requirements*.txt`
pins versions; `python scripts/list_licenses.py` verifies
installed versions/licenses):

| Package / service | Used for |
|---|---|
| LightRAG (`lightrag-hku`) | Knowledge-graph index over the PCs |
| Remotion (+ `@remotion/google-fonts`) | Slide clips and stills |
| Kokoro (+ torch CPU, soundfile, spacy, espeak-ng) | Local text-to-speech voiceover |
| ffmpeg (imageio-ffmpeg static build; Remotion compositor minimal build) | Assembly, stills, loudness |
| pdfplumber | PDF text + figure extraction |
| sentence-transformers, numpy, Pillow | Embeddings, math, thumbnails |
| KaTeX | Formula rendering on slides |
| Inter (Google Fonts) | Slide typeface |
| three.js, Kenney assets (`vendor/`) | 3D studio office |
| Tavily API | Web research for Cleo/Rex (optional) |
| Wikimedia Commons, Openverse APIs | Licensed photo search for Pia (per-picture licenses; non-commercial refused) |
| Meta Model API: Muse Spark 1.3 (crew + knowledge build), Muse Image 1.0 (Gene) / Baseten (optional) | Model calls (Meta direct since Baseten credits ran out 2026-11-03) |

GPL note: phonemizer-fork and eSpeak NG are GPL-3.0-or-later, pip-installed only, never bundled in this repository.

`vendor/`, `node_modules/`, `.venv/`, `storage/_pc/`, `orders/`,
`runs/`, and secrets (`.env`, `shk/`) are either third-party,
generated, or private — never our hackathon code.
