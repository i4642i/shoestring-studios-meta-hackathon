# 제출 양식 초안 — Shoestring Studios

작성: 2026-10-27 (개발 시작 전 초안)
제출 페이지: https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit
마감: **한국 11-05(목) 11:00** (미국 동부 11-04 9:00 PM). 마지막 한 시간까지 미루지 말 것.

> **주의**: 아래 서술형 답은 **계획 기준 초안**입니다. 실제로 만든 기능만 남기고, 만들지 못한 것은 반드시 지운 뒤 제출하세요. 심사 규칙상 대회 중 만든 것만 보여 줘야 하고, 없는 기능을 적으면 감점이나 실격 위험이 있습니다.
> `[ ]` 표시는 개발하면서 채우거나 확인할 곳입니다.

---

## 1. 선택·짧은 칸

| 칸 | 답 | 메모 |
|---|---|---|
| Team Name * | `Shoestring Studios` | 양식에 프로젝트 이름 칸이 없어서 팀 이름 칸에 넣음 |
| Team Members | Sangho KIM (NexTopologix) | 자동 표시 |
| Which track * | **Indie Developer Track** | |
| Which problem statement * | **Build for Your World** | |
| Most Viral용 X 게시물 링크 | `[ ]` | 선택. 도전하려면 X 계정이 필요 |
| Public GitHub Repository * | `https://github.com/i4642i/shoestring-studios-meta-hackathon` | 제출 전 **시크릿 창에서 열리는지 확인** |
| 3-Minute Demo Video * | `[ ]` YouTube 링크 | 공개 범위(일부 공개 가능 여부)는 확인 필요 |
| 동의 체크 | 체크 | Meta와 Cerebral Valley가 제출물을 홍보에 쓰도록 허락 |

---

## 2. Project Description *

> 무엇을 만들었고 어떤 문제를 푸는지

```
Shoestring Studios is a video studio staffed entirely by AI agents. Paste in a hard textbook chapter, and the crew turns it into a narrated explainer video plus a claim-to-source report that links every statement in the video back to the exact passage it came from.

The problem: dense material is where people need help most, yet AI-made explanations often feel generic, loosely structured and sometimes wrong, and viewers can't tell which parts to trust.

How it works: a Planner agent picks the 2-4 ideas that matter and designs the story. Writer agents draft a lively narration. Reviewer agents, a "beginner viewer" and an accuracy gate, must approve the script, and code checks that every quoted source passage really exists in the original text, so false claims cannot slip through silently. A production stage then builds the storyboard, illustrations, charts and narration, and renders the video automatically.
```

**번역**
Shoestring Studios는 직원 전원이 AI 에이전트인 영상 스튜디오입니다. 어려운 교재 한 장을 붙여 넣으면, 제작진이 나레이션이 붙은 해설 영상과 "주장↔근거" 보고서를 만듭니다. 이 보고서는 영상 속 모든 문장을 원문의 정확한 구절과 연결해 줍니다.

문제: 어려운 자료일수록 도움이 가장 필요한데, AI가 만든 설명은 뻔하고 구조가 느슨하며 가끔 틀립니다. 그리고 시청자는 어느 부분을 믿어도 되는지 알 수 없습니다.

작동 방식: 기획자 에이전트가 중요한 개념 2~4개를 골라 이야기를 설계합니다. 작가 에이전트들이 생생한 나레이션을 씁니다. 검토자 에이전트("초보 시청자"와 정확성 검사)가 대본을 통과시켜야 하고, 코드가 인용된 원문 구절이 실제로 원문에 있는지 확인합니다. 그래서 틀린 주장이 조용히 통과하지 못합니다. 마지막으로 제작 단계가 스토리보드, 삽화, 차트, 나레이션을 만들고 영상을 자동으로 렌더링합니다.

---

## 3. Describe your use of Meta products to build the submitted project *

> 어떤 Meta 제품을 어떻게 썼는지. 심사 항목 "Use of Meta AI tooling(25%)"과 직결

```
Every agent in the studio runs on a Meta model, each chosen for its role:

- Muse Spark 1.3 (Model API): the Planner and Writers. Its 1M-token context reads the whole chapter at once, and we use tool calling and structured output so each agent hands off clean JSON to the next.
- Muse Wonder 1.0 (Model API): the accuracy gate, the final reviewer that checks every claim against the source before anything is produced.
- Muse Image 1.0 (Model API): illustrations for each scene of the storyboard.
- Muse Glimmer (open weights, self-hosted on a single NVIDIA B200 with vLLM): the high-volume crew, such as per-claim source checks and rewrite passes, at zero token cost.
- [ ] Muse Spark Open via Baseten: [use only if credits are granted and it is actually used]
- [ ] Muse Voice Transcribe 1.0: transcribes the finished narration audio and compares it with the approved script, so the voice track says exactly what was verified. [idea, keep only if built]

We also used Muse Code during development. [keep only if true]
```

