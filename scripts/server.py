"""Shoestring Studios backend (stdlib only).

Serves the homepage + JSON API for crew management. No opaque background
work: every mutation returns what changed, and runs stay inspectable.
Run:   python scripts/server.py [--port 8000]
Open:  http://localhost:8000
"""
import argparse
import html
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

from agents._frame import board  # noqa: E402
from agents._frame import flow as flows  # noqa: E402
from agents._frame import projlog  # noqa: E402
from agents._frame import office as liveoffice  # noqa: E402
from agents._frame import memory as memstore  # noqa: E402
from agents._frame import graph  # noqa: E402
from agents._frame import pdfingest  # noqa: E402
from agents._frame import runner  # noqa: E402
from agents._frame import tools as registry  # noqa: E402
import validate_agent  # noqa: E402
import intake  # noqa: E402
from agents._frame import pc  # noqa: E402
from agents._frame import gallery  # noqa: E402
from agents._frame import profiles  # noqa: E402

ALLOWED_UPLOAD = (".md", ".txt", ".pdf")

ORDER_ID_RE = re.compile(r"^ord-[0-9]{8}-[0-9]{3}$")
INTAKE_KEYS = intake.INTAKE_KEYS
PC_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
MAX_PDF_BYTES = 25 * 1024 * 1024

