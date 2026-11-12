"""Sam's tool in the ORDER chat: hand the finished order over to the crew.

The site server does the handover (scripts/server.py handover(): readiness check by code, then in the background
input.json and `nextop run`). This tool asks it through the site's own endpoint POST /api/orders/<id>/handover on
127.0.0.1; the server puts its address in the environment of the `nextop ask sam` it starts (SHOESTRING_SITE_URL).
"""

import json
import os
import urllib.error
import urllib.request

from tools._orders import SITE_URL_ENV, order_dir

NAME = "finalize_and_send"
DESC = ("Hand the order over to the crew: the site checks that the form is full and the PDF is attached, then starts "
        "production. Returns ok, or what is still missing.")
SCHEMA = {
    "type": "object",
    "properties": {"order_id": {"type": "string", "description": "the order id from the question (ord-YYYYMMDD-NNN)"}},
    "required": ["order_id"],
    "additionalProperties": False,
}
TIMEOUT = 60
DEFAULT_SITE = "http://127.0.0.1:8000/"


def run(ctx, args):
    oid = str(args.get("order_id") or "")
    if order_dir(oid) is None:
        return {"error": f"no order {oid!r}; use the order id given in the question"}
    site = (os.environ.get(SITE_URL_ENV) or DEFAULT_SITE).rstrip("/") + "/"
    req = urllib.request.Request(site + f"api/orders/{oid}/handover", data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            body = json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8") or "{}")
        except ValueError:
            body = {}
        return {"error": "not handed over", "detail": body.get("detail") or body.get("error") or f"HTTP {e.code}"}
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"error": f"the site server at {site} did not answer ({e}); the order was not handed over"}
    return {"ok": True, "handed_over": True, "note": "production starts in the background; say a short goodbye"}
