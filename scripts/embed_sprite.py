"""Embed output/pd_chibi.png as base64 into office_mockup.html (one-shot).

Replaces the __PD_CHIBI_B64__ placeholder with a data URL so the mockup stays
a single offline file. Safe to run once; errors if already embedded.
"""
import base64

HTML = "office_mockup.html"
PH = "__PD_CHIBI_B64__"


def main():
    with open("output/pd_chibi.webp", "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    with open(HTML, encoding="utf-8") as f:
        s = f.read()
    assert s.count(PH) == 1, "placeholder count: %d" % s.count(PH)
    s = s.replace(PH, "data:image/png;base64," + b64)
    with open(HTML, "w", encoding="utf-8") as f:
        f.write(s)
    print("embedded", len(b64), "chars")


if __name__ == "__main__":
    main()
