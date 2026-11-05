# THE BOARDING PASS TIMES — 작업 규칙

인천·김포 출발 직항 노선의 실제 최저가를 매일 아침 신문 형식으로 발행하는 정적 사이트.
확정 사양은 `docs/PLAN.md`. 작업 전에 반드시 읽는다. 사용자와는 한국어로 대화한다.

## 구조
- `index.html`: 단일 파일 사이트(Tailwind CDN + Alpine.js, **Alpine은 `alpinejs@3.14.9`로 다섯 페이지 모두 고정**). `./flights_data.json`(형식 v2)을 읽어 렌더링. 불러오기 실패 시 가짜 데이터 없이 안내만 표시.
- `routes.py`: 도시 마스터(가격과 무관한 정보만). `airports`에 도시의 도착 공항들, `GMP_DESTINATIONS`에 김포 취항지.
- `collect_flights.py`: 매일 수집.
  1. 날짜 검색(fli 0.9.0, 구글 달력 API): 출발 ICN(+김포 취항지는 GMP) × 공항 × 2~8박, 출발 D+14~60, 직항, KRW.
  2. 토·일 포함 + 연차(공휴일 제외 평일) 5일 이하만 후보.
  3. 후보를 가격순으로 상세 검색(최대 6개)해 직항이 확인된 일정끼리 1위·2위(출발일 3일 이상 차이) 선정. 화면 가격 = 상세 검색 가격.
     상세 미확인 2위는 날짜 검색 가격 중 1위 이상만. 상세가 모두 오류이거나 모두 빈 결과(0건)면 날짜 검색 가격으로 발행(항공편 정보 없음, `detailError`에 사유). 경유만 나오면 발행하지 않음.
  4. 직항 0건·조건 불일치·조회 오류 도시는 발행하지 않고 `failed`에 사유 기록.
  5. 월요일엔 김포 출발을 모든 공항으로 조회(수동 실행 입력 `full_gmp=1`로도). `GMP_DESTINATIONS`에 없는 공항에서 김포 직항이 보이면 `data/gmp_auto.json`에 **자동 추가**(P5-5)해 다음 수집부터 매일 김포도 조회, 월요일 점검 4번 연속 미감지면 자동 제외(조회 오류는 세지 않음). 로그 `🆕`/`➖`. 로직은 `gmp_auto.py`.
- `flights_data.json` v2: `schemaVersion`, `latestDate`, `availableDates`(최근 14발행일), `status`(날짜별 발행 수), `flights`(1위 + `alt` 2위 + `leaveSaver` 연차 절약 일정 + `holidays` + `bestSeasons`), `failed`, `newRoutes`(P5-5: 신규 김포 노선이 감지된 주 7일 동안 그날 실제 조회한 김포 출발 최저 일정 — date·dest·code·city·addedOn·price·depDate·retDate·nights, 그날 1위가 그 노선이면 airline·googleUrl. 1면 '신규 취항' 기사가 톱), `historicalSeries`(영구 이력 live만, `fsc` 포함), `climate`(월 기후 평년값). (2026-11-03까지 있던 지표 키는 폐기, 아래 진행 상황 참고)
- `history_store.py` / `data/history/YYYY-MM.csv`: 영구 이력(1위만). 열: date,code,price,source,dep,ret,airline,fsc(2026-11 airline·fsc 추가). `build_reports.py` / `data/reports/`: 월간·분기·연간 리포트.
- `probe_route.py` + `.github/workflows/probe_live_price.yml`: 특정 노선 진단(수동 실행, 입력 route, mode=route).
- `.github/workflows/daily_flights.yml`: 매일 07:30 KST. 수동 실행 입력 `only_cities`, `dry_run`. 브랜치에서 실행하면 그 브랜치에 커밋.
  - `collect` 잡: 도시를 8묶음(`SHARD_INDEX`::8)으로 나눠 서로 다른 서버에서 동시 수집(`MODE=collect` → `shard_out/shard_N.json`).
  - `sellers` 잡(8개, 새 서버): 묶음 결과의 1위 일정을 브라우저로 열어 구글 예약 옵션(판매처별 가격)을 읽음(`MODE=sellers` → `sellers_out/`). 수집한 서버에서 하면 구글이 확인 화면을 띄우므로 반드시 별도 잡. 실패해도 발행은 계속.
  - `publish` 잡: 묶음 결과를 합쳐 저장(`MODE=merge`), 판매처 결과를 `sellers`로 붙임. 발행일은 묶음들이 쓴 날짜 중 다수결(자정 경계 대비). 결과가 없는 묶음의 도시는 `failed`에 기록. 발행 0건이면 저장하지 않고 실패.
  - `publish`는 `!cancelled()` 조건. 실행을 취소하면 저장도 하지 않는다(`always()`로 바꾸지 말 것).
