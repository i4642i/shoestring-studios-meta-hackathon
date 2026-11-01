"""Order handover check: a yes in chat finalizes at once (live model).

Starts scripts/server.py (never 8000), drives one order through the
real API the way a customer would: 4 chat answers, a tiny PDF upload,
then the exact yes line that used to loop back into another
confirmation question (ord-20261102-026). Asserts the turn is
accepted and handed over, and the request files exist.

Live model calls: ~6 (4 answers + yes, +1 retry at most). No browser,
no /progress poll (so no crew flow starts), stdlib only. The test
order and its output/runs folder are deleted afterwards (try/finally).
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_PORT = int(os.environ.get("CHECK_PORT", 8765))
SERVER_LOG = os.path.join(ROOT, "runs", "order_handover_server.log")

ANSWERS = [
    "My book club friends. Most of us never studied science.",
    "Around 12 minutes.",
    "Just the key ideas.",
    "Everyday stories and a bit of humor.",
]
YES = "Yes, I attached the PDF. Let's start."
YES2 = "Yes, confirmed. Start production now."

TINY_PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]/"
            b"Contents 4 0 R>>endobj\n"
            b"4 0 obj<</Length 44>>stream\n"
            b"BT /F1 12 Tf 20 180 Td (Hello handover test) Tj ET\n"
            b"endstream\nendobj\ntrailer<</Root 1 0 R>>\n")

fails = 0


def ok(cond, msg):
    global fails
    line = ("PASS " if cond else "FAIL ") + msg
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode(), flush=True)
    if not cond:
        fails += 1


def port_open(port):
    try:
        socket.create_connection(("127.0.0.1", port), timeout=2).close()
        return True
    except OSError:
        return False


def api(method, path, body=None, headers=None, timeout=180):
    data = None
    if body is not None:
        if isinstance(body, dict):
            data = json.dumps(body).encode()
            headers = dict(headers or {})
            headers.setdefault("Content-Type", "application/json")
        else:
            data = body
    req = urllib.request.Request("http://localhost:%d%s"
                                 % (SERVER_PORT, path),
                                 data=data, headers=headers or {},
                                 method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode())


def stop_proc(proc):
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=15)
    except (OSError, subprocess.SubprocessError):
        try:
            proc.kill()
        except (OSError, subprocess.SubprocessError):
            pass
    print("stopped server (exit %s)" % proc.poll(), flush=True)


def main():
    os.makedirs(os.path.join(ROOT, "runs"), exist_ok=True)
    if port_open(SERVER_PORT):
        ok(False, "port %d already busy, touching nothing" % SERVER_PORT)
        print("1 FAILURES")
        return 1
    server = None
    oid = ""
    try:
        logf = open(SERVER_LOG, "w", encoding="utf-8")
        server = subprocess.Popen(
            [sys.executable, "scripts/server.py",
             "--port", str(SERVER_PORT)],
            cwd=ROOT, stdout=logf, stderr=subprocess.STDOUT)
        t0 = time.time()
        while time.time() - t0 < 60:
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/api/version" % SERVER_PORT,
                        timeout=3) as r:
                    if r.status == 200:
                        break
            except OSError:
                time.sleep(1)
        else:
            ok(False, "server answers on %d" % SERVER_PORT)
            print("1 FAILURES")
            return 1
        ok(True, "server answers on %d" % SERVER_PORT)
        code, created = api("POST", "/api/orders", {"force": True})
        oid = created.get("id", "")
        ok(code in (200, 201) and oid.startswith("ord-"),
           "order created (%s)" % oid)
        history = []
        for answer in ANSWERS:
            history.append({"role": "user", "content": answer})
            code, turn = api("POST", "/api/orders/%s/chat" % oid,
                             {"messages": history, "mode": "free"})
            reply = (turn or {}).get("reply", "")
            ok(code == 200 and bool(reply.strip()),
               "chat turn answered (%s...)" % reply[:50])
            history.append({"role": "assistant", "content": reply})
        missing = (turn or {}).get("missing", ["?"])
        ok(missing == ["source PDF"],
           "form full, only the PDF missing (%s)" % missing)
        bound = "HANDOVERBOUND1"
        pre = ("--" + bound + "\r\nContent-Disposition: form-data; "
               'name="file"; filename="tiny.pdf"\r\n'
               "Content-Type: application/pdf\r\n\r\n").encode()
        post = ("\r\n--" + bound + "--\r\n").encode()
        code, up = api("POST", "/api/orders/%s/upload" % oid,
                       pre + TINY_PDF + post,
                       {"Content-Type":
                        "multipart/form-data; boundary=" + bound})
        ok(code == 200 and (up or {}).get("ok") is True,
           "tiny PDF uploaded (%s bytes)" % (up or {}).get("bytes"))
        ok((up or {}).get("missing") == [],
           "nothing missing after upload (%s)"
           % (up or {}).get("missing"))
        accepted = {}
        for attempt, line in enumerate((YES, YES2)):
            history.append({"role": "user", "content": line})
            code, turn = api("POST", "/api/orders/%s/chat" % oid,
                             {"messages": history, "mode": "free"})
            accepted = turn or {}
            if accepted.get("accepted") and accepted.get("handed_over"):
                break
            history.append({"role": "assistant",
                            "content": accepted.get("reply", "")})
        ok(accepted.get("accepted") is True
           and accepted.get("handed_over") is True,
           "yes finalizes at once, no second confirmation (%s)"
           % str(accepted.get("reply", ""))[:120])
        d = os.path.join(ROOT, "orders", oid)
        rep = os.path.join(d, "report.md")
        ok(os.path.isfile(rep), "report.md written")
        if os.path.isfile(rep):
            md = open(rep, encoding="utf-8").read()
            ok(len(md) > 200, "report holds the request (%d chars)"
               % len(md))
        intp = os.path.join(d, "intake.json")
        ok(os.path.isfile(intp), "intake.json written")
        if os.path.isfile(intp):
            saved = json.load(open(intp, encoding="utf-8"))
            form = accepted.get("form", {}) or {}
            ok(all((saved.get("answers", {}) or {}).get(k)
                   == (form.get(k) or "") and form.get(k)
                   for k in ("audience", "length", "depth", "theme")),
               "intake answers match the handed-over form")
        ok(os.path.isfile(os.path.join(d, "result.json")),
           "request category written (result.json)")
    finally:
        stop_proc(server)
        for path in (os.path.join(ROOT, "orders", oid),
                     os.path.join(ROOT, "output", "runs", oid)):
            if oid:
                shutil.rmtree(path, ignore_errors=True)
    if fails:
        print("%d FAILURES" % fails)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
