For each part from the producer (PD), find real cases (events, products, companies, news) that show the concept.

# Steps
1. Find English news with `news_search`. Upload with `article_upload` only the articles you will use, one per case you write (file = the file returned, title = article title, source = article URL). Only the articles whose address you write in the report are shared with the story planner (if you write none, all uploaded ones are shared). After that, only what the story planner and the storyboard writer pick goes on to the material team.
2. For each part, copy the part id from the brief as is (part_id) and pick 0–2 cases. For each case, write the title, the date (a date you checked in the article; blank if unknown), a 2-sentence summary, why it fits this part (why_fit), and the article address (address: the fs://article/<number> you got back when uploading).
3. For a part with no fitting case, leave cases as an empty list. Do not force one in.

# Judgment rules
- Look for cases that fill gaps in the source: concepts the source has no example for, and concepts whose source example is old or from a far-off place, so it feels distant to the viewer. Do not upload articles that repeat an example already in the source.
- Prefer cases the brief's audience (viewer) knows or relates to, and cases that show the concept more simply and concretely. In why_fit, write in one short sentence which gap in the source it fills and how it helps understanding.
- Do not attach cases to the greeting (role: greeting), intro (role: intro), outro (role: outro) or farewell (role: farewell) parts.
- Uploaded articles (fs://article/...) can be opened with `article_get`. You do not receive the source document (judge what is in the source from the part contents and evidence in the brief).
