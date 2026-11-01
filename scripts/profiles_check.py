"""Profile cards + handbook RAG retirement, J22 (fixtures only).

Checks: every employee has profile.md with the required sections;
no query_graph in any agent.json or persona; the profile builder
content; profile+handbook in the system prompt; the exact no-memory
sentences; runner.run fails loudly without profile.md; validate_agent
passes all employees. No model calls.
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from agents._frame import profiles  # noqa: E402
from agents._frame import runner  # noqa: E402
import validate_agent  # noqa: E402

fails = 0


def ok(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails += 1


def agents():
    adir = os.path.join(ROOT, "agents")
    return sorted(e for e in os.listdir(adir)
                  if not e.startswith("_") and os.path.isfile(
                      os.path.join(adir, e, "agent.json")))


def main():
    eids = agents()
    ok(len(eids) == 12, "%d employees found" % len(eids))

    for eid in eids:
        ad = os.path.join(ROOT, "agents", eid)
        with open(os.path.join(ad, "agent.json"),
                  encoding="utf-8") as f:
            agent = json.load(f)
        pp = os.path.join(ad, "profile.md")
        ok(os.path.isfile(pp), "%s has profile.md" % eid)
        if not os.path.isfile(pp):
            continue
        with open(pp, encoding="utf-8") as f:
            prof = f.read()
        ok(prof.startswith("# %s — " % agent.get("name", "?")),
           "%s profile heading" % eid)
        for section in ("## Duties", "## Flow", "## PCs",
                        "## Tools"):
            if section not in prof:
                ok(False, "%s profile has %s" % (eid, section))
        ok("query_graph" not in agent.get("tools", []),
           "%s tools drop query_graph" % eid)
        with open(os.path.join(ad, "persona.md"),
                  encoding="utf-8") as f:
            persona = f.read()
        ok("query_graph" not in persona,
           "%s persona drops query_graph" % eid)
        ok(validate_agent.validate(ad) == [],
           "%s validates (%s)"
           % (eid, validate_agent.validate(ad)))
        base = profiles.system_base(ad)
        ok("# PROFILE CARD" in base and agent.get("name", "?")
           in base and "## Duties" in base,
           "%s prompt holds the profile" % eid)
        hb = profiles.handbook_text(ad)
        if hb:
            ok(hb[:60] in base, "%s prompt holds handbook"
               % eid)

    flow = os.path.join(ROOT, "data", "flows", "default.json")
    names = {}
    for eid in eids:
        with open(os.path.join(ROOT, "agents", eid, "agent.json"),
                  encoding="utf-8") as f:
            names[eid] = json.load(f).get("name", eid)
    marty = profiles.build_profile(
        os.path.join(ROOT, "agents", "pd_marty"), flow, names)
    ok("Team: Storyboard team" in marty, "marty team line")
    ok("request from Sam (sales_sam)" in marty,
       "marty receives from sam")
    ok("concept to Cleo (explain_cleo)" in marty,
       "marty hands concept to cleo")
    ok("Source PC — read" in marty, "marty pc line")
    # No teamless employee ships anymore; probe the fallbacks
    # with a temp folder (id absent from the flow, no team key).
    stray = tempfile.mkdtemp(prefix="noprof_")
    try:
        with open(os.path.join(stray, "agent.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"id": "tmp24_stray", "name": "Stray",
                       "title": "Tester", "tools": []}, f)
        with open(os.path.join(stray, "persona.md"), "w",
                  encoding="utf-8") as f:
            f.write("# Stray\n\nTest persona.\n")
        built = profiles.build_profile(stray, flow, names)
        ok("Not in the current flow." in built,
           "teamless flow note")
        ok("Team: Unassigned" in built, "teamless team fallback")
    finally:
        shutil.rmtree(stray, ignore_errors=True)

    ok(profiles.refusal_for("building")
       == "My memory of this project is still building.",
       "building sentence")
    ok(profiles.refusal_for("failed", "no GPU")
       == "My memory of this project failed to build: no GPU.",
       "failed sentence")
    ok(profiles.refusal_for("failed", "no GPU.")
       == "My memory of this project failed to build: no GPU.",
       "failed sentence keeps one period")
    ok(profiles.refusal_for("none")
       == "I have not worked on this project yet.",
       "not-yet sentence")
    ok(profiles.refusal_for("closed")
       == "My memory of this project was deleted when the "
          "project closed.",
       "closed sentence")

    # runner.run fails loudly without profile.md; with it the
    # prompt builds (stubbed model captures the system text).
    tmp = tempfile.mkdtemp(prefix="proffix_")
    real_chat = runner._chat
    seen = {}

    def fake_chat(model, messages, tools, timeout=120, **kw):
        seen["system"] = messages[0]["content"]
        return {"choices": [{"message": {"role": "assistant",
                                         "content": "x"}}],
                "usage": {}}

    runner._chat = fake_chat
    try:
        ad = os.path.join(tmp, "agent")
        os.makedirs(os.path.join(ad, "handbook"))
        with open(os.path.join(ad, "agent.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"id": "t", "name": "T", "title": "t",
                       "model": "muse-spark-1.3",
                       "tools": ["write_structure"],
                       "bounds": {"max_steps": 1},
                       "io": {"output": "structure.json"}}, f)
        with open(os.path.join(ad, "persona.md"), "w",
                  encoding="utf-8") as f:
            f.write("# T the tester\n")
        with open(os.path.join(ad, "handbook", "craft.md"),
                  "w", encoding="utf-8") as f:
            f.write("craft notes here\n")
        rd = os.path.join(tmp, "run")
        os.makedirs(rd)
        brief = {"order_id": "o", "run_id": "r",
                 "producer": "t"}
        res = runner.run(ad, rd, brief, "")
        reasons = [e.get("reason", "") for e in res["events"]]
        ok(res["ok"] is False and any(
            r.startswith("bad prompt files") for r in reasons),
           "run fails loudly without profile.md (%s)"
           % reasons)
        with open(os.path.join(ad, "profile.md"), "w",
                  encoding="utf-8") as f:
            f.write("# T — t\nTeam: X\n")
        res = runner.run(ad, rd, brief, "")
        reasons = [e.get("reason", "") for e in res["events"]]
        ok(any("bad prompt files" in r for r in reasons)
           is False,
           "run with profile passes prompt build")
        ok("# PROFILE CARD" in seen.get("system", "")
           and "Team: X" in seen.get("system", "")
           and "# T the tester" in seen.get("system", "")
           and "craft notes here" in seen.get("system", ""),
           "run system holds profile+persona+handbook")
    finally:
        runner._chat = real_chat
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print("%d FAILURES" % fails)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
