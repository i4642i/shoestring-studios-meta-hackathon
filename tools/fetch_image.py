"""Downloads chosen web images (several at once) into this block's files, checks they are real images,
and gives back the local file paths to put in photo_candidates."""

import pathlib
import re

from functions._common import download, image_ext

NAME = "fetch_image"
DESC = ("Download up to 8 chosen images at once: [{cut_id, image_url}]. Returns the local file for each "
        "(use it as 'file' in photo_candidates) or why it failed (then try another hit).")
SCHEMA = {
    "type": "object",
    "properties": {"images": {"type": "array", "minItems": 1, "maxItems": 8, "items": {
        "type": "object",
        "properties": {"cut_id": {"type": "string"}, "image_url": {"type": "string"}},
        "required": ["cut_id", "image_url"]}}},
    "required": ["images"],
}


def _shrink(path: pathlib.Path) -> pathlib.Path:
    """Large or unusual images become a JPEG of at most 1920 px wide (Remotion reads it fast)."""
    try:
        from PIL import Image
        im = Image.open(path)
        if im.width <= 1920 and path.suffix in (".jpg", ".png"):
            return path
        im = im.convert("RGB")
        if im.width > 1920:
            im = im.resize((1920, int(im.height * 1920 / im.width)))
        out = path.with_suffix(".jpg")
        im.save(out, quality=88)
        if out != path:
            path.unlink(missing_ok=True)
        return out
    except Exception:
        return path


def run(ctx, args):
    out_dir = pathlib.Path(ctx["files_dir"]) / "photos"
    got = []
    for k, it in enumerate(args["images"][:8], 1):
        cut = re.sub(r"[^A-Za-z0-9_-]", "_", it["cut_id"])
        tmp = out_dir / f"{cut}_{k}.bin"
        try:
            download(it["image_url"], tmp, timeout=40)
            ext = image_ext(tmp.read_bytes()[:16])
            if not ext:
                tmp.unlink(missing_ok=True)
                got.append({"cut_id": it["cut_id"], "error": "not an image (the site may block downloads); pick another hit"})
                continue
            f = _shrink(tmp.rename(tmp.with_suffix(ext)))
            got.append({"cut_id": it["cut_id"], "file": str(f.resolve()), "image_url": it["image_url"]})
        except Exception as e:           # blocked, timeout, too large
            tmp.unlink(missing_ok=True)
            got.append({"cut_id": it["cut_id"], "error": f"download failed ({type(e).__name__}); pick another hit"})
    return {"images": got}
