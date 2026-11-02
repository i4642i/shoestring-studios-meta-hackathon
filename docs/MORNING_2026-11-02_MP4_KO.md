# 아침 노트 (2026-11-02 MP4 — 심야 체인 반영)

주문 `ord-20261102-030`, 런 `flow-20261102-122459-0471`.
MP4: `runs/flow-20261102-122459-0471/video_production/video.mp4`
(10:00, 1280x720 h264 + AAC mono, 9.0MB).
자막 `captions.srt`, 스토리보드 표 `storyboard_table.json` 같은 폴더.

## MP4 내용 확인 (프레임 직접 봄)
- 0:30: 텍스트 카드 (온스크린 문구 4개, 스타일 가이드 색 그대로)
- 5:00: Gene 생성 일러스트 (용접→전기→도장→조립 BMW 삽화) + 자막
- 실사진: 없음 (아래 Pia 429 참조), 차트: 없음 (Max 전부 none)

## Pia 7차 쿼리별 결과 (research.jsonl 실측)
- p1 c3 'Hong Kong skyline' 8건, c4 'trading floor' 8건
- p2 c12 'car factory' 8건, c15 'supercomputer' 7건
- p3 c16 'handshake' 7건 → 'business meeting' 8건,
  c18 'skyscraper' 8건 → 'office building' 8건,
  c21 'bank branch' 8건 → 'bank vault' 5건
- 짧은 쿼리·제목 심사·0건 재검색 모두 동작. 그러나
  다운로드가 IP 429로 전멸 (실측: 같은 URL 수동 요청도 429) →
  정직한 후보 6건 (홍콩하버 pdm, 시카고 거래소 pdm, 오펠 라인,
  크레이 슈퍼컴, LA 타워, PNC 지점)을 적고 전부 none. 승인됨.

## 직원별 수정 (전부 push됨)
- Pia: Commons 우선·Openverse 25초 2구간·짧은 쿼리·0건 재시도
  (`b5190da`)
- 러너: 모델 호출 중 TLS 끊김에 런 전체 크래시 → 2회 재시도 후
  단계 실패 처리 (`b1b250b`, Vera p2 크래시 원인)
- 인덱스: 실패 뒤 성공이면 recovered (오경보 해소),
  픽할 때 map+index 워커 자동 실행 (`88e7cc8`)
- PC 행: theory/article는 Penn/Wren만, 원본은 Pia/Vera에 그림만·
  Max에 표/수식만, voice는 video_production만, Ash handoff는
  Wren/Penn만, image/generated에서 video_production 제거,
  Penn/Wren은 base ID 합산 행 (`cae369a`, `c2b262c`)
- Vera/Remy: 재실행 후 승인 (텍스트 카드 22컷, PNG 22장)
- 영상조립: video_production 기록 + assemble (9.0MB)

## 인덱스 백필 (진행 중)
- Theory jetson 25/41, Article 0/124 (순차 워커 실행 중)
- 픽 1건당 LLM 약 15~35회 (LightRAG 개체 추출) + 60~170초

## 못 고친 것 / 남은 것
- 웹 실사진 0장: Wikimedia IP 스로틀 (429) — 조용해지면 Pia만
  다시 돌리면 됨 (검색은 이미 됨)
- 차트 없음: Max 전부 none (이번 문서에 표가 적음)
- Ash 입력에 실패했던 실행의 기사 9건이 남아 있음 (이후 실행부터 prune 적용)
- step 호출이 stopped 런에서 조용히 실패함 (started:true 반환)
- inputs 검사 28개 노드 전부 OK (fresh rows 기준 재평가)
