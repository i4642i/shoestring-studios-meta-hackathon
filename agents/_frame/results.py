"""Result JSON (one per agent run): envelope, registry, status flow.

Stdlib only. Shape: docs/RESULT_JSON_DRAFT_EN.md.
  header: producer, format_version, order_id, run_id, created_at, status,
          reviewed_by/at, verified_by/at
  categories: {name: {"version": int, "data": {...}}}
"""
import json
import os
import time

from . import schemas

HERE = os.path.dirname(os.path.abspath(__file__))
CATEGORIES = os.path.join(HERE, "categories.json")
FORMAT_VERSION = 1
STATUSES = ("unverified", "checked", "reviewed", "verified")
RESULT_FILE = "result.json"
HEADER_KEYS = ("producer", "format_version", "order_id", "run_id",
               "created_at", "status", "reviewed_by", "reviewed_at",
               "verified_by", "verified_at", "categories")

_registry = None


def registry():
    """Category registry {name: {version, description, schema}}."""
    global _registry
    if _registry is None:
        with open(CATEGORIES, encoding="utf-8") as f:
            _registry = json.load(f)
    return _registry


def validate_schema(value, schema, where="data"):
    """Minimal JSON-schema check. Supported subset: type (object, array,
    string, integer, number, boolean), properties, required, items (one
    schema), additionalProperties (bool), enum. Returns [errors]."""
    errors = []

    def walk(val, sch, path):
        if not isinstance(sch, dict):
            return
        if "enum" in sch and val not in sch["enum"]:
            errors.append("%s: not one of %r" % (path, sch["enum"]))
        typ = sch.get("type")
        if typ == "object":
            if not isinstance(val, dict):
                errors.append("%s: must be an object" % path)
                return
            for k in sch.get("required") or []:
                if k not in val:
                    errors.append("%s: missing %r" % (path, k))
            props = sch.get("properties") or {}
            for k, sub in props.items():
                if k in val:
                    walk(val[k], sub, "%s.%s" % (path, k))
            if sch.get("additionalProperties") is False:
                for k in val:
                    if k not in props:
                        errors.append("%s: unknown key %r" % (path, k))
        elif typ == "array":
            if not isinstance(val, list):
                errors.append("%s: must be an array" % path)
                return
            items = sch.get("items")
            if isinstance(items, dict):
                for i, item in enumerate(val):
                    walk(item, items, "%s[%d]" % (path, i))
        elif typ == "string":
            if not isinstance(val, str):
                errors.append("%s: must be a string" % path)
        elif typ == "integer":
            if not isinstance(val, int) or isinstance(val, bool):
                errors.append("%s: must be an integer" % path)
        elif typ == "number":
            if (not isinstance(val, (int, float))
                    or isinstance(val, bool)):
                errors.append("%s: must be a number" % path)
        elif typ == "boolean":
            if not isinstance(val, bool):
                errors.append("%s: must be a boolean" % path)

    walk(value, schema, where)
    return errors


def _stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def make_result(producer, order_id, run_id, categories):
    """Build a fresh result (status unverified). Raises RuntimeError for
    unknown categories or non-dict data."""
    reg = registry()
    wrapped = {}
    for name, data in (categories or {}).items():
        if name not in reg:
            raise RuntimeError("unknown category: %r" % name)
        if not isinstance(data, dict):
            raise RuntimeError("category %r data must be an object" % name)
        wrapped[name] = {"version": reg[name]["version"], "data": data}
    return {"producer": producer, "format_version": FORMAT_VERSION,
            "order_id": order_id, "run_id": run_id,
            "created_at": _stamp(), "status": "unverified",
            "reviewed_by": None, "reviewed_at": None,
            "verified_by": None, "verified_at": None,
            "categories": wrapped}


