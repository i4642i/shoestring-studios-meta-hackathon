# Inspection of worker photo

_2026-11-11 17:30, model qwen3.8-flash-next. Written by `nextop inspect`; files were not changed._

There are no outright failures, but the definition has gaps: an undocumented optional site field, an ambiguous photo_subject rule, and a numeric mismatch in the image-search tool.

## 1. [warning] The schema includes an optional site field and fetch_image notes tell the worker to write site = site name, but the mission and checker never ask for or describe site.

- parts: outputs, mission, tools
- where: outputs schema photo_candidates.cuts.items.properties.candidates.items.properties.site; fetch_image tool notes
- fix: Document site in the mission/schema, such as filling it with the site name for web candidates, or remove it from the schema and tool notes.

## 2. [warning] It is unclear whether a photo cut with no photo_subject must still get a web candidate or may be skipped unless the photo would help a lot.

- parts: mission
- where: mission common rules: 'A photo cut gets a web photo found from photo_subject' versus Step 1: 'For a cut with an empty photo_subject, search only when a photo would help a lot'
- fix: Add an explicit exception: if photo_subject is absent, search a photo cut only when the line clearly requires a photo; otherwise skip it.

## 3. [warning] The tool description says each query returns up to 8 hits, but the per_query argument allows values up to 10.

- parts: tools
- where: google_image_search: description and arguments.per_query
- fix: Align the numbers by setting the maximum to 8 or updating the description to say up to 10 can be requested but at most 8 are returned.
