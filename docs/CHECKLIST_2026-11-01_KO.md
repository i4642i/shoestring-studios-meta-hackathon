# 작업 체크리스트 (2026-11-01)

## STEP 0 정리
- [x] A1 Studio 파일 3개 커밋

## STEP 1 입력
- [x] F1 Marty: Source PC 지도를 전문보다 먼저 입력
- [x] F2 Penn: 그림·표·수식 목록 입력 (주소·제목만)
- [x] F3 Ash: 텍스트 전문 입력 제거 (pc_read_source는 유지)
- [x] F4 Penn: Wren 세부 시간 입력 제거, 컷 시간은 writer가 복사
- [x] F5 복사 직원 입력 3종: Pia·Max(컨셉 없음) / Gene·Vera(컨셉 포함) / Remy(컷 시간+스타일 가이드+Vera 초안만)
- [x] G1 경계 대사: Pia·Gene·Max·Vera에게 앞 파트 마지막 컷·다음 파트 첫 컷 (읽기 전용), Remy 제외
- [x] F6 검사는 ID·키 비교

## STEP 2 Vera
- [x] D1 후보 설명으로 1차 선택 후 고른 것만 열기 (컷당 vera_view_image ≤ 2)
- [x] D2 검사: 후보 4개인 컷에서 열기 ≤ 2

## STEP 3 Ash
- [x] E1 handoff에 slide_remy 허용, part_split이 slide_remy@pN 행 생성
- [x] E2 장면 ≥ 10초 검사
- [x] E3 Source/Theory/Article 행이 kind=map + parts인지 코드로 확인·보고

## STEP 4 영상 제작
- [x] H1 Marty 구성 → video_production 선 제거, 파트 정보는 복사 직원 결과에 붙여 전달, storyboard_table.json 동일

## STEP 4b Flow 탭
- [x] B1 캔버스가 화면 높이 전체 (고정 높이 없음, 리사이즈·탭 표시 때 재계산)
- [x] B2 직원 목록·STEP MODE는 접히는 서랍 (기본 접힘, 캔버스 위에 겹침)
- [x] B3 Fit 가로·세로 모두, 로드·리사이즈 자동, 휠 확대, 배경 드래그 이동
- [x] B4 70% 미만 줌: 노드 이름·역할만, 선 글자 hover만
- [x] B5 1920·1280·390 캡처, 노드 21개 겹침 없음, 페이지 스크롤바 없음

## STEP 5 Board 화면
- [x] C1 헤더: 제목, run 선택, 단계 버튼 4개(파트 선택), 범례
- [x] C2 단계 띠: 직원별 알약, 영상팀은 파트별 알약
- [x] C3 표: 2줄 머리글(STORYBOARD TEAM 파랑 / VIDEO TEAM 주황), 열 12개, 파트·장면 rowspan
- [x] C4 칸 색 6종 + 썸네일 + 작업 중 점 깜빡임 + 3초 자동 새로고침
- [x] C5 옆 패널: 열마다 카드(대사·음성 재생·사진 갤러리·레이아웃 미니맵·렌더 PNG·비용·report.md 링크)
- [x] C6 1000px 아래에서 패널이 표 아래로
- [x] C7 1920·1280 캡처 + 사진 칸 클릭 캡처, 콘솔 오류 0

## STEP 6 마무리
- [x] I1 전체 스위트 통과, 모델 호출 0, MP4 없음
- [x] I2 docs/REPORT_2026-11-01_INPUTS_EN.md (한국어 요약 먼저)

## Order 간판
- [x] J3 라운지 왼쪽 벽 간판 "MAKE AI PROVE IT." + 1280 기본뷰 캡처
  left wall, second line HACKATHON 2026, visible in default view

## Order 적응형
- [x] J5 카드 1600·방 높이 자동·말풍선 55%·입력창 전체·1920/1280/390 캡처

## 대기열 (2026-11-01 오후)
## 대기열 (2026-11-01 오후)
- [x] 1 J3 Order 휴게실 간판 + 기본 카메라 (10ac785)
- [x] 2 J4 Sam 말풍선 속 PDF 버튼 (a39b108)
- [x] 3 J5 Order 탭 적응형 (0180077)
- [x] 4 Flow 박스 (B1/B3/B5 재검사) (c11651b)
- [x] 5 J1/J2 직원 초상화 (dda766c)
- [x] 6 J12 메뉴 순서 (93dd36d)
- [x] 7 J6/J7 실행 제어 (9c62540)
- [x] 8 J10/J11 사무실 실시간 상태 + 클릭 채팅 (d524896)
- [x] 9 J8/J9 직원 프로젝트 메모리 + 채팅 (ae9bae9)
- [x] 10 J13/J14 입력 로그 + 스펙 검사 (3fa6b80)
- [x] 11 J15 Board 검증 화면 (9024280)
- [x] 12 J16 프로젝트 폴더 로그 (d3efb37)
- [x] 13 J17 설정 화면 배치 (e93dacf)
- [x] 14 J18 PC 탭 배치 + 실제 권한 (f70c709)
- [x] 15 J19/J20 전체 탭 너비 + 갤러리 (1302c52)
- [x] 16 J21 About 탭 + 정직한 표기 (6daa397)
- [x] 17 J22 프로필 카드 + handbook RAG 제거 (8be1c97)
- [x] 18 J23 네모 초상화 + Flow 노드 얼굴 (60b1325)
- [x] 19 J24 팀별 직원 묶음 + 직원 추가에 팀 (6a76e5e)
- [x] 20 J25 Order 접수 완료 상태 (2596620)
- [x] 21 J26 3D 성능 (1e99c16)
  측정 (1920x1080, GPU GTX 1050, window.__perf 3초):
  장면 | fps | draw calls | 삼각형 | 그림자 | 픽셀비
  사무실 전 | 29.6~35.3 | 565 | 48,582 | 4096 | 1
  사무실 후 | 58.9 (rAF) / 렌더 30fps 고정 | 425 | 37,182 | 2048 | 1
  Order룸 전 | 60.2 | 102 | 4,820 | 2048 | 1
  Order룸 후 | 60.1 | 102 | 4,820 | 2048 | 1 (변경 없음)
  전 측정은 2596620을 임시 worktree에 받아 측정용 __perf만 얹어 측정 (동작 변경 없음, worktree 삭제됨).
  렌더 fps가 그대로인 것은 30fps 고정 때문. 여유는 rAF 29.6→58.9Hz, calls −25%, 삼각형 −23%, 그림자 1/4로 확인.
- [x] 22 J27 영상 도구 설치 + 스모크 (143cb13)
  B5 실제 경로 시간: still 7.3초 / 음성 15.5초 (오디오 6.4초) / MP4 0.7초. still은 헤드리스 브라우저(GPU), 음성과 MP4 인코딩은 CPU.
- [x] 23 J28 검사 브라우저 GPU 사용 (9번 다음) (034da5c)
  office_live_check: gpu 32.4 s vs software 93.2 s, both ALL PASS
  flow_headless via scripts/_browser.dump_dom_args (fbde91c)
- [x] 24 J29 워크플로 없는 직원 삭제 (voice_iris) (b90193f)
- [x] 25 J30 사무실·Order룸 20fps 고정 + Settings 프레임 설정 (15/20/30) (7897e72)
- [x] 26 J31 채팅 토큰 청소 + 버튼 없는 대화 시작 (yes/no/모호함)
  측정 (1920x1080, GPU GTX 1050, 3초 렌더 수): 사무실 88→52, Order룸 181→53. rAF는 60 유지.
