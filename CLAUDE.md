# THE BOARDING PASS TIMES — 작업 규칙

인천·김포 출발 직항 노선의 실제 최저가를 매일 아침 신문 형식으로 발행하는 정적 사이트.
확정 사양은 `docs/PLAN.md`. 작업 전에 반드시 읽는다. 사용자와는 한국어로 대화한다.

## 구조
- `index.html`: 단일 파일 사이트(Tailwind CDN + Alpine.js). `./flights_data.json`을 읽어 렌더링.
- `collect_flights.py`: 매일 수집. 결과를 `flights_data.json`(최근 14발행일)과 `data/history/YYYY-MM.csv`(영구 이력)에 저장.
- `history_store.py`, `build_reports.py`: 영구 이력 저장, 월간·분기·연간 리포트(`data/reports/`).
- `migrate_history.py`: 과거 데이터 이전용(1회성).
- `probe_live_price.py` + `.github/workflows/probe_live_price.yml`: 실조회 진단(수동 실행).
- `.github/workflows/daily_flights.yml`: 매일 07:30 KST 수집 후 커밋 → GitHub Pages 배포.

## 절대 규칙
1. 가격·항공사·편명·시각은 그날 실제 조회값만. 기준가·이월·추정·고정값 금지. 조회 못 하면 그 노선은 발행하지 않고 사유를 남긴다.
2. 직항만. 출발 공항은 ICN·GMP.
3. 구글 플라이트 수집 요청에 `hl=ko` 금지(2026-10 장애 원인: fast-flights 2.2는 영어 "Nonstop"으로 직항 판정).
4. 영구 이력(`data/history`)에는 1위 일정만. 2위는 넣지 않는다.
5. API 키는 GitHub Secrets에만.
6. 차단 우회(CAPTCHA 회피 등) 금지.

## 작업 방식
- main은 매일 수집이 도는 브랜치라 항상 동작해야 한다. 단계별로 `feat/...` 브랜치 → 브랜치에서 워크플로 수동 실행으로 검증 → main 병합.
- 워크플로는 브랜치를 지정해 수동 실행할 수 있다(`workflow_dispatch`, ref=브랜치).
- 데이터 형식을 바꾸면 이 파일과 `docs/PLAN.md`의 해당 부분을 함께 고친다.
- 검증하지 않은 것을 "동작함"이라고 보고하지 않는다. 확인 못 한 항목은 명시한다.
- 확정되지 않은 판단은 기본값으로 진행하고 커밋/PR 설명 첫 줄에 적는다.

## 진행 상황
- 2026-11-02: 실조회 복구(fast-flights 2.2, currency=KRW, max_stops=0). 첫 실조회 51/58 성공.
- 2026-11-02: 개편 사양 확정(`docs/PLAN.md`). P0 착수.
