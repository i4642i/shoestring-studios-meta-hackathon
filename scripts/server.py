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
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from agents._frame import flow as flows  # noqa: E402
from agents._frame import graph  # noqa: E402
from agents._frame import runner  # noqa: E402
from agents._frame import tools as registry  # noqa: E402
import validate_agent  # noqa: E402
import intake  # noqa: E402

ALLOWED_UPLOAD = (".md", ".txt", ".pdf")

ORDER_ID_RE = re.compile(r"^ord-[0-9]{8}-[0-9]{3}$")
INTAKE_KEYS = intake.INTAKE_KEYS
PC_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
MAX_PDF_BYTES = 25 * 1024 * 1024

_INDEX_JOBS = {}  # (eid, profile) -> Popen of a running run_index.py build
_FLOW_JOBS = {}  # run_id -> live flow run status (threads share memory)

# Served code: the version stamp tracks the last commit touching these.
VERSION_PATHS = ("index.html", "office_3d.html", "office_editor.html",
                 "scripts/server.py", "agents/_frame", "api", "vendor",
                 "data/flows/default.json")


def _code_head():
    """Full hash of the last commit touching served code ("unknown")."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--"] + list(VERSION_PATHS),
            cwd=ROOT, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    h = (out.stdout or "").strip()
    return h if re.fullmatch(r"[0-9a-f]{40}", h) else "unknown"


def _is_ancestor(old, new):
    try:
        r = subprocess.run(["git", "merge-base", "--is-ancestor", old, new],
                           cwd=ROOT, capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


SERVER_COMMIT = _code_head()
SERVER_STARTED = time.strftime("%Y-%m-%dT%H:%M:%S")


def parse_multipart(handler):
    ctype = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in ctype:
        return None, None
    try:
        boundary = ctype.split("boundary=")[1].encode()
    except IndexError:
        return None, None
    body = handler._body
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
        import pdfplumber
    except ImportError:
        raise RuntimeError(
            "pdfplumber not installed (pip install -r requirements.txt)")
    import io
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        return "\n\n".join((page.extract_text() or "") for page in pdf.pages)


def pdf_parse(raw):
    """Split a PDF into per-page texts + images: ([str], [(name, bytes)])."""
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError(
            "pdfplumber not installed (pip install -r requirements.txt)")
    import io
    pages, images = [], []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for i, page in enumerate(pdf.pages):
            pages.append(page.extract_text() or "")
            for j, img in enumerate(page.images):
                try:
                    crop = page.crop((img["x0"], img["top"],
                                      img["x1"], img["bottom"]))
                    buf = io.BytesIO()
                    crop.to_image(resolution=150).original.save(buf, format="PNG")
                    images.append(("p%02d-img%02d.png" % (i + 1, j + 1),
                                   buf.getvalue()))
                except Exception:  # noqa: BLE001 - one bad image skips, parse goes on
                    continue
    return pages, images


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

    def _slurp(self):
        """Read the request body once, up front.

        Every POST/PUT route calls this first so a 404/400 never leaves
        an unread body on the socket (which aborts the connection)."""
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        self._body = self.rfile.read(length) if length > 0 else b""

    def _read_json(self):
        try:
            return json.loads(self._body.decode())
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
        if parts[:2] == ["api", "crew"] and len(parts) == 4 and parts[3] == "map":
            return self._api_map(parts[2])
        if parts[:2] == ["api", "orders"] and len(parts) == 3:
            return self._api_order_get(parts[2])
        if parts[:2] == ["api", "ref"] and len(parts) == 2:
            return self._api_ref()
        if parts[:2] == ["api", "pcs"] and len(parts) == 2:
            return self._api_pcs_list()
        if parts[:2] == ["api", "settings"] and len(parts) == 2:
            return self._api_settings_get()
        if parts[:2] == ["api", "version"] and len(parts) == 2:
            return self._api_version()
        if parts[:2] == ["api", "flows"] and len(parts) == 2:
            return self._api_flows_list()
        if parts[:2] == ["api", "flows"] and len(parts) == 3:
            if parts[2] == "catalog":
                return self._api_flows_catalog()
            if parts[2] == "runs":
                return self._api_flow_runs()
            return self._api_flow_get(parts[2])
        if parts[:2] == ["api", "flows"] and len(parts) == 4 \
                and parts[2] == "runs":
            return self._api_flow_run_get(parts[3])
        return self._static(parts)

    def do_PUT(self):
        self._slurp()
        parts = [p for p in unquote(self.path).split("?", 1)[0].split("/") if p]
        if parts[:2] == ["api", "crew"] and len(parts) == 3:
            return self._api_crew_update(parts[2])
        if parts[:2] == ["api", "orders"] and len(parts) == 4 and parts[3] == "intake":
            return self._api_order_intake(parts[2])
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        self._slurp()
        parts = [p for p in unquote(self.path).split("?", 1)[0].split("/") if p]
        if parts[:2] == ["api", "crew"] and len(parts) == 2:
            return self._api_crew_create()
        if parts[:2] == ["api", "crew"] and len(parts) == 4 and parts[3] == "train":
            return self._api_train(parts[2])
        if parts[:2] == ["api", "crew"] and len(parts) == 4 and parts[3] == "chat":
            return self._api_chat(parts[2])
        if parts[:2] == ["api", "orders"] and len(parts) == 2:
            return self._api_order_create()
        if parts[:2] == ["api", "orders"] and len(parts) == 4 and parts[3] == "upload":
            return self._api_order_upload(parts[2])
        if parts[:2] == ["api", "orders"] and len(parts) == 4 and parts[3] == "chat":
            return self._api_order_chat(parts[2])
        if parts[:2] == ["api", "orders"] and len(parts) == 4 and parts[3] == "complete":
            return self._api_order_complete(parts[2])
        if parts[:2] == ["api", "orders"] and len(parts) == 4 and parts[3] == "approve":
            return self._api_order_approve(parts[2])
        if parts[:2] == ["api", "orders"] and len(parts) == 4 and parts[3] == "start":
            return self._api_order_start(parts[2])
        if parts[:2] == ["api", "orders"] and len(parts) == 4 and parts[3] == "confirm":
            return self._api_order_confirm(parts[2])
        if parts[:2] == ["api", "pcs"] and len(parts) == 2:
            return self._api_pcs_add()
        if parts[:2] == ["api", "settings"] and len(parts) == 2:
            return self._api_settings_save()
        if parts[:2] == ["api", "settings"] and len(parts) == 3 \
                and parts[2] == "test":
            return self._api_settings_test()
        if parts[:2] == ["api", "crew"] and len(parts) == 4 \
                and parts[3] == "index":
            return self._api_index_build(parts[2])
        if parts[:2] == ["api", "flows"] and len(parts) == 3:
            if parts[2] == "validate":
                return self._api_flow_validate()
            return self._api_flow_save(parts[2])
        if parts[:2] == ["api", "flows"] and len(parts) == 4 \
                and parts[3] == "run":
            return self._api_flow_run(parts[2])
        return self._json(404, {"error": "not found"})

    def do_DELETE(self):
        parts = [p for p in unquote(self.path).split("?", 1)[0].split("/") if p]
        if parts[:2] == ["api", "crew"] and len(parts) == 3:
            return self._api_crew_delete(parts[2])
        if parts[:2] == ["api", "crew"] and len(parts) == 5 and parts[3] == "handbook":
            return self._api_handbook_delete(parts[2], parts[4])
        if parts[:2] == ["api", "pcs"] and len(parts) == 3:
            return self._api_pcs_delete(parts[2])
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
            "available_models": ["meta-models/muse-spark-open-1026",
                                 "muse-spark-1.3", "muse-spark-1.2",
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
        backup_json = json.dumps(agent, ensure_ascii=False, indent=2)
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
        model = body.get("model") or "meta-models/muse-spark-open-1026"
        os.makedirs(os.path.join(path, "handbook"))
        agent = {"frame_version": 1, "id": eid, "name": name, "title": title,
                 "model": model, "tools": ["read_md_section", "write_structure"],
                 "bounds": {"max_steps": 6},
                 "io": {"inputs": ["brief.json", "input.md"], "output": "result.json"},
                 "done": ["every section mapped", "links connect all neighbours",
                          "headings match the source"],
                 "flow": {"inputs": [], "outputs": []}}
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

    def _api_map(self, eid):
        path = self._employee(eid)
        if not path:
            return self._json(404, {"error": "no such employee"})
        m = graph.map_lightrag(path)
        if m is None:
            return self._json(200, {"available": False,
                                    "reason": "no LightRAG storage yet"})
        return self._json(200, m)

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
        if not runner.key_present(agent["model"]):
            return self._json(503, {"error": "%s missing: add it to .env"
                                    % runner.key_var(agent["model"])})
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
                None, timeout=120)
            reply = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
            if not isinstance(reply, str) or not reply.strip():
                raise ValueError("empty reply")
        except Exception as exc:  # noqa: BLE001 - surfaced as 502, key never leaks
            return self._json(502, {"error": "model API error: %s" % exc})
        return self._json(200, {"reply": reply.strip()})

    # ---- orders ----
    def _order_dir(self, oid):
        if not ORDER_ID_RE.match(oid or ""):
            return None
        d = os.path.join(ROOT, "orders", oid)
        return d if os.path.isdir(d) else None

    @staticmethod
    def _order_meta(d):
        with open(os.path.join(d, "meta.json"), encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _order_save_meta(d, meta):
        with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def _api_settings_get(self):
        mod = graph._adapter()
        eff = mod.resolved_settings()
        try:
            token_set = bool(mod.load_key("EMBED_REMOTE_TOKEN"))
        except RuntimeError:
            token_set = False
        agents_out = {}
        adir = os.path.join(ROOT, "agents")
        for eid in sorted(os.listdir(adir)):
            path = self._employee(eid)
            if not path:
                continue
            per = {}
            for prof in ("local", "jetson"):
                mark = mod.read_marker(path, prof)
                job = _INDEX_JOBS.get((eid, prof))
                building = job is not None and job.poll() is None
                if mark:
                    per[prof] = {
                        "built": True, "building": building,
                        "model": mark.get("model", ""),
                        "dim": mark.get("dim", 0),
                        "chunk_size": mark.get("chunk_size", 0),
                        "indexed_at": mark.get("indexed_at", "")}
                else:
                    per[prof] = {"built": False, "building": building}
            agents_out[eid] = per
        out = {"profile": eff["profile"], "jetson_url": eff["jetson_url"],
               "llm_model": eff["llm_model"], "query_mode": eff["query_mode"],
               "top_k": eff["top_k"], "chunk_local": eff["chunk_local"],
               "chunk_jetson": eff["chunk_jetson"],
               "llm_models": [{"model": m,
                               "provider": runner.provider_of(m)[0]}
                              for m in runner.LLM_MODELS],
               "query_modes": list(mod.QUERY_MODES),
               "token_set": token_set, "agents": agents_out}
        if eff["problems"]:
            out["settings_error"] = "; ".join(eff["problems"])
        return self._json(200, out)

    def _api_settings_save(self):
        body = self._read_json()
        if not isinstance(body, dict):
            return self._json(400, {"error": "need JSON object"})
        mod = graph._adapter()
        try:
            cleaned = mod.clean_settings(body)
        except RuntimeError as exc:
            return self._json(400, {"error": str(exc)})
        spath = os.path.join(ROOT, "data", "settings.json")
        stored = {}
        if os.path.isfile(spath):
            try:
                with open(spath, encoding="utf-8") as f:
                    stored = json.load(f)
            except ValueError:
                stored = {}
        if not isinstance(stored, dict):
            stored = {}
        stored.update(cleaned)
        stored.setdefault("embed_profile", "jetson")
        stored.setdefault("jetson_url", mod.DEFAULT_JETSON_URL)
        os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
        with open(spath, "w", encoding="utf-8") as f:
            json.dump(stored, f, ensure_ascii=False, indent=1)
        eff = mod.resolved_settings()
        return self._json(200, {"ok": True, "profile": eff["profile"],
                                "jetson_url": eff["jetson_url"]})

    def _api_settings_test(self):
        body = self._read_json()
        mod = graph._adapter()
        url = None
        if isinstance(body, dict) and body.get("jetson_url"):
            url = str(body.get("jetson_url")).strip().rstrip("/")
            if not (url.startswith("http://")
                    or url.startswith("https://")):
                return self._json(200, {"ok": False,
                                        "error": "jetson_url must start with "
                                                 "http(s)://"})
        try:
            base, token = mod._jetson_auth()
        except RuntimeError as exc:
            return self._json(200, {"ok": False, "error": str(exc)})
        try:
            h = mod.jetson_health(url or base, token)
        except RuntimeError as exc:
            return self._json(200, {"ok": False, "error": str(exc)})
        return self._json(200, {"ok": True, "model": h.get("model"),
                                "device": h.get("device"),
                                "dim": h.get("dim"), "ms": h.get("ms")})

    def _api_index_build(self, eid):
        path = self._employee(eid)
        if not path:
            return self._json(404, {"error": "no such employee"})
        body = self._read_json()
        mod = graph._adapter()
        want = str((body or {}).get("profile") or "").strip().lower()
        try:
            prof = mod.profile_config(want or None)["profile"]
        except RuntimeError as exc:
            return self._json(400, {"error": str(exc)})
        job = _INDEX_JOBS.get((eid, prof))
        if job is not None and job.poll() is None:
            return self._json(200, {"started": False,
                                    "reason": "already building"})
        if prof == "jetson":
            try:
                mod.jetson_health()
            except RuntimeError as exc:
                return self._json(200, {"started": False,
                                        "reason": str(exc)})
        logdir = os.path.join(ROOT, "experiments", "lightrag", "storage",
                              eid, prof)
        os.makedirs(logdir, exist_ok=True)
        logf = open(os.path.join(logdir, "build.log"), "a", encoding="utf-8")
        try:
            job = subprocess.Popen(
                [sys.executable,
                 os.path.join("experiments", "lightrag", "run_index.py"),
                 os.path.join("agents", eid), prof],
                cwd=ROOT, stdout=logf, stderr=subprocess.STDOUT)
        except OSError as exc:
            logf.close()
            return self._json(200, {"started": False,
                                    "reason": "spawn failed: %s" % exc})
        logf.close()
        _INDEX_JOBS[(eid, prof)] = job
        return self._json(200, {"started": True, "profile": prof})

    def _api_flows_list(self):
        out = []
        fdir = flows.FLOWS_DIR
        if os.path.isdir(fdir):
            for fn in sorted(os.listdir(fdir)):
                if not fn.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(fdir, fn), encoding="utf-8") as f:
                        d = json.load(f)
                    out.append({"id": fn[:-5],
                                "name": d.get("name", fn[:-5])})
                except (OSError, ValueError):
                    continue
        return self._json(200, {"flows": out})

    def _api_flows_catalog(self):
        return self._json(200, flows.load_catalog())

    def _api_flow_get(self, fid):
        try:
            return self._json(200, flows.load_flow(fid))
        except (ValueError, OSError):
            return self._json(404, {"error": "no such flow"})

    def _api_flow_save(self, fid):
        body = self._read_json()
        if not isinstance(body, dict):
            return self._json(400, {"error": "need flow object"})
        if fid in ("catalog", "validate", "runs") \
                or not validate_agent.ID_RE.match(fid or "") \
                or fid.startswith("_"):
            return self._json(400, {"error": "bad flow id"})
        flow_obj = {"id": fid, "name": body.get("name", fid),
                    "nodes": body.get("nodes", []),
                    "lines": body.get("lines", []),
                    "positions": body.get("positions", {})}
        errs = flows.validate_flow(flow_obj)
        if errs:
            return self._json(400, {"error": "invalid flow",
                                    "errors": errs})
        os.makedirs(flows.FLOWS_DIR, exist_ok=True)
        with open(os.path.join(flows.FLOWS_DIR, fid + ".json"), "w",
                  encoding="utf-8") as f:
            json.dump(flow_obj, f, ensure_ascii=False, indent=1)
        return self._json(200, {"ok": True, "id": fid})

    def _api_flow_validate(self):
        body = self._read_json()
        if not isinstance(body, dict):
            return self._json(400, {"error": "need flow object"})
        errs = flows.validate_flow(body)
        return self._json(200, {"ok": not errs, "errors": errs})

    def _api_flow_run(self, fid):
        try:
            flow_obj = flows.load_flow(fid)
        except (ValueError, OSError):
            return self._json(404, {"error": "no such flow"})
        errs = flows.validate_flow(flow_obj)
        if errs:
            return self._json(400, {"error": "invalid flow",
                                    "errors": errs})
        body = self._read_json()
        order_id = (body or {}).get("order_id") \
            if isinstance(body, dict) else None
        if not order_id or not isinstance(order_id, str):
            return self._json(400, {"error": "need {order_id}"})
        if not os.path.isfile(os.path.join(ROOT, "orders", order_id,
                                            "meta.json")):
            return self._json(404, {"error": "no such order"})
        run_id = flows.new_run_id()
        job = {"run_id": run_id, "flow_id": fid, "order_id": order_id,
               "state": "running", "error": ""}
        _FLOW_JOBS[run_id] = job

        def _work():
            try:
                flows.run_flow(flow_obj, order_id, runner.run,
                               run_id=run_id, flow_id=fid)
                job["state"] = "done"
            except Exception as exc:  # noqa: BLE001 - status surface
                job["state"] = "error"
                job["error"] = str(exc)[:1000]

        threading.Thread(target=_work, daemon=True).start()
        return self._json(200, {"started": True, "run_id": run_id})

    def _api_flow_runs(self):
        runs = []
        rdir = flows.RUNS_DIR
        if os.path.isdir(rdir):
            names = sorted(
                os.listdir(rdir),
                key=lambda n: os.path.getmtime(os.path.join(rdir, n)),
                reverse=True)[:20]
            for n in names:
                st = {"run_id": n, "state": "unknown"}
                try:
                    with open(os.path.join(rdir, n, "STATUS.json"),
                              encoding="utf-8") as f:
                        d = json.load(f)
                    st["state"] = d.get("state", "unknown")
                    st["flow_id"] = d.get("flow_id", "")
                    st["order_id"] = d.get("order_id", "")
                    st["error"] = d.get("error", "")
                except (OSError, ValueError):
                    pass
                if n in _FLOW_JOBS and _FLOW_JOBS[n]["state"] == "running":
                    st["state"] = "running"
                runs.append(st)
        return self._json(200, {"runs": runs})

    def _api_flow_run_get(self, run_id):
        if not run_id or "/" in run_id or "\\" in run_id \
                or run_id.startswith("."):
            return self._json(404, {"error": "no such run"})
        rdir = os.path.join(flows.RUNS_DIR, run_id)
        if not os.path.isdir(rdir):
            return self._json(404, {"error": "no such run"})
        events = []
        ep = os.path.join(rdir, "events.jsonl")
        if os.path.isfile(ep):
            with open(ep, encoding="utf-8") as f:
                for ln in f.read().splitlines():
                    try:
                        events.append(json.loads(ln))
                    except ValueError:
                        continue
        job = _FLOW_JOBS.get(run_id)
        if job is not None and job["state"] == "running":
            state, err = "running", ""
        else:
            state, err = "unknown", ""
            try:
                with open(os.path.join(rdir, "STATUS.json"),
                          encoding="utf-8") as f:
                    d = json.load(f)
                state, err = d.get("state", "unknown"), d.get("error", "")
            except (OSError, ValueError):
                pass
        out = {"run_id": run_id, "state": state, "events": events}
        if err:
            out["error"] = err
        if job is not None:
            out["flow_id"] = job.get("flow_id", "")
            out["order_id"] = job.get("order_id", "")
        return self._json(200, out)

    @staticmethod
    def _handbook_hints(agent_dir, text):
        """LightRAG answer excerpt for the client's latest line ("", if none)."""
        try:
            res = graph.query(agent_dir, text)
        except Exception as exc:  # noqa: BLE001 - no index, chat goes on plain
            print("[WARN] handbook hints unavailable: %s" % exc)
            return ""
        if not isinstance(res, dict):
            return ""
        return str(res.get("answer", ""))[:1200]

    @staticmethod
    def _check_messages(body):
        msgs = body.get("messages") if isinstance(body, dict) else None
        if (not isinstance(msgs, list) or not msgs
                or any(not isinstance(m, dict)
                       or m.get("role") not in ("user", "assistant")
                       or not isinstance(m.get("content"), str)
                       or not m["content"].strip()
                       or len(m["content"]) > 2000 for m in msgs)):
            return None
        return [{"role": m["role"], "content": m["content"]} for m in msgs]

    @staticmethod
    def _transcript_turns(d):
        """Full order transcript as chat turns (oldest first, ~8000 chars)."""
        turns = []
        chat = os.path.join(d, "chat.jsonl")
        if os.path.isfile(chat):
            with open(chat, encoding="utf-8") as f:
                for ln in f.read().splitlines():
                    try:
                        turn = json.loads(ln)
                    except ValueError:
                        continue
                    if turn.get("user"):
                        turns.append({"role": "user",
                                      "content": turn["user"]})
                    if turn.get("reply"):
                        turns.append({"role": "assistant",
                                      "content": turn["reply"]})
        total = sum(len(t["content"]) for t in turns)
        while total > 8000 and len(turns) > 2:
            total -= len(turns.pop(0)["content"])
        return turns

    def _api_order_create(self):
        body = self._read_json()
        if not isinstance(body, dict):
            return self._json(400, {"error": "need JSON object"})
        assignee = body.get("assignee") or "sales_sam"
        if not self._employee(assignee):
            return self._json(400, {"error": "unknown assignee: " + str(assignee)})
        day = time.strftime("%Y%m%d")
        odir = os.path.join(ROOT, "orders")
        os.makedirs(odir, exist_ok=True)
        oid = None
        for n in range(1, 1000):
            cand = "ord-%s-%03d" % (day, n)
            if not os.path.exists(os.path.join(odir, cand)):
                oid = cand
                break
        if not oid:
            return self._json(503, {"error": "order book full for today"})
        d = os.path.join(odir, oid)
        os.makedirs(d)
        meta = {"id": oid, "assignee": assignee,
                "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "status": "consulting", "answers": {}, "files": {}}
        self._order_save_meta(d, meta)
        print("order create %s (%s)" % (oid, assignee), flush=True)
        return self._json(201, meta)

    def _api_order_get(self, oid):
        d = self._order_dir(oid)
        if not d:
            return self._json(404, {"error": "no such order"})
        meta = self._order_meta(d)
        turns = self._transcript_turns(d)
        meta["transcript"] = [{"user": turns[i]["content"],
                               "reply": turns[i + 1]["content"]
                               if i + 1 < len(turns)
                               and turns[i + 1]["role"] == "assistant" else ""}
                              for i in range(0, len(turns), 2)
                              if turns[i]["role"] == "user"]
        return self._json(200, meta)

    def _api_version(self):
        """Code version: commit hash + start time. ?client=<hash> adds a
        stale verdict: true only when the server is strictly older."""
        qs = unquote(self.path).split("?", 1)
        client = ""
        if len(qs) > 1:
            client = dict(parse_qsl(qs[1])).get("client", "")
        stale = bool(re.fullmatch(r"[0-9a-f]{7,40}", client or "")
                     and SERVER_COMMIT != "unknown"
                     and client != SERVER_COMMIT
                     and not _is_ancestor(client, SERVER_COMMIT))
        return self._json(200, {"commit": SERVER_COMMIT,
                                "started_at": SERVER_STARTED,
                                "stale": stale})

    def _api_ref(self):
        """open_ref stub: citation links point here until the PCs exist."""
        qs = unquote(self.path).split("?", 1)
        ref = ""
        if len(qs) > 1:
            ref = dict(parse_qsl(qs[1])).get("ref", "")
        return self._json(501, {"error": "PCs not built yet; cannot open %r"
                                         % (ref or "this ref",)})

    def _api_order_upload(self, oid):
        d = self._order_dir(oid)
        if not d:
            return self._json(404, {"error": "no such order"})
        _, files = parse_multipart(self)
        if not files or "file" not in files:
            return self._json(400, {"error": "need multipart field 'file'"})
        raw_name, raw = files["file"]
        base = os.path.basename(raw_name)
        if not base.lower().endswith(".pdf"):
            return self._json(400, {"error": "accepts .pdf only"})
        if len(raw) > MAX_PDF_BYTES:
            return self._json(400, {"error": "PDF over 25 MB"})
        with open(os.path.join(d, "source.pdf"), "wb") as f:
            f.write(raw)
        try:
            pages, images = pdf_parse(raw)
        except RuntimeError as e:
            return self._json(500, {"error": str(e)})
        except Exception as exc:  # noqa: BLE001 - broken PDF, reported
            return self._json(400, {"error": "cannot parse PDF: %s" % exc})
        text = "\n\n".join(pages)
        if not text.strip():
            return self._json(400, {"error": "no extractable text in PDF"})
        parsed = ["# Parsed source: %s" % base, ""]
        for i, p in enumerate(pages):
            parsed += ["## Page %d" % (i + 1), "", p.strip(), ""]
        with open(os.path.join(d, "parsed.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(parsed))
        imgdir = os.path.join(d, "images")
        os.makedirs(imgdir, exist_ok=True)
        for name, blob in images:
            with open(os.path.join(imgdir, name), "wb") as f:
                f.write(blob)
        meta = self._order_meta(d)
        meta["files"] = {"source": "source.pdf", "parsed": "parsed.md",
                         "images": ["images/" + n for n, _ in images],
                         "pages": len(pages)}
        self._order_save_meta(d, meta)
        print("order upload %s/%s (%d pages, %d chars, %d images)"
              % (oid, base, len(pages), len(text), len(images)), flush=True)
        return self._json(200, {"ok": True, "pages": len(pages),
                                "chars": len(text), "images": len(images)})

    def _api_order_intake(self, oid):
        d = self._order_dir(oid)
        if not d:
            return self._json(404, {"error": "no such order"})
        body = self._read_json()
        answers = body.get("answers") if isinstance(body, dict) else None
        if not isinstance(answers, dict):
            return self._json(400, {"error": "need {answers: {...}}"})
        clean = {}
        for k in INTAKE_KEYS:
            v = answers.get(k)
            if not isinstance(v, str) or not v.strip() or len(v) > 500:
                return self._json(400, {"error":
                    "answers.%s must be 1-500 chars" % k})
            clean[k] = v.strip()
        meta = self._order_meta(d)
        meta["answers"] = clean
        self._order_save_meta(d, meta)
        print("order intake %s" % oid, flush=True)
        return self._json(200, {"ok": True, "answers": clean})

    def _api_order_chat(self, oid):
        d = self._order_dir(oid)
        if not d:
            return self._json(404, {"error": "no such order"})
        body = self._read_json()
        msgs = self._check_messages(body)
        if msgs is None:
            return self._json(400, {"error":
                "need {messages: [{role, content}*]} (<=2000 chars each)"})
        meta = self._order_meta(d)
        free = isinstance(body, dict) and body.get("mode") == "free"
        path = self._employee(meta["assignee"])
        agent = self._load_agent(path)
        with open(os.path.join(path, "persona.md"), encoding="utf-8") as f:
            persona = f.read()
        if not runner.key_present(agent["model"]):
            return self._json(503, {"error": "%s missing: add it to .env"
                                    % runner.key_var(agent["model"])})
        try:
            extra = msgs[-1]["content"] if msgs[-1]["role"] == "user" else ""
            self._try_fill_answers(d, meta, extra)
        except RuntimeError:
            pass  # extraction failed: readiness stays false, chat goes on
        missing = intake.missing_of(meta.get("answers", {}),
                                    meta.get("files", {}))
        ready = not missing
        answers = meta.get("answers", {})
        recorded = ("; ".join("%s is %s" % (k, answers[k])
                              for k in INTAKE_KEYS if k in answers)
                    or "none yet")
        context = ["[ORDER CONSULTATION for %s. Recorded answers: %s."
                   % (oid, recorded)]
        if ready:
            context.append("You now have everything (all answers + source "
                           "PDF). Reply with one short acknowledgement "
                           "sentence only and ask no follow-up question: "
                           "the system appends the confirmation question.")
        else:
            context.append("Still missing: %s. Steer the chat toward them, "
                           "one question at a time." % ", ".join(missing))
        parsed = os.path.join(d, "parsed.md")
        if os.path.isfile(parsed):
            with open(parsed, encoding="utf-8") as f:
                context.append("Parsed source head:\n" + f.read(1500))
        hints = self._handbook_hints(path, msgs[-1]["content"])
        if hints:
            context.append("Handbook examples for this topic (follow their "
                           "style when the client is vague; never present "
                           "an example as the client's own words):\n" + hints)
        if free:
            context.append("Free-chat mode: converse naturally like a friendly "
                           "sales call, but still cover every missing topic "
                           "before the client is done.")
        system = (persona + "\n\n" + "\n".join(context)
                  + "\nAlways reply in English only: never Korean or any other "
                  "language, no matter what language the user writes in. "
                  "Never promise to start production or claim anything "
                  "has started. "
                  "Keep replies to 1-3 short sentences. "
                  "Reply in plain conversational sentences only: never "
                  "output JSON, code, or tool calls.")
        try:
            tail = [msgs[-1]] if msgs[-1]["role"] == "user" else msgs
            resp = runner._chat(
                agent["model"],
                [{"role": "system", "content": system}]
                + self._transcript_turns(d) + tail,
                None, timeout=120)
            reply = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
            if not isinstance(reply, str) or not reply.strip():
                raise ValueError("empty reply")
        except Exception as exc:  # noqa: BLE001 - surfaced as 502, key never leaks
            return self._json(502, {"error": "model API error: %s" % exc})
        text = reply.strip()
        if ready:
            text = text + " " + intake.READY_QUESTION
        self._chat_append(d, msgs[-1]["content"], text)
        return self._json(200, {"reply": text, "ready": ready})

    @staticmethod
    def _chat_append(d, user, reply):
        with open(os.path.join(d, "chat.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"user": user, "reply": reply},
                               ensure_ascii=False) + "\n")

    def _api_order_complete(self, oid):
        d = self._order_dir(oid)
        if not d:
            return self._json(404, {"error": "no such order"})
        code, obj = self._do_complete(oid, d, self._order_meta(d),
                                      self._read_json(), "complete")
        return self._json(code, obj)

    def _api_order_approve(self, oid):
        d = self._order_dir(oid)
        if not d:
            return self._json(404, {"error": "no such order"})
        body = self._read_json()
        if not isinstance(body, dict) or body.get("approved") is not True:
            return self._json(400, {"error": "need {approved: true}"})
        meta = self._order_meta(d)
        meta["approved"] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "answers": dict(meta.get("answers", {}))}
        self._order_save_meta(d, meta)
        print("order approve %s" % oid, flush=True)
        return self._json(200, {"ok": True, "approved": True})

    def _api_order_start(self, oid):
        d = self._order_dir(oid)
        if not d:
            return self._json(404, {"error": "no such order"})
        meta = self._order_meta(d)
        if not meta.get("approved"):
            return self._json(409, {"error": "not approved yet"})
        code, obj = self._do_complete(oid, d, meta, self._read_json(),
                                      "in_production")
        return self._json(code, obj)

    def _api_order_confirm(self, oid):
        d = self._order_dir(oid)
        if not d:
            return self._json(404, {"error": "no such order"})
        body = self._read_json()
        if not isinstance(body, dict) or not isinstance(body.get("confirm"),
                                                       bool):
            return self._json(400, {"error": "need {confirm: true|false}"})
        meta = self._order_meta(d)
        if body["confirm"] is False:
            self._chat_append(d, intake.NO_LINE, intake.DECLINE_ACK)
            return self._json(200, {"ok": True, "declined": True,
                                    "reply": intake.DECLINE_ACK})
        if meta.get("status") in ("complete", "in_production"):
            return self._json(409, {"error": "already started"})
        try:
            self._try_fill_answers(d, meta)
        except RuntimeError as exc:
            return self._json(502, {"error": str(exc)})
        missing = intake.missing_of(meta.get("answers", {}),
                                    meta.get("files", {}))
        if missing:
            return self._json(409, {"error": "intake incomplete",
                                    "missing": missing})
        try:
            with open(os.path.join(d, "parsed.md"),
                      encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return self._json(409, {"error": "no parsed PDF yet"})
        md, heads = intake.build_sections(text)
        with open(os.path.join(d, "sections.md"), "w",
                  encoding="utf-8") as f:
            f.write(md)
        files = dict(meta.get("files", {}))
        files["sections"] = "sections.md"
        files["section_count"] = len(heads)
        meta["files"] = files
        meta["approved"] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "answers": dict(meta.get("answers", {})),
                            "via": "chat"}
        self._order_save_meta(d, meta)
        self._chat_append(d, intake.YES_LINE, intake.START_LINE)
        print("order confirm %s (%d sections)" % (oid, len(heads)),
              flush=True)
        return self._json(200, {"ok": True, "answers": meta["answers"],
                                "reply": intake.START_LINE,
                                "sections": {"file": "sections.md",
                                             "count": len(heads),
                                             "headings": heads[:20]}})

    def _do_complete(self, oid, d, meta, body, final_status):
        """Shared consultation pipeline. Returns (code, obj)."""
        if meta.get("status") in ("complete", "in_production"):
            with open(os.path.join(d, "report.md"), encoding="utf-8") as f:
                md = f.read()
            with open(os.path.join(d, "intake.json"), encoding="utf-8") as f:
                intake = json.load(f)
            return (200, {"ok": True, "repeated": True, "intake": intake,
                          "report_md": md,
                          "files": ["intake.json", "result.json",
                                    "report.md"]})
        if isinstance(body, dict) and body.get("extract"):
            problem = self._extract_intake(d, meta)
            if problem:
                return problem
        missing = [k for k in INTAKE_KEYS if k not in meta.get("answers", {})]
        if missing:
            return (409, {"error": "intake incomplete", "missing": missing})
        if not meta.get("files", {}).get("parsed"):
            return (409, {"error": "no parsed PDF yet"})
        agent_dir = self._employee(meta["assignee"])
        run_model = self._load_agent(agent_dir)["model"]
        if not runner.key_present(run_model):
            return (503, {"error": "%s missing: add it to .env"
                          % runner.key_var(run_model)})
        brief = {"order_id": oid, "answers": meta["answers"],
                 "source_file": meta["files"].get("source", "source.pdf")}
        run_dir = os.path.join(ROOT, "output", "runs", oid)
        result = runner.run(agent_dir, run_dir, brief,
                            os.path.join(d, "parsed.md"))
        if not result.get("ok"):
            reason = "unknown"
            for ev in reversed(result.get("events", [])):
                if ev.get("ev") == "run_fail":
                    reason = ev.get("reason", reason)
                    break
            return (502, {"error": "sales run failed: " + reason,
                          "usage": result.get("usage")})
        for fn in ("result.json", "report.md"):
            shutil.copyfile(os.path.join(run_dir, fn), os.path.join(d, fn))
        intake = {"order_id": oid,
                  "answers": dict(meta["answers"],
                                  source=meta["files"].get("source",
                                                           "source.pdf")),
                  "files": {"source": meta["files"].get("source"),
                            "parsed": meta["files"].get("parsed"),
                            "sections": meta["files"].get("sections"),
                            "images": meta["files"].get("images", [])}}
        with open(os.path.join(d, "intake.json"), "w", encoding="utf-8") as f:
            json.dump(intake, f, ensure_ascii=False, indent=2)
        meta["status"] = final_status
        self._order_save_meta(d, meta)
        with open(os.path.join(d, "report.md"), encoding="utf-8") as f:
            md = f.read()
        print("order %s %s (%s)"
              % ("start" if final_status == "in_production" else "complete",
                 oid, result.get("usage")), flush=True)
        return (200, {"ok": True, "intake": intake, "report_md": md,
                      "files": ["intake.json", "result.json", "report.md"],
                      "usage": result.get("usage")})

    def _try_fill_answers(self, d, meta, extra=""):
        """Best-effort fill of meta["answers"] from the chat, one LLM call.

        Returns (missing_keys, client_lines). Raises RuntimeError when the
        extraction call itself fails (missing key, bad reply)."""
        missing = [k for k in INTAKE_KEYS
                   if k not in meta.get("answers", {})]
        if not missing:
            return [], 0
        lines = []
        chat = os.path.join(d, "chat.jsonl")
        if os.path.isfile(chat):
            with open(chat, encoding="utf-8") as f:
                for ln in f.read().splitlines():
                    try:
                        turn = json.loads(ln)
                    except ValueError:
                        continue
                    if turn.get("user"):
                        lines.append("Client: " + turn["user"])
        if extra:
            lines.append("Client: " + extra)
        if not lines:
            return missing, 0
        agent = self._load_agent(self._employee(meta["assignee"]))
        if not runner.key_present(agent["model"]):
            raise RuntimeError("%s missing: add it to .env"
                               % runner.key_var(agent["model"]))
        prompt = ("Extract the client's video-order answers from this sales "
                  "consultation. Reply with ONLY a JSON object, no other text:\n"
                  '{"audience": "..."|null, "length": "..."|null, '
                  '"depth": "..."|null, "theme": "..."|null}\n'
                  "Use null for anything the client never stated. "
                  "English values, one line each.\n\nTRANSCRIPT:\n"
                  + "\n".join(lines))
        try:
            resp = runner._chat(agent["model"],
                                [{"role": "user", "content": prompt}],
                                None, timeout=120)
            text = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
            obj, status = runner.parse_json_answer(text or "")
            if status != "ok" or not isinstance(obj, dict):
                raise ValueError("no JSON in extraction reply")
        except Exception as exc:  # noqa: BLE001 - surfaced, key never leaks
            raise RuntimeError("answer extraction failed: %s" % exc)
        answers = dict(meta.get("answers", {}))
        for k in INTAKE_KEYS:
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                answers[k] = v.strip()[:500]
        meta["answers"] = answers
        self._order_save_meta(d, meta)
        missing = [k for k in INTAKE_KEYS if k not in answers]
        return missing, len(lines)

    def _extract_intake(self, d, meta):
        """Complete/start path: fill answers, else (code, obj) to send."""
        try:
            missing, nlines = self._try_fill_answers(d, meta)
        except RuntimeError as exc:
            msg = str(exc)
            if msg.endswith("add it to .env"):
                return (503, {"error": msg})
            return (502, {"error": msg})
        if missing:
            tip = ("chat first: no conversation to extract from"
                   if not nlines else
                   "keep chatting about: " + ", ".join(missing))
            return (409, {"error": "intake incomplete", "missing": missing,
                          "tip": tip})
        return None

    # ---- PC fleet registry ----
    def _pcs_path(self):
        p = os.path.join(ROOT, "data", "pcs.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if not os.path.isfile(p):
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"pcs": []}, f, ensure_ascii=False, indent=2)
        return p

    def _pcs_load(self):
        with open(self._pcs_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data.get("pcs", []) if isinstance(data, dict) else []

    def _api_pcs_list(self):
        return self._json(200, {"pcs": self._pcs_load()})

    def _api_pcs_add(self):
        body = self._read_json()
        if not isinstance(body, dict):
            return self._json(400, {"error": "need JSON object"})
        name = (body.get("name") or "").strip()
        if not name or len(name) > 64:
            return self._json(400, {"error": "name must be 1-64 chars"})
        pid = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        if not PC_ID_RE.match(pid or ""):
            return self._json(400, {"error": "name yields no valid id"})
        pcs = self._pcs_load()
        if any(p.get("id") == pid for p in pcs):
            return self._json(409, {"error": "PC exists: " + pid})
        mats = body.get("materials") or []
        if (not isinstance(mats, list)
                or any(not isinstance(m, str) for m in mats)):
            return self._json(400, {"error": "materials must be a string list"})
        pc = {"id": pid, "name": name,
              "materials": [m.strip() for m in mats if m.strip()],
              "owner": (body.get("owner") or "studio").strip() or "studio",
              "capability": (body.get("capability") or "").strip(),
              "tool": (body.get("tool") or "").strip(),
              "state": "planned"}
        pcs.append(pc)
        with open(self._pcs_path(), "w", encoding="utf-8") as f:
            json.dump({"pcs": pcs}, f, ensure_ascii=False, indent=2)
        print("pc add %s" % pid, flush=True)
        return self._json(201, {"ok": True, "id": pid})

    def _api_pcs_delete(self, pid):
        if not PC_ID_RE.match(pid or ""):
            return self._json(404, {"error": "no such PC"})
        pcs = self._pcs_load()
        keep = [p for p in pcs if p.get("id") != pid]
        if len(keep) == len(pcs):
            return self._json(404, {"error": "no such PC"})
        with open(self._pcs_path(), "w", encoding="utf-8") as f:
            json.dump({"pcs": keep}, f, ensure_ascii=False, indent=2)
        print("pc delete %s" % pid, flush=True)
        return self._json(200, {"ok": True, "deleted": pid})

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
        print("Shoestring Studios at http://localhost:%d (code %s)"
              % (port, SERVER_COMMIT[:12]), flush=True)
        server.serve_forever()
        return
    raise SystemExit("no free port %d-%d: %s"
                     % (args.port, args.port + 5, last))


if __name__ == "__main__":
    main()
