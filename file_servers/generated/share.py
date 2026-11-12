"""Share function of generated: the image generator's candidates go to the screen designer; it passes on only the ones it chose.

Material makers upload each candidate with its id as the title (e.g. ph-c03-1). The screen designer's report names the
used ids per slot ("cuts": [{"fill": [{"slot", "use"}]}]; older reports: "chosen"); only those files go to the slide
builder (ids under "dropped" or "considered" do not count). Makers share everything they uploaded."""

import re

from nextop.file_server import addresses_in, parse_address

_ID = re.compile(r"\b(?:ph|gn|ch|dg|qt|tl)-c\d+-\d+\b")


def share(file, report, receivers):
    if not str(file.get("owner", "")).startswith("designer"):
        return receivers                       # a maker shares every candidate it uploaded
    # only the "chosen" lists count: "dropped" names candidates too, but those must not go on
    chosen = set()
    for plan in (report or {}).values():
        for cut in (plan or {}).get("cuts", []) if isinstance(plan, dict) else []:
            for x in cut.get("chosen") or []:
                chosen |= set(_ID.findall(str(x)))
            for f in cut.get("fill") or []:
                chosen |= set(_ID.findall(str((f or {}).get("use") or "")))
    named = addresses_in(report).get(parse_address(file["address"])[0], set())
    return receivers if file.get("title") in chosen or file["number"] in named else []
