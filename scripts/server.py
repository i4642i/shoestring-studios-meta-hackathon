"""Shoestring Studios backend (stdlib only).

Serves the homepage + JSON API for crew management. No opaque background
work: every mutation returns what changed, and runs stay inspectable.
Run:   python scripts/server.py [--port 8000]
Open:  http://localhost:8000
"""
import argparse
import base64
import json
import mimetypes
import os
import re
import shutil
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from agents._frame import graph  # noqa: E402
from agents._frame import tools as registry  # noqa: E402
import validate_agent  # noqa: E402

ALLOWED_UPLOAD = (".md", ".txt", ".pdf")


def parse_multipart(handler):
    ctype = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in ctype:
        return None, None
    try:
        boundary = ctype.split("boundary=")[1].encode()
    except IndexError:
        return None, None
    try:
        length = int(handler.headers.get("Content-Length", 0))
    except ValueError:
        return None, None
    body = handler.rfile.read(length)
    fields, files = {}, {}
    for part in body.split(b"--" + boundary):
        if b"Content-Disposition" not in part:
            continue
        head, _, content = part.partition(b"\r\n\r\n")
        content = content.rsplit(b"\r\n", 1)[0]
        disp = head.decode("utf-8", "replace")
        name = re.search(r'name="([^"]+)"', disp)
        if not name:
            continue
        fn = re.search(r'filename="([^"]+)"', disp)
        if fn:
            files[name.group(1)] = (fn.group(1), content)
        else:
            fields[name.group(1)] = content.decode("utf-8", "replace")
    return fields, files


def pdf_to_text(raw):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("pypdf not installed (pip install pypdf)")
    import io
    reader = PdfReader(io.BytesIO(raw))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


