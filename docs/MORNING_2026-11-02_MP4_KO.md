# 아침 노트 (2026-11-02 MP4)

주문 ID: `ord-20261102-027`, 런: `flow-20261102-071503-2393`
MP4: `runs/flow-20261102-071503-2393/video_production/video.mp4`
(720초, 1280x720 h264 + AAC, 9.3MB, Gallery 탭에서 재생 확인)

## 직원별 수정 (한 줄씩)

- Sam: 수정 없음 (기존 요청서 재사용, 그대로 통과).
- Marty: key-concepts 축소 8→3부 + 스킵 사유, Sam 요청서 요약 제거·출처 PC 지도 사용.
- Cleo/Rex: temperature=0 되돌림(기본 샘플링이 통과율 높음) + 첫 pick 10단계 마감.
- Ash: storyboard_draft 정확한 형태 + 10단계 마감, 문자열 파싱·실패 원인 표시.
- Wren: make_voice(kokoro) 먼저 + 정확한 narration 형태 + 단어 수 직접 세기, 10→14단계, 부분-인식 거부 메시지, 모든 실패 경로에 원인 표시.
- Penn: 수정 없음 (42초 만에 한 번에 통과).
- part_split: style_guide를 들고만 있고 전달 안 하던 버그 수정.
- Pia/Gene/Max: 수정 없음 (세 파트 전부 통과).
- Vera: slide 형태 + 박스 수학(너비 계산식) + appear_s 규칙 + 8단계 마감.
- Remy: style_guide 전달 라인 c102 추가 + render 형태, 렌더 강건성(node 직접 실행·슬라이드 경로·PNG 필수 확인).
- video_production: assemble API + 내장 ffmpeg + 전체 길이(-t) + MP4 위치 수정.
- 공통: runner가 INPUT FILE 경로만 보내고 내용을 안 보내던 근본 원인 수정(70k 토큰 인라인 후 전 단계 안정화), "failed: unknown" 제거.

## 직접 확인해 주세요

1. Gallery 탭에서 영상 재생 (자막·음성·화면 어울림).
2. Board 탭에서 직원별 리포트 읽기 (특히 Wren 대사·Vera 슬라이드).
3. `runs/.../video_production/captions.srt` 자막 타이밍 (단어 단위 아님, 컷 단위 비례).

## 못 고친 것

- 단어 단위 자막용 음성인식(transcribe 400 오류) → 컷 단위 비례 자막으로 대체.
- smoke_server 기존 실패 1건 (crew 생성에 team 필수 이후 미갱신) → 오늘 범위 밖.
- tools-off 재시도는 거의 항상 빈 답으로 붕괴 → 마감·형태 규칙으로 우회, 재시도 자체는 그대로.
- TTS 목소리·영상 미감은 제가 판단 못 함 → 직접 보시고 말해주세요.

토큰: LLM 262회, prompt 약 14.7M(캐시 반복 포함), completion 약 538k.
자세한 로그: 각 단계 `llm_calls.jsonl`, `runs/.../video_production/assemble.log`.