- 화면 판정(index.html): 1면 A·C와 스탬프 1·3·6·7은 실조회 이력이 필요 일수(30·7·14) 쌓인 뒤에만 켜짐(`hasHistory`).
- `build_climate.py` → `data/climate_normals.json`(NASA POWER 월 평균기온·강수, 키 없음). 진단 워크플로 `mode=climate`로 갱신·커밋.
- 텍스트 축소(S5, 2026-11-04): 메타 줄은 VOL·발행호 선택만(링크·발행 정보는 판권으로). 1면은 요약 줄·각주·버튼 없이 제목(누르면 카드로) + 숫자 칸 [📅 일정][유형별 지표][💰 가격]. 환율 박스 삭제(수집의 `fx`는 유지). 탭은 국기·이모지 SVG + 짧은 이름. 판권: 엠블럼 → 이름 → 링크 줄 → 발행 정보 → [주의] 문구. 오늘 싣지 못한 도시는 접어 두고 사유는 쉬운 말(`plainReason`). 메인에는 출처 표기·'중앙값'·'실조회'를 쓰지 않는다(출처는 about). 날짜는 `MM/DD(요일)`(전광판만 `MM/DD-MM/DD`, 글자판 드럼에 `/`).
- 제호(S4): 왼쪽 엠블럼 `images/brand/emblem.svg`(저장소 자체 저작물, 손으로 고치지 않음) + 캡션·좌표, 오른쪽 붉은 인장. 1024px 미만은 엠블럼·인장을 한 줄에. 판권 맨 위에도 엠블럼 96px. (`images/brand/` = 엠블럼, `images/brands/` = 예약 버튼 로고)
- 도시 카드(S3, 2026-11-04 리뉴얼): 배지 + 관심·공유 툴바(SVG), 국기(`images/flags/<iso2>.svg`, flag-icons MIT, 도시→국가 `routes.CITY_ISO2`·`js/common.js`), 가격·직전호 대비, 📅 일정(`MM/DD(요일)~MM/DD(요일) N박 N일`)+출도착 시각, ✈️ 항공사명(편명은 카드에 안 씀), 🛫 터미널, 📌 현지 메모 + 도장, 예약 버튼 3개(티켓 스텁 2026-11-05: 위 브랜드 색 스텁 + 공식 로고 18px `images/brands/`, 아래 양피지에 이름. 구글 = 흰 스텁 + 4색 띠, 네이버 = 초록, 스카이스캐너 = 남색. 구글 링크가 없으면 2열). 출처·판매처·현지 통화·다른 일정·그래프는 카드에서 뺌.
- 터미널: `data/terminals.json` = 인천공항 공식 '취항정보'의 항공사별 T1/T2(2026-11-04 확인) + 도착 공항 짧은 이름. 화면에서 그날 실제 항공사 코드로 `인천 T1 ⇄ 간사이`처럼 만든다. 표에 없는 항공사·항공편 정보 없는 날은 🛫 행 숨김. **도착 공항 터미널 번호는 공식 확인 자료가 없어 쓰지 않는다.** 항공사 터미널 이전이 있으면 표를 다시 확인해 고친다.
- 이모지: 화면의 이모지는 문자 대신 `images/emoji/<코드포인트>.svg`(Noto Emoji, Apache-2.0)로. `<option>`·메타·전광판은 예외. 공용 함수 `js/common.js`(`BPT.fmtMD`·`fmtRange`·`fmtNights`·`flagSrc`).
- `about.html`(P5-1): 만드는 방법·원칙·1면 유형·스탬프·자료 출처·**사진 출처 전체 목록**(`data/photos.json`, 라이선스 링크). 이번 호 미발행 도시는 `flights_data.json`에서. 상단 발행 줄·1면 전광판 안내·판권에서 링크.
- `city.html?code=YGJ`(P5-2): 도시 상세. 오늘 1위·2위·연차 절약(실조회), 항공편·판매처, 가격 이력(`historicalSeries` 실조회 1위만, **7일 이상부터 그래프**), 월별 기후·추천 시즌. 미발행 도시는 사유만(가격 없음). 카드 도시 이름·'가격 이력·날씨 →'에서 연결.
- 관심 도시(P5-3): 카드 ☆ → localStorage `bpt-favs`(이 브라우저만). 1면 아래 '내 관심 도시' 띠(미발행이면 가격 없이 '이 호에는 미발행').
- `build_extras.py`(P5-3·4, 배포 때 실행, 커밋 안 함): `feed/<도시>.xml` 도시별 RSS(영구 이력 live만, 최근 30건) + `data/archive.json` 보관함 요약(날짜별 발행 수·하위 5곳, 이전 수집기 기록은 `source: reference`).
- 예약 시점 통계(P5-6): `build_extras.py`가 `data/leadtime.json`(지역별 1위 일정의 출발까지 남은 날 분포, 실조회 live만)을 만들고 `archive.html` 위에 표시. **실조회 90일 미만이면 숫자 없이 안내만**(`ready=false`).
- `archive.html`(P5-4): 지난 호 보관함. 최근 14발행일은 `index.html?d=YYYY-MM-DD`로 그날 호 열기. 10월 기록은 '참고용'.
- `monthly.html`: `data/reports/monthly/*.json` 월간지(이전 수집기 기록이나 부분 관측 달은 '참고용'). `feed.xml`: 수집 때 생성되는 RSS.
- 환율(P3): 수집 합치기 단계에서 `open.er-api.com`(키 없음) 조회 → `flights_data.json`의 `fx`. 실패하면 빈 값(환율 박스 숨김, 이월 없음). 통화는 `routes.CITY_CURRENCY`.
- 링크 공유(P4, 공유 이미지 버튼 대체): 카드의 '🔗 이 특가 공유' → `s/<도시>/?d=YYYYMMDD` 주소를 공유(휴대폰 공유 창, 컴퓨터 복사). `build_share.py`가 사이트 배포 때 `s/<도시>/index.html`(og 태그만, 열면 `./#<도시>`로 이동)과 `thumb.jpg`(1200×630, Pillow + fonts-noto-cjk), `s/og.jpg`(사이트 기본 미리보기 = 오늘 최저가 도시)를 만든다. `s/`는 커밋하지 않는다(.gitignore). 미발행 도시는 가격 없는 썸네일·"오늘은 발행되지 않았습니다". 실패해도 배포는 계속.
- 배포(P4, 2026-11-03 사용자 결정): GitHub Pages를 브랜치 배포에서 워크플로 배포(`.github/workflows/pages.yml`)로. main 푸시, 또는 매일 수집·진단 워크플로가 main에서 끝나면(`workflow_run`) 저장소 + `s/`를 묶어 배포. 브랜치에서 수동 실행하면 묶기만(배포 안 함). 저장소 설정 Pages Source = "GitHub Actions" 필요.
- 도시 사진(P4): `data/photos.json`(출처: title·page·license·artist, 선택 place) + `images/cities/<도시>.jpg`(1600)·`_640.jpg`. 위키미디어 공용만, 출처 표기 필수(카드·1면 사진 설명). 고르기: 진단 워크플로 `mode=photos`(후보 3장 → `preview/photos` 브랜치) → 사용자가 고르면 `mode=photos_fetch`, route에 `"YGJ:2 SDJ:1 ..."`. 마음에 드는 후보가 없는 도시는 `mode=photos_more`, route에 `"CTS KOJ"`(검색어 `build_photos.REQUERY`, 4번부터 덧붙임). 사진이 없는 도시는 기존 Unsplash 임시 사진.
- 1면 전광판(P4): `FlapBoard` 엔진(index.html, rAF 루프 하나, 윗장 낙하·아랫장 펼침). 열 [유형 4|도시 7|도착 3|일정 11 `MM.DD-MM.DD`|왕복 가격 10]. 화면에 절반 이상 들어오면 재생(나갔다 다시 들어오면 재생), 휴대폰은 2줄 + 유형은 왼쪽 색 막대·범례. 한 줄 배치는 1024px 이상.
- `sellers.py`: 판매처별 가격 읽기(사용자 결정으로 매일 수집 포함, 2026-11-03). 같은 출발 시각 직항을 못 찾으면 비움. 실험 기록 `docs/P3_booking_experiment.md`, 실험 스크립트 `probe_booking.py`.
- `check_site.py`: 로컬에서 사이트를 띄워 데스크톱·모바일 화면 검사(카드 수, 구글 버튼, 금지어, 콘솔 오류, P4 전광판·사진·링크 공유·공유 페이지·360~1366px 넘침) 후 스크린샷. 전광판 부드러움(CPU 4배 느림)은 참고 수치(서버 화면 처리가 실제 기기와 달라 실패로 치지 않음). `probe_live_price.yml`을 `mode=site`로 실행하면 `preview/screenshots` 브랜치에 올린다.

