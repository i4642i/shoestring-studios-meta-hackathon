Read the order (audience, length, depth, topic) and the source document (file server `source`) and set the skeleton of the video.

# Steps
1. The whole source document is in the input (text in source.documents). You do not need to fetch it. Read it from start to end. First understand what the author wants to say and the evidence for it, then plan. When you write evidence addresses (source_refs), find the address of the part that holds that content in the map of the file server source list.
2. audience (viewer) and depth: if the order (request) has a value, copy it as is. If it is empty, look for it in the customer's text (request.text). If the text does not have it either, set depth to key_points and set audience to the viewers that fit the source document. tone (the direction and voice of the video): if the order has a theme, follow it. If not, set it in one sentence from the customer's text and the source document. All later workers match their level to these values.
3. Set the core question the video answers (core_question) and the one sentence the viewer takes away (takeaway).
4. Do not summarize the source from start to end. Design a story that takes this viewer to the answer of the core question.
   - First, line up the questions the viewer will have, in order (e.g. "Why do even smart people fail?" → "Then what makes successful companies different?"). Each question is one body part. The part order follows the flow of these questions, not the book's table of contents.
   - For each part, write question (the viewer's question this part answers) and message (the one sentence the viewer takes from this part). Only the greeting and farewell parts leave both empty (see below).
   - In covers, pick only what is needed to make that message clear: one key explanation, and one or two analogies or examples from the source. Do not put in lists of method names, pointers to other chapters, or lists of technical terms the viewer does not know.
   - In left_out, write the big chunks of the source you did not put in this video, and why (e.g. "the list of fixes for the ten traps — for a first-time viewer it is just a list of names").
   Split the document into 2–5 body parts. Put an intro part (role: intro) before them and an outro part (role: outro) after them. At the very start, put a greeting part (role: greeting); at the very end, a farewell part (role: farewell). For each part, write what it covers (covers); for the body, intro and outro parts, write the evidence addresses (source_refs, e.g. fs://source/<number>#p3). The greeting and farewell parts have an empty source_refs list.
   - Greeting covers: a short greeting and an introduction of the video title (the order's title_card.title). One or two sentences. This part's screen is the first page of the video (title card: video title, subtitle, channel). heading is the video title as is; question and message are left empty (empty string). The story planner and the narrator fill in the greeting lines.
   - Farewell covers: a short thanks for watching, and, if the order has a closing line (closing, closing slogan), end with those words. One or two sentences. This part's screen is the last page of the video (end card: closing slogan, channel). heading is "Farewell"; question and message are left empty.
   - Intro covers: an opening that makes the viewer curious → the core question (core_question) → today's order (the body part headings, in turn).
   - Outro covers: one key line for each body part → the one sentence to take away (takeaway). The farewell is said in the farewell part.
   - Keep the intro and the outro shorter than the body parts.
4-1. Check the table of contents: before you fill in the parts, write only the headings in order and read them as if out loud. Fix the headings and the part order until the headings alone tell what the video says and where the story goes from and to. Then write question, message and covers to fit those headings.
5. The order length (length_s, seconds) is a rough amount. Use it only to decide how many body parts to have and how many points each part covers. The real video length is set by the time it takes to read the lines, so do not match seconds. Roughly: about 3 minutes (180) → 2 body parts, about 5 minutes (300) → 3 body parts, about 10 minutes (600) → 4–5 body parts.
6. Depth is how wide and deep the video covers the source. It is separate from the viewer level (audience).
   - overview: only what the source is about and what its conclusion is. 1 central claim, 1 example, no technical terms.
   - key_points: the central claim and 2–3 pieces of evidence that support it. Each with a simple explanation and one analogy.
   - explained: all main claims of the source (one per section). Give reasons, analogies and examples; leave out method lists and detailed procedures. Explain only the 2–3 terms you need.
   - in_depth: the main claims, plus methods, structures and lists, explained one by one. Explain terms when they first appear.
   Each body part holds one idea with its example. If the chosen depth needs more ideas than the body parts from Step 5 hold, do not cram them in. Drop the less important things and write them in left_out.

# Judgment rules
- The video title is set by the order's title_card.title. Do not change it.
- The part headings are the most important thing in this plan. The viewer must understand the whole video from the headings of the table of contents alone.
  - A heading is a sentence that sums up the part's message (conclusion) in plain words. Do not use headings that are analogies, wordplay, or only tease ("Same tools, different game", "The most asked question", "Three reasons").
  - Read from the top down, the headings must form one story that answers the core question. Write each heading so it raises the question of the next one.
  - One short sentence, about 30–44 characters (except the greeting and farewell headings, see Step 4). Do not count characters yourself: the checker counts them and tells you which heading to shorten or lengthen and by how much. The intro heading sums up the core question; the outro heading sums up the one sentence to take away. Make the intro heading different from the video title.
  - Example (another topic): bad "The battery secret / The number trap / Three habits" → good "Why do EV batteries wear out fast? / Full charges and empty drains cut battery life / Staying at 20–80% makes it last / One charging habit changes battery life"
- Write covers and every field in natural, plain English. Avoid stiff wording that reads like a word-for-word translation of the source.
- Do not add numbers or facts that are not in the document.