**번역**
스튜디오의 모든 에이전트는 Meta 모델로 돌아가며, 모델마다 역할에 맞게 골랐습니다.
- Muse Spark 1.3 (Model API): 기획자와 작가. 100만 토큰 컨텍스트로 교재 한 장을 통째로 읽습니다. 도구 호출과 구조화 출력을 써서 각 에이전트가 다음 에이전트에게 깔끔한 JSON을 넘깁니다.
- Muse Wonder 1.0 (Model API): 정확성 검사. 제작에 들어가기 전에 모든 주장을 원문과 대조하는 최종 검토자입니다.
- Muse Image 1.0 (Model API): 스토리보드 장면별 삽화.
- Muse Glimmer (공개 가중치, NVIDIA B200 1장에서 vLLM으로 직접 실행): 주장별 근거 확인, 다시 쓰기 같은 반복 작업 담당. 토큰 비용이 0입니다.
- `[ ]` Muse Spark Open (Baseten): 크레딧을 받고 실제로 썼을 때만 남김.
- `[ ]` Muse Voice Transcribe 1.0: 완성된 나레이션 음성을 받아쓰기해서 승인된 대본과 비교합니다. 음성이 검증된 내용 그대로 말하는지 확인합니다. (아이디어 단계, 만들었을 때만 남김)

개발할 때 Muse Code도 썼습니다. (사실일 때만 남김)

---

## 4. Why are Meta's models important to your solution? *

> 왜 Meta 모델이 핵심인지

```
Three things make this project possible on Meta's models:

1. Long context and multimodal input. A textbook chapter, with its figures, fits in Muse Spark's 1M-token window, so every agent works from the full original instead of fragments. That is what makes claim-to-source checking reliable.
2. One model family from cloud to open weights. Muse Glimmer is distilled from Muse Spark, so we can split the work: the heavy, repetitive checks run on open weights on a single GPU, and only the decisions that matter go to Muse Spark and Muse Wonder. A full chapter-to-video run stays cheap enough for an individual creator. [replace with measured cost per run]
3. A full creative toolset in one place. Reasoning, illustration and transcription all come from Meta models, so the whole pipeline, from reading to the finished video, is built on one platform.
```

**번역**
Meta 모델이라서 이 프로젝트가 가능한 이유는 세 가지입니다.
1. **긴 컨텍스트와 멀티모달 입력.** 교재 한 장을 그림까지 포함해 Muse Spark의 100만 토큰 창에 통째로 넣을 수 있습니다. 그래서 모든 에이전트가 조각이 아니라 원문 전체를 보고 일하고, 그 덕분에 주장↔근거 대조를 믿을 수 있습니다.
2. **클라우드부터 공개 모델까지 한 가족.** Muse Glimmer는 Muse Spark에서 증류된 모델이라 일을 나눌 수 있습니다. 무겁고 반복적인 검사는 GPU 한 장의 공개 모델이 하고, 중요한 판단만 Muse Spark와 Muse Wonder가 합니다. 그래서 교재 한 장을 영상으로 만드는 비용이 개인 제작자도 감당할 만큼 낮습니다. `[ ]` 실제로 잰 1회 비용으로 바꿀 것
3. **창작 도구가 한곳에.** 추론, 삽화, 받아쓰기를 모두 Meta 모델로 하니, 읽기부터 완성 영상까지 파이프라인 전체를 한 플랫폼 위에 만들었습니다.

---

## 5. 선택 칸 (개발 후 작성)

| 칸 | 계획 |
|---|---|
| Meta 제품 사용 소감 | `[ ]` 실제로 써 보고 좋았던 점, 불편했던 점을 솔직하게. 예: Muse Code, API 문서, 도구 호출 |
| 파트너 기술 사용 소감 (Fireworks, Modal, Baseten) | `[ ]` 실제로 쓴 것만 |

---

## 6. 제출 전 체크리스트

- [ ] 서술형 답에서 **만들지 못한 기능은 모두 지웠는가**
- [ ] `[ ]` 표시를 모두 채우거나 지웠는가
- [ ] GitHub 저장소가 **Public**이고, **시크릿 창에서 열리는가**
- [ ] 저장소에 `.env`, API 키, 교재 원문이 **없는가**
- [ ] README에 "모든 코드는 대회 기간에 작성"과 실행 방법이 있는가
- [ ] 3분 영상이 **대회 중 만든 것만** 보여 주는가, 실제로 끝까지 도는 모습이 있는가
- [ ] 영상 첫 부분에서 "누가, 어떤 문제를, 어떻게 나아지는지"(Impact 30%)를 말하는가
- [ ] YouTube 링크가 로그아웃 상태에서 재생되는가
- [ ] 마감(한국 11-05 11:00)보다 **여유 있게** 제출했는가
