# Static API fallbacks

Files here serve API-shaped URLs when the page is hosted WITHOUT the
Python backend (plain static hosting, or the check_page.py harness which
serves this folder directly).

- `crew` — GET api/crew fallback: the current roster as plain JSON.

Under `scripts/server.py` these files are never served: the live API routes
take precedence over static files.
