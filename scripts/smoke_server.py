"""Backend smoke test (stdlib only). Starts the server in-process and hits it.

Usage: python scripts/smoke_server.py
Covers: static /, .env blocked, crew list/detail (+ appearance, no portrait),
chat validation (404/400, no LLM), PUT roundtrip + invalid rejected,
train upload (.md), handbook delete. Exits nonzero on failure.
"""
import json
import os
import re
import shutil
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


def make_pdf(text):
    """One-page PDF with correct xref (stdlib-only, for parse tests)."""
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = "BT /F1 24 Tf 72 720 Td (%s) Tj ET" % safe
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        "<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += ("%d 0 obj\n" % i).encode() + body.encode() + b"\nendobj\n"
    xref = len(out)
    out += ("xref\n0 %d\n" % (len(objs) + 1)).encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += ("%010d 00000 n \n" % off).encode()
    out += ("trailer\n<< /Size %d /Root 1 0 R >>\n"
            "startxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)).encode()
    return bytes(out)


def make_img_pdf():
    """One-page PDF with a 4x2 RGB image XObject (for image tests)."""
    raw = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255] * 2)
    stream = ("BT /F1 24 Tf 72 720 Td (Hi) Tj ET\n"
              "q 100 0 0 50 72 500 cm /Im1 Do Q")
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> "
        "/XObject << /Im1 6 0 R >> >> >>",
        None,
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        None,
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        if i == 4:
            out += ("4 0 obj\n<< /Length %d >>\nstream\n%s\nendstream\n"
                    "endobj\n" % (len(stream), stream)).encode()
        elif i == 6:
            out += ("6 0 obj\n<< /Type /XObject /Subtype /Image /Width 4 "
                    "/Height 2 /ColorSpace /DeviceRGB /BitsPerComponent 8 "
                    "/Length %d >>\nstream\n" % len(raw)).encode()
            out += raw + b"\nendstream\nendobj\n"
        else:
            out += ("%d 0 obj\n" % i).encode() + body.encode() + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 7\n0000000000 65535 f \n"
    for off in offsets:
        out += ("%010d 00000 n \n" % off).encode()
    out += ("trailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % xref).encode()
    return bytes(out)


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
              and d.get("graph", {}).get("state") in ("not_indexed", "indexed")
              and "muse-spark-1.3" in d.get("available_models", []), s)
        check("detail appearance, no portrait",
              (d.get("appearance") or {}).get("variant", "").endswith(".glb")
              and "portrait" not in d)
        s, b = req("GET", "/api/crew/sales_sam/map")
        m = json.loads(b.decode()) if s == 200 else {}
        check("map lightrag", s == 200 and m.get("available")
              and len(m.get("entities", [])) >= 20
              and len(m.get("relations", [])) >= 20
              and (m.get("built") or {}).get("llm_calls", 0) >= 1, s)
        s, _ = req("GET", "/api/crew/nobody/map")
        check("map unknown id", s == 404, s)
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
              and json.loads(b2.decode())["model"] == "meta-models/muse-spark-open-1026", s)
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
              and d3.get("io", {}).get("output") == "result.json"
              and d3.get("appearance", {}).get("variant", "").endswith(".glb"), s)
        check("create defaults to baseten",
              d3.get("model") == "meta-models/muse-spark-open-1026",
              d3.get("model"))
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
        # orders: create -> get -> intake -> pdf upload -> chat guards
        s, b = jpost("/api/orders", {})
        o = json.loads(b.decode()) if s == 201 else {}
        oid = o.get("id", "")
        check("order create", s == 201 and oid.startswith("ord-")
              and o.get("assignee") == "sales_sam", (s, oid))
        s, b = req("GET", "/api/orders/" + oid)
        check("order get", s == 200
              and json.loads(b.decode())["status"] == "consulting", s)
        check("order get has transcript", s == 200
              and json.loads(b.decode()).get("transcript") == [], s)
        s, _ = req("GET", "/api/orders/ord-20000101-999")
        check("order unknown", s == 404, s)
        s, _ = jpost("/api/orders", {"assignee": "nobody"})
        check("order bad assignee", s == 400, s)
        good_answers = {"audience": "beginners", "length": "10 minutes",
                        "depth": "key concepts", "theme": "story-led"}
        s, _ = req("PUT", "/api/orders/" + oid + "/intake",
                   json.dumps({"answers": good_answers}).encode(),
                   {"Content-Type": "application/json"})
        check("order intake", s == 200, s)
        s, _ = req("PUT", "/api/orders/" + oid + "/intake",
                   json.dumps({"answers": {"audience": "x"}}).encode(),
                   {"Content-Type": "application/json"})
        check("order intake rejects partial", s == 400, s)
        pdf = make_pdf("Hello order")
        mp = lambda fn, blob: (
            ("--BOUND123\r\nContent-Disposition: form-data; name=\"file\"; "
             "filename=\"%s\"\r\nContent-Type: application/pdf\r\n\r\n" % fn
             ).encode() + blob + b"\r\n--BOUND123--\r\n")
        s, b = req("POST", "/api/orders/" + oid + "/upload",
                   mp("source.pdf", pdf),
                   {"Content-Type": "multipart/form-data; boundary=BOUND123"})
        r = json.loads(b.decode()) if s == 200 else {}
        stored_ok = os.path.isfile("orders/%s/source.pdf" % oid)
        check("order pdf stored", s == 200 and r.get("file") == "source.pdf"
              and r.get("bytes", 0) > 0 and r.get("name") == "source.pdf"
              and stored_ok
              and not os.path.isfile("orders/%s/parsed.md" % oid),
              (s, r))
        s, _ = req("POST", "/api/orders/" + oid + "/upload",
                   mp("notes.md", b"# hi"),
                   {"Content-Type": "multipart/form-data; boundary=BOUND123"})
        check("order upload rejects non-pdf", s == 400, s)
        s, b = req("POST", "/api/orders/" + oid + "/upload",
                   mp("img.pdf", make_img_pdf()),
                   {"Content-Type": "multipart/form-data; boundary=BOUND123"})
        r = json.loads(b.decode()) if s == 200 else {}
        check("order pdf re-upload stores", s == 200
              and r.get("name") == "img.pdf"
              and os.path.isfile("orders/%s/source.pdf" % oid)
              and not os.path.isdir("orders/%s/images" % oid),
              (s, r))
        s, _ = jpost("/api/orders/" + oid + "/chat", {"messages": []})
        check("order chat bad shape", s == 400, s)
        s, _ = jpost("/api/orders/ord-20000101-999/chat",
                     {"messages": [{"role": "user", "content": "hi"}]})
        check("order chat unknown order", s == 404, s)
        s, b = jpost("/api/orders", {})
        oid2 = json.loads(b.decode()).get("id", "") if s == 201 else ""
        s, _ = jpost("/api/orders/" + oid2 + "/complete", {})
        check("complete guards intake", s == 409, s)
        s, b = jpost("/api/orders/" + oid2 + "/complete", {"extract": True})
        r = json.loads(b.decode()) if s == 409 else {}
        check("extract needs chat", s == 409 and "tip" in r, (s, r))
        s, b = jpost("/api/orders", {})
        oid3 = json.loads(b.decode()).get("id", "") if s == 201 else ""
        s, _ = req("PUT", "/api/orders/" + oid3 + "/intake",
                   json.dumps({"answers": good_answers}).encode(),
                   {"Content-Type": "application/json"})
        s, b = jpost("/api/orders/" + oid3 + "/complete", {"extract": True})
        check("extract skips when answered", s == 409
              and "no attached PDF" in b.decode(), s)
        s, _ = jpost("/api/orders/" + oid2 + "/start", {})
        check("start needs approval", s == 409, s)
        s, _ = jpost("/api/orders/ord-20000101-999/start", {})
        check("start unknown", s == 404, s)
        s, _ = jpost("/api/orders/" + oid2 + "/approve", {"approved": False})
        check("approve bad shape", s == 400, s)
        s, b = jpost("/api/orders/" + oid2 + "/approve", {"approved": True})
        check("approve ok", s == 200, s)
        s, b = req("GET", "/api/orders/" + oid2)
        check("approve stored", s == 200
              and json.loads(b.decode()).get("approved"), s)
        s, b = jpost("/api/orders/" + oid2 + "/start", {})
        check("start guards intake", s == 409
              and "intake incomplete" in b.decode(), s)
        for cand in (oid, oid2, oid3):
            shutil.rmtree("orders/" + cand, ignore_errors=True)
        check("orders cleaned", not os.path.exists("orders/" + oid), oid)
        # PC fleet registry
        s, b = req("GET", "/api/pcs")
        pcs = json.loads(b.decode()).get("pcs", []) if s == 200 else []
        check("pcs list seeds shared-pc", s == 200
              and any(p["id"] == "shared-pc" for p in pcs), s)
        s, b = jpost("/api/pcs", {"name": "ZZ Test Rig",
                                  "materials": ["demo reels"],
                                  "owner": "lab", "capability": "embedding",
                                  "tool": "query_pc"})
        check("pc add", s == 201, s)
        s, _ = jpost("/api/pcs", {"name": "ZZ Test Rig"})
        check("pc duplicate", s == 409, s)
        s, b = req("GET", "/api/pcs")
        have = [p for p in json.loads(b.decode())["pcs"]
                if p["id"] == "zz-test-rig"]
        check("pc stored", s == 200 and len(have) == 1
              and have[0]["state"] == "planned", s)
        s, _ = req("DELETE", "/api/pcs/zz-test-rig")
        s, b = req("GET", "/api/pcs")
        gone = all(p["id"] != "zz-test-rig"
                   for p in json.loads(b.decode())["pcs"])
        check("pc delete", s == 200 and gone, s)
        s, _ = req("DELETE", "/api/pcs/no-such-pc")
        check("pc delete unknown", s == 404, s)
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