## 알아 둘 함정
- 하위 페이지(about·city·archive·monthly)는 `x-data="xxxPage()"`에 `init()` 메서드가 있으면 Alpine이 알아서 한 번 부른다. `x-init="init()"`를 함께 쓰면 **두 번** 실행된다(2026-11-04 수정: 데이터 요청 2회 → 1회). 새 페이지에도 `x-init`을 붙이지 않는다.
- fli는 0.9.0으로 고정. 0.10부터는 구글이 달력 API에 브라우저 서명을 요구해 날짜마다 페이지를 받으므로 수십 배 느림.
- fli 0.9.0은 영문 이름이 같은 공항을 하나로 합침. 오키나와 OKA가 인도네시아 NAH로 바뀌던 문제를 워크플로 `Patch fli airport aliases` 단계에서 보정·검사한다. 노선을 추가하면 이 검사가 잡아 준다.
- fli 항공사 목록이 오래됨(예: 9G를 "9G Rail"로 표기). `AIRLINE_KO`에 없는 코드는 코드로 표시한다.
- 달력 API가 막히면 예비 수단: 실제 브라우저(Playwright)로 구글 항공권을 열면 화면이 보내는 `GetCalendarPicker`/`GetCalendarGraph` 응답에 원화 가격이 들어 있음(2026-11-02 실측 확인, 브랜치 `spike/calendar`의 `probe_calendar.py`).
- 구글 시트 동기화와 Gemini 노트는 v2에서 제거됨.
- 한 서버에서 수백 번 연속 조회하면 구글 응답이 크게 느려짐(0.16초 → 3.4초/회, 2026-11-02 실측). 상세 검색은 빈 결과(0건)로 돌아오기도 함(같은 날짜를 새 서버에서 조회하면 정상). 그래서 8묶음 병렬 수집, 상세 검색은 `top_n=1`, 빈 결과는 쉬었다 재시도. 스레드 병렬은 fli 내부 병렬과 엉켜 멈췄으므로 묶음 안에서는 순차 조회.

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
- 2026-11-03: P0 main 병합(PR #1, 8묶음 수집, 시험 수집 56/58). 3일 연속 정기 수집 검증은 전체 작업 후 마지막에(사용자 결정). P1 착수: 브랜치 `feat/p1-frontpage`.
- 2026-11-03: 단계별 통과 조건 없이 P1→P2→P3 연속 진행, 전체 검증은 P3 후(PLAN.md 8-1). 12월 초 10월 이력 삭제 예정. 사용량 추가 구매 금지.
- 2026-11-03: P1(PR #2)·P2(PR #3) 병합. P3(환율·공유 이미지·판매처 실험) 브랜치 `feat/p3-extras`.
- 2026-11-03: P3(PR #4) 병합. 판매처별 가격 매일 수집(PR #5).
- 2026-11-03: P4 기획안(2판) 착수: 전광판 재작성·1면 사진·링크 공유·위키미디어 사진 후보. main 병합은 11/5 '3일 연속 수집' 판정 뒤.
- 2026-11-03: P4 PR #6(병합은 11/5 판정 뒤). P5 기획안 승인(`docs/P5_PLAN.md`), 브랜치 `feat/p5-pages`(P4 브랜치에서 분기, P4 병합 뒤 main 기준으로 정리). P5-1 소개 페이지 착수.
- 2026-11-04: 2026-11-03 사용자 결정으로 '쏠림 지수'(한국인 여행객 쏠림, 1면 '한적한 여행지' 유형 포함) 폐기. 수집·워크플로·화면·데이터 키에서 모두 삭제. 사유: 정확하다고 보기 어렵고, 한국인이 적다고 다른 여행객도 적다는 보장이 없음.
