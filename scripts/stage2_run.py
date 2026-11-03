"""Stage 2 driver: new PDF order -> full flow -> assemble -> video.mp4.

Resumable: approvals persist in STATUS.json, so re-running with
--from <node> skips approved stages (approved upstream results
may be reused). Usage:

  python scripts/stage2_run.py --src-order ord-20261102-030 \
      --new-order ord-20261103-001
  python scripts/stage2_run.py --resume <run_id> --from board_vera
  python scripts/stage2_run.py --assemble-only <run_id>
"""
import argparse
import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agents._frame import flow  # noqa: E402
from agents._frame import runner  # noqa: E402
from agents._frame import video as _video  # noqa: E402

TARGETS = ["sales_sam", "pd_marty", "explain_cleo", "case_rex",
           "plan_ash", "voice_wren", "board_penn", "part_split",
           "photo_pia", "image_gene", "anim_max", "board_vera",
           "slide_remy", "video_production", "final"]


def load_dotenv(path):
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def log(run_dir, msg):
    line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(os.path.join(run_dir, "driver.log"), "a",
                  encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def make_order(new_id, src_id):
    sdir = os.path.join(ROOT, "orders", src_id)
    ndir = os.path.join(ROOT, "orders", new_id)
    with open(os.path.join(sdir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    if os.path.isdir(ndir):
        raise RuntimeError("order dir exists already: %s" % ndir)
    os.makedirs(ndir, exist_ok=True)
    meta = {"id": new_id, "assignee": "sales_sam",
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "status": "in_production",
            "answers": meta.get("answers", {}),
            "files": {"source": "source.pdf"}}
    with open(os.path.join(ndir, "meta.json"), "w",
              encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    shutil.copyfile(os.path.join(sdir, "source.pdf"),
                    os.path.join(ndir, "source.pdf"))
    return ndir


def assemble(run_id):
    run_dir = os.path.join(ROOT, "runs", run_id)
    vdir = os.path.join(run_dir, "video_production")
    with open(os.path.join(vdir, "assembly.json"),
              encoding="utf-8") as f:
        cmd = json.load(f).get("ffmpeg_cmd", [])
    t0 = time.time()
    out = _video.run_ffmpeg(cmd, timeout_s=900, cwd=run_dir)
    rec = {"ok": bool(out.get("ok")),
           "seconds": round(time.time() - t0, 1),
           "error": out.get("error", "")}
    mp = os.path.join(vdir, "video.mp4")
    raw = os.path.join(run_dir, "video.mp4")
    # The fresh MP4 always replaces video_production/video.mp4: a
    # re-assembly after a fix must not leave the old file in place
    # (the first run 043822 showed the black build for 16 minutes).
    if rec["ok"] and os.path.isfile(raw):
        try:
            os.replace(raw, mp)
        except OSError:
            pass
    with open(os.path.join(vdir, "assemble.log"), "w",
              encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    log(run_dir, "assemble ok=%s seconds=%s err=%s"
        % (rec["ok"], rec["seconds"], rec["error"][:200]))
    return rec["ok"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src-order", default="ord-20261102-030")
    ap.add_argument("--new-order", default="")
    ap.add_argument("--resume", default="")
    ap.add_argument("--from", dest="from_node", default="")
    ap.add_argument("--assemble-only", default="")
    a = ap.parse_args()
    load_dotenv(os.path.join(ROOT, ".env"))

    if a.assemble_only:
        ok = assemble(a.assemble_only)
        return 0 if ok else 1

    with open(os.path.join(ROOT, "data", "flows", "default.json"),
              encoding="utf-8") as f:
        dflt = json.load(f)

    if a.resume:
        run_id = a.resume
        order_id = json.load(open(os.path.join(
            ROOT, "runs", run_id, "STATUS.json"),
            encoding="utf-8")).get("order_id", "")
    else:
        order_id = a.new_order or ("ord-%s-001"
                                   % time.strftime("%Y%m%d"))
        make_order(order_id, a.src_order)
        run_id = flow.new_run_id()
    run_dir = os.path.join(ROOT, "runs", run_id)
    os.makedirs(run_dir, exist_ok=True)
    log(run_dir, "driver start order=%s run=%s from=%s"
        % (order_id, run_id, a.from_node or "top"))

    targets = TARGETS
    if a.from_node:
        targets = TARGETS[TARGETS.index(a.from_node):]
    for t in targets:
        t0 = time.time()
        got = flow.step_run(dflt, order_id, runner.run, t,
                            run_id=run_id, flow_id="default")
        log(run_dir, "step %s ok=%s ran=%s err=%s (%.0fs)"
            % (t, got.get("ok"), got.get("ran"),
               str(got.get("error", ""))[:300],
               time.time() - t0))
        if not got.get("ok"):
            return 1
        if t == "final":
            break
        ap_ = flow.approve_node(run_id, t)
        log(run_dir, "approve %s ok=%s err=%s"
            % (t, ap_.get("ok"), str(ap_.get("error", ""))[:200]))
        if not ap_.get("ok"):
            return 1
    ok = assemble(run_id)
    log(run_dir, "driver done ok=%s" % ok)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
