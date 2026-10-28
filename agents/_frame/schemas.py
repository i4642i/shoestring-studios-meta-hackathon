"""JSON contracts between crew (v1). Stdlib only."""

DRAFT_SCHEMA_V1 = "storyboard-draft/1"

REQUIRED_TOP = ("title", "key_ideas", "scenes")


def validate_draft(obj):
    """Return a list of error strings (empty == valid)."""
    errors = []
    if not isinstance(obj, dict):
        return ["draft must be an object"]
    for k in REQUIRED_TOP:
        if k not in obj:
            errors.append("missing: %s" % k)
    ideas = obj.get("key_ideas")
    if isinstance(ideas, list):
        if not 2 <= len(ideas) <= 4:
            errors.append("key_ideas must have 2-4 items (got %d)" % len(ideas))
        for i, idea in enumerate(ideas):
            if not isinstance(idea, dict):
                errors.append("key_ideas[%d] must be an object" % i)
            elif not idea.get("id") or not idea.get("title"):
                errors.append("key_ideas[%d] needs id + title" % i)
    elif "key_ideas" in obj:
        errors.append("key_ideas must be a list")
    scenes = obj.get("scenes")
    if isinstance(scenes, list):
        if not scenes:
            errors.append("scenes must be non-empty")
        for i, sc in enumerate(scenes):
            if not isinstance(sc, dict):
                errors.append("scenes[%d] must be an object" % i)
                continue
            if not sc.get("narration"):
                errors.append("scenes[%d] needs narration" % i)
            srcs = sc.get("sources")
            if not isinstance(srcs, list) or not srcs:
                errors.append("scenes[%d] needs >=1 source" % i)
    elif "scenes" in obj:
        errors.append("scenes must be a list")
    if "title" in obj and not isinstance(obj["title"], str):
        errors.append("title must be a string")
    return errors
