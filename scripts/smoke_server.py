"""Backend smoke test (stdlib only). Starts the server in-process and hits it.

Usage: python scripts/smoke_server.py
Covers: static /, .env blocked, crew list/detail (+ appearance, no portrait),
chat validation (404/400, no LLM), PUT roundtrip + invalid rejected,
train upload (.md), handbook delete. Exits nonzero on failure.
"""
import json
import os
import re
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
        check("list appearance", any(
            (c.get("appearance") or {}).get("variant", "").endswith(".glb")
            for c in crew))
        s, b = req("GET", "/api/crew/pd_marty")
        d = json.loads(b.decode()) if s == 200 else {}
        check("crew detail", s == 200 and d.get("persona", "").startswith("# Marty")
              and d.get("graph", {}).get("state") == "not_indexed"
              and "muse-spark-1.3" in d.get("available_models", []), s)
        check("detail appearance, no portrait",
              (d.get("appearance") or {}).get("variant", "").endswith(".glb")
              and "portrait" not in d)
        s0, b0 = req("GET", "/")
        s1, b1 = req("GET", "/office_3d.html")
        served = b0.decode() + b1.decode() if s0 == 200 and s1 == 200 else "KO?"
        check("served pages have no Korean", s0 == 200 and s1 == 200
              and not re.search(r"[ㄱ-ㅎ가-힣]", served), (s0, s1))
        jpost = lambda p, o: req("POST", p, json.dumps(o).encode(),
                                 {"Content-Type": "application/json"})
        s, _ = jpost("/api/crew/nobody/chat",
                     {"messages": [{"role": "user", "content": "hi"}]})
        check("chat unknown id", s == 404, s)
        bads = [{}, {"messages": []}, {"messages": "x"},
                {"messages": [{"role": "user", "content": ""}]},
                {"messages": [{"role": "user", "content": "x" * 2001}]},
                {"messages": [{"role": "boss", "content": "x"}]},
                {"messages": [{"role": "user", "content": "x"}] * 13}]
        codes = [jpost("/api/crew/pd_marty/chat", b)[0] for b in bads]
        check("chat bad shape", all(c == 400 for c in codes), codes)
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
        # platform CRUD: create -> detail -> update -> preview -> delete
        s, b = jpost("/api/crew", {"id": "zz_temp", "name": "Zed", "title": "Temp"})
        check("create employee", s == 201, s)
        s, b = req("GET", "/api/crew/zz_temp")
        d3 = json.loads(b.decode()) if s == 200 else {}
        check("detail has io", s == 200
              and d3.get("io", {}).get("output") == "structure.json"
              and d3.get("appearance", {}).get("variant", "").endswith(".glb"), s)
        check("create validates", validate_agent.validate("agents/zz_temp") == [])
        s, _ = jpost("/api/crew", {"id": "zz_temp", "name": "Z", "title": "T"})
        check("duplicate rejected", s == 409, s)
        s, _ = jpost("/api/crew", {"id": "Bad Id", "name": "Z", "title": "T"})
        check("bad id rejected", s == 400, s)
        badu = json.dumps({"model": "gpt-4"}).encode()
        s, _ = req("PUT", "/api/crew/zz_temp", badu,
                   {"Content-Type": "application/json"})
        check("update invalid model", s == 422, s)
        upd = {"title": "Temp Two", "done": ["a", "b"], "bounds": {"max_steps": 8},
               "tools": ["read_md_section", "write_draft"],
               "appearance": {"variant": "character-female-a.glb", "tint": "#ff0000"}}
        s, b = req("PUT", "/api/crew/zz_temp", json.dumps(upd).encode(),
                   {"Content-Type": "application/json"})
        check("update extended", s == 200, s)
        _, b = req("GET", "/api/crew/zz_temp")
        d4 = json.loads(b.decode())
        check("io follows writer", d4["io"]["output"] == "draft.json"
              and d4["title"] == "Temp Two" and d4["bounds"]["max_steps"] == 8
              and d4["appearance"]["tint"] == "#ff0000", d4["io"])
        check("update validates", validate_agent.validate("agents/zz_temp") == [])
        s, b = req("GET", "/api/crew/zz_temp/handbook/notes.md")
        check("handbook preview", s == 200 and "Seed expertise" in b.decode(), s)
        s, _ = req("DELETE", "/api/crew/zz_temp")
        gone = not os.path.exists("agents/zz_temp")
        check("delete employee", s == 200 and gone, s)
        s, _ = req("GET", "/api/crew/zz_temp")
        check("deleted gone", s == 404, s)
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
