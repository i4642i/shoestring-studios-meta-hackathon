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
- [x] 1 J3 sign + default camera (10ac785)
- [x] 2 J5 Order adaptive (0180077)
- [ ] 3 Flow box (B1/B3/B5 re-test)
- [ ] 4 J1/J2 Crew portraits
- [ ] 5 J4 PDF button in Sam's bubble
- [ ] 6 J6/J7 run controls
- [ ] 7 J8/J9 employee memory + chat
- [ ] 8 J10/J11 office live states + click to chat
