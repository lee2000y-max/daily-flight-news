# 예약 버튼 로고

도시 카드 아래 예약 버튼(티켓 스텁, 2026-11-05 B안)의 스텁 가운데에 18px로 들어가는 공식 로고.

| 파일 | 출처 | 라이선스·조건 |
|---|---|---|
| `google-flights.png` | 구글 플라이트 공식 파비콘 `https://www.gstatic.com/images/branding/product/2x/travel_flights_64dp.png`(128px, google.com/travel/flights 페이지의 `<link rel="icon">`). 원색 그대로. Simple Icons에 구글 플라이트 전용 아이콘이 없어 공식 파비콘 사용 | 상표는 Google LLC 소유, [브랜드 가이드](https://about.google/brand-resource-center/brand-elements/). 링크 버튼 식별용으로만 사용 |
| `naver.svg` | [Simple Icons](https://simpleicons.org) 16.36.0 `naver`. 채움 색만 네이버 그린 `#03C75A`(Simple Icons `hex` 값과 같음)로 바꿈 | 아이콘 CC0. 상표는 NAVER Corp. 소유, [가이드](https://developers.naver.com/docs/login/bi/bi.md) |
| `skyscanner-white.png` | Skyscanner 공식 파비콘 `https://www.skyscanner.net/favicon.ico`(64px)에서 흰 로고 부분만 남기고 파란 바탕을 투명하게 뺌(모양은 손대지 않음). Simple Icons 16.36.0에 없음 | 상표는 Skyscanner Ltd 소유. 링크 버튼 식별용으로만 사용 |

- 직접 그리거나 비슷하게 흉내 내지 않았다.
- 스텁 색(`index.html` `:root`):
  - 구글 플라이트: 흰 바탕 + 맨 위 3px 구글 4색 띠 `#4285F4`·`#EA4335`·`#FBBC04`·`#34A853`, 로고 칸 테두리 `#DADCE0`
  - 네이버: `#03C75A`(Simple Icons 값과 같음), 로고는 흰 칸에 초록
  - 스카이스캐너: 바탕 `#05203C`, 로고 칸 `#0062E3`, 흰 로고. 두 값은 Skyscanner 디자인 시스템 Backpack(`@skyscanner/bpk-foundations-web` 24.9.0, Apache-2.0)의 `core-primary-day` rgb(5,32,60)·`core-accent-day` rgb(0,98,227)과 같음. (공식 파비콘의 파란색은 이전 색 `#0770E3`)
- 이름 글자는 브랜드 색 위가 아니라 양피지(`#FAF7F0`) 위 `#1E1B18`.
