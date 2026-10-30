"""Source PC core checks (stdlib only).

Run: python scripts/pc_check.py. Pure-function checks for the PC core:
content-hash ids, page cleaning (running headers/footers, hyphens,
page-break joins, page metadata), numbered-section split, addresses,
omitted candidates, key terms, see-range checks, and open_ref reads.
No sockets, no model calls, no writes.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agents._frame import pc  # noqa: E402

FAILS = []


def ok(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


# ---- content-hash ids (§9) ----
ok(pc.content_id("Hello  World") == pc.content_id("hello world"),
   "id ignores case/whitespace")
ok(len(pc.content_id("x")) == 12
   and all(c in "0123456789abcdef" for c in pc.content_id("x")),
   "id is 12 hex chars")
ok(pc.content_id("aaa") != pc.content_id("aab"), "different text, id differs")
ok(pc.entry_ref("source", "a3f9c1d4e2b8")
   == "pc://source/a3f9c1d4e2b8", "entry ref shape")

# ---- cleaning: running headers/footers ----
PAGES = ["CHAPTER ONE\nThe story begins here.\n1",
         "CHAPTER ONE\nIt continues on and on.\n2",
         "CHAPTER ONE\nAnd it ends right here.\n3"]
paras = pc.clean_pages(PAGES)
texts = [p["text"] for p in paras]
ok(all("CHAPTER ONE" not in t for t in texts),
   "repeating header removed")
ok(all(t.strip() not in ("1", "2", "3") for t in texts),
   "page-number footers removed")
ok(any("begins" in t for t in texts)
   and any("continues" in t for t in texts),
   "body text kept")
ok(not any("INTRODUCTION" in t for t in
           [p["text"] for p in pc.clean_pages(
               ["INTRODUCTION\nBody one.", "INTRODUCTION\nBody two."])]),
   "2-page repeat removed")

# body refrains are not headers: only edge zones count
REFRAIN = ["Top line one.\n\nThe moral is clear.\n\nBottom one.",
           "Top line two.\n\nThe moral is clear.\n\nBottom two."]
ok(sum("moral" in p["text"] for p in pc.clean_pages(REFRAIN)) == 2,
   "mid-page repeats kept")
ok("42" in [p["text"] for p in pc.clean_pages(["First.\n42\nLast."])][1],
   "mid-page bare number kept")

# ---- cleaning: hyphen joins ----
ok(pc.clean_pages(["The finan-\ncial result."])[0]["text"]
   == "The financial result.", "hyphen + lowercase joins")
ok(pc.clean_pages(["A well-\nKnown fact."])[0]["text"]
   == "A well-Known fact.", "hyphen + capital keeps hyphen")

# ---- cleaning: page-break joins + page metadata ----
JOIN = ["First page tells the story of finan-",
        "cial markets and how they grow."]
jp = pc.clean_pages(JOIN)
ok(len(jp) == 1 and jp[0]["text"]
   == "First page tells the story of financial markets and how they grow.",
   "page-break paragraph joined")
ok(jp[0]["pages"] == [1, 2], "page numbers kept as metadata")
ok(not any("## Page" in p["text"] for p in jp),
   "no page markers in text")

# wrapped sentences join; blank lines split
WRAP = ["One sentence here.\nSecond starts here and\nruns on a bit.\n\n"
        "New paragraph."]
wp = pc.clean_pages(WRAP)
ok(len(wp) == 2 and wp[0]["text"]
   == "One sentence here. Second starts here and runs on a bit.",
   "wrapped lines join, blank line splits")

# a heading at the top of a page stays separate
CAP = ["Previous paragraph ends here",
       "INTRODUCTION", "Fresh text follows."]
cp = pc.clean_pages(CAP)
ok(len(cp) == 3 and cp[1]["text"] == "INTRODUCTION",
   "caps heading not glued to previous page")

# ---- section split ----
SEC = ["Preface line.\n\n1.1 Getting started\nBody of one one.\n"
       "1.1.1 First steps\nDeep detail here.\n\n1.2 Moving on\n"
       "Body of one two."]
secs = pc.split_sections(pc.clean_pages(SEC))
ok([s["n"] for s in secs] == ["0", "1.1", "1.2"],
   "preamble is section 0, numbered split in order")
ok(secs[1]["subsections"] == ["1.1.1 First steps"],
   "deeper number is a subsection")
ok(secs[1]["paras"][2]["text"] == "1.1.1 First steps",
   "subsection heading kept as paragraph")
ok(pc.split_sections(pc.clean_pages(["Just prose, no numbers."]))[0]["n"]
   == "1", "unheaded doc is one section")

# lists stay separate paragraphs
LST = ["Intro line:\n- apples\n- oranges\n"]
lp = pc.clean_pages(LST)
ok(len(lp) == 3 and lp[1]["text"] == "- apples",
   "list items stay separate")

# ---- entry assembly + addresses ----
entry = pc.build_entry(
    doc_id="a3f9c1d4e2b8", title="book", origin_file="book.pdf",
    order_id="ord-20261030-001", parsed_at="2026-10-30T03:00:00",
    added_by="sales_sam", sections=secs,
    images=[("p01-img01.png", 1, 1)])
addrs = [p["addr"] for p in entry["paragraphs"]]
ok(addrs[0] == "s0/p1" and "s1.1/p1" in addrs and "s1.2/p1" in addrs,
   "paragraph addrs restart per section")
ok(entry["images"] == [{"file": "p01-img01.png", "caption": "",
                        "addr": "fig1.1"}],
   "figure addresses from images")
ok(entry["chars"] == sum(len(p["text"]) for p in entry["paragraphs"]),
   "chars counted")
ok(entry["sections"][1] == {"n": "1.1", "heading": "Getting started",
                            "start": 1, "count": 4,
                            "subsections": ["1.1.1 First steps"]},
   "section index points into paragraphs")

# ---- open_ref ----
got = pc.open_ref(entry, "pc://source/a3f9c1d4e2b8#s1.1/p2")
ok(got["text"] == "Body of one one.",
   "open_ref paragraph verbatim")
ok(got["provenance"]["order_id"] == "ord-20261030-001"
   and got["provenance"]["title"] == "book",
   "open_ref provenance attached")
ok("Body of one one" in
   pc.open_ref(entry, "pc://source/a3f9c1d4e2b8#s1.1")["text"],
   "open_ref whole section")
ok(pc.open_ref(entry, "pc://source/a3f9c1d4e2b8#fig1.1")["file"]
   == "p01-img01.png", "open_ref figure resolves")
for bad in ("pc://source/WRONGIDHERE12#s1.1/p1",
            "pc://source/a3f9c1d4e2b8#s9.9/p1",
            "pc://theory/a3f9c1d4e2b8#p1", "not-a-ref"):
    try:
        pc.open_ref(entry, bad)
        ok(False, "bad ref rejected: " + bad)
    except (KeyError, ValueError):
        ok(True, "bad ref rejected: " + bad)

# ---- omitted candidates + key terms ----
OM = pc.split_sections(pc.clean_pages(
    ["1.1 Numbers\nSales grew 42 percent in 2024.\n"
     "For example, the spring launch doubled.\nSee Figure 3 for proof.\n"
     '- "Baptism" changed **everything** for Ada.\n']))
cands = pc.omitted_candidates(OM[0])
whats = " ".join(c["what"] for c in cands)
ok("42" in whats and "Figure 3" in whats and "For example" in whats,
   "omitted finds numbers, examples, figure mentions")
LC = pc.split_sections(pc.clean_pages(["1.1 Lists\n- apples\n- oranges\n"]))
lc = pc.omitted_candidates(LC[0])
ok(any("apples" in c["what"] and c["see"] == "p2" for c in lc),
   "list items are candidates")
terms = pc.key_terms(OM[0])
ok("Baptism" in terms and "everything" in terms and "Ada" in terms,
   "key terms: quoted, bold, capitalized")
ok("Sales" not in terms, "sentence-initial capital excluded")

# ---- see ranges ----
ok(pc.check_see("p1-p3", 4) and pc.check_see("p4", 4),
   "valid see ranges pass")
ok(not pc.check_see("p5", 4) and not pc.check_see("p3-p1", 4)
   and not pc.check_see("x", 4) and not pc.check_see("p1-p4", 3),
   "bad see ranges fail")
om = pc.resolve_omitted([{"what": "a", "see": "p2"},
                         {"what": "b", "see": "p4"}],
                        [{"text": "t", "see": "p1-p3"}])
ok(om == [{"what": "b", "see": "p4"}],
   "covered candidates leave the omitted list")

# ---- map skeleton ----
skel = pc.blank_map(entry, "model-x")
ok(skel["status"] == "pending" and skel["llm_model"] == "model-x"
   and skel["map_version"] == pc.MAP_VERSION
   and len(skel["sections"]) == len(entry["sections"]),
   "blank map skeleton")

print("FAILURES: %d" % len(FAILS) if FAILS else "ALL PASS")
sys.exit(1 if FAILS else 0)
