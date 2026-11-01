"""Gallery card tests, J20 (fixtures only, no server, no browser).

Builds temp orders/ + runs/ trees and checks gallery.gallery_cards:
card shape, status precedence, title fallbacks, latest-run pick,
length fallbacks, URL shapes, and the mp4 serving dependency.
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agents._frame import board  # noqa: E402
from agents._frame import gallery  # noqa: E402

fails = 0


def ok(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails += 1


PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
       b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
       b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
       b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")


def wjson(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def mkorder(od, oid, created="2026-11-01T10:00:00", closed=False,
            files=None):
    wjson(os.path.join(od, oid, "meta.json"),
          {"id": oid, "status": "in_production", "created": created,
           "closed": closed, "files": files or {}})


def mkvideo(rd, run, oid, with_video=True, with_table=True,
            duration=None, total=None, slides=True):
    vd = os.path.join(rd, run, "video_production")
    os.makedirs(vd, exist_ok=True)
    wjson(os.path.join(rd, run, "STATUS.json"),
          {"run_id": run, "order_id": oid, "state": "done"})
    if with_table:
        wjson(os.path.join(vd, "storyboard_table.json"),
              {"rows": []})
    if duration is not None or total is not None:
        pass
    if duration is not None:
        wjson(os.path.join(vd, "result.json"),
              {"categories": {"video": {"data": {
                  "duration_s": duration}}}})
    if total is not None:
        wjson(os.path.join(vd, "assembly.json"),
              {"total_s": total, "segments": []})
    if with_video:
        with open(os.path.join(vd, "video.mp4"), "wb") as f:
            f.write(b"fixture-video-bytes")
    if slides:
        sd = os.path.join(rd, run, "slide_remy", "slides")
        os.makedirs(sd, exist_ok=True)
        with open(os.path.join(sd, "s1-c1.png"), "wb") as f:
            f.write(PNG)


def main():
    tmp = tempfile.mkdtemp(prefix="galfix_")
    try:
        od = os.path.join(tmp, "orders")
        rd = os.path.join(tmp, "runs")
        os.makedirs(od)
        os.makedirs(rd)

        mkorder(od, "ord-20261101-101",
                files={"pc_title": "Photosynthesis"})
        mkvideo(rd, "run-vid", "ord-20261101-101",
                duration=612)
        with open(os.path.join(od, "ord-20261101-101",
                               "TIMELINE.md"), "w") as f:
            f.write("# t\n")

        mkorder(od, "ord-20261101-102",
                created="2026-11-01T09:00:00",
                files={"upload_name": "My Talk.pdf"})
        mkvideo(rd, "run-tab", "ord-20261101-102",
                with_video=False, total=300)

        mkorder(od, "ord-20261101-103", closed=True,
                created="2026-11-01T08:00:00")
        mkvideo(rd, "run-closed", "ord-20261101-103",
                duration=120)

        mkorder(od, "ord-20261101-104")  # run, no outputs
        vd = os.path.join(rd, "run-empty", "video_production")
        os.makedirs(vd, exist_ok=True)
        wjson(os.path.join(rd, "run-empty", "STATUS.json"),
              {"run_id": "run-empty",
               "order_id": "ord-20261101-104",
               "state": "done"})

        mkorder(od, "ord-20261101-105")  # no run at all

        mkorder(od, "ord-20261101-106",  # newer run wins
                created="2026-11-01T07:00:00")
        mkvideo(rd, "run-old", "ord-20261101-106",
                duration=60)
        mkvideo(rd, "run-new", "ord-20261101-106",
                with_video=False, total=61)
        old_t = os.path.getmtime(os.path.join(rd, "run-old"))
        os.utime(os.path.join(rd, "run-new"), (old_t + 10,
                                               old_t + 10))

        cards = gallery.gallery_cards(od, rd)
        by = {c["order_id"]: c for c in cards}
        ok(sorted(by) == ["ord-20261101-101", "ord-20261101-102",
                          "ord-20261101-103", "ord-20261101-106"],
           "only qualifying orders get cards (%s)"
           % sorted(by))
        ok([c["order_id"] for c in cards]
           == ["ord-20261101-101", "ord-20261101-102",
               "ord-20261101-103", "ord-20261101-106"],
           "newest first")

        v = by["ord-20261101-101"]
        ok(v["status"] == "video" and v["title"] == "Photosynthesis"
           and v["length_s"] == 612 and v["run_id"] == "run-vid"
           and v["closed"] is False, "video card fields (%s)" % v)
        ok(v["video_url"] == "/api/flows/runs/run-vid/file"
           "?node=video_production&path=video.mp4",
           "video url (%s)" % v["video_url"])
        ok(v["table_url"] == "/api/flows/runs/run-vid/file"
           "?node=video_production&name=storyboard_table.json",
           "table url (%s)" % v["table_url"])
        ok(v["thumb_url"] == "/api/flows/runs/run-vid/file"
           "?node=slide_remy&path=slides/s1-c1.png",
           "thumb url (%s)" % v["thumb_url"])
        ok(v["log_url"] == "/api/orders/ord-20261101-101/projectlog"
           "?name=TIMELINE.md", "log url (%s)" % v["log_url"])

        t = by["ord-20261101-102"]
        ok(t["status"] == "table" and t["video_url"] is None
           and t["length_s"] == 300, "table-only card (%s)"
           % t["status"])
        ok(t["title"] == "My Talk", "title from upload stem")
        ok(t["log_url"] is None, "no log url without TIMELINE.md")

        c = by["ord-20261101-103"]
        ok(c["status"] == "closed"
           and c["video_url"] is not None,
           "closed wins over video, play still linked")
        ok(c["title"] == "ord-20261101-103",
           "title falls back to order id")

        n = by["ord-20261101-106"]
        ok(n["run_id"] == "run-new" and n["status"] == "table",
           "latest run wins (%s)" % n["run_id"])

        ok(gallery.order_card(od, rd, "bogus") is None,
           "bad order id gives no card")
        ok(gallery.gallery_cards(os.path.join(tmp, "nope"),
                                 rd) == [],
           "missing orders root gives no cards")

        # Play dependency: mp4 served, traversal still blocked.
        vp = os.path.join(rd, "run-vid", "video_production")
        got = board.safe_run_path(rd, "run-vid", "video_production",
                                  "video.mp4")
        ok(got is not None and got.endswith("video.mp4"),
           "mp4 passes the file gate")
        ok(board.safe_run_path(rd, "run-vid", "video_production",
                               "../STATUS.json") is None,
           "dotdot still blocked")
        ok(board.safe_run_path(rd, "run-vid", "video_production",
                               "video.exe") is None,
           "foreign extension still blocked")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print("%d FAILURES" % fails)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
