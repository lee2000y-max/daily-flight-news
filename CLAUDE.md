# THE BOARDING PASS TIMES — 작업 규칙

인천·김포 출발 직항 노선의 실제 최저가를 매일 아침 신문 형식으로 발행하는 정적 사이트.
확정 사양은 `docs/PLAN.md`. 작업 전에 반드시 읽는다. 사용자와는 한국어로 대화한다.

## 구조
- `index.html`: 단일 파일 사이트(Tailwind CDN + Alpine.js). `./flights_data.json`(형식 v2)을 읽어 렌더링. 불러오기 실패 시 가짜 데이터 없이 안내만 표시.
- `routes.py`: 도시 마스터(가격과 무관한 정보만). `airports`에 도시의 도착 공항들, `GMP_DESTINATIONS`에 김포 취항지.
- `collect_flights.py`: 매일 수집.
  1. 날짜 검색(fli 0.9.0, 구글 달력 API): 출발 ICN(+김포 취항지는 GMP) × 공항 × 2~8박, 출발 D+14~60, 직항, KRW.
  2. 토·일 포함 + 연차(공휴일 제외 평일) 5일 이하만 후보.
  3. 후보를 가격순으로 상세 검색(최대 6개)해 직항이 확인된 일정끼리 1위·2위(출발일 3일 이상 차이) 선정. 화면 가격 = 상세 검색 가격.
     상세 미확인 2위는 날짜 검색 가격 중 1위 이상만. 상세가 모두 오류면 날짜 검색 가격으로 발행(항공편 정보 없음).
  4. 직항 0건·조건 불일치·조회 오류 도시는 발행하지 않고 `failed`에 사유 기록.
  5. 월요일엔 김포 출발을 모든 공항으로 조회해 새 노선을 로그에 보고(`🆕`).
- `flights_data.json` v2: `schemaVersion`, `latestDate`, `availableDates`(최근 14발행일), `status`(날짜별 발행 수), `flights`(1위 + `alt` 2위), `failed`, `historicalSeries`(영구 이력에서 계산).
- `history_store.py` / `data/history/YYYY-MM.csv`: 영구 이력(1위만). `build_reports.py` / `data/reports/`: 월간·분기·연간 리포트.
- `probe_route.py` + `.github/workflows/probe_live_price.yml`: 특정 노선 진단(수동 실행, 입력 route).
- `.github/workflows/daily_flights.yml`: 매일 07:30 KST. 수동 실행 입력 `only_cities`, `dry_run`. 브랜치에서 실행하면 그 브랜치에 커밋.

## 알아 둘 함정
- fli는 0.9.0으로 고정. 0.10부터는 구글이 달력 API에 브라우저 서명을 요구해 날짜마다 페이지를 받으므로 수십 배 느림.
- fli 0.9.0은 영문 이름이 같은 공항을 하나로 합침. 오키나와 OKA가 인도네시아 NAH로 바뀌던 문제를 워크플로 `Patch fli airport aliases` 단계에서 보정·검사한다. 노선을 추가하면 이 검사가 잡아 준다.
- fli 항공사 목록이 오래됨(예: 9G를 "9G Rail"로 표기). `AIRLINE_KO`에 없는 코드는 코드로 표시한다.
- 달력 API가 막히면 예비 수단: 실제 브라우저(Playwright)로 구글 항공권을 열면 화면이 보내는 `GetCalendarPicker`/`GetCalendarGraph` 응답에 원화 가격이 들어 있음(2026-11-02 실측 확인, 브랜치 `spike/calendar`의 `probe_calendar.py`).
- 구글 시트 동기화와 Gemini 노트는 v2에서 제거됨.

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
- 2026-11-02: 개편 사양 확정(`docs/PLAN.md`). P0 착수: 새 수집기(v2)·화면 반영, 브랜치 `feat/p0-collector`.
