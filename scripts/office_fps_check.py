"""Office 3D frame-rate setting check (fixture only, no server, no browser).

Asserts the office_fps plumbing end to end at the static level:
- experiments/lightrag/adapter.py: clean_settings accepts 15/20/30,
  rejects anything else, resolved_settings always carries office_fps.
- scripts/server.py: GET api/settings exposes office_fps.
- index.html: OFFICE 3D FRAME RATE radios + save/load wiring +
  reception loop capped by recepFps.
- office_3d.html: loop gated by officeFps (20 default), settings load
  at boot + on wake, live update via the office-fps message.
Stdlib only.
"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

fails = 0


def ok(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails += 1


def load_adapter():
    path = os.path.join(ROOT, "experiments", "lightrag", "adapter.py")
    spec = importlib.util.spec_from_file_location("fps_adapter", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    mod = load_adapter()
    ok(tuple(mod.OFFICE_FPS_VALUES) == (15, 20, 30),
       "allowed values are 15/20/30")
    ok(mod.OFFICE_FPS_DEFAULT == 20, "default is 20")
    for v in (15, 20, 30):
        try:
            out = mod.clean_settings({"office_fps": v})
            good = out.get("office_fps") == v
        except RuntimeError:
            good = False
        ok(good, "clean_settings accepts %d" % v)
    for v in (25, 0, -1, "fast", None):
        try:
            mod.clean_settings({"office_fps": v})
            good = False
        except RuntimeError:
            good = True
        ok(good, "clean_settings rejects %r" % (v,))
    ok(mod.clean_settings({}).get("office_fps") is None,
       "absent key stays absent")
    try:
        eff = mod.resolved_settings()
        good = eff.get("office_fps") in (15, 20, 30)
    except Exception:
        good = False
    ok(good, "resolved_settings carries a valid office_fps "
       "(got %r)" % (eff.get("office_fps") if good else None))
    fps = mod.office_fps_settings()["fps"]
    ok(fps in (15, 20, 30), "office_fps_settings valid (%r)" % fps)

    def src(name):
        with open(os.path.join(ROOT, name),
                  encoding="utf-8") as f:
            return f.read()

    srv = src(os.path.join("scripts", "server.py"))
    ok('"office_fps": eff["office_fps"]' in srv,
       "GET api/settings exposes office_fps")
    idx = src("index.html")
    ok('name="se-fps"' in idx and idx.count('value="15"') >= 1,
       "settings has 15/20/30 radios")
    ok("office_fps: (() =>" in idx,
       "settings save posts office_fps")
    ok('window.__setOfficeFps' in idx,
       "settings load propagates via __setOfficeFps")
    ok("1000 / recepFps" in idx,
       "reception loop capped by recepFps")
    off = src("office_3d.html")
    ok("1000 / officeFps" in off and "< 33)" not in off,
       "office loop gated by officeFps (no 33ms gate left)")
    ok("loadOfficeFps();" in off,
       "office reads api/settings at boot")
    ok('kind === "office-fps"' in off,
       "office accepts live office-fps updates")

    if fails:
        print("%d FAILURES" % fails)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