class Handler(BaseHTTPRequestHandler):
    server_version = "Shoestring/1"

    # ---- helpers ----
    def _json(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return None
        try:
            return json.loads(self.rfile.read(length).decode())
        except ValueError:
            return None

    def _employee(self, eid):
        if not validate_agent.ID_RE.match(eid):
            return None
        path = os.path.join(ROOT, "agents", eid)
        if not os.path.isdir(path) or eid.startswith("_"):
            return None
        return path

    def _load_agent(self, path):
        with open(os.path.join(path, "agent.json"), encoding="utf-8") as f:
            return json.load(f)

    # ---- API ----
    def do_GET(self):
        parts = [p for p in unquote(self.path).split("?", 1)[0].split("/") if p]
        if parts[:2] == ["api", "crew"] and len(parts) == 2:
            return self._api_crew_list()
        if parts[:2] == ["api", "crew"] and len(parts) == 3:
            return self._api_crew_detail(parts[2])
        if parts[:2] == ["api", "crew"] and len(parts) == 4 and parts[3] == "handbook":
            return self._api_handbook(parts[2])
        if parts[:2] == ["api", "crew"] and len(parts) == 4 and parts[3] == "graph":
            return self._api_graph(parts[2])
        return self._static(parts)

    def do_PUT(self):
        parts = [p for p in unquote(self.path).split("?", 1)[0].split("/") if p]
        if parts[:2] == ["api", "crew"] and len(parts) == 3:
            return self._api_crew_update(parts[2])
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        parts = [p for p in unquote(self.path).split("?", 1)[0].split("/") if p]
        if parts[:2] == ["api", "crew"] and len(parts) == 4 and parts[3] == "train":
            return self._api_train(parts[2])
        return self._json(404, {"error": "not found"})

    def do_DELETE(self):
        parts = [p for p in unquote(self.path).split("?", 1)[0].split("/") if p]
        if parts[:2] == ["api", "crew"] and len(parts) == 5 and parts[3] == "handbook":
            return self._api_handbook_delete(parts[2], parts[4])
        return self._json(404, {"error": "not found"})

    def _api_crew_list(self):
        adir = os.path.join(ROOT, "agents")
        out = []
        for eid in sorted(os.listdir(adir)):
            path = self._employee(eid)
            if not path:
                continue
            agent = self._load_agent(path)
            out.append({"id": agent["id"], "name": agent["name"],
                        "title": agent["title"], "model": agent["model"],
                        "tools": agent["tools"],
                        "graph": graph.get_status(path)["state"]})
        return self._json(200, out)

    def _api_crew_detail(self, eid):
        path = self._employee(eid)
        if not path:
            return self._json(404, {"error": "no such employee"})
        agent = self._load_agent(path)
        with open(os.path.join(path, "persona.md"), encoding="utf-8") as f:
            persona = f.read()
        with open(os.path.join(path, "portrait.webp"), "rb") as f:
            img = base64.b64encode(f.read()).decode()
        hb = sorted(f for f in os.listdir(os.path.join(path, "handbook"))
                    if f.endswith(".md"))
        available = sorted(registry.get_tools(path))
        return self._json(200, {
            "id": agent["id"], "name": agent["name"], "title": agent["title"],
            "model": agent["model"], "tools": agent["tools"],
            "bounds": agent["bounds"], "done": agent["done"],
            "persona": persona, "portrait": "data:image/webp;base64," + img,
            "handbook": hb, "graph": graph.get_status(path),
            "available_tools": available,
            "available_models": ["muse-spark-1.3", "muse-spark-1.2",
                                 "muse-spark-1.1", "muse-wonder-1.0"],
        })

    def _api_crew_update(self, eid):
        path = self._employee(eid)
        if not path:
            return self._json(404, {"error": "no such employee"})
        body = self._read_json()
        if not isinstance(body, dict):
            return self._json(400, {"error": "need JSON object"})
        agent = self._load_agent(path)
        backup_json = json.dumps(agent, ensure_ascii=False)
        with open(os.path.join(path, "persona.md"), encoding="utf-8") as f:
            backup_persona = f.read()
        changed = []
        if "model" in body:
            agent["model"] = body["model"]
            changed.append("model")
        if "tools" in body:
            agent["tools"] = body["tools"]
            changed.append("tools")
        with open(os.path.join(path, "agent.json"), "w", encoding="utf-8") as f:
            json.dump(agent, f, ensure_ascii=False, indent=2)
        if "persona" in body:
            with open(os.path.join(path, "persona.md"), "w", encoding="utf-8") as f:
                f.write(body["persona"])
            changed.append("persona")
        errs = validate_agent.validate(path)
        if errs:
            with open(os.path.join(path, "agent.json"), "w", encoding="utf-8") as f:
                f.write(backup_json)
            with open(os.path.join(path, "persona.md"), "w", encoding="utf-8") as f:
                f.write(backup_persona)
            return self._json(422, {"error": "validation failed", "details": errs})
        print("update %s: %s" % (eid, ",".join(changed)), flush=True)
        return self._json(200, {"ok": True, "changed": changed})

    def _api_handbook(self, eid):
        path = self._employee(eid)
        if not path:
            return self._json(404, {"error": "no such employee"})
        hb = sorted(f for f in os.listdir(os.path.join(path, "handbook"))
                    if f.endswith(".md"))
        return self._json(200, {"files": hb})

    def _api_graph(self, eid):
        path = self._employee(eid)
        if not path:
            return self._json(404, {"error": "no such employee"})
        st = graph.get_status(path)
        out = {"state": st["state"], "staged": st.get("staged", [])}
        if st["state"] == "indexed":
            out.update(graph.summarize(path))
        else:
            out["reason"] = st.get("reason", "")
            out.update({"entities": [], "relations": [],
                        "communities": []})
        return self._json(200, out)

    def _api_handbook_delete(self, eid, filename):
        path = self._employee(eid)
        if not path:
            return self._json(404, {"error": "no such employee"})
        name = os.path.basename(unquote(filename))
        if not name.endswith(".md") or "/" in filename or "\\" in filename:
            return self._json(400, {"error": "only .md files"})
        full = os.path.join(path, "handbook", name)
        if not os.path.isfile(full):
            return self._json(404, {"error": "no such file"})
        os.remove(full)
        print("handbook delete %s/%s" % (eid, name), flush=True)
        return self._json(200, {"ok": True, "deleted": name})

    def _api_train(self, eid):
        path = self._employee(eid)
        if not path:
            return self._json(404, {"error": "no such employee"})
        _, files = parse_multipart(self)
        if not files or "file" not in files:
            return self._json(400, {"error": "need multipart field 'file'"})
        raw_name, raw = files["file"]
        base = os.path.basename(raw_name)
        stem, ext = os.path.splitext(base.lower())
        if ext not in ALLOWED_UPLOAD:
            return self._json(400, {"error": "accepts .md/.txt/.pdf only"})
        stem = re.sub(r"[^a-z0-9_]+", "_", stem).strip("_") or "upload"
        if ext == ".pdf":
            try:
                text = pdf_to_text(raw)
            except RuntimeError as e:
                return self._json(500, {"error": str(e)})
            if not text.strip():
                return self._json(400, {"error": "no extractable text in PDF"})
        else:
            text = raw.decode("utf-8", "replace")
        dest = os.path.join(path, "handbook", stem + ".md")
        with open(dest, "w", encoding="utf-8") as f:
            f.write(text if text.endswith("\n") else text + "\n")
        print("train upload %s/%s (%d chars)" % (eid, stem + ".md", len(text)),
              flush=True)
        hb = sorted(f for f in os.listdir(os.path.join(path, "handbook"))
                    if f.endswith(".md"))
        return self._json(200, {"ok": True, "saved": stem + ".md",
                                "chars": len(text),
                                "preview": text[:500], "staged": hb})

    # ---- static ----
    def _static(self, parts):
        if not parts:
            parts = ["index.html"]
        if any(p.startswith(".") or p in ("..",) for p in parts):
            return self._json(403, {"error": "forbidden"})
        if parts == [".env"]:
            return self._json(403, {"error": "forbidden"})
        full = os.path.join(ROOT, *parts)
        if not os.path.isfile(full):
            return self._json(404, {"error": "not found"})
        mime = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    last = None
    for port in range(args.port, args.port + 6):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        except OSError as e:
            last = e
            continue
        print("Shoestring Studios at http://localhost:%d" % port, flush=True)
        server.serve_forever()
        return
    raise SystemExit("no free port %d-%d: %s"
                     % (args.port, args.port + 5, last))


if __name__ == "__main__":
    main()
