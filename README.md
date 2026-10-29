# Shoestring Studios

AI-agent video team: dense source material in, publish-grade narrated explainer video out. Built during the Meta Global AI Developer Hackathon 2026 (Indie Developer track, Build for Your World).

All code in this repository was written during the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026).

## Run it (first time)

Prereqs: Python 3.10+, Git, a Meta Model API key.

1. `pip install -r requirements.txt` (includes the LightRAG knowledge backend; first install downloads ~1GB of ML packages)
2. Create `.env` next to this file containing `MODEL_API_KEY=your-key-here` (never commit it).
3. Double-click `start_server.bat` (or run `python scripts/server.py`).
4. Open the printed URL (usually http://localhost:8000) → Crew tab → click Marty.

No Jetson LAN server? Set `EMBED_PROFILE=local` in `.env` (or pick Local in the Settings tab) to embed on your own PC instead.

## Layout

- `index.html` — homepage (Order / Crew / Studio / Gallery / PC / Settings / About).
- `agents/` — one folder per AI employee (`_frame/` is the shared runtime).
- `scripts/server.py` — stdlib backend + crew API; `run_agent.py` — run one employee; `validate_agent.py` — validate one employee folder.
- `docs/` — planning docs and meeting minutes (English).
- `requirements.txt` — install list (`pdfplumber` + frozen LightRAG pins; the server code itself is Python stdlib).
