"""Drive a real customer order through the browser UI (no API shortcuts).

Usage:
  python scripts/night_order.py order <pdf> <answers.json>   # chat to handover
  python scripts/night_order.py shot <hash> <png>            # screenshot, close

The order mode types into the real chat box, attaches the PDF through
the real file input, says yes in chat, and waits for the handover
popup. Prints ORDER=<id> and HANDOVER=yes/no. Real model, no stubs.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import _browser
import order_chat_check as oc

PORT = 8000
CDP = 9444
RUNS = os.path.join(ROOT, "runs")

GREET_JS = "(() => (document.getElementById('o-sambub') || {})" \
    ".innerText || '')()"
SAM_JS = GREET_JS
OID_JS = "(() => { const t = document.body.innerText; const m =" \
    " t.match(/ord-[0-9-]+/); return m ? m[0] : ''; })()"
FORM_JS = "(() => Array.from(document.querySelectorAll(" \
    "'#o-formpanel .frow')).map(r => r.innerText))()"
POP_JS = "(() => { const p = document.getElementById('o-handover');" \
    " return !!p && p.style.display !== 'none' ? p.innerText : ''; })()"
ME_JS = "(() => (document.getElementById('o-mebub') || {})" \
    ".innerText || '')()"


def launch():
    if oc.port_open(CDP):
        print("cdp port busy, touching nothing")
        return None, None, ""
    profile = os.path.join(tempfile.gettempdir(), "night_profile")
    shutil.rmtree(profile, ignore_errors=True)
    edge = subprocess.Popen(
        _browser.launch_args(CDP, profile, 1280, 720))
    ws = None
    try:
        t0 = time.time()
        page = None
        while time.time() - t0 < 40:
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/json/list" % CDP,
                        timeout=3) as r:
                    targets = json.load(r)
                page = next((t for t in targets
                             if t.get("type") == "page"), None)
                if page:
                    break
            except OSError:
                time.sleep(1)
        if page is None:
            raise RuntimeError("no page target")
        wsu = page["webSocketDebuggerUrl"]
        hostport, _, path = wsu.split("://", 1)[1].partition("/")
        host, _, port = hostport.partition(":")
        ws = oc.WS(host, int(port or 80), "/" + path)
        ws.call("Runtime.enable")
        ws.call("Page.enable")
        return edge, ws, profile
    except Exception:
        if ws is not None:
            ws.close()
        _browser.stop_tree(edge, "edge")
        raise


def prt(s):
    print("".join(c if ord(c) < 128 else "?"
                   for c in str(s)),
          flush=True)


def close(edge, ws, profile):
    try:
        if ws is not None:
            ws.close()
    except OSError:
        pass
    _browser.stop_tree(edge, "edge")
    shutil.rmtree(profile, ignore_errors=True)


def _core(s):
    t = (s or "").strip()
    if t.startswith("SAM"):
        t = t[3:].strip()
    return t


def wait_sam(ws, old, timeout=300):
    """Wait for a real reply: skip the thinking bubble and require the
    text to stay put for two polls, so a mid-render read never counts."""
    stable = ""
    stable_n = 0
    t0 = time.time()
    while time.time() - t0 < timeout:
        core = _core(oc.js_eval(ws, SAM_JS))
        if core and core != "…" and core != old:
            if core == stable:
                stable_n += 1
                if stable_n >= 2:
                    return core
            else:
                stable, stable_n = core, 1
        else:
            stable, stable_n = "", 0
        time.sleep(3)
    return ""


def send_now(ws, text):
    """Submit one chat message; our bubble must echo it (the app queues
    it behind an in-flight turn instead of dropping it)."""
    for _ in range(2):
        ws.call("Runtime.evaluate",
                {"expression":
                 "document.getElementById('o-input').value = %s; "
                 "document.getElementById('o-form').requestSubmit();"
                 % json.dumps(text),
                 "returnByValue": True})
        t0 = time.time()
        while time.time() - t0 < 25:
            if text in (oc.js_eval(ws, ME_JS) or ""):
                return True
            time.sleep(1)
    return False


def do_order(pdf, answers_path):
    with open(answers_path, encoding="utf-8") as f:
        answers = json.load(f)
    edge, ws, profile = launch()
    if edge is None:
        return 1
    oid = ""
    try:
        ws.call("Page.navigate",
                {"url": "http://localhost:%d/#order" % PORT})
        oc.drain_dialogs(ws, 12)
        first = wait_sam(ws, "", 180)
        if not first:
            print("NO-GREETING")
            return 1
        print("GREETING-OK")
        oid = oc.js_eval(ws, OID_JS) or ""
        print("ORDER=" + oid, flush=True)
        last = first
        for key in ("audience", "length", "depth", "theme"):
            msg = answers[key]
            if not send_now(ws, msg):
                print("NO-ECHO after " + key)
                return 1
            last = wait_sam(ws, last)
            if not last:
                print("NO-REPLY after " + key)
                return 1
            print("REPLIED-" + key, flush=True)
        prt("REPLIED-theme FORM=" +
            "|".join(oc.js_eval(ws, FORM_JS) or []))
        attached_sel = "!!document.querySelector" \
            "('label.pdfbtn input')"
        t0 = time.time()
        while time.time() - t0 < 90:
            if oc.js_eval(ws, attached_sel):
                break
            time.sleep(3)
        else:
            bub = oc.js_eval(
                ws, "(() => document.getElementById('o-bubbles')"
                    ".innerText)()") or ""
            prt("NO-ATTACH-BUTTON bub=" + bub[-300:])
            return 1
        doc = ws.call("DOM.getDocument", {"depth": 0})
        node = ws.call("DOM.querySelector",
                       {"nodeId": doc["root"]["nodeId"],
                        "selector": "label.pdfbtn input"})
        if "nodeId" not in node:
            prt("NO-ATTACH-NODE")
            return 1
        ws.call("DOM.setFileInputFiles",
                {"nodeId": node["nodeId"], "files": [pdf]})
        t0 = time.time()
        attached = False
        while time.time() - t0 < 120:
            bub = oc.js_eval(
                ws, "(() => document.getElementById('o-bubbles')"
                    ".innerText)()") or ""
            if "Attached" in bub:
                attached = True
                break
            time.sleep(3)
        if not attached:
            print("NO-ATTACH")
            return 1
        print("ATTACHED", flush=True)
        if not send_now(ws, answers["yes"]):
            print("NO-ECHO after yes")
            return 1
        t0 = time.time()
        pop = ""
        while time.time() - t0 < 420:
            pop = oc.js_eval(ws, POP_JS) or ""
            if pop:
                break
            time.sleep(5)
        oc.shot(ws, os.path.join(RUNS, "night_%s_handover.png" % oid))
        errs = oc.console_errors(ws.events)
        print("HANDOVER=" + ("yes" if pop else "no")
              + " console_errors=%d" % errs, flush=True)
        prt("POP=" + (pop[:200] if pop else "-"))
        return 0 if pop else 1
    finally:
        close(edge, ws, profile)


def do_shot(hsh, png):
    edge, ws, profile = launch()
    if edge is None:
        return 1
    try:
        ws.call("Page.navigate",
                {"url": "http://localhost:%d/%s" % (PORT, hsh)})
        time.sleep(8)
        oc.shot(ws, png)
        print("SHOT=" + png + " console_errors=%d"
              % oc.console_errors(ws.events), flush=True)
        return 0
    finally:
        close(edge, ws, profile)


if __name__ == "__main__":
    os.makedirs(RUNS, exist_ok=True)
    if len(sys.argv) < 2:
        print("usage: night_order.py order|shot ...")
        sys.exit(2)
    if sys.argv[1] == "order":
        sys.exit(do_order(sys.argv[2], sys.argv[3]))
    if sys.argv[1] == "shot":
        sys.exit(do_shot(sys.argv[2], sys.argv[3]))
    print("unknown mode")
    sys.exit(2)
