"""Embed office assets as base64 into office.html (one-shot).

Replaces __OFFICE_BG_B64__ and __PD_CHIBI_B64__ with data URLs so the page stays
a single offline file. Errors if placeholders are already gone.
"""
import base64

HTML = "office.html"
JOBS = [
    ("__OFFICE_BG_B64__", "output/office_bg.webp", "image/webp"),
    ("__PD_CHIBI_B64__", "output/pd_chibi.webp", "image/webp"),
]


def main():
    with open(HTML, encoding="utf-8") as f:
        s = f.read()
    for ph, path, mime in JOBS:
        assert s.count(ph) == 1, "placeholder %s count: %d" % (ph, s.count(ph))
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        s = s.replace(ph, "data:%s;base64," % mime + b64)
        print("embedded", path, len(b64), "chars")
    with open(HTML, "w", encoding="utf-8") as f:
        f.write(s)


if __name__ == "__main__":
    main()
