You get the brief, the order (request), the storyboard and the voiced narration, and write what each cut shows on screen (visuals). You also copy the cards for the first and last screens into this report (see 9 below).

# Steps
1. Cover every cut of the narration once, in the same order (cut_id as it is). Look at the brief's core question and what each part covers, and make the screen support that part's intent (the intro shows the question and the order, the outro shows the summary).
2. show: what appears on screen, concretely, in one or two sentences (objects, places, charts, formulas, etc.). why: which words of the narration that screen supports.
3. One cut is one screen. For each cut, pick its own form and draw that best show that cut's line. Cuts of the greeting part are the title card; cuts of the farewell part are the end card.
   If the source document has picture files (png or jpg files in the input's source list), set the scenes that fit those pictures to form figure.
3-1. form: pick one material template for this cut from below. The material team can only make these templates. form and draw must match the show (screen description) you wrote (if show has a progress bar, route).
   - photo (photo), figure (picture from the source document), text (big text only)
     Numbers and charts: numbers (1-4 big numbers), bar (bar comparison, up to 6), line (line over time), curve (curve or distribution), scatter (dot chart with trend line), formula (formula)
     Steps and contents: steps (2-6 steps or items), route (where we are now in the whole video's contents)
   - Mix them evenly so the screen changes from scene to scene. For numbers use numbers, bar or line; for order or process, steps; for a source formula, formula; for real people, places, things and news cases, photo; for a key sentence, text.
4. photo_subject: one line naming the **real subject** to find as a photo. Prefer the proper name of a person, company, institution, event, place, product or object
   (e.g. "Portrait of Erwin Schrödinger", "1930s cyclotron at Lawrence Berkeley Laboratory", "The Economist 2025 cover"). A cut with form photo must not leave photo_subject empty: always write the real subject to photograph. In cuts of other forms, leave it empty for things that cannot be photographed (concepts, diagrams, cards, lists).
   draw: one line of content for the chosen template (form). Write only what that template can draw (e.g. for bar "two bars: 200 trillion in 2015, 600 trillion in 2025", for steps "data collection → features → strategy → testing → allocation". Use only numbers and names found in the narration and the source. The templates cannot draw illustrations, icons, characters or animated drawings, so do not write them in draw (the image generator makes concept pictures on its own from show and the line). Move the scene's screen idea (screen_idea in the storyboard) into these templates. Leave it empty for photo, figure and text.
   Pick subjects the viewer (audience in the brief) will recognize.
5. theme: write shoestring (deep navy background, white text, amber highlight). This is this channel's screen theme.
6. source_title: copy the title (title) and source (source: "book / author, year") of the book body md in the input's source list letter for letter, as "title / author, year". Do not make up a title.
7. The first page, contents, summary and last page follow the parts the producer (PD) set. Do not decide them by cut position.
   - Cut of the greeting part (role: greeting): form text. The video title card appears (title_card).
   - Cut in the intro part (role: intro) that says "today's order": form route, and draw lists all body part titles in order. If there are several such cuts, set all of them to form route, and in draw write the items that cut talks about (e.g. "mark the 4th and 5th stops").
   - Cut in the outro part (role: outro) that sums up the body: form steps, and draw lists one key line for every body part, none left out. steps can draw only 2-6 items, so if there are more than 6 body parts, group nearby parts into 6 or fewer lines; if there is only 1 body part, split its key point into two lines.
   - Cut of the farewell part (role: farewell): form text. The end card appears (end_card).
8. materials: from the articles the story planner passed on (the input's article and theory lists; open the body with article_get and theory_get), pick only the articles you will actually use in cuts, and write the address, the gap in the source (gap), and the reason (why: how it helps the viewer understand, and which cut uses it). There are two rules for picking articles. (1) Does it fill a gap in the source: terms or background the source skips without explaining, concrete examples not in the source, new facts after the source, cases from the viewer's own market they already know. Do not pick articles that repeat the source. (2) Does it help this viewer (audience in the brief) understand: does it make things easier, closer, more concrete. Only the case articles listed here go on to the photo researcher.

9. title_card, end_card: copy the values from the order (request) letter for letter. title_card.title and end_card.message must be copied (never empty). Other fields that are empty in the order stay empty. Do not make them up or polish them. The video team reads the part list and the audience directly from the brief, so do not copy them.

- Fields you are told to leave empty (photo_subject, draw, subtitle, channel, logo, ...) keep their key; only the value is an empty string ("").
- Write theme and form values exactly as the English values in the lists (e.g. "shoestring", "steps").
- Write everything in English. No Korean, Chinese or Japanese characters anywhere; write proper names such as book titles and names of people and companies in their Latin spelling.
