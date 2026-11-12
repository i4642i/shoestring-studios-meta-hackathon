"""Sam's tool in the ORDER chat: save what the client said into the order's request form (orders/<id>/form.json)."""

from tools._orders import FORM_FIELDS, form_of, length_problem, order_dir, save_form

NAME = "update_form"
DESC = ("Save what the client said into the order's request form: audience (who watches), length (the video length, "
        "between 30 seconds and 10 minutes), depth (overview, key points, explained or in depth), theme (angle or "
        "tone). Give only the fields this message revealed. Returns the whole form and which fields changed.")
SCHEMA = {
    "type": "object",
    "properties": {
        "order_id": {"type": "string", "description": "the order id from the question (ord-YYYYMMDD-NNN)"},
        "audience": {"type": "string"},
        "length": {"type": "string"},
        "depth": {"type": "string"},
        "theme": {"type": "string"},
    },
    "required": ["order_id"],
    "additionalProperties": False,
}
TIMEOUT = 30


def run(ctx, args):
    d = order_dir(args.get("order_id"))
    if d is None:
        return {"error": f"no order {args.get('order_id')!r}; use the order id given in the question"}
    fields = {k: str(args[k]).strip()[:500] for k in FORM_FIELDS if isinstance(args.get(k), str) and args[k].strip()}
    if not fields:
        return {"error": "no field given; pass at least one of audience, length, depth, theme"}
    refused = []
    if "length" in fields:
        p = length_problem(fields["length"])
        if p:
            refused.append(p)
            fields.pop("length")
    before = form_of(d)
    form = save_form(d, fields) if fields else before
    out = {"ok": not refused, "form": form, "changed": [k for k in fields if before.get(k) != form.get(k)]}
    if refused:
        out["refused"] = refused
    return out
