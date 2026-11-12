# Inspection of worker editor

_2026-11-11 17:34, model qwen3.8-flash-next. Written by `nextop inspect`; files were not changed._

The role and outputs agree, but the mission omits or conflicts with several checked details: font-size bands, BigText limits, preview arguments, design_spec where values, BigText emphasis, and a checker rule about ch- material templates.

## 1. [warning] The mission gives HtmlSlide font-size bands as body 28-40px, small 22-24px, and big 44-72px, but its own weight section and the checker use body 28-43px and small up to 27px/big 44px+, so allowed sizes 25-27 and 41-43 are unclear or excluded.

- parts: mission, checker
- where: mission 'Designing a slot with HtmlSlide' font-size bands vs weight/checker rules
- fix: State one compatible set of font-size bands matching the checker's categories: small 22-27px, body 28-43px, and big 44px and above.

## 2. [warning] The mission says text can be BigText and lines may be broken, but it omits the checker-enforced BigText limit of at most 3 lines and size 28-140px, which can produce a rejected first draft.

- parts: mission, checker
- where: mission 'Filling the slots' text mapping vs BigText checker checks
- fix: Add BigText's 28-140px size range or omit-size option and the max-3-lines rule to the mission's text-slot instructions.

## 3. [warning] The mission tells the worker to preview but does not say to pass the exact timeline with a seconds mapping using each cut's screen_seconds and the theme, as the preview_slides tool notes require.

- parts: mission, tools
- where: mission Step 3 vs preview_slides tool notes
- fix: Add preview call requirements: pass the exact timeline, the seconds map {cut_id: screen_seconds}, and the visuals theme.

## 4. [warning] The mission says element where is the slot id, while the schema requires kicker and source elements to use where values 'kicker' and 'source', leaving a required field ambiguous.

- parts: mission, outputs
- where: mission 'Design spec' elements vs design_spec element.where description
- fix: Explain that slot elements use the slot id, kicker uses where 'kicker', source uses where 'source', and any inner place may be appended.

## 5. [warning] The emphasis instructions list Steps active, RouteMap current, BarChart highlight, and HtmlSlide data-on, but omit BigText highlight, although the checker's cue guidance expects BigText emphasis to be set with props.

- parts: mission, checker
- where: mission 'Emphasis' vs checker FOCUS/cues guidance
- fix: Add BigText highlight as the BigText emphasis prop and note that cues are not used.

## 6. [warning] The checker RULES say each ch- material must use its specific screen template, but the checker code only checks the ch- prefix and does not enforce the exact template mapping.

- parts: checker
- where: checker RULES material rule vs check/_slots code
- fix: Either enforce the specific template mapping in the checker code or soften the RULES to match the code's prefix-only check.
