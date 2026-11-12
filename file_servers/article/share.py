"""Share function of this file server.

The planner and the storyboard writer pass on only the articles their report names ("materials": [{address, why}]);
naming none passes none. The collectors (explainer, cases) pass on the articles their report cites, or all they
uploaded when the report cites none."""

from nextop.file_server import addresses_in, parse_address

SELECTORS = ("planner", "board")


def share(file, report, receivers):
    server = parse_address(file["address"])[0]
    named = addresses_in(report).get(server, set())
    if str(file.get("owner", "")).split("@", 1)[0] in SELECTORS:
        return receivers if file["number"] in named else []
    if not named:
        return receivers
    return receivers if file["number"] in named else []
