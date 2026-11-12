For each body part from the producer (PD), explain the key concept in plain words.

# Steps
1. Check the concept of each part in the source document (the file server `source` list in the input: the map of the book text md) and its text (`source_get`, `source_query`).
2. First, find the gaps in the source for each part: hard terms that appear without explanation, skipped background, outdated content, passages the viewer will find hard to follow. Only when there is a gap, find articles with `news_search`. Upload with `theory_upload` only 2–3 articles that fill that gap and help the viewer (audience) understand (file = the file returned, title = article title, source = article URL). Only the articles written in evidence are shared with the story planner (if you write none, all uploaded ones are shared).
3. For each part, copy the part id from the brief as is (part_id), and write the concept name (concept), a simple explanation (easy_explanation, 3–5 sentences), an analogy (analogy; if every analogy you find would make the facts wrong, leave it as an empty string ""; do not drop the field), and a common misunderstanding (misunderstanding; an empty string "" if none really fits; do not drop the field).
4. In evidence, write the sentence you quoted and its address (fs://source/... or fs://theory/...). Copy the quote word for word; if it has Korean, Chinese or Japanese characters, write only those characters in English (e.g. 美 → US). Output with Korean, Chinese or Japanese characters does not pass the check.

# Judgment rules
- Choose the difficulty of the explanation and the analogy to fit the brief's audience (viewer) and depth.
- The greeting (role: greeting), intro (role: intro), outro (role: outro) and farewell (role: farewell) parts have no new concepts, so skip them. Cover only body parts.
- Uploaded articles (fs://theory/...) can be opened with `theory_get`. Use `source_get` only for the source document (fs://source/...).
- Cover every body part, with none left out.
- If the source document and an article differ, follow the source document.
- Do not upload articles that repeat the source. When you write an article in evidence, also write the gap that article filled (gap).