def check_result(res, accepts=None, where="result"):
    """Validate header + per-category versions and schemas. accepts maps
    category -> [versions] a receiver takes; default is the registry
    version. Returns [errors]."""
    if not isinstance(res, dict):
        return ["%s: must be an object" % where]
    errors = []
    for k in HEADER_KEYS:
        if k not in res:
            errors.append("%s: missing %r" % (where, k))
    if errors:
        return errors
    if res["format_version"] != FORMAT_VERSION:
        errors.append("%s: format_version %r != %d"
                      % (where, res["format_version"], FORMAT_VERSION))
    if res["status"] not in STATUSES:
        errors.append("%s: bad status %r" % (where, res["status"]))
    if res["status"] in ("reviewed", "verified") and not res["reviewed_by"]:
        errors.append("%s: %s needs reviewed_by"
                      % (where, res["status"]))
    if res["status"] == "verified" and not res["verified_by"]:
        errors.append("%s: verified needs verified_by" % where)
    for tag in ("reviewed", "verified"):
        if res[tag + "_by"] and not res[tag + "_at"]:
            errors.append("%s: %s_by without %s_at" % (where, tag, tag))
    cats = res["categories"]
    if not isinstance(cats, dict):
        return errors + ["%s: categories must be an object" % where]
    reg = registry()
    accepts = accepts or {}
    for name, wrapped in cats.items():
        path = "%s.categories.%s" % (where, name)
        if name not in reg:
            errors.append("%s: unknown category" % path)
            continue
        if not isinstance(wrapped, dict):
            errors.append("%s: must be {version, data}" % path)
            continue
        want = accepts.get(name, [reg[name]["version"]])
        if wrapped.get("version") not in want:
            errors.append("%s: version %r not in accepted %r"
                          % (path, wrapped.get("version"), want))
        if not isinstance(wrapped.get("data"), dict):
            errors.append("%s: data must be an object" % path)
            continue
        errors += validate_schema(wrapped["data"], reg[name]["schema"],
                                  path + ".data")
    return errors


def promote_checked(res):
    """unverified -> checked (code check passed). Idempotent on checked;
    refuses reviewed/verified (never downgrade, never touch verified)."""
    if res["status"] == "unverified":
        res["status"] = "checked"
    elif res["status"] != "checked":
        raise RuntimeError("cannot promote status %r to checked"
                           % res["status"])
    return res


def set_reviewed(res, reviewer):
    """checked -> reviewed by a reviewer agent. Sets reviewed_by/at."""
    if res["status"] != "checked":
        raise RuntimeError("only a checked result can be reviewed (is %r)"
                           % res["status"])
    res["status"] = "reviewed"
    res["reviewed_by"] = reviewer
    res["reviewed_at"] = _stamp()
    return res


def set_verified(res, actor):
    """checked/reviewed -> verified. Only the developer confirms (Q2);
    a verified result is read-only afterwards."""
    if actor != "developer":
        raise RuntimeError("only the developer can verify (actor %r)"
                           % (actor,))
    if res["status"] not in ("checked", "reviewed"):
        raise RuntimeError("only a checked/reviewed result can be verified"
                           " (is %r)" % res["status"])
    res["status"] = "verified"
    res["verified_by"] = actor
    res["verified_at"] = _stamp()
    return res


def load_result(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_result(run_dir, res):
    """Write result.json. Refuses to overwrite a verified result on disk."""
    path = os.path.join(run_dir, RESULT_FILE)
    if os.path.isfile(path):
        try:
            if load_result(path).get("status") == "verified":
                raise RuntimeError("%s is verified (read-only); "
                                   "start a new run" % path)
        except ValueError:
            pass
    with open(path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    return path


TEMPLATES = {
    ("brief", 1): schemas.render_brief_md,
    ("source", 1): schemas.render_source_md,
    ("source", 2): schemas.render_source_v2_md,
    ("source", 3): schemas.render_source_v3_md,
    ("structure", 3): schemas.render_structure_v2_md,
    ("storyboard_draft", 1): schemas.render_storyboard_draft_md,
    ("storyboard", 1): schemas.render_storyboard_md,
    ("narration", 1): schemas.render_narration_md,
    ("request", 1): schemas.render_request_md,
    ("structure", 1): schemas.render_structure_md,
    ("concept", 1): schemas.render_concept_md,
    ("structure", 2): schemas.render_structure_v2_md,
    ("concepts", 1): schemas.render_concepts_md,
    ("cases", 1): schemas.render_cases_md,
    ("video", 1): schemas.render_video_md,
}


def render_report(res):
    """Human-readable report from any result JSON (Q6). One template per
    category+version; unknown pairs render as fenced JSON. Reports show
    nothing that is not in the JSON and are never read by agents."""
    lines = ["# Run report — %s" % res["producer"], "",
             "generated from %s, do not edit" % res["run_id"],
             "order %s · run %s · status %s · %s"
             % (res["order_id"], res["run_id"], res["status"],
                res["created_at"]), ""]
    for name, wrapped in res["categories"].items():
        fn = TEMPLATES.get((name, wrapped.get("version")))
        lines.append("## %s (v%s)" % (name, wrapped.get("version")))
        lines.append("")
        if fn is None:
            lines.append("```json")
            lines.append(json.dumps(wrapped.get("data"), ensure_ascii=False,
                                    indent=1))
            lines.append("```")
        else:
            lines.append(fn(wrapped["data"]))
        lines.append("")
    return "\n".join(lines)
