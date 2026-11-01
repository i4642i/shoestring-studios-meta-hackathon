# -*- coding: utf-8 -*-
"""Poll a flow run and print stage-state changes (for muse.monitor).

Usage: watch_flow.py <run_id>
Exits 0 when explain_cleo + case_rex are both terminal (or run ends).
Prints DONE <agent> <status> lines only on change.
"""
import json
import os
import sys
import time
import urllib.request

RUN = sys.argv[1]
BASE = "http://localhost:8000/api/flows/runs/" + RUN
WANT = ("explain_cleo", "case_rex", "pd_marty", "sales_sam")
seen = {}
while True:
    try:
        d = json.loads(urllib.request.urlopen(BASE).read().decode())
    except Exception as e:  # noqa: BLE001 - transient server poll
        print("POLL-ERR %s" % e, flush=True)
        time.sleep(30)
        continue
    evs = d.get("events", [])
    states = {}
    for e in evs:
        n = e.get("node") or e.get("agent") or ""
        s = e.get("ev") or e.get("status") or ""
        if n:
            states[n] = s
    for n in WANT:
        s = states.get(n, "-")
        if seen.get(n) != s:
            seen[n] = s
            print("STAGE %s %s" % (n, s), flush=True)
    term = {n for n in ("explain_cleo", "case_rex")
            if (seen.get(n) or "").startswith(
                ("agent_done", "agent_ok", "agent_fail", "agent_error"))}
    if len(term) == 2 or d.get("state") in ("done", "failed", "error"):
        print("WATCH-END state=%s %s" % (d.get("state"), seen), flush=True)
        break
    time.sleep(60)
