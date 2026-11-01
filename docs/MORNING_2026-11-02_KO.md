# 아침 보고 (2026-11-02)

대기열 24개를 다 했습니다. 모델 호출 0번, MP4는 테스트용 8초짜리 1개 만들고 바로 지웠습니다.

## 1. 체크리스트 결과: 54/54 [x], 남은 [ ] 없음

- STEP 정리/입력/Vera/Ash/영상제작/Flow탭/Board/마무리 28개 전부 [x]
- 대기열 1~24 전부 [x] (J3/J4/J5/Flow/J1-J2/J12/J6-J7/J10-J11/J8-J9/J13-J14/
  J15/J16/J17/J18/J19-J20/J21/J22/J23/J24/J25/J26/J27/J28/J29)
- 마지막 전체 재검사: 29개 스위트 전부 통과 (fixture 13 + live 16)

## 2. 커밋 목록 (큐 항목 순)

- 10ac785 Queue 1 (J3): slogan second line + default camera shows both signs
- a39b108 J4: PDF button inside Sam's bubble, drop on room, missing in replies
- 0180077 Queue 2 (J5): Order tab adaptive (wide card, room fills window, bubbles)
- c11651b Flow box fills card+window, Fit floor 0.25, status on toolbar
- dda766c J1/J2: crew card portraits from shared offscreen 3D renderer
- 93dd36d J12: menu order Order Crew PC Flow Studio Board Gallery Settings
- 9c62540 J6/J7: run controls (pause/resume/step/stop), auto-start, Studio+Board bars
- d524896 J10/J11: office live states from run files + click to chat
- ae9bae9 J8/J9: per-employee project memory (LightRAG) + Studio chat
- 3fa6b80 Item 10: per-node INPUTS manifest + PC reads log + inputs spec check
- 9024280 Item 11: Board verify view (summary bar, empty state, per-cell cards)
- d3efb37 Item 12: per-order project log (LOG_INDEX.json, timeline, Project log link)
- e93dacf Item 13: Settings two-column layout with Local/Jetson index matrix
- f70c709 J18 PC tab layout plus real rights
- 1302c52 J19/J20 All tabs width plus Gallery
- 6daa397 J21 About layout plus honest claims
- 8be1c97 Item 17 J22: profile card per employee, handbook plain text, no handbook RAG
- 60b1325 Item 18 J23: square crew portraits, faces on Flow nodes
- 6a76e5e Item 19 J24: crew grouped by team, team on add/edit employee
- 2596620 Item 20 J25: order received lock, server refuses started orders
- 1e99c16 Item 21 J26: 3D perf (cheaper shadows, pause hidden, __perf hooks)
- 5f4b545 Item 22 J27: video toolchain installed, smoke proven, MP4 deleted
- 034da5c J28: check browsers use the GPU via shared helper (+ fbde91c 후속)
- b90193f Item 24 J29: delete voice_iris, 12 employees all in the flow

푸시는 안 했습니다. main이 origin보다 앞서 있으니 직접 푸시해 주세요.

## 3. 직접 눈으로 확인할 것 (이번 작업분)

- Crew 탭: 카드 사진이 네모(88px) + STORYBOARD TEAM (7) / VIDEO TEAM (5) 두 구역 + Iris 없음 (runs/crew_12_1920.png와 비교)
- Flow 탭: 직원 노드에 얼굴, Fit 53% (1920x940) / 33% (1280x720) (runs/flow_faces_1920.png)
- Order 탭: 실제 주문 1건을 끝까지 시작해 보면 방이 어두워지고 Order received 카드 (runs/order_received_1920.png)
- Studio 탭: 사무실 그림자 이상 없는지, 탭을 옮겼다 돌아오면 사무실이 멈췄다가 다시 움직이는지 (runs/office_perf_1920.png)
- Studio 채팅: 메모리 없는 직원에게 물으면 "I don't have my project memory yet" 식으로 모른다고 하는지
- Board 탭: 영상팀 칸이 파트별 상태로 나오는지 (fixture로만 확인됨)

## 4. 설치·실행이 필요한 것 (Needs owner)

- 영상 도구 2개는 수동 설치가 필요합니다 (pip로는 안 됨):
  `ffmpeg` (ffmpeg.org, PATH에) + `espeak-ng` (Kokoro 영어 폴백용)
  나머지는 설치됨: requirements-video.txt (kokoro 0.9.4, torch 2.14.1+cpu,
  soundfile 0.14.0, imageio-ffmpeg 0.7.0) + video/remotion/node_modules
  확인용: powershell -ExecutionPolicy Bypass -File tools/setup_video.ps1
- Jetson 인덱스는 REBUILD INDEX를 직접 눌러 주세요 (규칙대로 안 건드림)
- TAVILY_API_KEY가 없으면 Cleo/Rex 검색은 스텁입니다
- 첫 실제 운영은 Flow step mode로 1단계씩 승인하면서 해주세요
- 테스트 흔적: runs/smoke_still.png, runs/smoke_sentence.wav만 남김 (무시 목록이라 커밋 안 됨). 테스트 MP4는 지웠습니다.
