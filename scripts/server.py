"""Shoestring Studios backend (stdlib only).

Serves the homepage + JSON API for crew management. No opaque background
work: every mutation returns what changed, and runs stay inspectable.
Run:   python scripts/server.py [--port 8000]
Open:  http://localhost:8000
"""
import argparse
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
from agents._frame import runner  # noqa: E402
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


def load_dotenv(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


class Handler(BaseHTTPRequestHandler):
    server_version = "Shoestring/1"

    # ---- helpers ----
    def _json(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
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

    def _appearance(self, path):
        try:
            with open(os.path.join(path, "appearance.json"), encoding="utf-8") as f:
                ap = json.load(f)
            if not isinstance(ap, dict):
                return {"variant": None, "tint": None}
            return {"variant": ap.get("variant"), "tint": ap.get("tint")}
        except (OSError, ValueError):
            return {"variant": None, "tint": None}

    # ---- API ----
    def do_GET(self):
        parts = [p for p in unquote(self.path).split("?", 1)[0].split("/") if p]
        if parts[:2] == ["api", "crew"] and len(parts) == 2:
            return self._api_crew_list()
        if parts[:2] == ["api", "crew"] and len(parts) == 3:
            return self._api_crew_detail(parts[2])
        if parts[:2] == ["api", "crew"] and len(parts) == 4 and parts[3] == "handbook":
            return self._api_handbook(parts[2])
        if parts[:2] == ["api", "crew"] and len(parts) == 5 and parts[3] == "handbook":
            return self._api_handbook_file(parts[2], parts[4])
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
        if parts[:2] == ["api", "crew"] and len(parts) == 2:
            return self._api_crew_create()
        if parts[:2] == ["api", "crew"] and len(parts) == 4 and parts[3] == "train":
            return self._api_train(parts[2])
        if parts[:2] == ["api", "crew"] and len(parts) == 4 and parts[3] == "chat":
            return self._api_chat(parts[2])
        return self._json(404, {"error": "not found"})

    def do_DELETE(self):
        parts = [p for p in unquote(self.path).split("?", 1)[0].split("/") if p]
        if parts[:2] == ["api", "crew"] and len(parts) == 3:
            return self._api_crew_delete(parts[2])
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
                        "appearance": self._appearance(path),
                        "graph": graph.get_status(path)["state"]})
        return self._json(200, out)

    def _api_crew_detail(self, eid):
        path = self._employee(eid)
        if not path:
            return self._json(404, {"error": "no such employee"})
        agent = self._load_agent(path)
        with open(os.path.join(path, "persona.md"), encoding="utf-8") as f:
            persona = f.read()
        hb = sorted(f for f in os.listdir(os.path.join(path, "handbook"))
                    if f.endswith(".md"))
        available = sorted(registry.get_tools(path))
        return self._json(200, {
            "id": agent["id"], "name": agent["name"], "title": agent["title"],
            "model": agent["model"], "tools": agent["tools"],
            "bounds": agent["bounds"], "io": agent["io"], "done": agent["done"],
            "persona": persona,
            "appearance": self._appearance(path),
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
        ap_path = os.path.join(path, "appearance.json")
        backup_ap = None
        if os.path.isfile(ap_path):
            with open(ap_path, encoding="utf-8") as f:
                backup_ap = f.read()
        bad = self._apply_update(agent, body)
        if bad:
            return self._json(400, {"error": bad})
        changed = [k for k in ("name", "title", "model", "tools", "bounds",
                               "done", "persona", "appearance") if k in body]
        with open(os.path.join(path, "agent.json"), "w", encoding="utf-8") as f:
            json.dump(agent, f, ensure_ascii=False, indent=2)
        if "persona" in body:
            with open(os.path.join(path, "persona.md"), "w", encoding="utf-8") as f:
                f.write(body["persona"])
        if "appearance" in body:
            with open(ap_path, "w", encoding="utf-8") as f:
                json.dump(body["appearance"], f, ensure_ascii=False, indent=2)
        errs = validate_agent.validate(path)
        if errs:
            with open(os.path.join(path, "agent.json"), "w", encoding="utf-8") as f:
                f.write(backup_json)
            with open(os.path.join(path, "persona.md"), "w", encoding="utf-8") as f:
                f.write(backup_persona)
            if backup_ap is None:
                if os.path.isfile(ap_path):
                    os.remove(ap_path)
            else:
                with open(ap_path, "w", encoding="utf-8") as f:
                    f.write(backup_ap)
            return self._json(422, {"error": "validation failed", "details": errs})
        print("update %s: %s" % (eid, ",".join(changed)), flush=True)
        return self._json(200, {"ok": True, "changed": changed})

    @staticmethod
    def _apply_update(agent, body):
        """Copy editable fields into agent; return an error string or ''."""
        for key in ("name", "title"):
            if key in body:
                if not isinstance(body[key], str) or not body[key].strip():
                    return "%s must be a non-empty string" % key
                agent[key] = body[key].strip()
        if "model" in body:
            agent["model"] = body["model"]
        if "tools" in body:
            if not isinstance(body["tools"], list):
                return "tools must be a list"
            agent["tools"] = body["tools"]
            writers = [t for t in body["tools"]
                       if isinstance(t, str) and t.startswith("write_")]
            if len(writers) == 1:
                if writers[0] not in registry.OUTPUTS:
                    return "unknown writer tool: " + writers[0]
                agent["io"]["output"] = registry.OUTPUTS[writers[0]]
        if "bounds" in body:
            steps = (body["bounds"] or {}).get("max_steps")
            if not isinstance(steps, int) or isinstance(steps, bool) \
                    or not 1 <= steps <= 20:
                return "bounds.max_steps must be int 1-20"
            agent["bounds"]["max_steps"] = steps
        if "done" in body:
            if (not isinstance(body["done"], list) or not body["done"]
                    or any(not isinstance(d, str) or not d.strip()
                           for d in body["done"])):
                return "done must be a non-empty string list"
            agent["done"] = [d.strip() for d in body["done"]]
        if "persona" in body and not isinstance(body["persona"], str):
            return "persona must be a string"
        if "appearance" in body:
            ap = body["appearance"]
            if not isinstance(ap, dict) or not isinstance(ap.get("variant"), str):
                return "appearance needs {variant, tint?}"
            if "tint" in ap and not re.match(r"^#[0-9a-fA-F]{6}$", ap["tint"] or ""):
                return "tint must be #rrggbb"
        return ""

    def _api_crew_create(self):
        body = self._read_json()
        if not isinstance(body, dict):
            return self._json(400, {"error": "need JSON object"})
        eid = body.get("id", "")
        name = (body.get("name") or "").strip()
        title = (body.get("title") or "").strip()
        if not validate_agent.ID_RE.match(eid) or eid.startswith("_"):
            return self._json(400, {"error": "bad id (lowercase snake, no leading _)"})
        if not name or not title:
            return self._json(400, {"error": "name and title are required"})
        path = os.path.join(ROOT, "agents", eid)
        if os.path.exists(path):
            return self._json(409, {"error": "employee exists: " + eid})
        model = body.get("model") or "muse-spark-1.3"
        os.makedirs(os.path.join(path, "handbook"))
        agent = {"frame_version": 1, "id": eid, "name": name, "title": title,
                 "model": model, "tools": ["read_md_section", "write_structure"],
                 "bounds": {"max_steps": 6},
                 "io": {"inputs": ["brief.json", "input.md"], "output": "structure.json"},
                 "done": ["every section mapped", "links connect all neighbours",
                          "headings match the source"]}
        with open(os.path.join(path, "agent.json"), "w", encoding="utf-8") as f:
            json.dump(agent, f, ensure_ascii=False, indent=2)
        with open(os.path.join(path, "persona.md"), "w", encoding="utf-8") as f:
            f.write(self._persona_template(name, title))
        with open(os.path.join(path, "handbook", "notes.md"), "w", encoding="utf-8") as f:
            f.write("# Notes\n\nSeed expertise for %s. Replace with real training notes.\n" % name)
        with open(os.path.join(path, "appearance.json"), "w", encoding="utf-8") as f:
            json.dump({"variant": body.get("variant") or self._pick_variant(),
                       "tint": body.get("tint") or "#ffffff"},
                      f, ensure_ascii=False, indent=2)
        errs = validate_agent.validate(path)
        if errs:
            shutil.rmtree(path, ignore_errors=True)
            return self._json(422, {"error": "validation failed", "details": errs})
        print("create %s" % eid, flush=True)
        return self._json(201, {"ok": True, "id": eid})

    def _api_crew_delete(self, eid):
        path = self._employee(eid)
        if not path:
            return self._json(404, {"error": "no such employee"})
        shutil.rmtree(path)
        print("delete %s" % eid, flush=True)
        return self._json(200, {"ok": True, "deleted": eid})

    def _api_handbook_file(self, eid, filename):
        path = self._employee(eid)
        if not path:
            return self._json(404, {"error": "no such employee"})
        name = os.path.basename(unquote(filename))
        if not name.endswith(".md") or "/" in filename or "\\" in filename:
            return self._json(400, {"error": "only .md files"})
        full = os.path.join(path, "handbook", name)
        if not os.path.isfile(full):
            return self._json(404, {"error": "no such file"})
        with open(full, encoding="utf-8") as f:
            return self._json(200, {"file": name, "content": f.read()})

    def _pick_variant(self):
        used = set()
        adir = os.path.join(ROOT, "agents")
        for eid in sorted(os.listdir(adir)):
            ap = os.path.join(adir, eid, "appearance.json")
            if os.path.isfile(ap):
                try:
                    with open(ap, encoding="utf-8") as f:
                        used.add(json.load(f).get("variant"))
                except ValueError:
                    pass
        for sex in ("male", "female"):
            for letter in "abcdef":
                v = "character-%s-%s.glb" % (sex, letter)
                if v not in used:
                    return v
        return "character-male-a.glb"

    @staticmethod
    def _persona_template(name, title):
        return ("# %s — %s\n"
                "\n"
                "You are %s, %s of Shoestring Studios, an AI video team.\n"
                "Your job: read the input markdown and map its structure.\n"
                "\n"
                "## Persona\n"
                "\n"
                "- Careful reader; maps what is on the page.\n"
                "- Respects the author's framing and section order.\n"
                "- Plain wording, no hype.\n"
                "\n"
                "## Voice\n"
                "\n"
                "- Plain, compact English. Short phrases.\n"
                "\n"
                "## Rules\n"
                "\n"
                "- Read the input with read_md_section before mapping anything.\n"
                "- Map every section in source order; headings match the source exactly.\n"
                "- Bounded tools only: read_md_section, write_structure. Ask for nothing else.\n"
                "- Finish by calling write_structure with the COMPLETE object.\n"
                % (name, title, name, title))

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

    def _api_chat(self, eid):
        path = self._employee(eid)
        if not path:
            return self._json(404, {"error": "no such employee"})
        body = self._read_json()
        msgs = body.get("messages") if isinstance(body, dict) else None
        if (not isinstance(msgs, list) or not msgs or len(msgs) > 12
                or any(not isinstance(m, dict)
                       or m.get("role") not in ("user", "assistant")
                       or not isinstance(m.get("content"), str)
                       or not m["content"].strip()
                       or len(m["content"]) > 2000 for m in msgs)):
            return self._json(400, {"error": "need {messages: [{role, content}*]} (<=12, <=2000 chars)"})
        agent = self._load_agent(path)
        with open(os.path.join(path, "persona.md"), encoding="utf-8") as f:
            persona = f.read()
        if not (os.environ.get("MODEL_API_KEY") or os.environ.get("META_API_KEY")):
            return self._json(503, {"error": "MODEL_API_KEY missing: add it to .env"})
        system = (persona + "\n\n[LIVE CHAT — reply in English as %s, %s. "
                  "Always reply in English only: never Korean or any other "
                  "language, no matter what language the user writes in. "
                  "Keep replies to 1-3 short sentences. Stay in character; "
                  "you work at Shoestring Studios.]"
                  % (agent["name"], agent["title"]))
        try:
            resp = runner._chat(
                agent["model"],
                [{"role": "system", "content": system}]
                + [{"role": m["role"], "content": m["content"]} for m in msgs],
                None, max_tokens=400, timeout=120)
            reply = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
            if not isinstance(reply, str) or not reply.strip():
                raise ValueError("empty reply")
        except Exception as exc:  # noqa: BLE001 - surfaced as 502, key never leaks
            return self._json(502, {"error": "model API error: %s" % exc})
        return self._json(200, {"reply": reply.strip()})

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
        if mime == "text/html":
            self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    load_dotenv(os.path.join(ROOT, ".env"))
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
