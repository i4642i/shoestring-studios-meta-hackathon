# Hackathon Don'ts — Shoestring Studios

Meta Global AI Developer Hackathon 2026 (Indie Developer track). Written 2026-10-27.

- **[RULE]** = stated in official sources (participant guide, kickoff slides, organizer answers on Discord). Breaking these can get the project disqualified.
- **[ADVICE]** = not an official rule, but breaking it would likely cost points or cause real damage.

---

## 1. Disqualification risks [RULE]

1. **Do not submit work made before the event.** Only work built between Oct 26 and Nov 4, 2026 (ET) counts. All code in this repository must be written during the hackathon.
2. **Do not demo anything you did not build during the event.** If judges cannot tell what was created during the hackathon, the project is disqualified at the judges' discretion.
3. **Do not use code, data or assets you don't have the rights to.** This includes copyrighted textbook text, images, fonts, music and video clips.
4. **Do not break legal, ethical or platform policies.**
5. **Do not submit a private GitHub repository.** The repo must be public. Check it in a logged-out browser before submitting.
6. **Do not miss the deadline.** Nov 4, 2026, 9:00 PM ET (Nov 5, 11:00 KST). Late submissions are not accepted.
7. **Do not skip Meta AI products.** Stage 1 is pass/fail: the project must fit a theme and actually use Meta AI products.
8. **Do not register twice, give false identity information, or spam.**
9. **Do not add teammates who were not accepted to the hackathon.** Max team size is four, and every member must be an accepted participant.

## 2. Overdone projects to avoid [RULE: listed in kickoff slides as projects to skip; the list is not complete]

- AI-generated medical advice (including mental-health advisors and skin-blemish detectors)
- Basic RAG apps
- Simple image analyzers
- **Streamlit apps**
- **Dashboards as the main feature**
- **"AI for Education" chatbots**
- AI job-application screeners
- AI nutrition coaches
- Personality analyzers
- Sports analyzers or coaches
- Political or war-related projects (participant guide)

**What this means for us [ADVICE]:**
- Do not build the UI with Streamlit.
- Do not make a chat window the center of the product. We are a video production pipeline, not a Q&A chatbot.
- Do not make an agent-progress dashboard the main feature. The finished video and the claim-to-source report are the stars.
- Do not present the project as "AI for education." Present it as a studio that produces cited explainer videos.

## 3. Security and money [ADVICE]

1. **Never commit API keys or `.env` files.** Keys go only in `.env`, which is in `.gitignore`.
2. **Never paste API keys into chats, screenshots, Discord, GitHub issues or the terminal prompt.** If a key leaks, revoke it and create a new one immediately.
3. **Never send secrets to Muse Code in Contributor mode.** Contributor mode content may be used to train Meta models.
4. **Do not run Muse Code with `--yolo`.** It turns off approvals and the sandbox.
5. **Do not subscribe to a paid Muse Code plan.** Use the API key with hackathon credits.
6. **Do not run large batch jobs without checking cost first.** Measure one run, check Usage on dev.meta.ai, then scale.
7. **Do not lose the Baseten API key.** It cannot be regenerated. Save it the moment it arrives.
8. **Do not commit textbook source files, generated videos or audio.** `data/sources/`, `output/`, `*.mp4`, `*.wav`, `*.mp3` are ignored.

## 4. Submission mistakes [RULE where marked, otherwise ADVICE]

1. **[RULE]** Do not wait for the last hour to submit. Organizers warned about this.
2. Do not claim features in the submission form that were not actually built.
3. Do not submit a demo video that only shows slides. Show the real pipeline running end to end.
4. Do not make the demo video longer than 3 minutes.
5. Do not leave `[ ]` placeholders in the submission text.
6. Do not forget to check that the YouTube link plays while logged out.
7. Do not reuse old projects' code (agents_town, storyboard_studio, video_studio). Decision made on 2026-10-27: everything is written from scratch.

## 5. Discord etiquette [ADVICE]

1. Do not treat the "Cerebral Valley app" bot's answers as official. Confirm specific cases with organizers.
2. Do not post credit requests as chat messages. Use the official forms.
3. Do not share personal account details (team IDs, card info, emails) in public channels.
