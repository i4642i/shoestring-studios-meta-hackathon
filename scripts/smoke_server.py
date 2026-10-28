"""Backend smoke test (stdlib only). Starts the server in-process and hits it.

Usage: python scripts/smoke_server.py
Covers: static /, .env blocked, crew list/detail, PUT roundtrip + invalid
rejected, train upload (.md), handbook delete. Exits nonzero on failure.
"""
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import server  # noqa: E402
import validate_agent  # noqa: E402

BASE = None
FAILS = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name, extra)
    if not cond:
        FAILS.append(name)


def req(method, path, data=None, headers=None):
    r = urllib.request.Request(BASE + path, data=data,
                               headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def main():
    global BASE
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    BASE = "http://127.0.0.1:%d" % httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        s, b = req("GET", "/")
        check("static /", s == 200 and b"SHOESTRING" in b, s)
        s, _ = req("GET", "/.env")
        check(".env blocked", s == 403, s)
        s, b = req("GET", "/api/crew")
        crew = json.loads(b.decode()) if s == 200 else []
        check("crew list", s == 200 and any(c["id"] == "pd_marty" for c in crew), s)
        s, b = req("GET", "/api/crew/pd_marty")
        d = json.loads(b.decode()) if s == 200 else {}
        check("crew detail", s == 200 and d.get("persona", "").startswith("# Marty")
              and d.get("graph", {}).get("state") == "not_indexed"
              and "muse-spark-1.3" in d.get("available_models", []), s)
        # PUT roundtrip (same values back)
        payload = json.dumps({"persona": d["persona"], "model": d["model"],
                              "tools": d["tools"]}).encode()
        s, b = req("PUT", "/api/crew/pd_marty", payload,
                   {"Content-Type": "application/json"})
        check("PUT roundtrip", s == 200 and json.loads(b.decode()).get("ok"), s)
        check("validator still PASS",
              validate_agent.validate("agents/pd_marty") == [])
        # PUT invalid model rejected + unchanged
        bad = json.dumps({"model": "gpt-4"}).encode()
        s, _ = req("PUT", "/api/crew/pd_marty", bad,
                   {"Content-Type": "application/json"})
        _, b2 = req("GET", "/api/crew/pd_marty")
        check("PUT invalid rejected", s == 422
              and json.loads(b2.decode())["model"] == "muse-spark-1.3", s)
        # train upload (.md multipart)
        bound = "BOUND123"
        body = ("\r\n".join([
            "--" + bound,
            'Content-Disposition: form-data; name="file"; filename="zz_smoke.md"',
            "Content-Type: text/markdown", "",
            "# Smoke\n\nhello train"]) + "\r\n--" + bound + "--\r\n").encode()
        s, b = req("POST", "/api/crew/pd_marty/train", body,
                   {"Content-Type": "multipart/form-data; boundary=" + bound})
        r = json.loads(b.decode()) if s == 200 else {}
        saved = r.get("saved") == "zz_smoke.md"
        ondisk = os.path.isfile("agents/pd_marty/handbook/zz_smoke.md")
        check("train upload", s == 200 and saved and ondisk, s)
        s, _ = req("DELETE", "/api/crew/pd_marty/handbook/zz_smoke.md")
        gone = not os.path.isfile("agents/pd_marty/handbook/zz_smoke.md")
        check("handbook delete", s == 200 and gone, s)
    finally:
        httpd.shutdown()
        t.join()
    if FAILS:
        print("FAILS:", FAILS)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
