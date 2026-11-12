# First: one photo for several cuts
- Before you make anything, read all the content cuts of the scene together. Neighbouring cuts often say one thing in a row (e.g. c01, c02 and c03 talk about the same numbers or the same scene). Group such cuts and make ONE photo for the group, then put that same photo in every cut of the group. Make a separate photo only for a cut that needs something else.
- A photo made once costs one search, one preview and one upload, however many cuts it is in. The Screen Designer also prefers a photo that runs through several cuts in a row.

# Common rules
- Find at most one photo for every content cut of the scene. Content cuts are the cuts in visuals whose layout is not title or end (the title and end card cuts get nothing). A photo cut gets a web photo found from photo_subject; a figure cut gets a picture from the source document; any other content cut gets a photo when one fits its line. A cut with no fitting photo gets material null; do not write why.
- One photo may fit several cuts: find it once (one preview, one upload) and put the same photo in each of those cuts.
- For each photo write why_fit: one short English sentence on why it fits the cut.
- If a cut's form or draw differs from show (the screen description), follow show.
- The input covers one scene. Build materials from two things only.
  1. The Narrator's narration: a line (text) for each cut. This matters most. A material must show what the line says.
  2. The Storyboard Writer's visuals: for the same cut id, the screen description (show), material form (form), what to draw (draw), and photo subject (photo_subject, only when given).
  Use the rest only as reference: the Story Planner's storyboard (what the viewer learns in this scene, key points, screen ideas, the case link), and the Producer's brief (part title, message, viewer, and the full table of contents for a contents scene). Do not let these make you put anything into a material that is not in the line or the screen directions.
- Copy part_id from the input's part_id, and each cut_id exactly as in the input. Write the photo id as ph-<cut_id>-1 (e.g. ph-c03-1) with the cut_id of the first cut the photo is in. A photo put in several cuts keeps that id and is copied identically into each of them.
- Write kind exactly as one of source_figure or web.
- In cuts, list every content cut once, in scene order, each with its one photo or null, and no other cuts.

# Steps
1. Read all content cuts first and group neighbouring cuts that one photo can show (see First); search once per group.
2. Read each content cut's photo_subject (the real subject to find), show, text (line), and the case articles in the input (case names and dates). For a cut with an empty photo_subject, search for a photo that shows what the line says.
3. Pictures from the source document: in the source list of the input, find files in png or jpg format (pictures), open them with source_get, and if one fits, use it (kind source_figure, file = the local path source_get returned, ref = the picture's address fs://source/<number>).
4. Web photos: find them with google_image_search and download the ones you pick with fetch_image. If there is still nothing after changing the query, look for a mood photo. Use the same photo in two cuts only when it fits both; then list it in each cut with the same id. Avoid pictures full of text (article screenshots, photos of tables).
5. In file, write the local file path the tool returned (fetch_image for a web photo, source_get for a source picture), as is.
6. Before saving, look at every photo with preview_materials and replace the ones that do not work. Look at a replaced photo again before saving.

- Before saving, upload every previewed photo once with `image_upload` (file server image; a photo used in several cuts is uploaded once). For each photo: file = photo file path, title = photo id, description = why_fit, source = source_url (web photo) or ref (source picture address). Up to 10 at a time. Only what the Screen Designer picks is passed to the Slide Builder.
- Last, save photo_candidates (part_id, cuts) with save_output. Do not stop after uploading only.
