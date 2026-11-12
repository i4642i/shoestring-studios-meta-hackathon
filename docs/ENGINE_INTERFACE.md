# Engine interface (for the site: scripts/server.py, index.html, office)

Owner of the engine side: workers/, flows/, functions/, tools/, file_servers/, layouts/, remotion/, project.json.
The site reads only what is listed here. If you need more, add a line under "Requests" at the end.

## Starting a run

`python -m nextop run . --flow main --run-id <id> --input <file.json>` (cwd = project root, PYTHONIOENCODING=utf-8).
The input file is one JSON object with the fields of the start worker Sam (`workers/sam/worker.json` "inputs"):

| field | required | meaning |
|---|---|---|
| order | no | the customer's words as written (Sam's summary of the chat is fine) |
| audience | no | who watches |
| length_min | yes | video length in minutes, 0.5-10 (a rough amount; the video is as long as its lines) |
| depth | no | "" / overview / key_points / explained / in_depth (Shoestring orders: key_points) |
| theme | no | angle or tone |
| voice | no | draft / final (both use the English Kokoro voice af_heart) |
| video_title | yes | title on the first slide |
| subtitle | no | subtitle on the first slide |
| closing | yes | closing message on the last slide |
| channel | no | channel or company name on the first and last slides |
| logo | no | full path of a logo image |
| pdf | yes | the customer's PDF (full path, or relative to the project folder); the parser block reads it |
| book_title | no | title of the book or paper in the PDF (empty: the PDF's own title or file name) |

Resume: `python -m nextop resume . --run-id <id>`.

## Run folder: runs/<id>/

| path | what |
|---|---|
| status.json | run status: `status` (running/done/failed/stopped...), `done` [blocks], `running` [blocks], `failed` {block: why}, `not_run`, `started`, `ended`, `reason` |
| events.jsonl | one JSON per line: `run_start`, `block_start` {block}, `block_done` {block, calls}, ... |
| cost.json | LLM usage: `calls`, `usage` {prompt_tokens, completion_tokens, total_tokens}, `seconds`, `blocks` {block: {calls, usage}}. qwen is local: cost 0 USD |
| image_cost.json | written by tools/generate_image.py: `{"images": n, "usd": n*0.01, "model": "muse-image-1.0", "items": [{prompt_hash, file, block, time}]}`. Absent = 0 images |
| blocks/<block>/attempt-<k>/status.json | per block (copies are `<block>@<n>`, e.g. `photo@3`): `status`, `time`, `calls` |
| blocks/<block>/attempt-<k>/tools.jsonl | tool calls of a worker block: `{no, time, name, args, result}` per line (for speech bubbles: last line) |
| blocks/<block>/attempt-<k>/output.json | the block's saved output |
| blocks/assemble/attempt-<k>/output.json | `{"video": {file, srt, seconds, parts, cuts, left_unfixed?}}` |
| blocks/assemble/attempt-<k>/files/video.mp4 | final video (and captions.srt next to it) |
| blocks/render@<n>/attempt-<k>/files/part_<piece>.mp4 | part videos |
| file_servers/<name>/ | file server store of the run (items/, files/, shares.jsonl, tools.json) |

Use the highest attempt-k of a block.

## Workers (display names)

`workers/<id>/worker.json`: `name` = person's name, `title` = role, `team`.

| block id | name | title |
|---|---|---|
| sam | Sam | Sales representative / order consultant |
| pd | Marty | Producer (PD) |
| explainer | Cleo | Explainer writer (theory research) |
| cases | Rex | Case researcher (news articles) |
| planner | Ash | Story planner |
| narrator | Wren | Narrator (voice) |
| board | Penn | Storyboard writer |
| photo | Pia | Photo researcher |
| gene | Gene | Image generator |
| anim | Max | Animation maker (charts, formulas, steps, contents) |
| designer | Vera | Screen designer |
| editor | Remy | Slide builder |
| reviewer | Iris | Screen reviewer |

Function blocks (no person): parser, split, check_layout (switch: pass / redesign / rebuild), render, gather, assemble.
Sam is the start block (she copies the run input into the order sheet `request` and the PDF hand-off `pdf`);
the site's ORDER chat asks the same worker with `nextop ask sam --history`.

## File servers (the six server PCs)

| name | original PC | filled by | read by |
|---|---|---|---|
| source | SOURCE | parser (the customer's PDF read into book .md + figures) | pd, explainer, photo, anim, board |
| theory | THEORY | explainer (Cleo) | planner -> board |
| article | ARTICLE | cases (Rex) | planner -> board -> photo |
| image | IMAGE | photo (Pia) | designer -> editor |
| generated | GEN IMAGE | gene (Gene) | designer -> editor |
| voice | VOICE | narrator (Wren) | render |

`materials` is internal (Max's chart, formula, steps and contents values, from anim to designer -> editor);
do not show it as a server PC.

## Requests
(site side: add here)
