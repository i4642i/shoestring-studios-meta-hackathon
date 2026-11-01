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
FEW = ["Top %d.\nBody %d." % (i, i) for i in range(6)] + \
    ["BARS 25\nBody six.", "BARS 27\nBody seven."]
ok(not any("BARS" in p["text"] for p in pc.clean_pages(FEW)),
   "short-lived numbered head stripped at 2 repeats")
PF = ["Top %d.\n\nMiddle %d.\n\nBottom %d." % (i, i, i)
      for i in range(10)] + \
    ["Same words\n\nMiddle ten.\n\nBottom ten.",
     "Same words\n\nMiddle eleven.\n\nBottom eleven."]
ok(sum("Same words" in p["text"] for p in pc.clean_pages(PF)) == 2,
   "plain edge line kept below a third")
ok(pc._norm_key("2.1 MOTIVATION") == "2.1 motivation"
   and pc._norm_key("BARS 25") == "bars",
   "norm key keeps dotted numbers, drops page numbers")
ZSC = pc.split_sections(
    pc.clean_pages(["0 t t fragment\n1.1 Real\nBody."]))
ok([s["n"] for s in ZSC] == ["0", "1.1"]
   and ZSC[0]["paras"][0]["text"] == "0 t t fragment",
   "zero-numbered line is not a section")
WRP = pc.split_sections(pc.clean_pages(
    ["Ends mid-sentence recorded as\n10 separate transactions here."]))
ok([s["n"] for s in WRP] == ["1"]
   and "recorded as 10 separate" in WRP[0]["paras"][0]["text"],
   "wrapped line starting with a bare number joins")
BHD = pc.split_sections(pc.clean_pages(
    ["Body ends here.\n10 APPENDIX\nAppendix text."]))
ok([s["n"] for s in BHD] == ["1"]
   and "10 APPENDIX" in " ".join(
       p["text"] for p in BHD[0]["paras"]),
   "bare number stays body text after a sentence end")
FNT = pc.split_sections(pc.clean_pages(
    ["Real text ends here.\n\n1 Berkeley Lab, http://www.lbl.gov/about.\n\n1.1 Next real.\nBody."]))
ok([s["n"] for s in FNT] == ["0", "1.1"]
   and "Berkeley Lab" in " ".join(
       p["text"] for p in FNT[0]["paras"]),
   "footnote number never becomes a section")
TBL = pc.split_sections(pc.clean_pages(
    ["Row above.\n\n3 10 X X\n\n4 17 X X X\n\n"
     "1.2 After.\nBody."]))
ok([s["n"] for s in TBL] == ["0", "1.2"],
   "table row numbers never become sections")
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
   and entry["tables"][0]["described_by"] == "pdfplumber",
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
                            "subsections": ["1.1.1 First steps"],
                            "non_content": False},
   "section index points into paragraphs")
NC = pc.split_sections(pc.clean_pages(
    ["1.1 Body\nText here.\n\nEXERCISES\n\n1.1 Do this.\n\n"
     "REFERENCES 41\n"]))
ok([s["n"] for s in NC] == ["1.1", "exercises", "references"]
   and NC[1]["non_content"] is True and NC[2]["non_content"] is True
   and NC[1]["subsections"] == ["1.1 Do this."]
   and NC[1]["paras"][1]["text"] == "1.1 Do this.",
   "non-content parts split off, exercise numbers demoted")

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
rgot = pc.open_ref(entry, "pc://source/a3f9c1d4e2b8#s1.1/p2-p3")
ok(rgot["kind"] == "range" and "Body of one one." in rgot["text"],
   "open_ref para range resolves")
try:
    pc.open_ref(entry, "pc://source/a3f9c1d4e2b8#s1.1/p4-p9")
    ok(False, "short range rejected")
