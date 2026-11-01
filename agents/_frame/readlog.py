"""PC tool call log (item 10): every PC tool call appends one line
to the calling node/part's reads_log.jsonl, refusals included.
Never raises and never blocks the run; without a node dir in the
tool context it quietly does nothing. Stdlib only.
"""
import functools
import json
import os
import time

from . import pc

LOG_FILE = "reads_log.jsonl"


def _pc_of(ref):
    try:
        name, _doc, _frag = pc.parse_ref(ref or "")
    except (ValueError, TypeError):
        return ""
    return name or ""


def _item_of(args):
    args = args if isinstance(args, dict) else {}
    for key in ("item", "part_id", "cut_id", "query", "agent",
                "url", "prompt"):
        val = args.get(key)
        if isinstance(val, str) and val:
            return val[:120]
    return ""


def log_read(ctx, tool, args, out, exc, pc_hint=None):
    """Append one reads_log.jsonl line. allowed is False on tool
    errors and refusals; reason carries the error (truncated)."""
    try:
        d = os.path.dirname((ctx or {}).get("input_md", ""))
        if not d or not os.path.isdir(d):
            return
        args = args if isinstance(args, dict) else {}
        out = out if isinstance(out, dict) else {}
        ref = args.get("ref") or out.get("ref") \
            or out.get("voice_pc_ref") or ""
        if not isinstance(ref, str):
            ref = ""
        allowed = exc is None and "error" not in out \
            and out.get("ok") is not False
        if allowed:
            reason = ""
        elif exc is not None:
            reason = str(exc)
        else:
            reason = str(out.get("error") or out.get("errors")
                         or "refused")
        line = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "tool": tool,
                "pc": pc_hint or _pc_of(ref),
                "ref": ref,
                "section": args.get("section", "")
                if isinstance(args.get("section", ""), str) else "",
                "item": _item_of(args),
                "allowed": bool(allowed),
                "reason": reason[:300]}
        with open(os.path.join(d, LOG_FILE), "a",
                  encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except (OSError, ValueError, TypeError):
        pass


def logged(pc_hint=None):
    """Decorator for PC tool functions: log the call (and any
    exception, then re-raise for the runner's own error path)."""
    def wrap(fn):
        @functools.wraps(fn)
        def inner(ctx, args):
            try:
                out = fn(ctx, args)
            except Exception as exc:
                log_read(ctx, fn.__name__, args, None, exc,
                         pc_hint)
                raise
            log_read(ctx, fn.__name__, args, out, None, pc_hint)
            return out
        return inner
    return wrap
