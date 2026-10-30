"""Tavily key check: one basic search, prints hit count + top title.

Usage: python scripts/tavily_smoke.py "time weighted average price"
Needs TAVILY_API_KEY in .env (see .env.example). Never prints the key.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import server  # noqa: E402
from agents._frame import tools  # noqa: E402

server.load_dotenv(os.path.join(ROOT, ".env"))
q = sys.argv[1] if len(sys.argv) > 1 else "time weighted average price"
try:
    hits = tools._tavily_search(q, 3)
except RuntimeError as exc:
    print("TAVILY FAIL: %s" % exc)
    sys.exit(1)
print("TAVILY OK: %d hits for %r" % (len(hits), q))
for h in hits:
    print("-", (h["title"] or "")[:70], "|", h["url"][:70])
