"""Source PC core checks (stdlib only).

Run: python scripts/pc_check.py. Pure-function checks for the PC core:
content-hash ids, page cleaning (running headers/footers, hyphens,
page-break joins, page metadata), numbered-section split, addresses,
omitted candidates, key terms, see-range checks, and open_ref reads.
No sockets, no model calls, no writes.
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tempfile.tempdir = os.path.join(ROOT, "scripts", "_tmpclip", "t")
os.makedirs(tempfile.tempdir, exist_ok=True)
from agents._frame import pc  # noqa: E402
from agents._frame import tools as tmod  # noqa: E402

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
NH = pc.clean_pages(["28 FINANCIAL DATA\nBody page one.",
                     "29 FINANCIAL DATA\nBody page two."])
ok(len(NH) == 1 and "Body page one. Body page two." in NH[0]["text"],
   "numbered running heads removed")
RV = [x for pair in zip(
    ["%d FINANCIAL DATA\nBody even %d." % (20 + 2 * i, i) for i in range(6)],
    ["ODD HEAD\nBody odd %d." % i for i in range(6)])
    for x in pair]
RVX = [p["text"] for p in pc.clean_pages(RV)]
ok(not any("FINANCIAL DATA" in t or "ODD HEAD" in t for t in RVX),
   "alternating recto/verso heads removed")
RARE = ["SHARED EDGE\nBody %d." % i for i in range(2)] + \
    ["Unique top %d.\nBody %d." % (i, i) for i in range(10)]
ok(sum("SHARED EDGE" in p["text"] for p in pc.clean_pages(RARE)) == 2,
   "rare edge repeat kept")
TF = pc.clean_pages(["Body one.\nBARS 25", "Body two.\nBARS 27",
                     "Body three.\nBARS 29"])
ok(not any("BARS" in p["text"] for p in TF),
   "trailing-number footers removed")
ok(pc._norm_key("2.1 MOTIVATION") == "2.1 motivation"
   and pc._norm_key("BARS 25") == "bars",
   "norm key keeps dotted numbers, drops page numbers")
ZSC = pc.split_sections(
    pc.clean_pages(["0 t t fragment\n1.1 Real\nBody."]))
ok([s["n"] for s in ZSC] == ["0", "1.1"]
   and ZSC[0]["paras"][0]["text"] == "0 t t fragment",
   "zero-numbered line is not a section")
DUP = pc.split_sections(
    pc.clean_pages(["1.1 A\nBody a.\n\n1.1 A again\nBody b."]))
ok([s["n"] for s in DUP] == ["1.1"]
   and DUP[0]["subsections"] == ["1.1 A again"]
   and len(DUP[0]["paras"]) == 4,
   "duplicate section number demoted to subsection")

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
SEC = ["Preface line.\n\n1.1 Getting started\nBody of one one.",
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
FIGS = [{"page": 1, "top": 100.0, "caption": "Figure 1 Getting started",
         "number": "1", "bbox": [10.0, 100.0, 200.0, 300.0], "w": 190.0,
         "h": 200.0, "blob": b"PNGDATA"}]
TABLES = [{"page": 2, "top": 50.0, "caption": "Table 1 Data",
           "number": "1", "bbox": [10.0, 50.0, 300.0, 150.0],
           "rows": [["a", "b"], ["c", "d"]],
           "markdown": "| a | b |\n| c | d |", "blob": None}]
entry = pc.build_entry(
    doc_id="a3f9c1d4e2b8", title="book", origin_file="book.pdf",
    order_id="ord-20261030-001", parsed_at="2026-10-30T03:00:00",
    added_by="sales_sam", sections=secs, figures=FIGS, tables=TABLES)
addrs = [p["addr"] for p in entry["paragraphs"]]
ok(addrs[0] == "s0/p1" and "s1.1/p1" in addrs and "s1.2/p1" in addrs,
   "paragraph addrs restart per section")
ok(entry["figures"][0]["addr"] == "fig1.1.1"
   and entry["figures"][0]["file"] == "fig1.png"
   and entry["tables"][0]["addr"] == "tab1.2.1",
   "section-based fig/tab addresses + fig files")
ok(entry["figures"][0]["caption"] == "Figure 1 Getting started"
   and entry["figures"][0]["printed_no"] == "1"
   and entry["figures"][0]["page"] == 1
   and entry["figures"][0]["described"] is False,
   "figure record keeps caption, page, undescribed")
ok(entry["tables"][0]["rows"] == [["a", "b"], ["c", "d"]]
   and entry["tables"][0]["generated_by"] == "pdfplumber",
   "table record keeps rows + generator")
ok("[fig1.1.1 p.1] Figure 1 Getting started" in
   [p["text"] for p in entry["paragraphs"]],
   "figure placeholder placed in text")
ok("[tab1.2.1 p.2] Table 1 Data" in
   [p["text"] for p in entry["paragraphs"]],
   "table placeholder placed in text")
ok(entry["chars"] == sum(len(p["text"]) for p in entry["paragraphs"]),
   "chars counted")
ok(entry["sections"][1] == {"n": "1.1", "heading": "Getting started",
                            "start": 1, "count": 5,
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
fgot = pc.open_ref(entry, "pc://source/a3f9c1d4e2b8#fig1.1.1")
ok(fgot["file"] == "fig1.png" and fgot["page"] == 1
   and fgot["caption"] == "Figure 1 Getting started"
   and fgot["described"] is False, "open_ref figure resolves")
tgot = pc.open_ref(entry, "pc://source/a3f9c1d4e2b8#tab1.2.1")
ok(tgot["rows"] == [["a", "b"], ["c", "d"]]
   and "| a | b |" in tgot["markdown"], "open_ref table resolves")
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
ph = pc.split_sections(pc.clean_pages(["1.1 Pics\nBody here."]))
ph[0]["paras"].append({"text": "[fig1.1.1 p.1] Cap", "pages": [1],
                       "has": ["fig1.1.1"]})
ok(any(c["what"] == "figure fig1.1.1" for c in pc.omitted_candidates(ph[0])),
   "figure tags read as figures, not formulas")

# ---- captions, chunks, caption terms ----
cap = pc.parse_caption("Figure 1.1 System overview")
ok(cap == {"label": "Figure 1.1", "number": "1.1",
           "rest": "System overview"}, "figure caption parsed")
ok(pc.parse_caption("Exhibit A Growth")["number"] == "A",
   "exhibit caption parsed")
ok(pc.parse_caption("FIGURE2.1 Averagedailyfrequency")["number"] == "2.1",
   "caps run-together caption parsed")
ok(pc.parse_caption("FIGURE2.1Averagedailyfrequency") == {
    "label": "FIGURE 2.1", "number": "2.1", "rest": "Averagedailyfrequency"},
   "glued caption number split")
ok(pc.parse_caption("Just body text.") is None,
   "non-caption rejected")
ct = pc.chunk_text("pc://source/abc#fig1.1.1", "figure", "Getting started",
                   "Figure 1 Cap", "A chart going up.", "Jan Feb",
                   ["42%"])
ok(ct.startswith("[REF pc://source/abc#fig1.1.1]\n")
   and "Getting started" in ct and "42%" in ct,
   "figure chunk carries ref + context")
ok(pc.caption_terms("Figure 1.1 System Overview") == ["System", "Overview"]
   and pc.caption_terms("Table 2 Regional Sales Data")
   == ["Regional", "Sales", "Data"],
   "caption terms extracted")
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

# ---- start prompt for Cleo/Rex (§8.6) ----
STRUCT = {"parts": [{"id": "p1", "heading": "1.1 Getting started",
                      "covers": "c", "keywords": ["k"]},
                     {"id": "p2", "heading": "9.9 Elsewhere",
                      "covers": "c", "keywords": ["k"]}]}
txt, meta = pc.start_prompt_for("Cleo", STRUCT, entry)
ok("Start prompt for Cleo" in txt and entry["ref"] in txt,
   "start prompt header names agent + entry")
ok("Body of one one." in txt and "p1: 1.1 Getting started" in txt,
   "start prompt carries matched section text")
ok("fig1.1.1" in txt, "start prompt notes section figures")
ok(meta == {"parts": 2, "missing": ["p2"]},
   "start prompt reports missing parts")
ok("no matching source section" in txt,
   "missing part marked in prompt")
txt2, _m2 = pc.start_prompt_for("Rex", STRUCT, entry, max_chars=20)
ok("Start prompt for Rex" in txt2 and "truncated" in txt2,
   "start prompt truncates long sections honestly")
MAPF = {"entry_summary": "A book about bars.",
        "sections": [{"ref": "s1.1", "summary": [{"text": "Bars talk.",
                                                 "see": "p1-p2"}],
                      "key_terms": ["bars"],
                      "omitted": [{"what": "number 42", "see": "p2"}]}]}
txt3, _m3 = pc.start_prompt_for("Cleo", STRUCT, entry, MAPF)
ok("A book about bars." in txt3 and "### Section list" in txt3
   and "s1.1 Getting started" in txt3 and "Bars talk. [p1-p2]" in txt3
   and "Terms: bars" in txt3 and "number 42 [p2]" in txt3
   and "### How to read more" in txt3 and "open_ref" in txt3,
   "start prompt carries summary, map, list, open_ref guide")
ok("(map pending)" in txt, "start prompt notes a pending map")

# ---- map skeleton ----
skel = pc.blank_map(entry, "model-x")
ok(skel["status"] == "pending" and skel["llm_model"] == "model-x"
   and skel["map_version"] == pc.MAP_VERSION
   and len(skel["sections"]) == len(entry["sections"]),
   "blank map skeleton")

# ---- ingest_source (temp root under gitignored scratch) ----
tmp = tempfile.mkdtemp(prefix="pc_ingest_")
try:
    IPAGES = ["CHAPTER ONE\n1.1 Getting started\nBody of one one.\n1",
              "CHAPTER ONE\n1.2 Moving on\nBody of one two.\n2"]
    IFIGS = [{"page": 1, "top": 100.0, "caption": "Figure 1 One",
              "number": "1", "bbox": [0.0, 100.0, 100.0, 200.0],
              "w": 100.0, "h": 100.0, "blob": b"PNGDATA"}]
    ITABS = [{"page": 2, "top": 50.0, "caption": "Table 1 Two",
              "number": "1", "bbox": [0.0, 50.0, 100.0, 120.0],
              "rows": [["x"]], "markdown": "| x |", "blob": None}]
    r1 = pc.ingest_source("ord-20261030-001", "book.pdf",
                          "2026-10-30T03:00:00", "sales_sam", IPAGES,
                          IFIGS, ITABS, 2, root=tmp)
    ok(r1["ref"].startswith("pc://source/")
       and len(r1["doc_id"]) == 12 and r1["duplicate"] is False,
       "ingest returns ref + id")
    ok(r1["figures"] == 1 and r1["tables"] == 1,
       "ingest returns figure/table counts")
    ok(r1["title"] == "book" and r1["sections"] == 2
       and r1["chars"] > 0, "ingest returns title/sections/chars")
    edir = pc.entry_dir("source", r1["doc_id"], root=tmp)
    with open(os.path.join(edir, "entry.json"),
              encoding="utf-8") as f:
        ientry = json.load(f)
    ok(ientry["title"] == "book" and ientry["order_id"]
       == "ord-20261030-001" and ientry["added_by"] == "sales_sam",
       "ingest provenance recorded")
    ok([s["n"] for s in ientry["sections"]] == ["1.1", "1.2"],
       "ingest sections split")
    with open(os.path.join(edir, "map.json"), encoding="utf-8") as f:
        imap = json.load(f)
    ok(imap["status"] == "pending", "ingest leaves map pending")
    with open(os.path.join(edir, "figures", "fig1.png"),
              "rb") as f:
        ok(f.read() == b"PNGDATA", "ingest stores figures as figN")
    ok(os.path.isfile(os.path.join(edir, "log.jsonl")),
       "ingest writes first log line")
    r2 = pc.ingest_source("ord-20261030-002", "book.pdf",
                          "2026-10-30T04:00:00", "sales_sam", IPAGES,
                          [], [], 0, root=tmp)
    ok(r2["duplicate"] is True and r2["ref"] == r1["ref"],
       "same content re-ingest is a no-op")
    with open(os.path.join(edir, "entry.json"),
              encoding="utf-8") as f:
        ok(json.load(f)["order_id"] == "ord-20261030-001",
           "duplicate keeps first provenance")
    got = pc.open_ref(ientry, r1["ref"] + "#s1.1/p2")
    ok(got["text"] == "Body of one one.",
       "ingested entry opens via ref")
    fz, tz = pc.assign_objects(
        pc.split_sections(pc.clean_pages(["1.1 Solo\nBody solo."])),
        [], [{"page": 1, "top": 10.0, "caption": "Table 9 Scanned",
              "number": "9", "bbox": [0.0, 10.0, 50.0, 60.0],
              "rows": None, "markdown": "", "blob": b"SCAN"}])
    ok(len(tz) == 0 and len(fz) == 1
       and fz[0]["kind"] == "table-image"
       and fz[0]["addr"] == "fig1.1.1",
       "failed table becomes a table-image figure")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ---- read tools (ROOT_OVERRIDE temp root) ----
tmp2 = tempfile.mkdtemp(prefix="pc_tools_")
try:
    pc.ROOT_OVERRIDE = tmp2
    for eid, tl in (("explain_cleo", ["pc_list_source", "pc_read_source",
                                      "open_ref"]),
                    ("sales_sam", ["read_md_section"])):
        ad = os.path.join(tmp2, "agents", eid)
        os.makedirs(ad)
        with open(os.path.join(ad, "agent.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"tools": tl}, f)
    r3 = pc.ingest_source("ord-20261030-009", "toolbook.pdf",
                          "2026-10-30T06:00:00", "sales_sam",
                          ["1.1 Tools\nBody tools here."], [], [], 0,
                          root=tmp2)
    os.makedirs(os.path.join(tmp2, "orders", "ord-20261030-009"))
    with open(os.path.join(tmp2, "orders", "ord-20261030-009",
                            "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"files": {"pc_ref": r3["ref"]}}, f)
    cleo = {"agent_dir": os.path.join(tmp2, "agents", "explain_cleo"),
            "order_id": "ord-20261030-009"}
    sam = {"agent_dir": os.path.join(tmp2, "agents", "sales_sam"),
           "order_id": "ord-20261030-009"}
    lst = tmod.pc_list_source(cleo, {})
    ok(lst["ref"] == r3["ref"] and lst["sections"][0]["n"] == "1.1",
       "pc_list_source lists entry sections")
    ok("Body tools here." in
       tmod.pc_read_source(cleo, {"section": "1.1"}).get("text", ""),
       "pc_read_source reads a section")
    ok(tmod.pc_read_source(
        cleo, {"ref": r3["ref"] + "#s1.1/p2"}).get("text")
       == "Body tools here.", "pc_read_source reads a ref")
    ok("error" in tmod.pc_read_source(cleo, {"section": "9.9"}),
       "pc_read_source bad section errors")
    ok("error" in tmod.pc_read_source(cleo, {}),
       "pc_read_source needs a target")
    ok(tmod.open_ref(
        cleo, {"ref": r3["ref"] + "#s1.1/p2"}).get("text")
       == "Body tools here.", "open_ref opens with grant")
    ok(tmod.open_ref(
        sam, {"ref": r3["ref"] + "#s1.1/p2"}).get("error", "")
       .startswith("no read grant"), "open_ref denies without grant")
    noref = tmod.pc_list_source(
        {"agent_dir": cleo["agent_dir"], "order_id": "ord-missing"}, {})
    ok("error" in noref, "tools report a missing order entry")
finally:
    pc.ROOT_OVERRIDE = None
    shutil.rmtree(tmp2, ignore_errors=True)

print("FAILURES: %d" % len(FAILS) if FAILS else "ALL PASS")
sys.exit(1 if FAILS else 0)