_PC_JOBS = {}  # doc_id -> Popen of a running pc_worker.py build
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
        if parts[:2] == ["api", "crew"] and len(parts) == 4 and parts[3] == "start-prompt":
            return self._api_start_prompt(parts[2])
        if parts[:2] == ["api", "orders"] and len(parts) == 2:
            return self._api_orders_list()
        if parts[:2] == ["api", "orders"] and len(parts) == 3:
            return self._api_order_get(parts[2])
        if parts[:2] == ["api", "orders"] and len(parts) == 4 \
                and parts[3] == "projectlog":
            return self._api_order_projectlog(parts[2])
        if parts[:2] == ["api", "orders"] and len(parts) == 4 \
                and parts[3] == "progress":
            return self._api_order_progress(parts[2])
        if parts[:2] == ["api", "gallery"] and len(parts) == 2:
            return self._api_gallery_list()
        if parts[:2] == ["api", "ref"] and len(parts) == 2:
            return self._api_ref()
        if parts[:2] == ["api", "pcs"] and len(parts) == 2:
            return self._api_pcs_list()
        if parts[:2] == ["api", "pcs"] and len(parts) == 3 \
                and parts[2] == "rights":
            return self._api_pcs_rights()
        if parts[:2] == ["api", "pcs"] and len(parts) == 4 \
                and parts[3] == "entries":
            return self._api_pc_entries(parts[2])
        if parts[:2] == ["api", "pcs"] and len(parts) == 5 \
                and parts[3] == "entries":
            return self._api_pc_entry(parts[2], parts[4])
        if parts[:2] == ["api", "pcs"] and len(parts) == 7 \
                and parts[3] == "entries" and parts[5] == "figures":
            return self._api_pc_figure(parts[2], parts[4], parts[6])
        if parts[:2] == ["api", "pcs"] and len(parts) == 7 \
                and parts[3] == "entries" and parts[5] == "media":
            return self._api_pc_media(parts[2], parts[4], parts[6])
        if parts[:2] == ["api", "pcs"] and len(parts) == 6 \
                and parts[3] == "entries" and parts[5] == "picks":
            return self._api_pc_entry_picks(parts[2], parts[4])
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
        if parts[:2] == ["api", "flows"] and len(parts) == 5 \
                and parts[2] == "runs" and parts[4] == "status":
            return self._api_flow_step_status(parts[3])
        if parts[:2] == ["api", "flows"] and len(parts) == 5 \
                and parts[2] == "runs" and parts[4] == "file":
            return self._api_flow_file(parts[3])
        if parts[:2] == ["api", "flows"] and len(parts) == 5 \
                and parts[2] == "runs" and parts[4] == "board":
            return self._api_flow_board(parts[3])
        if parts[:2] == ["api", "flows"] and len(parts) == 5 \
                and parts[2] == "runs" and parts[4] == "verify":
            return self._api_flow_verify(parts[3])
        if parts[:2] == ["api", "flows"] and len(parts) == 5 \
                and parts[2] == "runs" and parts[4] == "files":
            return self._api_flow_files(parts[3])
        if parts[:2] == ["api", "flows"] and len(parts) == 5 \
                and parts[2] == "runs" and parts[4] == "state":
            return self._api_flow_run_state(parts[3])
        if parts[:2] == ["api", "flows"] and len(parts) == 5 \
                and parts[2] == "runs" and parts[4] == "office":
            return self._api_flow_office(parts[3])
        if parts[:2] == ["api", "flows"] and len(parts) == 5 \
                and parts[2] == "runs" and parts[4] == "memory":
            return self._api_run_memory(parts[3])
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
        if parts[:2] == ["api", "pcs"] and len(parts) == 6 \
                and parts[3] == "entries" and parts[5] == "build":
            return self._api_pc_build(parts[2], parts[4])
        if parts[:2] == ["api", "pcs"] and len(parts) == 6 \
                and parts[3] == "entries" and parts[5] == "index":
            return self._api_pc_index(parts[2], parts[4])
        if parts[:2] == ["api", "settings"] and len(parts) == 2:
            return self._api_settings_save()
        if parts[:2] == ["api", "settings"] and len(parts) == 3 \
                and parts[2] == "test":
            return self._api_settings_test()

        if parts[:2] == ["api", "flows"] and len(parts) == 3:
            if parts[2] == "validate":
                return self._api_flow_validate()
            return self._api_flow_save(parts[2])
        if parts[:2] == ["api", "flows"] and len(parts) == 4 \
                and parts[3] == "run":
            return self._api_flow_run(parts[2])
        if parts[:2] == ["api", "flows"] and len(parts) == 4 \
                and parts[3] == "step":
            return self._api_flow_step(parts[2])
        if parts[:2] == ["api", "flows"] and len(parts) == 5 \
                and parts[2] == "runs" and parts[4] == "approve":
            return self._api_flow_approve(parts[3])
        if parts[:2] == ["api", "flows"] and len(parts) == 5 \
                and parts[2] == "runs" and parts[4] == "invalidate":
            return self._api_flow_invalidate(parts[3])
        if parts[:2] == ["api", "flows"] and len(parts) == 5 \
                and parts[2] == "runs" and parts[4] == "stop":
            return self._api_flow_stop(parts[3])
        if parts[:2] == ["api", "flows"] and len(parts) == 5 \
                and parts[2] == "runs" and parts[4] in (
                    "pause", "resume", "step"):
            return self._api_flow_ctl(parts[3], parts[4])
        if parts[:2] == ["api", "flows"] and len(parts) == 5 \
                and parts[2] == "runs" and parts[4] == "control":
            return self._api_flow_control(parts[3])
        if parts[:2] == ["api", "flows"] and len(parts) == 6 \
                and parts[2] == "runs" and parts[4] == "memory":
            return self._api_run_memory_retry(parts[3], parts[5])
        if parts[:2] == ["api", "flows"] and len(parts) == 5 \
                and parts[2] == "runs" and parts[4] == "close":
            return self._api_run_close(parts[3])
        if parts[:2] == ["api", "orders"] and len(parts) == 4 \
                and parts[3] == "close":
            return self._api_order_close(parts[2])
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
                        "stage": agent.get("stage"),
                        "team": agent.get("team"),
                        "title": agent["title"], "model": agent["model"],
                        "tools": agent["tools"],
                        "appearance": self._appearance(path),
                        "graph": graph.get_status(path)["state"]})
            out.sort(key=lambda c: (c.get("stage") if isinstance(c.get("stage"), int) else 99, c["id"]))
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
            "team": agent.get("team"),
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
        changed = [k for k in ("name", "title", "model", "team", "tools",
                               "bounds", "done", "persona",
                               "appearance") if k in body]
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
        if "team" in body:
            prof_names = {}
            for _eid in sorted(os.listdir(os.path.join(ROOT, "agents"))):
                _jp = os.path.join(ROOT, "agents", _eid, "agent.json")
                if os.path.isfile(_jp):
                    try:
                        with open(_jp, encoding="utf-8") as _f:
                            prof_names[_eid] = json.load(_f).get(
                                "name", _eid)
                    except ValueError:
                        continue
            with open(os.path.join(path, "profile.md"), "w",
                      encoding="utf-8") as f:
                f.write(profiles.build_profile(
                    path,
                    os.path.join(ROOT, "data", "flows", "default.json"),
                    prof_names))
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
        if "team" in body:
            if body["team"] not in ("story", "video", "", None):
                return "team must be story, video or empty"
            if body["team"]:
                agent["team"] = body["team"]
            elif "team" in agent:
                del agent["team"]
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
        team = body.get("team") or ""
        if team not in ("story", "video"):
            return self._json(400, {"error": "team is required: story or video"})
        path = os.path.join(ROOT, "agents", eid)
        if os.path.exists(path):
            return self._json(409, {"error": "employee exists: " + eid})
        model = body.get("model") or "meta-models/muse-spark-open-1026"
        os.makedirs(os.path.join(path, "handbook"))
        agent = {"frame_version": 1, "id": eid, "name": name, "title": title,
                 "team": team,
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
        prof_names = {}
        for _eid in sorted(os.listdir(os.path.join(ROOT, "agents"))):
            _jp = os.path.join(ROOT, "agents", _eid, "agent.json")
            if os.path.isfile(_jp):
                try:
                    with open(_jp, encoding="utf-8") as _f:
                        prof_names[_eid] = json.load(_f).get(
                            "name", _eid)
                except ValueError:
                    continue
        with open(os.path.join(path, "profile.md"), "w",
                  encoding="utf-8") as f:
            f.write(profiles.build_profile(
                path,
                os.path.join(ROOT, "data", "flows", "default.json"),
                prof_names))
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
                text = pdfingest.pdf_to_text(raw)
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
        try:
            system_base = profiles.system_base(path)
        except OSError as exc:
            return self._json(500, {"error": "bad prompt files: %s"
                                             % exc})
        mem_ctx, note, mem_badge = "", "", "none"
        run_id = body.get("run_id") if isinstance(body, dict) else ""
        if run_id:
            last_q = ""
            for m in reversed(msgs):
                if m.get("role") == "user":
                    last_q = m["content"]
                    break
            code, obj, mem_ctx, note = self._memory_gate(
                eid, run_id, last_q)
            if code != 200:
                return self._json(code, obj)
            mem_badge = obj.get("memory", "none")
        if not runner.key_present(agent["model"]):
            return self._json(503, {"error": "%s missing: add it to .env"
                                    % runner.key_var(agent["model"])})
        system = (system_base + "\n\n[LIVE CHAT — reply in English as %s, %s. "
                  "Always reply in English only: never Korean or any other "
                  "language, no matter what language the user writes in. "
                  "Keep replies to 1-3 short sentences. Stay in character; "
                  "you work at Shoestring Studios.]"
                  % (agent["name"], agent["title"]))
        if mem_badge == "ready" and mem_ctx:
            system += ("\n\n[PROJECT MEMORY — run %s. Answer ONLY "
                       "from this memory about THIS project: what you "
                       "received, decided and why, sources and "
                       "licenses used. If it is not in the memory, say "
                       "you don't know. 1-4 sentences, no JSON, no "
                       "tool calls, no promises to change results "
                       "(changes go through Re-run with note).]\n%s"
                       % (run_id, mem_ctx[:4000]))
        elif run_id and mem_badge != "ready":
            system += ("\n\n[PROJECT MEMORY — run %s: UNAVAILABLE. "
                       "You may still answer interview questions about "
                       "YOURSELF (who you are, your job, team, duties, "
                       "tools, who you work with) from the profile card "
                       "above. If asked anything about the project — "
                       "what you received, decided, or used — reply "
                       "with EXACTLY this sentence and nothing else: "
                       "\"%s\"]" % (run_id, note))
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

    # ---- project memories (item 9) ----
    def _run_dir(self, rid):
        if not self._run_id_ok(rid):
            return None
        d = os.path.join(flows.RUNS_DIR, rid)
        return d if os.path.isdir(d) else None

    def _api_run_memory(self, rid):
        if not self._run_dir(rid):
            return self._json(404, {"error": "no such run"})
        return self._json(200, {
            "run_id": rid,
            "closed": memstore.is_closed(rid, flows.RUNS_DIR),
            "agents": memstore.run_memory_states(
                rid, flows.RUNS_DIR)})

    def _api_run_memory_retry(self, rid, agent):
        if not self._run_dir(rid):
            return self._json(404, {"error": "no such run"})
        if not self._employee(agent):
            return self._json(404, {"error": "no such employee"})
        if memstore.is_closed(rid, flows.RUNS_DIR):
            return self._json(409, {"error": "project closed"})
        if memstore._INDEXER is None:
            return self._json(503, {"error": "memory indexer "
                                             "not configured"})
        out = memstore.queue_build(
            rid, agent,
            memstore.default_docs_fn(rid, agent, flows.RUNS_DIR),
            runs_root=flows.RUNS_DIR)
        if not out.get("ok"):
            return self._json(409, out)
        oid = self._order_of_run(rid)
        if oid:
            projlog.log_owner(oid, rid, "memory_retry", agent)
        return self._json(202, out)

    def _order_of_run(self, rid):
        try:
            with open(os.path.join(flows.RUNS_DIR, rid,
                                   "STATUS.json"),
                      encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, ValueError):
            return ""
        return st.get("order_id", "") if isinstance(st, dict) \
            else ""

    def _runs_for_order(self, oid):
        rdir = flows.RUNS_DIR
        out = []
        if not os.path.isdir(rdir):
            return out
        for n in sorted(os.listdir(rdir)):
            if os.path.isdir(os.path.join(rdir, n)) \
                    and self._order_of_run(n) == oid:
                out.append(n)
        return out

    def _api_run_close(self, rid):
        if not self._run_dir(rid):
            return self._json(404, {"error": "no such run"})
        gone = memstore.close_run_memory(rid, flows.RUNS_DIR)
        oid = self._order_of_run(rid)
        if oid:
            d = self._order_dir(oid)
            if d:
                meta = self._order_meta(d)
                meta["closed"] = True
                self._order_save_meta(d, meta)
        print("run %s closed (memory deleted: %s)" % (rid, gone),
              flush=True)
        if oid:
            projlog.log_owner(oid, rid, "close",
                              summary="project closed",
                              file="runs/%s/MEMORY_CLOSED.json"
                              % rid)
            projlog.do_refresh(oid)
        return self._json(200, {"ok": True, "run_id": rid,
                                "order_id": oid,
                                "memory_deleted": gone})

    def _api_order_close(self, oid):
        d = self._order_dir(oid)
        if not d:
            return self._json(404, {"error": "no such order"})
        runs = self._runs_for_order(oid)
        for rid in runs:
            memstore.close_run_memory(rid, flows.RUNS_DIR)
        meta = self._order_meta(d)
        meta["closed"] = True
        self._order_save_meta(d, meta)
        print("order %s closed (%d runs)" % (oid, len(runs)),
              flush=True)
        projlog.log_owner(oid, "", "close",
                          summary="%d runs closed" % len(runs))
        projlog.do_refresh(oid)
        return self._json(200, {"ok": True, "order_id": oid,
                                "runs": runs})

    def _open_orders(self):
        odir = os.path.join(ROOT, "orders")
        out = []
        if not os.path.isdir(odir):
            return out
        for oid in sorted(os.listdir(odir)):
            d = os.path.join(odir, oid)
            mp = os.path.join(d, "meta.json")
            if not os.path.isfile(mp):
                continue
            try:
                with open(mp, encoding="utf-8") as f:
                    meta = json.load(f)
            except ValueError:
                continue
            if isinstance(meta, dict) \
                    and meta.get("status") in (
                        "complete", "in_production") \
                    and not meta.get("closed"):
                out.append(oid)
        return out

    def _memory_gate(self, eid, run_id, question):
        """Item 17 chat memory: interviews stay open without memory.

        Returns (code, obj, mem_ctx, note): 404 only for a bad run;
        otherwise 200 with mem_ctx ("" unless ready) and note (the
        exact no-memory sentence, "" when ready)."""
        if not self._run_dir(run_id):
            return (404, {"error": "no such run",
                          "memory": "none"}, "", "")
        if memstore.is_closed(run_id, flows.RUNS_DIR):
            return (200, {"memory": "closed"}, "",
                    profiles.refusal_for("closed"))
        st = memstore.memory_state(run_id, eid, flows.RUNS_DIR)
        if st["state"] == "building":
            return (200, {"memory": "building"}, "",
                    profiles.refusal_for("building"))
        if st["state"] == "failed":
            return (200, {"memory": "failed"}, "",
                    profiles.refusal_for("failed",
                                         st.get("error", "")))
        if st["state"] != "ready":
            return (200, {"memory": "not yet"}, "",
                    profiles.refusal_for("none"))
        try:
            ctx = memstore.query_memory(run_id, eid, question,
                                        flows.RUNS_DIR)
        except RuntimeError as exc:
            return (200, {"memory": "failed"}, "",
                    profiles.refusal_for("failed", str(exc)))
        return (200, {"memory": "ready"}, ctx, "")

    def _api_start_prompt(self, eid):
        """Preview the recipients-gated PC input preloaded for one
        crew member: the same shared builder a real run uses."""
        if eid not in ("explain_cleo", "case_rex", "plan_ash",
                       "pd_marty"):
            return self._json(404, {"error": "start prompts exist for "
                                             "Cleo, Rex, Marty and Ash only"})
        qs = unquote(self.path).split("?", 1)
        oid = dict(parse_qsl(qs[1])).get("order", "") if len(qs) > 1 else ""
        d = self._order_dir(oid)
        if not d:
            return self._json(404, {"error": "no such order"})
        meta = self._order_meta(d)
        refs = []
        sent = (meta.get("files") or {}).get("pc_ref", "")
        if sent:
            refs.append(sent)
        try:
            text, meta2 = pc.prompt_chunks_for(eid, oid, refs,
                                               flows.RUNS_DIR)
        except (OSError, ValueError) as exc:
            return self._json(409, {"error": str(exc)})
        if not meta2["included"]:
            if not refs and not pc.order_picks_with_reasons(
                    oid, flows.RUNS_DIR):
                return self._json(409, {"error": "order has no Source "
                                                 "entry yet: Sam sends it "
                                                 "after Yes"})
            return self._json(409, {"error": "no access to this order's "
                                             "items for %s" % eid,
                                    "denied": meta2["denied"]})
        return self._json(200, {"prompt": text, "chars": len(text),
                                "included": meta2["included"],
                                "denied": meta2["denied"],
                                "picks": meta2["picks"]})

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

    @staticmethod
    def _pc_entry_failed(edir):
        try:
            with open(os.path.join(edir, "log.jsonl"),
                      encoding="utf-8") as f:
                lines = f.read().splitlines()[-5:]
        except OSError:
            return False
        for ln in lines:
            try:
                ev = json.loads(ln)
            except ValueError:
                continue
            if ev.get("ev") in ("failed", "map_failed",
                                "index_failed") and ev.get("error"):
                return True
        return False

    def _pc_profile_cell(self, pcname, prof, entries):
        idx = os.path.join(pc.index_dir(pcname, prof), "index.json")
        mark = None
        try:
            with open(idx, encoding="utf-8") as f:
                mark = json.load(f)
        except (OSError, ValueError):
            mark = None
        indexed = set((mark or {}).get("entries", [])
                      if isinstance(mark, dict) else [])
        building, failed = False, False
        for doc_id in entries:
            job = _PC_JOBS.get(doc_id)
            if job is not None and job.poll() is None:
                building = True
            if doc_id not in indexed and self._pc_entry_failed(
                    os.path.join(pc.pc_dir(pcname), "entries",
                                 doc_id)):
                failed = True
        cell = {"built": bool(mark), "building": building,
                "failed": failed and not building,
                "entries_indexed": len(indexed & set(entries)),
                "entries_total": len(entries)}
        if isinstance(mark, dict):
            cell["model"] = mark.get("model", "")
            cell["dim"] = mark.get("dim", 0)
            cell["indexed_at"] = mark.get("indexed_at", "")
        return cell

    def _api_settings_get(self):
        mod = graph._adapter()
        eff = mod.resolved_settings()
        try:
            token_set = bool(mod.load_key("EMBED_REMOTE_TOKEN"))
        except RuntimeError:
            token_set = False
        self._pc_reap_finished()
        pcs_out = {}
        for pcname in ("source", "theory", "article"):
            ed = os.path.join(pc.pc_dir(pcname), "entries")
            entries = []
            if os.path.isdir(ed):
                for doc_id in sorted(os.listdir(ed)):
                    if re.fullmatch(r"[0-9a-f]{12}",
                                    doc_id or "") and os.path.isfile(
                            os.path.join(ed, doc_id,
                                         "entry.json")):
                        entries.append(doc_id)
            pcs_out[pcname] = {
                prof: self._pc_profile_cell(pcname, prof, entries)
                for prof in ("local", "jetson")}
        mem_out = []
        rdir = flows.RUNS_DIR
        if os.path.isdir(rdir):
            names = sorted(
                os.listdir(rdir),
                key=lambda n: os.path.getmtime(os.path.join(
                    rdir, n)), reverse=True)
            for n in names:
                if len(mem_out) >= 5:
                    break
                if not os.path.isdir(os.path.join(rdir, n)):
                    continue
                try:
                    with open(os.path.join(rdir, n, "STATUS.json"),
                              encoding="utf-8") as f:
                        st = json.load(f)
                except (OSError, ValueError):
                    continue
                if not isinstance(st, dict):
                    continue
                mem_out.append({
                    "run_id": n,
                    "order_id": st.get("order_id", ""),
                    "closed": memstore.is_closed(n, flows.RUNS_DIR),
                    "agents": memstore.run_memory_states(
                        n, flows.RUNS_DIR)})
        out = {"profile": eff["profile"], "jetson_url": eff["jetson_url"],
               "llm_model": eff["llm_model"], "query_mode": eff["query_mode"],
               "top_k": eff["top_k"], "chunk_local": eff["chunk_local"],
               "chunk_jetson": eff["chunk_jetson"],
               "office_fps": eff["office_fps"],
               "llm_models": [{"model": m,
                               "provider": runner.provider_of(m)[0]}
                              for m in runner.LLM_MODELS],
               "query_modes": list(mod.QUERY_MODES),
               "token_set": token_set, "pcs": pcs_out,
               "memories": mem_out}
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
                    "pc_lines": body.get("pc_lines", []),
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
        warns = flows.lint_flow(body)
        return self._json(200, {"ok": not errs, "errors": errs,
                                "warnings": warns})

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
        run_id = self._launch_flow_run(fid, flow_obj, order_id)
        return self._json(200, {"started": True, "run_id": run_id})

    def _launch_flow_run(self, fid, flow_obj, order_id):
        """Start a run_flow thread; returns run_id. Shared by the
        manual run endpoint and the post-Sam auto-start."""
        run_id = flows.new_run_id()
        job = {"run_id": run_id, "flow_id": fid, "order_id": order_id,
               "state": "running", "error": ""}
        _FLOW_JOBS[run_id] = job

        def _work():
            try:
                out = flows.run_flow(
                    flow_obj, order_id, runner.run,
                    run_id=run_id, flow_id=fid,
                    stop_check=lambda: job.get("stop", False))
                if out.get("ok"):
                    job["state"] = "done"
                elif str(out.get("error", "")).startswith(
                        "stopped:"):
                    job["state"] = "stopped"
                else:
                    job["state"] = "error"
                    job["error"] = str(out.get("error", ""))[:1000]
            except Exception as exc:  # noqa: BLE001 - status surface
                job["state"] = "error"
                job["error"] = str(exc)[:1000]

        threading.Thread(target=_work, daemon=True).start()
        return run_id

    def _api_flow_runs(self):
        runs = []
        rdir = flows.RUNS_DIR
        if os.path.isdir(rdir):
            names = sorted(
                os.listdir(rdir),
                key=lambda n: os.path.getmtime(os.path.join(rdir, n)),
                reverse=True)[:20]
            for n in names:
                if not os.path.isdir(os.path.join(rdir, n)):
                    continue
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
                if n in _FLOW_JOBS and _FLOW_JOBS[n]["state"] == "running" \
                        and st["state"] not in ("paused", "done",
                                                "stopped", "error",
                                                "failed"):
                    st["state"] = "running"
                if st["state"] == "failed":
                    st["state"] = "error"
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
        approved, last = [], ""
        if job is not None and job["state"] == "running":
            state, err = "running", ""
        else:
            state, err = "unknown", ""
            try:
                with open(os.path.join(rdir, "STATUS.json"),
                          encoding="utf-8") as f:
                    d = json.load(f)
                state, err = d.get("state", "unknown"), d.get("error", "")
                approved, last = d.get("approved", []), d.get("last", "")
            except (OSError, ValueError):
                pass
        out = {"run_id": run_id, "state": state, "events": events}
        if approved:
            out["approved"] = approved
        if last:
            out["last"] = last
        if err:
            out["error"] = err
        if job is not None:
            out["flow_id"] = job.get("flow_id", "")
            out["order_id"] = job.get("order_id", "")
        return self._json(200, out)

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
        if not body.get("force"):
            open_orders = self._open_orders()
            if open_orders:
                return self._json(200, {"created": False,
                                        "open_orders": open_orders})
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
        projlog.log_event(oid, "order", "created",
                          "order opened (%s)" % assignee,
                          file="orders/%s/meta.json" % oid)
        projlog.do_refresh(oid)
        return self._json(201, dict(meta, created=True))

    def _api_orders_list(self):
        odir = os.path.join(ROOT, "orders")
        out = []
        try:
            names = sorted(os.listdir(odir))
        except OSError:
            names = []
        for n in names:
            if not ORDER_ID_RE.match(n):
                continue
            d = os.path.join(odir, n)
            if not os.path.isdir(d):
                continue
            try:
                meta = self._order_meta(d)
            except (OSError, ValueError):
                continue
            if not isinstance(meta, dict):
                continue
            try:
                mtime = os.path.getmtime(
                    os.path.join(d, "meta.json"))
            except OSError:
                mtime = 0
            out.append({"id": n,
                        "status": meta.get("status", ""),
                        "closed": bool(meta.get("closed")),
                        "created": meta.get("created", ""),
                        "mtime": mtime})
        out.sort(key=lambda e: (e["created"], e["mtime"]),
                 reverse=True)
        for e in out:
            del e["mtime"]
        return self._json(200, {"orders": out})

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
        meta["missing"] = intake.missing_of(meta.get("answers", {}),
                                            meta.get("files", {}))
        meta["run_id"] = self._latest_run_for_order(oid)
        return self._json(200, meta)

    @staticmethod
    def _run_id_ok(run_id):
        return bool(run_id) and "/" not in run_id \
            and "\\" not in run_id \
            and not run_id.startswith(".")

    _PROJECTLOG_MIME = {"TIMELINE.md": "text/markdown",
                        "timeline.jsonl": "text/plain",
                        "LOG_INDEX.json": "application/json"}

    def _api_gallery_list(self):
        """One card per order with a video or storyboard table."""
        odir = os.path.join(ROOT, "orders")
        cards = gallery.gallery_cards(odir, flows.RUNS_DIR)
        return self._json(200, {"cards": cards})

    @staticmethod
    def _tail_jsonl(path, n):
        try:
            with open(path, encoding="utf-8") as f:
                rows = []
                for ln in f.read().splitlines()[-n:]:
                    try:
                        rows.append(json.loads(ln))
                    except ValueError:
                        continue
                return [r for r in rows if isinstance(r, dict)]
        except OSError:
            return []

    @staticmethod
    def _order_entry_log(oid):
        try:
            base = os.path.join(pc.pc_dir("source"), "entries")
            cands = []
            for doc_id in sorted(os.listdir(base)):
                p = os.path.join(base, doc_id, "entry.json")
                try:
                    with open(p, encoding="utf-8") as f:
                        e = json.load(f)
                except (OSError, ValueError):
                    continue
                if isinstance(e, dict) and e.get("order_id") == oid:
                    cands.append((os.path.getmtime(p),
                                  os.path.join(base, doc_id,
                                               "log.jsonl")))
            if not cands:
                return []
            cands.sort()
            return Handler._tail_jsonl(cands[-1][1], 60)
        except OSError:
            return []

    def _api_order_progress(self, oid):
        """Live start progress for the Order tab card (polled)."""
        d = self._order_dir(oid)
        if not d:
            return self._json(404, {"error": "no such order"})
        meta = self._order_meta(d)
        starting = meta.get("starting")
        starting = starting if isinstance(starting, dict) else None
        out = {"starting": bool(starting), "elapsed_s": 0,
               "lines": [], "failed": False, "reason": "",
               "status": meta.get("status", ""),
               "run_id": self._latest_run_for_order(oid)}
        if starting:
            try:
                t0 = time.mktime(time.strptime(
                    starting.get("at", ""), "%Y-%m-%dT%H:%M:%S"))
            except ValueError:
                t0 = time.time()
            out["elapsed_s"] = max(0, int(time.time() - t0))
            since = starting.get("at", "").replace("T", " ")
            tl = [r for r in self._tail_jsonl(
                      os.path.join(d, "timeline.jsonl"), 80)
                  if str(r.get("at", "")) >= since]
            el = self._order_entry_log(oid)
            lines, failed, reason = intake.progress_lines(tl, el)
            out.update({"lines": lines, "failed": failed,
                        "reason": reason})
        if not starting and meta.get("status") in intake.STARTED:
            try:
                with open(os.path.join(d, "start_result.json"),
                          encoding="utf-8") as f:
                    out["start_result"] = json.load(f)
            except (OSError, ValueError):
                pass
        return self._json(200, out)

    def _api_order_projectlog(self, oid):
        """Serve one project-log file (Board "Project log" link)."""
        qs = unquote(self.path).split("?", 1)
        q = dict(parse_qsl(qs[1])) if len(qs) > 1 else {}
        full = projlog.projectlog_path(oid, q.get("name", ""))
        if full is None:
            return self._json(404, {"error": "no such log"})
        with open(full, "rb") as f:
            data = f.read()
        if len(data) > 5242880:
            return self._json(413, {"error": "file too large"})
        self.send_response(200)
        self.send_header("Content-Type",
                         self._PROJECTLOG_MIME[q["name"]])
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _api_flow_step(self, fid):
        try:
            flow_obj = flows.load_flow(fid)
        except (ValueError, OSError):
            return self._json(404, {"error": "no such flow"})
        errs = flows.validate_flow(flow_obj)
        if errs:
            return self._json(400, {"error": "invalid flow",
                                    "errors": errs})
        body = self._read_json()
        if not isinstance(body, dict):
            return self._json(400, {"error": "need JSON object"})
        order_id = body.get("order_id")
        target = body.get("target")
        if not order_id or not isinstance(order_id, str):
            return self._json(400, {"error": "need {order_id}"})
        if not target or not isinstance(target, str):
            return self._json(400, {"error": "need {target}"})
        if not os.path.isfile(os.path.join(ROOT, "orders", order_id,
                                            "meta.json")):
            return self._json(404, {"error": "no such order"})
        run_id = body.get("run_id") or flows.new_run_id()
        if not self._run_id_ok(run_id):
            return self._json(400, {"error": "bad run_id"})
        note = body.get("note") or None
        job = {"run_id": run_id, "flow_id": fid, "order_id": order_id,
               "state": "running", "error": ""}
        _FLOW_JOBS[run_id] = job

        def _work():
            try:
                out = flows.step_run(
                    flow_obj, order_id, runner.run, target,
                    run_id=run_id, note=note, flow_id=fid,
                    stop_check=lambda: job.get("stop", False))
                job["state"] = "done"
                if not out.get("ok"):
                    if str(out.get("error", "")).startswith(
                            "stopped:"):
                        job["state"] = "stopped"
                    else:
                        job["state"] = "error"
                        job["error"] = str(out.get("error", ""))[:1000]
            except Exception as exc:  # noqa: BLE001 - status surface
                job["state"] = "error"
                job["error"] = str(exc)[:1000]

        threading.Thread(target=_work, daemon=True).start()
        projlog.log_owner(order_id, run_id, "step_to", target,
                          note or "to %s" % target)
        projlog.do_refresh(order_id)
        return self._json(200, {"started": True, "run_id": run_id})

    def _api_flow_approve(self, run_id):
        if not self._run_id_ok(run_id):
            return self._json(404, {"error": "no such run"})
        body = self._read_json()
        node = (body or {}).get("node") if isinstance(body, dict) \
            else None
        if not node or not isinstance(node, str):
            return self._json(400, {"error": "need {node}"})
        out = flows.approve_node(run_id, node)
        if not out.get("ok"):
            return self._json(400, out)
        return self._json(200, out)

    def _api_flow_invalidate(self, run_id):
        if not self._run_id_ok(run_id):
            return self._json(404, {"error": "no such run"})
        body = self._read_json()
        node = (body or {}).get("node") if isinstance(body, dict) \
            else None
        if not node or not isinstance(node, str):
            return self._json(400, {"error": "need {node}"})
        out = flows.invalidate_node(run_id, node)
        if not out.get("ok"):
            return self._json(400, out)
        return self._json(200, out)

    def _api_flow_stop(self, run_id):
        if not self._run_id_ok(run_id):
            return self._json(404, {"error": "no such run"})
        body = self._read_json()
        node = (body or {}).get("node") if isinstance(body, dict) \
            else None
        if node is not None and not isinstance(node, str):
            return self._json(400, {"error": "node must be a string"})
        job = _FLOW_JOBS.get(run_id)
        if job is not None and job.get("state") == "running":
            job["stop"] = True
            ctl = flows.ctl_stop(run_id, True)
            return self._json(200, {"ok": True, "run_id": run_id,
                                    "state": "stopping",
                                    "control": ctl.get("state",
                                                       "")})
        out = flows.stop_run(run_id, node)
        if not out.get("ok"):
            return self._json(400, out)
        return self._json(200, out)

    def _api_flow_step_status(self, run_id):
        if not self._run_id_ok(run_id):
            return self._json(404, {"error": "no such run"})
        out = flows.step_status(run_id)
        if not out.get("ok"):
            return self._json(404, out)
        return self._json(200, out)

    def _run_live(self, run_id):
        job = _FLOW_JOBS.get(run_id)
        return bool(job) and job.get("state") == "running"

    def _api_flow_office(self, run_id):
        if not self._run_id_ok(run_id):
            return self._json(404, {"error": "no such run"})
        out = liveoffice.build_office(run_id)
        if not out.get("ok"):
            return self._json(404, out)
        return self._json(200, out)

    def _api_flow_run_state(self, run_id):
        if not self._run_id_ok(run_id):
            return self._json(404, {"error": "no such run"})
        out = flows.run_state(run_id, live=self._run_live(run_id))
        if not out.get("ok"):
            return self._json(404, out)
        return self._json(200, out)

    def _api_flow_ctl(self, run_id, which):
        if not self._run_id_ok(run_id):
            return self._json(404, {"error": "no such run"})
        fn = {"pause": flows.ctl_pause, "resume": flows.ctl_resume,
              "step": flows.ctl_step}[which]
        out = fn(run_id, self._run_live(run_id))
        if not out.get("ok"):
            if out.get("error", "").startswith("no such run"):
                return self._json(404, out)
            return self._json(409, out)
        return self._json(200, out)

    def _api_flow_control(self, run_id):
        if not self._run_id_ok(run_id):
            return self._json(404, {"error": "no such run"})
        run_dir = os.path.join(flows.RUNS_DIR, run_id)
        if not os.path.isfile(os.path.join(run_dir, "STATUS.json")):
            return self._json(404, {"error": "no such run"})
        body = self._read_json()
        if not isinstance(body, dict) or \
                not isinstance(body.get("pause_each_stage"), bool):
            return self._json(400, {"error":
                                    "need {pause_each_stage: bool}"})
        ctl = flows.write_control(
            run_dir, {"pause_each_stage":
                      body["pause_each_stage"]})
        flows.log_run_event(
            run_dir, {"ev": "run_each_stage",
                      "on": body["pause_each_stage"], "by": "owner"})
        return self._json(200, {"ok": True, "run_id": run_id,
                                "control": ctl})

    def _api_flow_board(self, run_id):
        if not self._run_id_ok(run_id):
            return self._json(404, {"error": "no such run"})
        job = _FLOW_JOBS.get(run_id)
        live = bool(job) and job.get("state") == "running"
        st = flows.run_state(run_id, live=live)
        out = board.build_board(
            run_id, running=st.get("state") in ("running",
                                                "pausing"))
        if not out.get("ok"):
            return self._json(404, out)
        return self._json(200, out)

    def _api_flow_verify(self, run_id):
        if not self._run_id_ok(run_id):
            return self._json(404, {"error": "no such run"})
        qs = unquote(self.path).split("?", 1)
        q = dict(parse_qsl(qs[1])) if len(qs) > 1 else {}
        part = None
        if q.get("part"):
            try:
                part = int(q["part"])
            except ValueError:
                return self._json(404, {"error": "no such part"})
        out = board.build_verify(run_id, q.get("node", ""),
                                 part)
        if not out.get("ok"):
            return self._json(404, out)
        return self._json(200, out)

    def _api_flow_files(self, run_id):
        """Read-only run-folder listing (the Board's "Open run
        folder" link). Every row links to the file endpoint."""
        if not self._run_id_ok(run_id):
            return self._json(404, {"error": "no such run"})
        out = board.list_run_files(run_id)
        if not out.get("ok"):
            return self._json(404, out)
        rows = []
        for e in out["files"]:
            url = "/api/flows/runs/%s/file?node=%s&path=%s" % (
                run_id, e["node"], e["rel"])
            rows.append("<tr><td><a href=\"%s\">%s</a></td>"
                        "<td>%d</td></tr>"
                        % (html.escape(url, quote=True),
                           html.escape(e["path"]),
                           e["size"]))
        body = ("<!doctype html><html><head><meta charset=\"utf-8\">"
                "<title>run %s</title></head><body>"
                "<h1>run %s</h1>"
                "<table><tr><th>file</th><th>bytes</th></tr>%s"
                "</table></body></html>") % (
                    html.escape(run_id), html.escape(run_id),
                    "".join(rows))
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type",
                         "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _api_flow_path(self, run_id, node, rel):
        """Path mode of the step file endpoint: Remy slide PNGs and
        other small dashboard files inside one stage folder. An
        empty node means the run folder itself (STATUS.json,
        events.jsonl, flow.json)."""
        if not self._run_id_ok(run_id):
            return self._json(404, {"error": "no such run"})
        full = board.safe_run_path(
            flows.RUNS_DIR, run_id, node, rel)
        if full is None:
            return self._json(404, {"error": "no such file"})
        if os.path.splitext(full)[1].lower() in (".mp4", ".webm"):
            return self._serve_media(full)
        with open(full, "rb") as f:
            data = f.read()
        if len(data) > 5242880:
            return self._json(413, {"error": "file too large"})
        self.send_response(200)
        self.send_header("Content-Type",
                         mimetypes.guess_type(full)[0]
                         or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_media(self, full):
        """Stream a video file with byte ranges (<video> seeking)."""
        try:
            size = os.path.getsize(full)
        except OSError:
            return self._json(404, {"error": "no such file"})
        start, end, ranged = 0, size - 1, False
        m = re.match(r"bytes=(\d*)-(\d*)$",
                     self.headers.get("Range", "").strip())
        if m and size > 0:
            a, b = m.group(1), m.group(2)
            if a:
                start = int(a)
            elif b:
                start = max(0, size - int(b))
            if b and a:
                end = min(int(b), size - 1)
            if start >= size:
                self.send_response(416)
                self.send_header("Content-Range",
                                 "bytes */%d" % size)
                self.end_headers()
                return
            ranged = True
        length = end - start + 1
        self.send_response(206 if ranged else 200)
        self.send_header("Content-Type",
                         mimetypes.guess_type(full)[0]
                         or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        if ranged:
            self.send_header("Content-Range", "bytes %d-%d/%d"
                             % (start, end, size))
        self.send_header("Content-Length", str(length))
        self.end_headers()
        try:
            with open(full, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(65536, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (OSError, ValueError):
            pass

    _RUN_FILES = {"INPUTS.md": "text/markdown",
                  "INPUTS.json": "application/json",
                  "inputs_log.json": "application/json",
                  "inputs_check.json": "application/json",
                  "reads_log.jsonl": "text/plain",
                  "events.jsonl": "text/plain",
                  "report.md": "text/markdown",
                  "summary_ko.md": "text/markdown",
                  "result.json": "application/json",
                  "usage.json": "application/json",
                  "captions.srt": "text/plain",
                  "assembly.json": "application/json",
                  "storyboard_table.json": "application/json"}

    def _api_flow_file(self, run_id):
        if not self._run_id_ok(run_id):
            return self._json(404, {"error": "no such run"})
        qs = unquote(self.path).split("?", 1)
        q = dict(parse_qsl(qs[1])) if len(qs) > 1 else {}
        node, name = q.get("node", ""), q.get("name", "")
        if not name and q.get("path"):
            return self._api_flow_path(run_id, node, q["path"])
        sub = board.clone_run_dir(node)
        if sub is None:
            return self._json(404, {"error": "no such node"})
        if name not in self._RUN_FILES:
            return self._json(404, {"error": "no such file"})
        full = os.path.join(flows.RUNS_DIR, run_id, sub, name)
        if not os.path.isfile(full):
            return self._json(404, {"error": "no such file"})
        with open(full, "rb") as f:
            data = f.read()
        if len(data) > 1048576:
            return self._json(413, {"error": "file too large"})
        self.send_response(200)
        self.send_header("Content-Type", self._RUN_FILES[name])
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

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
        """open_ref: the passage at ref, verbatim, with provenance."""
        qs = unquote(self.path).split("?", 1)
        ref = ""
        if len(qs) > 1:
            ref = dict(parse_qsl(qs[1])).get("ref", "")
        try:
            pcname, doc_id, _frag = pc.parse_ref(ref)
        except ValueError:
            return self._json(400, {"error": "bad ref: %r" % ref})
        ep = os.path.join(pc.entry_dir(pcname, doc_id), "entry.json")
        if not os.path.isfile(ep):
            return self._json(404, {"error": "no such PC entry"})
        with open(ep, encoding="utf-8") as f:
            entry = json.load(f)
        try:
            out = pc.open_ref(entry, ref)
        except (KeyError, ValueError) as exc:
            return self._json(404, {"error": str(exc)})
        return self._json(200, out)

    def _api_order_upload(self, oid):
        """Store the client's PDF only. Sam parses and sends it to the
        Source PC after the client confirms (Yes)."""
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
        meta = self._order_meta(d)
        meta["files"] = {"source": "source.pdf", "bytes": len(raw),
                         "upload_name": base}
        self._order_save_meta(d, meta)
        print("order upload %s/%s (%d bytes, stored; Sam parses it "
              "after Yes)" % (oid, base, len(raw)), flush=True)
        projlog.log_event(oid, "order", "upload",
                          "%s (%d bytes)" % (base, len(raw)),
                          file="orders/%s/source.pdf" % oid)
        projlog.do_refresh(oid)
        missing = intake.missing_of(meta.get("answers", {}),
                                    meta.get("files", {}))
        return self._json(200, {"ok": True, "file": "source.pdf",
                                "bytes": len(raw), "name": base,
                                "missing": missing})

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
        projlog.log_event(oid, "order", "intake",
                          "answers saved (%d keys)"
                          % len(clean),
                          file="orders/%s/meta.json" % oid)
        projlog.do_refresh(oid)
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
        if meta.get("status") in intake.STARTED:
            return self._json(409, {"error": "already started: "
                                             "consultation is closed"})
        free = isinstance(body, dict) and body.get("mode") == "free"
        path = self._employee(meta["assignee"])
        agent = self._load_agent(path)
        try:
            system_base = profiles.system_base(path)
        except OSError as exc:
            return self._json(500, {"error": "bad prompt files: %s"
                                             % exc})
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
        step = intake.confirm_step(ready, extra)
        if step == "ask" and ready:
            judged = self._judge_confirm(agent["model"], extra)
            if judged == "yes":
                step = "start"
            elif judged == "no":
                step = "keep"
        if step == "start":
            code, out = self._do_chat_accept(oid, d, meta, extra)
            return self._json(code, out)
        if step == "keep":
            code, out = self._sam_turn(
                oid, d, meta, agent, system_base, msgs, ready, [],
                "The client said not yet: they need more time before "
                "starting. Acknowledge warmly in your own words, tell "
                "them you'll be right here when they're ready, and ask "
                "nothing new.")
            return self._json(code, out)
        if step == "ask":
            code, out = self._sam_turn(
                oid, d, meta, agent, system_base, msgs, ready, [],
                "You have everything (all answers + source PDF). The "
                "client's last message was not a clear yes or no. Ask "
                "one natural question: shall I start production now? "
                "Nothing else.")
            return self._json(code, out)
        direction = ("Still missing: %s. Steer the chat toward them, "
                     "one question at a time." % ", ".join(missing))
        if free:
            direction += (" Free-chat mode: converse naturally like a "
                          "friendly sales call, but still cover every "
                          "missing topic before the client is done.")
        code, out = self._sam_turn(
            oid, d, meta, agent, system_base, msgs, False, missing,
            direction)
        return self._json(code, out)

    @staticmethod
    def _judge_confirm(model, user_text):
        """One-word LLM verdict on an unclear ready-turn reply.

        Returns "yes", "no" or None (keep asking). Keywords stay the
        fast path; this runs only when they are unclear."""
        try:
            resp = runner._chat(
                model,
                [{"role": "system",
                  "content": intake.JUDGE_PROMPT + user_text + "\""}],
                None, timeout=30)
            word = ((resp.get("choices") or [{}])[0]
                    .get("message", {}).get("content", ""))
            return intake.parse_confirm_word(word)
        except Exception:  # noqa: BLE001 - fallback keeps "ask"
            return None

    def _sam_turn(self, oid, d, meta, agent, system_base, msgs,
                  ready, missing, direction):
        """One model-worded Sam turn. Returns (code, obj); sends nothing.

        The decision (start/keep/ask/chat) is made by code before this
        runs; only the wording comes from the model. The cleaning net
        below stays: control/function blocks never reach the client."""
        answers = meta.get("answers", {})
        recorded = ("; ".join("%s is %s" % (k, answers[k])
                              for k in INTAKE_KEYS if k in answers)
                    or "none yet")
        context = ["[ORDER CONSULTATION for %s. Recorded answers: %s."
                   % (oid, recorded),
                   "Your handbook (in the prompt above) holds sales "
                   "examples: follow their style when the client is "
                   "vague; never present an example as the client's "
                   "own words.",
                   direction]
        system = (system_base + "\n\n" + "\n".join(context)
                  + "\nAlways reply in English only: never Korean or any other "
                  "language, no matter what language the user writes in. "
                  + intake.NO_PROMISE_RULE + " "
                  "A few sentences at most. Sound like a person, not a "
                  "form: answer the client's actual words first and vary "
                  "your phrasing. "
                  "Reply in plain conversational sentences only: never "
                  "output JSON, code, tool calls, or anything in "
                  "<|...|> or <function> tags.")
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
            return (502, {"error": "model API error: %s" % exc})
        raw = reply.strip()
        text = intake.clean_chat_reply(raw)
        if not text:
            text = intake.CHAT_UNREADABLE
        self._chat_append(d, msgs[-1]["content"], text, raw=raw)
        projlog.log_event(
            oid, "order", "chat",
            "client: %s / Sam: %s"
            % (msgs[-1]["content"], text),
            file="orders/%s/chat.jsonl" % oid)
        projlog.do_refresh(oid)
        return (200, intake.chat_reply_payload(text, ready, missing))

    @staticmethod
    def _chat_append(d, user, reply, raw=None):
        rec = {"user": user, "reply": reply}
        if raw is not None and raw != reply:
            rec["raw"] = raw
        with open(os.path.join(d, "chat.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

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
        projlog.log_event(oid, "order", "approved",
                          "answers approved",
                          file="orders/%s/meta.json" % oid)
        projlog.do_refresh(oid)
        return self._json(200, {"ok": True, "approved": True})

    def _api_order_start(self, oid):
        d = self._order_dir(oid)
        if not d:
            return self._json(404, {"error": "no such order"})
        meta = self._order_meta(d)
        if not meta.get("approved"):
            return self._json(409, {"error": "not approved yet"})
        try:
            code, obj = self._do_complete(oid, d, meta,
                                          self._read_json(),
                                          "in_production")
        finally:
            try:
                fresh = self._order_meta(d)
                fresh.pop("starting", None)
                self._order_save_meta(d, fresh)
            except (OSError, ValueError):
                pass
        if code == 200 and isinstance(obj, dict):
            try:
                with open(os.path.join(d, "start_result.json"),
                          "w", encoding="utf-8") as f:
                    json.dump(obj, f, ensure_ascii=False)
            except (OSError, ValueError, TypeError):
                pass
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
        if meta.get("status") in intake.STARTED:
            return self._json(409, {"error": "already started"})
        if body["confirm"] is False:
            self._chat_append(d, intake.NO_LINE, intake.DECLINE_ACK)
            projlog.log_event(oid, "order", "declined",
                              "client said not yet",
                              file="orders/%s/chat.jsonl" % oid)
            projlog.do_refresh(oid)
            return self._json(200, {"ok": True, "declined": True,
                                    "reply": intake.DECLINE_ACK})
        code, out = self._confirm_yes_out(oid, d, meta)
        if code == 200:
            self._chat_append(d, intake.YES_LINE, intake.START_LINE)
        return self._json(code, out)

    def _confirm_yes_out(self, oid, d, meta):
        """Shared approve step (confirm:true and a clear yes in chat).

        Returns (code, obj); sends nothing. The caller appends the
        chat line with its own user text."""
        if meta.get("status") in ("complete", "in_production"):
            return (409, {"error": "already started"})
        try:
            self._try_fill_answers(d, meta)
        except RuntimeError as exc:
            return (502, {"error": str(exc)})
        missing = intake.missing_of(meta.get("answers", {}),
                                    meta.get("files", {}))
        if missing:
            return (409, {"error": "intake incomplete",
                          "missing": missing})
        legacy = None
        parsed_p = os.path.join(d, "parsed.md")
        if os.path.isfile(parsed_p):
            with open(parsed_p, encoding="utf-8") as f:
                text = f.read()
            md, heads = intake.build_sections(text)
            with open(os.path.join(d, "sections.md"), "w",
                      encoding="utf-8") as f:
                f.write(md)
            files = dict(meta.get("files", {}))
            files["sections"] = "sections.md"
            files["section_count"] = len(heads)
            meta["files"] = files
            legacy = {"file": "sections.md", "count": len(heads),
                      "headings": heads[:20]}
        pdf_p = os.path.join(d, "source.pdf")
        pdf = {"file": "source.pdf",
               "bytes": os.path.getsize(pdf_p)
               if os.path.isfile(pdf_p) else 0}
        meta["approved"] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "answers": dict(meta.get("answers", {})),
                            "via": "chat"}
        self._order_save_meta(d, meta)
        print("order confirm %s (%s)" % (oid, "legacy sections.md"
                                         if legacy else "stored PDF"),
              flush=True)
        projlog.log_event(oid, "order", "confirmed",
                          "client said yes (%s)"
                          % ("legacy sections.md"
                             if legacy else "stored PDF"),
                          file="orders/%s/chat.jsonl" % oid)
        projlog.do_refresh(oid)
        out = {"ok": True, "answers": meta["answers"],
               "reply": intake.START_LINE, "pdf": pdf}
        if legacy:
            out["sections"] = legacy
        return (200, out)

    def _do_chat_accept(self, oid, d, meta, user_text):
        """Conversation-only accept: confirm now, the client then
        calls start (same confirm-then-start the Yes button ran)."""
        meta["starting"] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        self._order_save_meta(d, meta)
        code, out = self._confirm_yes_out(oid, d, meta)
        if code != 200:
            meta.pop("starting", None)
            self._order_save_meta(d, meta)
            err = (out.get("error") if isinstance(out, dict)
                   else "confirm failed")
            reply = "Couldn't start: " + err
            self._chat_append(d, user_text, reply)
            bad = intake.chat_reply_payload(reply, True, [])
            bad["accepted"] = False
            return self._json(code, bad)
        reply = intake.ACCEPT_LINE
        self._chat_append(d, user_text, reply)
        projlog.log_event(oid, "order", "chat",
                          "client: %s / Sam: %s" % (user_text, reply),
                          file="orders/%s/chat.jsonl" % oid)
        projlog.do_refresh(oid)
        payload = intake.chat_reply_payload(reply, False, [])
        payload.update({"accepted": True,
                        "answers": out.get("answers"),
                        "pdf": out.get("pdf")})
        if "sections" in out:
            payload["sections"] = out["sections"]
        return self._json(200, payload)

    @staticmethod
    def _sam_inputs_md(oid, meta):
        """Sam's run input: the order answers + the attached PDF facts.
        The send/sequence instructions live in Sam's persona."""
        files = meta.get("files", {}) or {}
        pdf = os.path.join(ROOT, "orders", oid, "source.pdf")
        nbytes = os.path.getsize(pdf) if os.path.isfile(pdf) else 0
        return "\n".join([
            "# Inputs for sales_sam", "",
            "## Order brief (order %s)" % oid,
            json.dumps({"order_id": oid,
                        "answers": meta.get("answers", {}),
                        "source_file": files.get("source", "source.pdf")},
                       ensure_ascii=False, indent=1), "",
            "## Attached source",
            "%s (%d bytes, uploaded as %s). Stored, not parsed yet."
            % (files.get("source", "source.pdf"), nbytes,
               files.get("upload_name", "?")), ""])

    def _do_complete(self, oid, d, meta, body, final_status):
        """Shared consultation pipeline: run Sam live (he sends the
        PDF to the Source PC, sets recipients, writes request +
        source). Returns (code, obj)."""
        if meta.get("status") in ("complete", "in_production"):
            with open(os.path.join(d, "report.md"), encoding="utf-8") as f:
                md = f.read()
            with open(os.path.join(d, "intake.json"), encoding="utf-8") as f:
                intake = json.load(f)
            return (200, {"ok": True, "repeated": True, "intake": intake,
                          "report_md": md,
                          "files": ["intake.json", "result.json",
                                    "report.md"],
                          "run_id": self._latest_run_for_order(oid)})
        if isinstance(body, dict) and body.get("extract"):
            problem = self._extract_intake(d, meta)
            if problem:
                return problem
        missing = [k for k in INTAKE_KEYS if k not in meta.get("answers", {})]
        if missing:
            return (409, {"error": "intake incomplete", "missing": missing})
        if not os.path.isfile(os.path.join(d, "source.pdf")):
            return (409, {"error": "no attached PDF yet"})
        agent_dir = self._employee(meta["assignee"])
        run_model = self._load_agent(agent_dir)["model"]
        if not runner.key_present(run_model):
            return (503, {"error": "%s missing: add it to .env"
                          % runner.key_var(run_model)})
        brief = {"order_id": oid, "answers": meta["answers"],
                 "source_file": meta.get("files", {}).get("source",
                                                          "source.pdf")}
        run_dir = os.path.join(ROOT, "output", "runs", oid)
        os.makedirs(run_dir, exist_ok=True)
        input_md = os.path.join(run_dir, "INPUTS.md")
        with open(input_md, "w", encoding="utf-8") as f:
            f.write(self._sam_inputs_md(oid, meta))
        projlog.log_event(oid, "sam", "start",
                          "Sam runs the consultation report",
                          node="sales_sam",
                          file="output/runs/%s/INPUTS.md" % oid)
        result = runner.run(agent_dir, run_dir, brief, input_md)
        if not result.get("ok"):
            reason = "unknown"
            for ev in reversed(result.get("events", [])):
                if ev.get("ev") == "run_fail":
                    reason = ev.get("reason", reason)
                    break
            projlog.log_event(oid, "sam", "error", reason,
                              node="sales_sam",
                              file="output/runs/%s/events.jsonl"
                              % oid)
            projlog.do_refresh(oid)
            return (502, {"error": "sales run failed: " + reason,
                          "usage": result.get("usage")})
        for fn in ("result.json", "report.md"):
            shutil.copyfile(os.path.join(run_dir, fn), os.path.join(d, fn))
        with open(os.path.join(d, "result.json"), encoding="utf-8") as f:
            res = json.load(f)
        cats = res.get("categories", {}) or {}
        mfresh = (self._order_meta(d).get("files", {}) or {})
        source = {"ref": mfresh.get("pc_ref", ""),
                  "title": mfresh.get("pc_title", ""),
                  "sections": mfresh.get("pc_sections", "?"),
                  "chars": mfresh.get("pc_chars", "?")}
        files = dict(meta.get("files", {}))
        intake = {"order_id": oid,
                  "answers": dict(meta["answers"],
                                  source=files.get("source", "source.pdf")),
                  "files": {"source": files.get("source"),
                            "pc_ref": source.get("ref", "")},
                  "source": source}
        with open(os.path.join(d, "intake.json"), "w", encoding="utf-8") as f:
            json.dump(intake, f, ensure_ascii=False, indent=2)
        meta = self._order_meta(d)
        meta["status"] = final_status
        self._order_save_meta(d, meta)
        with open(os.path.join(d, "report.md"), encoding="utf-8") as f:
            md = f.read()
        stages = [
            "a) answers saved (audience, length, depth, theme)",
            "b) PDF sent to the Source PC: %s (%s sections, %s chars)"
            % (source.get("ref", "?"), source.get("sections", "?"),
               source.get("chars", "?")),
            "c) production request written (result.json + report.md)"]
        print("order %s %s (%s, %s)"
              % ("start" if final_status == "in_production" else "complete",
                 oid, source.get("ref", "?"), result.get("usage")),
              flush=True)
        projlog.log_event(
            oid, "sam", "done",
            "%s sections, %s chars -> %s"
            % (source.get("sections", "?"),
               source.get("chars", "?"),
               source.get("ref", "?")),
            node="sales_sam",
            file="output/runs/%s/report.md" % oid)
        projlog.log_event(
            oid, "order",
            "start" if final_status == "in_production"
            else "complete",
            "consultation %s" % final_status,
            file="orders/%s/intake.json" % oid)
        projlog.do_refresh(oid)
        out = {"ok": True, "intake": intake, "report_md": md,
               "files": ["intake.json", "result.json", "report.md"],
               "usage": result.get("usage"), "source": source,
               "stages": stages, "run_id": ""}
        if final_status == "in_production":
            run_id, auto_err = self._auto_start_flow(oid)
            out["run_id"] = run_id
            if auto_err:
                out["auto_run_error"] = auto_err
            elif run_id and memstore._INDEXER is not None:
                memstore.queue_build(
                    run_id, "sales_sam",
                    lambda: memstore.collect_sam_docs(
                        d, self._order_meta(d)))
        return (200, out)

    def _latest_run_for_order(self, oid):
        """Newest run dir whose STATUS names this order ("" if none)."""
        rdir = flows.RUNS_DIR
        if not os.path.isdir(rdir):
            return ""
        names = sorted(
            os.listdir(rdir),
            key=lambda n: os.path.getmtime(os.path.join(rdir, n)),
            reverse=True)
        for n in names:
            if not os.path.isdir(os.path.join(rdir, n)):
                continue
            try:
                with open(os.path.join(rdir, n, "STATUS.json"),
                          encoding="utf-8") as f:
                    st = json.load(f)
            except (OSError, ValueError):
                continue
            if isinstance(st, dict) and st.get("order_id") == oid:
                return n
        return ""

    def _auto_start_flow(self, oid):
        """Start the default crew flow after Sam's request is
        written. Returns (run_id, error); a failure never fails
        the order (Sam's work is done)."""
        try:
            flow_obj = flows.load_flow("default")
        except (ValueError, OSError) as exc:
            return "", "default flow missing (%s)" % exc
        errs = flows.validate_flow(flow_obj)
        if errs:
            return "", errs[0].get("message", "invalid flow")
        try:
            run_id = self._launch_flow_run("default", flow_obj, oid)
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            return "", str(exc)[:200]
        print("order %s auto-started run %s" % (oid, run_id),
              flush=True)
        return run_id, ""

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

    # ---- Source PC ----
    def _pc_maybe_build(self, doc_id, force=False, mode="all",
                        pcname="source"):
        """Spawn the map/index worker unless the map is done or a
        worker already runs for this entry. force rebuilds anyway.
        mode passes through to the worker (all/index)."""
        if not force:
            try:
                with open(os.path.join(pc.entry_dir(pcname, doc_id),
                                       "map.json"),
                          encoding="utf-8") as f:
                    if json.load(f).get("status") == "done":
                        return
            except (OSError, ValueError):
                pass
        job = _PC_JOBS.get(doc_id)
        if job is not None and job.poll() is None:
            return
        edir = pc.entry_dir(pcname, doc_id)
        logf = open(os.path.join(edir, "worker.log"), "a",
                    encoding="utf-8")
        cmd = [sys.executable, os.path.join("scripts", "pc_worker.py"),
               doc_id, mode, pcname]
        try:
            _PC_JOBS[doc_id] = subprocess.Popen(
                cmd, cwd=ROOT, stdout=logf, stderr=subprocess.STDOUT)
        except OSError:
            logf.close()
            raise
        logf.close()
        print("order pc worker %s/%s" % (pcname, doc_id), flush=True)

    @staticmethod
    def _pc_reap_finished():
        """Print one server-window line per finished PC worker (stage
        counts + time from its log), then drop it from the job table."""
        for doc_id, job in list(_PC_JOBS.items()):
            if job.poll() is None:
                continue
            try:
                _pcn = next((p for p in ("source", "theory", "article")
                             if os.path.isfile(os.path.join(pc.entry_dir(p, doc_id), "log.jsonl"))),
                            "source")
                with open(os.path.join(pc.entry_dir(_pcn, doc_id),
                                       "log.jsonl"), encoding="utf-8") as f:
                    evs = [json.loads(ln) for ln in f.read().splitlines()]
            except (OSError, ValueError):
                evs = []
            parts = []
            for e in evs:
                ev = e.get("ev", "")
                if ev == "describe_done":
                    parts.append("describe %d ok/%d failed %s %ss"
                                 % (e.get("described", 0),
                                    e.get("failed", 0),
                                    e.get("backend", "?"),
                                    e.get("seconds", 0)))
                elif ev == "map_done":
                    parts.append("map %s %d calls %d tok %ss"
                                 % (e.get("status", "?"),
                                    e.get("llm_calls", 0),
                                    e.get("tokens_est", 0),
                                    e.get("seconds", 0)))
                elif ev == "index_done":
                    parts.append("index %s %d calls %d tok %ss"
                                 % (e.get("profile", "?"),
                                    e.get("llm_calls", 0),
                                    e.get("tokens_est", 0),
                                    e.get("seconds", 0)))
                elif ev in ("failed", "map_failed"):
                    parts.append("%s: %s" % (ev, e.get("error", "")[:100]))
            print("order pc done %s: %s"
                  % (doc_id, "; ".join(parts) if parts else "no stages"),
                  flush=True)
            del _PC_JOBS[doc_id]

    @staticmethod
    def _pc_indexed(prof, pcname, doc_id):
        try:
            with open(os.path.join(pc.index_dir(pcname, prof),
                                   "index.json"), encoding="utf-8") as f:
                return doc_id in json.load(f).get("entries", [])
        except (OSError, ValueError):
            return False

    @staticmethod
    def _pc_media_summary(pcname, e):
        if pcname == "voice":
            cuts = e.get("cuts", {}) or {}
            return {"cuts": len(cuts),
                    "seconds": round(sum(
                        c.get("seconds", 0) for c in cuts.values()
                        if isinstance(c, dict)), 1)}
        if pcname == "image":
            return {"file": e.get("file", ""),
                    "license": e.get("license", "")}
        if pcname == "generated":
            return {"file": e.get("file", ""),
                    "model": e.get("model", ""),
                    "cost_usd": e.get("cost_usd", 0)}
        return {}

    @staticmethod
    def _pc_media_detail(pcname, e):
        if pcname == "voice":
            return {"cuts": [
                {"cut_id": cid, "file": c.get("file", ""),
                 "seconds": c.get("seconds", 0),
                 "attempt": c.get("attempt", 1),
                 "engine": c.get("engine", ""),
                 "text": c.get("text", "")}
                for cid, c in sorted((e.get("cuts", {}) or {}).items())
                if isinstance(c, dict)]}
        if pcname == "image":
            return {"file": e.get("file", ""),
                    "source_url": e.get("source_url", ""),
                    "license": e.get("license", ""),
                    "reason": e.get("reason", "")}
        if pcname == "generated":
            return {"file": e.get("file", ""),
                    "prompt": e.get("prompt", ""),
                    "model": e.get("model", ""),
                    "cost_usd": e.get("cost_usd", 0)}
        return {}

    def _api_pc_entries(self, pcname):
        if pcname not in ("source", "theory", "article", "image", "generated", "voice"):
            return self._json(404, {"error": "no such PC"})

        self._pc_reap_finished()
        out = []
        ed = os.path.join(pc.pc_dir(pcname), "entries")
        if os.path.isdir(ed):
            for doc_id in sorted(os.listdir(ed)):
                if not re.fullmatch(r"[0-9a-f]{12}", doc_id or ""):
                    continue
                try:
                    with open(os.path.join(ed, doc_id, "entry.json"),
                              encoding="utf-8") as f:
                        e = json.load(f)
                    if pcname in ("image", "generated", "voice"):
                        mstatus = "n/a"
                    else:
                        with open(os.path.join(ed, doc_id, "map.json"),
                                  encoding="utf-8") as f:
                            mstatus = json.load(f).get("status",
                                                       "pending")
                except (OSError, ValueError):
                    continue
                job = _PC_JOBS.get(doc_id)
                out.append({"id": doc_id, "ref": e.get("ref", ""),
                            "title": e.get("title", ""),
                            "origin_file": e.get("origin_file", ""),
                            "url": e.get("url", ""),
                            "order_id": e.get("order_id", ""),
                            "parsed_at": e.get("parsed_at", ""),
                            "added_by": e.get("added_by", ""),
                            "sections": len(e.get("sections", [])),
                            "paras": len(e.get("paragraphs", [])),
                            "chars": e.get("chars", 0),
                            "figures": len(e.get("figures", [])),
                            "tables": len(e.get("tables", [])),
                            "media": self._pc_media_summary(pcname, e),
                            "map": mstatus,
                            "building": job is not None
                            and job.poll() is None,
                            "index": {
                                p: self._pc_indexed(p, pcname, doc_id)
                                for p in ("local", "jetson")}})
        out.sort(key=lambda r: r["parsed_at"], reverse=True)
        return self._json(200, {"entries": out})

    def _api_pc_entry(self, pcname, doc_id):
        self._pc_reap_finished()
        if not re.fullmatch(r"[0-9a-f]{12}", doc_id or ""):
            return self._json(404, {"error": "no such PC entry"})
        if pcname not in ("source", "theory", "article", "image", "generated", "voice"):
            return self._json(404, {"error": "no such PC"})
        ed = pc.entry_dir(pcname, doc_id)
        if not os.path.isfile(os.path.join(ed, "entry.json")):
            return self._json(404, {"error": "no such PC entry"})
        with open(os.path.join(ed, "entry.json"), encoding="utf-8") as f:
            e = json.load(f)
        try:
            with open(os.path.join(ed, "map.json"), encoding="utf-8") as f:
                m = json.load(f)
        except (OSError, ValueError):
            m = {"status": ("n/a" if pcname in
                             ("image", "generated", "voice")
                             else "pending"),
                 "sections": []}
        entry = {k: e.get(k) for k in ("ref", "title", "origin_file",
                                       "order_id", "parsed_at",
                                       "added_by", "chars", "url",
                                       "publisher", "date", "fetched_at")}
        entry["sections"] = [{"n": s["n"], "heading": s["heading"],
                               "count": s["count"], "start": s["start"],
                               "non_content": bool(s.get("non_content"))}
                              for s in e.get("sections", [])]
        entry["paragraphs"] = [{"addr": p["addr"], "text": p["text"],
                                "pages": p.get("pages", [])}
                               for p in e.get("paragraphs", [])]
        entry["figures"] = e.get("figures", [])
        entry["tables"] = e.get("tables", [])
        entry["equations"] = e.get("equations", [])
        entry["recipients"] = e.get("recipients")
        entry["media"] = self._pc_media_detail(pcname, e)
        job = _PC_JOBS.get(doc_id)
        entry["building"] = job is not None and job.poll() is None
        entry["index"] = {p: self._pc_indexed(p, pcname, doc_id)
                          for p in ("local", "jetson")}
        return self._json(200, {"entry": entry, "map": m})

    def _api_pc_entry_picks(self, pcname, doc_id):
        if pcname not in ("theory", "article"):
            return self._json(404, {"error": "picks exist for theory/article only"})
        if not re.fullmatch(r"[0-9a-f]{12}", doc_id or ""):
            return self._json(404, {"error": "no such PC entry"})
        ref = pc.entry_ref(pcname, doc_id)
        picks = pc.pick_orders(ref, flows.RUNS_DIR)
        return self._json(200, {"ref": ref, "picks": picks,
                                "latest_order": picks[0]["order_id"]
                                if picks else ""})

    def _api_pc_figure(self, pcname, doc_id, file):
        if pcname not in ("source", "theory", "article"):
            return self._json(404, {"error": "no such PC"})
        if not re.fullmatch(r"[0-9a-f]{12}", doc_id or ""):
            return self._json(404, {"error": "no such PC entry"})
        if not re.fullmatch(r"fig\d+\.png", file or ""):
            return self._json(404, {"error": "no such figure"})
        full = os.path.join(pc.entry_dir(pcname, doc_id), "figures",
                            file)
        if not os.path.isfile(full):
            return self._json(404, {"error": "no such figure"})
        qs = unquote(self.path).split("?", 1)
        thumb = len(qs) > 1 and dict(parse_qsl(qs[1])).get("thumb") == "1"
        with open(full, "rb") as f:
            data = f.read()
        if thumb:
            try:
                import io
                from PIL import Image
                im = Image.open(io.BytesIO(data))
                im.thumbnail((320, 320))
                buf = io.BytesIO()
                im.save(buf, format="PNG")
                data = buf.getvalue()
            except Exception:  # noqa: BLE001 - thumb failed, full size
                pass
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _api_pc_media(self, pcname, doc_id, file):
        if pcname not in ("image", "generated", "voice"):
            return self._json(404, {"error": "no media on this PC"})
        if not re.fullmatch(r"[0-9a-f]{12}", doc_id or ""):
            return self._json(404, {"error": "no such PC entry"})
        if not re.fullmatch(r"[A-Za-z0-9][\w.\-]*", file or ""):
            return self._json(404, {"error": "no such file"})
        sub = "audio" if pcname == "voice" else "files"
        full = os.path.join(pc.entry_dir(pcname, doc_id), sub, file)
        if not os.path.isfile(full):
            return self._json(404, {"error": "no such file"})
        with open(full, "rb") as f:
            data = f.read()
        mime = mimetypes.guess_type(file)[0] \
            or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _api_pc_build(self, pcname, doc_id):
        return self._api_pc_spawn(pcname, doc_id, "all")

    def _api_pc_index(self, pcname, doc_id):
        return self._api_pc_spawn(pcname, doc_id, "index")

    def _api_pc_spawn(self, pcname, doc_id, mode):
        if pcname not in ("source", "theory", "article"):
            return self._json(404, {"error": "no such PC"})
        if not re.fullmatch(r"[0-9a-f]{12}", doc_id or ""):
            return self._json(404, {"error": "no such PC entry"})
        if not os.path.isfile(os.path.join(pc.entry_dir(pcname, doc_id),
                                            "entry.json")):
            return self._json(404, {"error": "no such PC entry"})
        job = _PC_JOBS.get(doc_id)
        if job is not None and job.poll() is None:
            return self._json(409, {"started": False,
                                    "reason": "already building"})
        try:
            self._pc_maybe_build(doc_id, force=True, mode=mode,
                                     pcname=pcname)
        except OSError as exc:
            return self._json(200, {"started": False,
                                    "reason": "spawn failed: %s" % exc})
        return self._json(200, {"started": True})

    # ---- company PCs (designed stores, draft §8) ----
    _PC_INFO = (
        {"id": "source", "name": "Source PC",
         "holds": "Parsed client documents: markdown, images, section list.",
         "add": "intake only (Sam's parser step)",
         "tools": ["pc_list_source", "pc_read_source", "open_ref"]},
        {"id": "theory", "name": "Theory PC",
         "holds": "Concept explanations, lectures, papers.",
         "add": "Cleo (concept explainer) picks only",
         "tools": ["pc_search_theory", "pc_pick_theory", "pc_read_theory",
                   "open_ref"]},
        {"id": "article", "name": "Article PC",
         "holds": "Cases: events, companies, people, films.",
         "add": "Rex (case researcher) picks only",
         "tools": ["pc_search_articles", "pc_pick_article",
                   "pc_read_article", "open_ref"]},
        {"id": "image", "name": "Image PC", "media": True,
         "holds": "Licensed web photos Pia picked: file, URL, license.",
         "add": "Pia (photo researcher) picks only",
         "tools": ["open_ref"]},
        {"id": "generated", "name": "Generated PC", "media": True,
         "holds": "Gene's generated concept images: file, prompt, model.",
         "add": "Gene (image generator) only",
         "tools": ["open_ref"]},
        {"id": "voice", "name": "Voice PC", "media": True,
         "holds": "Wren's cut narration audio: file, text, seconds.",
         "add": "Wren (narration writer) via make_voice",
         "tools": ["open_ref"]},
    )
    @staticmethod
    def _pc_size(pcname):
        total = 0
        for dp, _dn, fn in os.walk(pc.pc_dir(pcname)):
            for f in fn:
                try:
                    total += os.path.getsize(os.path.join(dp, f))
                except OSError:
                    pass
        return total

    @staticmethod
    def _pc_index_info(pcname, prof):
        try:
            with open(os.path.join(pc.index_dir(pcname, prof),
                                   "index.json"), encoding="utf-8") as f:
                m = json.load(f)
            return {"built": True,
                    "entries": len(m.get("entries", [])),
                    "model": m.get("model", ""),
                    "dim": m.get("dim", 0)}
        except (OSError, ValueError):
            return {"built": False, "entries": 0}

    def _api_pcs_rights(self):
        qs = unquote(self.path).split("?", 1)
        q = dict(parse_qsl(qs[1])) if len(qs) > 1 else {}
        oid = q.get("order", "")
        if not self._order_dir(oid):
            return self._json(404, {"error": "no such order"})
        rights = pc.rights_for_order(oid)
        names = {}
        adir = os.path.join(ROOT, "agents")
        try:
            eids = sorted(os.listdir(adir))
        except OSError:
            eids = []
        for eid in eids:
            jp = os.path.join(adir, eid, "agent.json")
            try:
                with open(jp, encoding="utf-8") as f:
                    agent = json.load(f)
            except (OSError, ValueError):
                continue
            if isinstance(agent, dict):
                names[eid] = agent.get("name", eid)
        rows = []
        for agent in sorted(set(names) | set(rights["agents"])):
            disp = names.get(agent, agent)
            cells = {}
            for pcname in pc.PCS:
                cell = rights["cells"].get((agent, pcname))
                if cell is None:
                    cells[pcname] = None
                    continue
                cells[pcname] = {
                    "v": pc.cell_label(cell["kind"],
                                       cell["parts"], agent),
                    "kind": cell["kind"],
                    "parts": cell["parts"],
                    "entries": cell["entries"]}
            rows.append({"agent": agent, "name": disp,
                         "cells": cells})
        return self._json(200, {"order": oid, "pcs": list(pc.PCS),
                                "rows": rows})

    def _api_pcs_list(self):
        try:
            prof = graph._adapter().embed_settings()["profile"]
        except RuntimeError:
            prof = "?"
        out = []
        for info in self._PC_INFO:
            pid = info["id"]
            ed = os.path.join(pc.pc_dir(pid), "entries")
            n = 0
            if os.path.isdir(ed):
                n = sum(1 for d in os.listdir(ed)
                        if os.path.isfile(os.path.join(ed, d,
                                                       "entry.json")))
            row = dict(info)
            row["entries"] = n
            row["state"] = ("active" if n else
                            ("empty" if os.path.isdir(ed)
                             else "not built yet"))
            row["size_bytes"] = self._pc_size(pid)
            row["profile"] = prof
            row["index"] = {p: self._pc_index_info(pid, p)
                            for p in ("local", "jetson")}
            out.append(row)
        return self._json(200, {"pcs": out})

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


def _mem_stub_indexer(docs, store_dir, log_id, profile):
    """Deterministic stand-in for headless checks only (never fakes
    a real memory: active only with SHOESTRING_MEM_STUB=1)."""
    os.makedirs(store_dir, exist_ok=True)
    with open(os.path.join(store_dir, "index.json"), "w",
              encoding="utf-8") as f:
        json.dump({"stub": True, "log_id": log_id,
                   "docs": [n for n, _ in docs]}, f)
    return {"llm_calls": 0, "profile": profile or "stub"}


def _mem_stub_retriever(store_dir, question, log_id, profile):
    return ("From my project memory: I received %s and wrote my "
            "report from it. (stub answer for headless checks)"
            % question[:60])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    load_dotenv(os.path.join(ROOT, ".env"))
    if os.environ.get("SHOESTRING_MEM_STUB") == "1":
        memstore._INDEXER = _mem_stub_indexer
        memstore._RETRIEVER = _mem_stub_retriever

        def _stub_chat(model, messages, tools, timeout=120):
            first = messages[0]["content"] if messages else ""
            has = "PROJECT MEMORY" in first \
                and "UNAVAILABLE" not in first
            return {"choices": [{"message": {
                "content": "Stub reply from memory "
                           "(project ctx: %s)." % has}}]}

        runner._chat = _stub_chat
        runner.key_present = lambda model: True
        print("memory: STUB indexer (headless check mode)",
              flush=True)
    else:
        memstore._INDEXER = memstore._real_indexer
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