except KeyError:
    ok(True, "short range rejected")
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
ok(any(c["what"] == "figure: fig1.1.1"
       for c in pc.omitted_candidates(ph[0])),
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
KT = {"paras": [
    {"text": "Market risk models use the “ETF trick” every day.",
     "bold": ["Inverse Variance"]},
    {"text": "Still, the Principal Component view wins. Risk parity "
             "follows Value-at-Risk rules."},
    {"text": "He told The Manager twice."}]}
kts = pc.key_terms(KT)
ok("ETF trick" in kts and "Inverse Variance" in kts
   and "Principal Component" in kts and "Value-at-Risk" in kts
   and "The Manager" in kts and "Manager" not in kts
   and "Market" not in kts and "Still" not in kts
   and "Risk" not in kts and "Principal" not in kts
   and "Component" not in kts and "The" not in kts,
   "key terms: curly quotes, bold, phrases; initials dropped")
RK = {"paras": [{"text": '"Solo" fund notes Alpha Beta pairs. '
                          'Alpha Beta repeats daily while Zed watches '
                          'Zed closely.'}]}
ok(pc.rank_key_terms(RK) == ["Solo", "Alpha Beta", "Zed"],
   "terms ranked: quoted beats frequent, phrases beat singles")

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
SUMS = [{"text": "Tick bars sample every 1,000 transactions.",
         "see": "p1-p2"}]
om2 = pc.resolve_omitted(
    [{"what": "number 1,000", "see": "p1"},
     {"what": "number 42", "see": "p2"},
     {"what": "example: TWAP algorithms leave footprints.", "see": "p2"},
     {"what": "mention Figure 3", "see": "p2"}], SUMS,
    "pc://source/abc#s1.1")
ok([c["what"] for c in om2]
   == ["number 42", "example: TWAP algorithms leave footprints.",
       "mention Figure 3"]
   and om2[0]["ref"] == "pc://source/abc#s1.1/p2",
   "omitted judged by summary text, with exact refs")
NOC = pc.split_sections(pc.clean_pages(
    ["1.1 Vals\n(cid:2) first (cid:2) second\nSee 2.3.1 and 42 things."]))
nwhats = " ".join(c["what"] for c in pc.omitted_candidates(NOC[0]))
ok("number 2" not in nwhats and "number 2.3.1" not in nwhats
   and "number 42" in nwhats,
   "bullets and dotted numbers are not number candidates")
DUP = pc.resolve_omitted([{"what": "number 7", "see": "p1"},
                           {"what": "number 7", "see": "p3"}],
                          [{"text": "nothing here.", "see": "p1-p3"}],
                          "pc://source/abc#s1.1")
ok(DUP == [{"what": "number 7", "see": "p1",
            "ref": "pc://source/abc#s1.1/p1"}],
   "identical omitteds merge into first occurrence")

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
ok("Start prompt for Rex" in txt2
   and "p2-p5 not included -> open_ref pc://source/a3f9c1d4e2b8"
       "#s1.1/p2-p5" in txt2,
   "start prompt names the missing range + open_ref")
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
NCENTRY = {"ref": entry["ref"], "doc_id": entry["doc_id"],
           "paragraphs": entry["paragraphs"],
           "sections": entry["sections"] + [
               {"n": "exercises", "heading": "EXERCISES", "start": 0,
                "count": 0, "subsections": [], "non_content": True}]}
ok([s["ref"] for s in pc.blank_map(NCENTRY, "m")["sections"]]
   == ["s" + s["n"] for s in entry["sections"]],
   "blank map skips non-content sections")
txtnc, _mnc = pc.start_prompt_for("Cleo", STRUCT, NCENTRY)
ok("sexercises" not in txtnc and "EXERCISES" not in txtnc,
   "start prompt section list skips non-content")

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
    ok(all(isinstance(s.get("terms_all"), list)
           for s in ientry["sections"]),
       "ingest stores full ranked terms per section")
    t1 = pc.ingest_theory("https://example.com/twap", "TWAP Basics",
                          "Example", "2024-01-01", "2026-10-30T00:00:00",
                          "explain_cleo",
                          "TWAP slices orders over time.\n\nIt suits "
                          "patient traders using VWAP daily.", root=tmp)
    tentry = json.load(open(os.path.join(
        tmp, "storage", "_pc", "theory", "entries", t1["doc_id"],
        "entry.json"), encoding="utf-8"))
    ok(t1["duplicate"] is False
       and [p["addr"] for p in tentry["paragraphs"]] == ["p1", "p2"]
       and tentry["sections"][0]["terms_all"]
       and tentry["url"] == "https://example.com/twap",
       "theory ingest: pN addrs, provenance, terms")
    t2 = pc.ingest_theory("https://example.com/other", "TWAP Basics",
                          "Example", "2024-01-01", "2026-10-30T00:00:00",
                          "explain_cleo",
                          "TWAP slices orders over time.\n\nIt suits "
                          "patient traders using VWAP daily.", root=tmp)
    ok(t2["duplicate"] is True and t2["doc_id"] == t1["doc_id"],
       "same content under a new url is a no-op")
    t3 = pc.ingest_theory("https://example.com/twap", "TWAP Basics",
                          "Example", "2024-01-02", "2026-10-30T00:00:00",
                          "explain_cleo", "TWAP slices orders over time "
                          "in small pieces.\n\nIt suits patient traders "
                          "using VWAP daily.",
                          root=tmp)
    ok(t3["duplicate"] is False and t3["doc_id"] != t1["doc_id"]
       and t3["supersedes"] == t1["doc_id"],
       "same url with changed content supersedes")
    a1 = pc.ingest_article("https://example.com/flash", "Flash Crash",
                           "News", "2010-05-06", "2026-10-30T00:00:00",
                           "case_rex", "Stocks fell fast.\n\nThey came "
                           "back.", root=tmp)
    ok(a1["ref"].startswith("pc://article/"),
       "article ingest ref shape")
    got = pc.open_ref(tentry, t1["ref"] + "#p2")
    ok(got["text"] == "It suits patient traders using VWAP daily."
       and got["provenance"]["url"] == "https://example.com/twap",
       "open_ref bare theory paragraph + provenance")
    got = pc.open_ref(tentry, t1["ref"] + "#p1-p2")
    ok(got["kind"] == "range" and "TWAP slices" in got["text"],
       "open_ref theory range")
    got = pc.open_ref(tentry, t1["ref"] + "#g1")
    ok(got["kind"] == "group" and "patient traders" in got["text"],
       "open_ref theory group")
    ok(pc.blank_map(tentry, "m")["sections"][0]["ref"] == "g1",
       "theory map uses g-prefix")
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
    pc.set_recipients("source", r3["doc_id"], "ord-20261030-009",
                        ["explain_cleo"], "sales_sam", kind="map",
                        root=tmp2)
    cleo = {"agent_dir": os.path.join(tmp2, "agents", "explain_cleo"),
            "producer": "explain_cleo", "order_id": "ord-20261030-009"}
    sam = {"agent_dir": os.path.join(tmp2, "agents", "sales_sam"),
           "producer": "sales_sam", "order_id": "ord-20261030-009"}
    rex = {"agent_dir": os.path.join(tmp2, "agents", "explain_cleo"),
           "producer": "case_rex", "order_id": "ord-20261030-009"}
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
    ok(tmod.pc_list_source(rex, {}).get("error")
       == "no access to this item",
       "unlisted agent refused on list")
    ok(tmod.pc_read_source(rex, {"section": "1.1"}).get("error")
       == "no access to this item",
       "unlisted agent refused on read")
    ok(tmod.open_ref(
        rex, {"ref": r3["ref"] + "#s1.1/p2"}).get("error")
       == "no access to this item",
       "unlisted agent refused on open_ref")
    full = tmod.pc_read_source(cleo, {"ref": r3["ref"]})
    ok(full.get("kind") == "full-text"
       and "Body tools here." in full.get("text", ""),
       "bare entry ref reads the whole entry")
    ent = pc.load_entry_by_ref(r3["ref"], root=tmp2)
    ok(pc.may_read(ent, "explain_cleo", "ord-20261030-009")
       and not pc.may_read(ent, "case_rex", "ord-20261030-009")
       and not pc.may_read(ent, "explain_cleo", "ord-other"),
       "may_read gates agent + order")
    del ent["recipients"]
    ok(pc.may_read(ent, "anyone", "ord-20261030-009"),
       "legacy entry without recipients stays open")
    rows = pc.set_recipients("source", r3["doc_id"], "ord-20261030-009",
                             ["case_rex"], "sales_sam", kind="map",
                             root=tmp2)
    ok(sorted(r["agent"] for r in rows
              if r["order_id"] == "ord-20261030-009")
       == ["case_rex", "explain_cleo"],
       "set_recipients merges per agent")
    md = pc.entry_markdown(pc.load_entry_by_ref(r3["ref"], root=tmp2))
    ok("## 1.1 Tools" in md and "(ref: %s#s1.1)" % r3["ref"] in md
       and "Body tools here." in md,
       "entry_markdown keeps exact headings + refs")
    text, meta = pc.prompt_chunks_for("explain_cleo", "ord-20261030-009",
                                      [r3["ref"]],
                                      os.path.join(tmp2, "runs"))
    ok(meta["included"] == [r3["ref"]] and meta["denied"] == []
       and "s1.1 Tools" in text and r3["ref"] in text,
       "prompt chunk includes listed entry")
    text2, meta2 = pc.prompt_chunks_for("case_rex", "ord-20261030-009",
                                        [r3["ref"]],
                                        os.path.join(tmp2, "runs"))
    ok(meta2["included"] == [r3["ref"]] and "s1.1 Tools" in text2,
       "merged recipient gets the chunk too")
    _t3, meta3 = pc.prompt_chunks_for("pd_marty", "ord-20261030-009",
                                      [r3["ref"]],
                                      os.path.join(tmp2, "runs"))
    ok(meta3["included"] == [] and meta3["denied"] == [r3["ref"]],
       "non-listed entry contributes no chunk")
    pcp = r3["ref"] + "#s1.1/p2"
    pc.set_recipients("source", r3["doc_id"], "ord-20261030-009",
                      ["board_penn"], "plan_ash", kind="map",
                      parts=[pcp], root=tmp2)
    penn = {"agent_dir": cleo["agent_dir"], "producer": "board_penn",
            "order_id": "ord-20261030-009"}
    ok(tmod.pc_read_source(penn, {"ref": pcp}).get("kind") == "paragraph",
       "parts-listed member reads inside the part")
    ok(tmod.pc_read_source(
        penn, {"ref": r3["ref"] + "#s1.1/p1"}).get("error")
       == "no access to this item",
       "parts-listed member refused outside the part")
    ok(tmod.pc_read_source(penn, {"section": "1.1"}).get("error")
       == "no access to this item",
       "parts-listed member refused the whole section")
    ok(tmod.pc_read_source(penn, {"ref": r3["ref"]}).get("error")
       == "no access to this item",
       "parts-listed member refused the whole entry")
    ok(pc.ref_within(r3["ref"] + "#s1.1/p2", r3["ref"] + "#s1.1")
       and not pc.ref_within(r3["ref"] + "#s1.1",
                             r3["ref"] + "#s1.1/p2")
       and not pc.ref_within(r3["ref"] + "#s1.1/p1",
                             "pc://source/deadbeefdead#s1.1")
       and not pc.ref_within("nope", r3["ref"] + "#s1.1"),
       "ref_within matches entry + containment")
    ok(pc.row_kind({}) == "full"
       and pc.row_kind({"kind": "map"}) == "map"
       and pc.row_parts({}) == [],
       "kindless rows default to full, parts to whole")
    other = dict(cleo, order_id="ord-20261030-999")
    ok(tmod.pc_list_source(other, {"ref": r3["ref"]}).get("error")
       == "no access to this item",
       "listing in order A gives nothing in order B")
    pc.set_recipients("source", r3["doc_id"], "ord-20261030-009",
                      ["pd_marty"], "sales_sam", kind="full", root=tmp2)
    text4, meta4 = pc.prompt_chunks_for("pd_marty", "ord-20261030-009",
                                        [r3["ref"]],
                                        os.path.join(tmp2, "runs"))
    ok(meta4["included"] == [r3["ref"]]
       and "Body tools here." in text4
       and "(ref: %s#s1.1)" % r3["ref"] in text4,
       "full row gets the full text in the prompt")
    text5, meta5 = pc.prompt_chunks_for("board_penn", "ord-20261030-009",
                                        [r3["ref"]],
                                        os.path.join(tmp2, "runs"))
    ok(meta5["included"] == [r3["ref"]] and pcp in text5
       and "Open only your listed parts" in text5
       and "Body tools here." not in text5,
       "parts row gets listed parts only")
    pc.set_recipients("source", r3["doc_id"], "ord-20261030-009",
                      ["voice_wren"], "plan_ash", kind="full",
                      parts=[pcp], root=tmp2)
    text6, meta6 = pc.prompt_chunks_for("voice_wren", "ord-20261030-009",
                                        [r3["ref"]],
                                        os.path.join(tmp2, "runs"))
    ok(meta6["included"] == [r3["ref"]]
       and "(ref: %s)" % pcp in text6
       and "MAP NOTES" not in text6,
       "full+parts row gets the listed part text")
    ok("### Source:" in text4
       and text4.index("### Source:")
       < text4.index("Body tools here."),
       "marty sees the map before the full text")
    pc.set_recipients("source", r3["doc_id"], "ord-20261030-009",
                      ["plan_ash"], "sales_sam", kind="full",
                      root=tmp2)
    texta, metaa = pc.prompt_chunks_for(
        "plan_ash", "ord-20261030-009", [r3["ref"]],
        os.path.join(tmp2, "runs"))
    ok(metaa["included"] == [r3["ref"]]
       and "### Source:" in texta
       and "Body tools here." not in texta,
       "ash full row still gets the map, not the text")
    ash = {"agent_dir": cleo["agent_dir"], "producer": "plan_ash",
           "order_id": "ord-20261030-009"}
    ok("Body tools here." in tmod.pc_read_source(
        ash, {"ref": r3["ref"] + "#s1.1"}).get("text", ""),
       "ash tool still reads full sections")
    ep = os.path.join(pc.entry_dir("source", r3["doc_id"]),
                      "entry.json")
    with open(ep, encoding="utf-8") as f:
        ent = json.load(f)
    ent["figures"] = [{"addr": "fig1.1", "file": "fig1.png",
                       "page": 3, "caption": "Tools at work",
                       "printed_no": "Figure 1.1"}]
    ent["tables"] = [{"addr": "tab1.1", "page": 4,
                      "caption": "Census", "printed_no": "",
                      "rows": []}]
    ent["equations"] = [{"addr": "eq1.1", "sec": "1.1",
                         "page": 5, "latex": "a+b=c"}]
    with open(ep, "w", encoding="utf-8") as f:
        json.dump(ent, f)
    pc.set_recipients("source", r3["doc_id"], "ord-20261030-009",
                      ["board_penn"], "plan_ash", kind="map",
                      root=tmp2)
    textm, _m = pc.prompt_chunks_for(
        "board_penn", "ord-20261030-009", [r3["ref"]],
        os.path.join(tmp2, "runs"))
    ok("#fig1.1" in textm
       and "Figure 1.1 Tools at work" in textm
       and "#tab1.1" in textm and "a+b=c" in textm
       and "fig1.png" not in textm,
       "penn media list is addr+title, no files")
    textam, _m = pc.prompt_chunks_for(
        "plan_ash", "ord-20261030-009", [r3["ref"]],
        os.path.join(tmp2, "runs"))
    ok("#fig1.1" in textam, "ash gets the media list too")
    text4b, _m = pc.prompt_chunks_for(
        "pd_marty", "ord-20261030-009", [r3["ref"]],
        os.path.join(tmp2, "runs"))
    ok("Figures/tables/formulas" not in text4b
       and "Body tools here." in text4b
       and "Figures/tables/formulas" not in text,
       "marty and cleo get no media list")

    # ---- reads_log.jsonl (item 10) ----
    ndir = os.path.join(tmp2, "runs", "rlog", "explain_cleo")
    os.makedirs(ndir)
    cleo2 = dict(cleo, input_md=os.path.join(ndir, "INPUTS.md"))
    nobody = {"agent_dir": cleo["agent_dir"],
              "producer": "board_vera",
              "order_id": "ord-20261030-009",
              "input_md": os.path.join(ndir, "INPUTS.md")}
    tmod.pc_read_source(cleo2, {"section": "1.1"})
    tmod.pc_read_source(nobody, {"section": "1.1"})
    tmod.open_ref(cleo2, {"ref": r3["ref"] + "#s1.1/p2"})
    with open(os.path.join(ndir, "reads_log.jsonl"),
              encoding="utf-8") as f:
        lines = [json.loads(l) for l in f]
    ok(len(lines) == 3
       and all(set(l) == {"at", "tool", "pc", "ref", "section",
                          "item", "allowed", "reason"}
               for l in lines),
       "reads_log lines carry the 8 keys")
    ok(lines[0]["tool"] == "pc_read_source"
       and lines[0]["pc"] == "source"
       and lines[0]["allowed"] is True
       and lines[0]["section"] == "1.1"
       and lines[0]["reason"] == "",
       "allowed read logged with section")
    ok(lines[1]["allowed"] is False
       and lines[1]["reason"] == "no access to this item",
       "refused read logged with the reason")
    ok(lines[2]["tool"] == "open_ref"
       and lines[2]["pc"] == "source"
       and lines[2]["ref"] == r3["ref"] + "#s1.1/p2"
       and lines[2]["allowed"] is True,
       "open_ref logged with the pc from the ref")
    found = []
    for base, _ds, fs in os.walk(tmp2):
        if "reads_log.jsonl" in fs:
            found.append(os.path.join(base, "reads_log.jsonl"))
    ok(found == [os.path.join(ndir, "reads_log.jsonl")],
       "tools without a node dir log nothing")
    from agents._frame import media as _med  # noqa: E402
    missing_wrap = [
        n for n, m in
        (("pc_list_source", tmod), ("pc_read_source", tmod),
         ("open_ref", tmod), ("pc_search_theory", tmod),
         ("pc_search_articles", tmod), ("pc_pick_theory", tmod),
         ("pc_pick_article", tmod), ("pc_read_theory", tmod),
         ("pc_read_article", tmod), ("pc_send_source", tmod),
         ("pc_set_recipients", tmod), ("make_voice", tmod),
         ("pc_search_images", _med), ("pc_pick_image", _med),
         ("pc_generate_image", _med), ("vera_view_image", _med))
        if not hasattr(getattr(m, n), "__wrapped__")]
    wt = pc.ingest_theory("http://x.test/a", "T", "P", "2020", "now",
                           "case_rex",
                           "First paragraph here.\n\nSecond paragraph here.",
                           tmp2)
    pc.set_recipients("theory", wt["doc_id"], "ord-20261030-009",
                      ["explain_cleo"], "case_rex", kind="full", root=tmp2)
    cleor = {"agent_dir": os.path.join(ROOT, "agents",
                                       "explain_cleo"),
               "producer": "explain_cleo",
               "order_id": "ord-20261030-009"}
    bare = tmod.pc_read_theory(cleor, {"ref": wt["ref"]})
    ok(bare.get("kind") == "passage"
       and "[p1]" in bare.get("text", "")
       and "First paragraph here." in bare.get("text", ""),
       "bare theory read returns quotable text with markers")
    frag = tmod.pc_read_theory(cleor, {"ref": wt["ref"] + "#p2"})
    ok(frag.get("text") == "Second paragraph here.",
       "theory fragment read still exact")

    ok(missing_wrap == [],
       "all 16 PC tools wrapped for reads logging (%s)"
       % (missing_wrap,))
finally:
    pc.ROOT_OVERRIDE = None
    shutil.rmtree(tmp2, ignore_errors=True)

# ---- vision transcription fixtures (recorded 2026-10-31, no live calls) ----
from agents._frame import pdfingest  # noqa: E402
FIX = os.path.join(ROOT, "scripts", "fixtures", "eqtab")


def _fix(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def _fixj(name):
    return json.loads(_fix(name))


ok(pdfingest.XTOL == 1, "word-gap tolerance pinned at 1")


class _StubPage:
    def __init__(self, chars):
        self.chars = chars


row = _fixj("row_spacing.json")
stub = _StubPage([{"top": 79.0, "x0": x0, "x1": x1, "text": t,
                   "bottom": 88.0} for x0, x1, t in row])
built = pdfingest._text_rows(stub)
ok(len(built) == 1 and built[0][1] ==
   "Macro variables Open interest expectations Metadata",
   "recorded 2.2pt gaps join into spaced words")

P2 = _fix("page_2.txt")
ok("Macro variables" in P2 and "Credit ratings" in P2
   and "Open interest" in P2, "page 2 spacing words present")

CAP = "TABLE 2.1 The Four Essential Types of Financial Data"
scan_rows = [(-4.0, CAP, 130.0, 460.0, 5.0),
             (16.0, "Fundamental Data Market Data", 130.0, 460.0, 25.0),
             (26.0, "(cid:2) (cid:2) (cid:2)", 130.0, 460.0, 38.0),
             (35.0, "Assets Price/yield/implied Volatility", 130.0, 460.0,
              44.0),
             (46.0, "(cid:2)", 130.0, 200.0, 59.0),
             (57.0, ". . .", 130.0, 200.0, 65.0),
             (141.0, "fundamental data, especially in the factor-investing "
              "literature. Once you align the data", 60.0, 550.0, 151.0)]
scan_gaps = {16.0: 3, 26.0: 0, 35.0: 3, 46.0: 0, 57.0: 0,
             141.0: 0}
body = pdfingest._scan_table_body(scan_rows, scan_gaps, 0, -4.0)
ok([b[1] for b in body] == [r[1] for r in scan_rows[1:6]],
   "table scan keeps alternating rows, stops at prose")

ok(pc.formula_candidate_pages(
    ["o is the raw open price of instrument i = 1, .., I at bar t.",
     "def pcaWeights(cov, riskDist=None, riskTarget=1.):",
     "T\u03b8 = arg min |T| \u2265 E",
     "t t t=1,...,T t"]) == [3, 4],
   "vision gate: garble yes, prose/code no")

P7 = _fix("page_7.txt")
P8 = _fix("page_8.txt")
F7 = _fixj("formulas_p7.json")
F8 = _fixj("formulas_p8.json")


def _syn_entry(text, page, sec):
    return {"ref": "pc://source/testtesttest",
            "sections": [{"n": sec, "heading": "h", "start": 0,
                          "count": 1, "subsections": []}],
            "paragraphs": [{"addr": "s%s/p1" % sec, "text": text,
                            "pages": [page], "has": []}],
            "figures": [], "tables": [], "equations": []}


e7 = _syn_entry(P7, 7, "2.3")
new, bad, dup = pc.apply_equations(
    e7, 7, F7["response"]["formulas"], P7, F7["model"], "t")
ok(len(new) == 3 and not bad and not dup
   and any("\\arg" in q["latex"] and "\\min" in q["latex"]
           for q in e7["equations"])
   and all(q["in"] == ["s2.3/p1"] for q in e7["equations"])
   and all(a in e7["paragraphs"][0]["has"] for a in new),
   "page 7 fixture: 3 formulas incl argmin, linked")

e8 = _syn_entry(P8, 8, "2.3")
new8, bad8, _d8 = pc.apply_equations(
    e8, 8, F8["response"]["formulas"], P8, F8["model"], "t")
ok(len(new8) == 4 and not bad8, "page 8 fixture: 4 formulas")

newf, badf, _d = pc.apply_equations(
    e7, 7, [{"latex": "x=1",
             "context": "quantum zebra basketball parliament oracle"}],
    P7, "m", "t")
ok(newf == [] and len(badf) == 1, "fake context rejected")

ok(pc.context_found(
    "The rule defines a sequence {b_t}_{t} where",
    "The rule defines a xx sequence yy where"),
   "latex-ified context anchors on prose")
ok(not pc.context_found("alpha beta {x} gamma", "nothing alike here"),
   "short unanchored context rejected")

T2 = _fixj("table_p2.json")
ok(len(T2["response"]["columns"]) == 4, "TABLE 2.1 has 4 columns")
ok(pc.cells_found(T2["response"]["columns"], T2["response"]["rows"],
                  P2) == [], "TABLE 2.1 all cells checked")
eT = _syn_entry(P2, 2, "2.2")
eT["figures"] = [{"addr": "fig2.2.1", "page": 2, "caption": CAP,
                  "printed_no": "2.1", "kind": "table-image",
                  "bbox": [0, 0, 1, 1]}]
addr, checked, missing = pc.apply_table_vision(
    eT, "fig2.2.1", T2["response"]["columns"], T2["response"]["rows"],
    P2, T2["model"], "t")
ok(addr == "tab2.2.1" and checked and not missing
   and eT["figures"][0]["table"] == "tab2.2.1",
   "TABLE 2.1 applies checked with figure link")

ok(pc.cells_found(["Analyst"], [["implied volatility"]],
                  "Price/yield/implied Analyst X Liabilities "
                  "volatility Y") == [],
   "spanning cell tokens in order pass")
ok(pc.cells_found(["Analyst"], [["volatility implied"]],
                  "Price/yield/implied Analyst X Liabilities "
                  "volatility Y") != [],
   "reordered tokens fail")
ok(pc.cells_found(["Analyst"], [["unicorn strides"]],
                  "Price/yield/implied Analyst volatility") != [],
   "invented cell fails")

eH = {"ref": "pc://source/x",
      "figures": [{"addr": "fig2.3.1", "file": "fig2.png",
                   "caption": "c"}],
      "tables": [{"addr": "tab2.2.1", "caption": "c", "rows": [[1]]}],
      "equations": [{"addr": "eq2.3.1", "sec": "2.3", "latex": "x",
                     "context": "y"}]}
h3 = pc.section_has(eH, "2.3")
ok(any(h["ref"].endswith("#fig2.3.1") and h["kind"] == "figure"
       and h["file"] == "fig2.png" for h in h3)
   and any(h["kind"] == "equation" and h["caption"] == "x"
           for h in h3),
   "map has lists fig2.3.1 + equations")
h2 = pc.section_has(eH, "2.2")
ok(any(h["ref"].endswith("#tab2.2.1") and h["kind"] == "table"
       for h in h2),
   "map has lists the TABLE 2.1 address")

eG = {"pc": "source", "doc_id": "d" * 12,
      "ref": "pc://source/" + "d" * 12, "title": "t", "order_id": "o",
      "added_by": "a", "sections": [], "paragraphs": [],
      "figures": [],
      "tables": [{"addr": "tab1.1.1", "caption": "c", "printed_no": "",
                  "page": 1, "rows": [["h"]], "markdown": "m",
                  "transcribed_by": "m", "checked": False}],
      "equations": [{"addr": "eq1.1.1", "sec": "1.1", "page": 1,
                     "latex": "L", "context": "C", "in": [],
                     "transcribed_by": "m", "checked": True}]}
pt = pc.open_ref(eG, eG["ref"] + "#tab1.1.1")
ok(pt["markdown"] == "" and "UNCHECKED" in pt["note"],
   "unchecked table gated")
pe = pc.open_ref(eG, eG["ref"] + "#eq1.1.1")
ok(pe["latex"] == "L"
   and pe["evidence_note"].startswith("transcribed by model")
   and "L" in tmod._verbatim_haystack(pe),
   "checked equation citable")


# ---- rights matrix from recipient rows (J18) ----
ok(pc.cell_label("full", [], "pd_marty") == "full",
   "label full")
ok(pc.cell_label("map", [], "voice_wren") == "map",
   "label map")
ok(pc.cell_label("map", ["pc://source/d#s1.1",
                         "pc://source/d#s1.2"],
                 "voice_wren") == "map·s1.1+1",
   "label map with part refs")
ok(pc.cell_label("map", ["pc://source/d#s1.1"],
                 "voice_wren") == "map·s1.1",
   "label map with one part ref")
ok(pc.cell_label("map", [], "photo_pia@p2") == "map·P2",
   "label clone names its part")
ok(pc.cell_label("map", ["pc://source/d"],
                 "voice_wren") == "map·ref",
   "label frag-less ref")

_J18 = tempfile.mkdtemp(prefix="pcrights_")


def _j18_entry(pcname, doc, entry):
    edir = os.path.join(_J18, "storage", "_pc", pcname,
                        "entries", doc)
    os.makedirs(edir, exist_ok=True)
    with open(os.path.join(edir, "entry.json"), "w",
              encoding="utf-8") as f:
        json.dump(entry, f)


_J18_OID = "ord-20260101-001"
_J18_OTHER = "ord-20260202-002"
_j18_rows_s1 = [
    {"agent": "pd_marty", "order_id": _J18_OID, "kind": "full",
     "parts": [], "set_by": "sales_sam", "at": "t"},
    {"agent": "voice_wren", "order_id": _J18_OID, "kind": "map",
     "parts": ["pc://source/s1#s1.1",
               "pc://source/s1#s1.2"],
     "set_by": "plan_ash", "at": "t"},
    {"agent": "photo_pia@p1", "order_id": _J18_OID,
     "kind": "map", "parts": ["pc://source/s1#s1.1"],
     "set_by": "part_split", "at": "t"},
    {"agent": "pd_marty", "order_id": _J18_OTHER,
     "kind": "full", "parts": [], "set_by": "x", "at": "t"}]
_j18_rows_s2 = [
    {"agent": "pd_marty", "order_id": _J18_OID, "kind": "map",
     "parts": [], "set_by": "sales_sam", "at": "t"},
    {"agent": "photo_pia@p1", "order_id": _J18_OID,
     "kind": "map", "parts": [], "set_by": "part_split",
     "at": "t"}]
_j18_rows_i1 = [
    {"agent": "board_vera@p1", "order_id": _J18_OID,
     "kind": "map", "parts": [], "set_by": "photo_pia",
     "at": "t"}]
_j18_rows_v1 = [
    {"agent": "pd_marty", "order_id": _J18_OTHER,
     "kind": "map", "parts": [], "set_by": "x", "at": "t"}]
_j18_entry("source", "s1",
           {"pc": "source", "doc_id": "s1",
            "ref": "pc://source/s1", "order_id": _J18_OID,
            "title": "Doc one", "recipients": _j18_rows_s1})
_j18_entry("source", "s2",
           {"pc": "source", "doc_id": "s2",
            "ref": "pc://source/s2", "order_id": _J18_OID,
            "title": "Doc two", "recipients": _j18_rows_s2})
_j18_entry("image", "i1",
           {"pc": "image", "doc_id": "i1",
            "ref": "pc://image/i1", "order_id": _J18_OID,
            "title": "Pic one", "recipients": _j18_rows_i1})
_j18_entry("generated", "g1",
           {"pc": "generated", "doc_id": "g1",
            "ref": "pc://generated/g1",
            "order_id": _J18_OID, "title": "Gen one"})
_j18_entry("voice", "v1",
           {"pc": "voice", "doc_id": "v1",
            "ref": "pc://voice/v1", "order_id": _J18_OTHER,
            "title": "Clip", "recipients": _j18_rows_v1})
_baddir = os.path.join(_J18, "storage", "_pc", "theory",
                       "entries", "broken")
os.makedirs(_baddir, exist_ok=True)
with open(os.path.join(_baddir, "entry.json"), "w",
          encoding="utf-8") as f:
    f.write("{not json")

jr = pc.rights_for_order(_J18_OID, root=_J18)
ok(jr["agents"] == ["board_vera@p1", "pd_marty",
                    "photo_pia@p1", "voice_wren"],
   "rights agents incl clones, no foreigners")
jm = jr["cells"].get(("pd_marty", "source"))
ok(jm is not None and jm["kind"] == "full"
   and len(jm["entries"]) == 2
   and pc.cell_label(jm["kind"], jm["parts"],
                     "pd_marty") == "full",
   "full wins across entries")
jw = jr["cells"].get(("voice_wren", "source"))
ok(jw is not None and jw["kind"] == "map"
   and len(jw["parts"]) == 2
   and pc.cell_label(jw["kind"], jw["parts"],
                     "voice_wren") == "map·s1.1+1",
   "map parts merge with refs")
jp = jr["cells"].get(("photo_pia@p1", "source"))
ok(jp is not None and len(jp["entries"]) == 2
   and pc.cell_label(jp["kind"], jp["parts"],
                     "photo_pia@p1") == "map·P1",
   "clone cell names its part")
jv = jr["cells"].get(("board_vera@p1", "image"))
ok(jv is not None and len(jv["entries"]) == 1
   and jv["entries"][0]["title"] == "Pic one",
   "media cell carries its entry")
ok(("pd_marty", "voice") not in jr["cells"]
   and ("pd_marty", "generated") not in jr["cells"]
   and all(a != "pd_marty" or p == "source"
           for a, p in jr["cells"]
           if a == "pd_marty"),
   "other orders, legacy and corrupt entries excluded")
je = pc.rights_for_order("ord-20260303-003", root=_J18)
ok(je == {"agents": [], "cells": {}},
   "empty order gives empty rights")
shutil.rmtree(_J18, ignore_errors=True)

# ---- transcribe cache write (live bb3b195801b7: "secs" NameError) ----
# A paid vision call must be cached with its measured seconds, so a
# retry never repays it. _vision_chat and the PDF layer are stubbed;
# the cache write + reuse path is real.
import importlib.util as _ilu
import types as _types
_sp = _ilu.spec_from_file_location(
    "pc_worker_t", os.path.join(ROOT, "scripts", "pc_worker.py"))
_wmod = _ilu.module_from_spec(_sp)
_sp.loader.exec_module(_wmod)
from agents._frame import pdfingest as _pdi
class _FakePage:
    pass

class _FakePdf:
    def __init__(self):
        self.pages = [_FakePage()]
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False

_fake_plumber = _types.ModuleType("pdfplumber")
_fake_plumber.open = lambda buf: _FakePdf()
_real_plumber = sys.modules.get("pdfplumber")
_real_ext = _pdi.extract_page_text
_real_png = _pdi.page_png
_real_cand = pc.formula_candidate_pages
_real_open = _wmod._order_pdf_bytes
_real_apply = pc.apply_table_vision
_seen = []
sys.modules["pdfplumber"] = _fake_plumber
_pdi.extract_page_text = lambda pg: "nothing here"
_pdi.page_png = lambda pg: b"PNG"
pc.formula_candidate_pages = lambda texts: []
_wmod._order_pdf_bytes = lambda entry: b"fakepdf"
_vcalls = []
def _fake_vision(model, png, prompt, timeout=240, **kw):
    _vcalls.append(prompt)
    return {"columns": ["A"], "rows": [["1"]]}, 30, 40
_wmod._vision_chat = _fake_vision
def _fake_apply(entry, addr, cols, rows, page_text, model, now):
    _seen.append(addr)
    return (addr, "checked", [])
pc.apply_table_vision = _fake_apply
try:
    _edir = tempfile.mkdtemp(prefix="pc_transcribe_")
    _entry = {"ref": "pc://source/abcd1234efgh",
              "doc_id": "abcd1234efgh", "order_id": "ord-test",
              "pc": "source",
              "figures": [{"addr": "f8.1", "page": 1,
                             "kind": "table-image",
                             "caption": "Table 1",
                             "file": "f8_1.png"}]}
    _sum = _wmod.transcribe_entry(_entry, _edir, "m")
    ok(_sum["tables"] == ["f8.1"] and _sum["calls"] == 1,
       "vision table transcribed with one paid call")
    _cf = os.path.join(_edir, "vision_cache",
                       "table_p1_eqtab-v1.json")
    _cj = json.load(open(_cf, encoding="utf-8"))
    ok(isinstance(_cj.get("seconds"), (int, float)),
       "cache stores the measured seconds (got %r)"
       % (_cj.get("seconds"),))
    ok(_cj.get("prompt_tokens") == 30
       and _cj.get("completion_tokens") == 40
       and _cj.get("response", {}).get("columns") == ["A"],
       "cache stores tokens + response")
    del _vcalls[:]
    _sum2 = _wmod.transcribe_entry(_entry, _edir, "m")
    ok(_sum2["cached"] == 1 and not _vcalls,
       "retry reuses the cache, repays nothing")
finally:
    if _real_plumber is None:
        del sys.modules["pdfplumber"]
    else:
        sys.modules["pdfplumber"] = _real_plumber
    _pdi.extract_page_text = _real_ext
    _pdi.page_png = _real_png
    pc.formula_candidate_pages = _real_cand
    _wmod._order_pdf_bytes = _real_open
    pc.apply_table_vision = _real_apply

print("FAILURES: %d" % len(FAILS) if FAILS else "ALL PASS")
sys.exit(1 if FAILS else 0)
