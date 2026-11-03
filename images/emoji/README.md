# 이모지 SVG

- 출처: Google [Noto Emoji](https://github.com/googlefonts/noto-emoji) (Apache License 2.0)
  - 받은 경로: npm `@iconify-json/noto` 1.2.10(Noto Emoji를 Iconify 형식으로 담은 패키지, Apache-2.0)의 아이콘 본문을 SVG로 그대로 옮김
  - 파일 이름은 유니코드 코드포인트(이형 선택자 FE0F 제외). 예: `1f4c5.svg` = 📅
- 화면의 이모지를 문자 대신 이 그림으로 그린다(Windows 등에서 이모지가 글자로 깨지는 문제 방지).
- 사이트에서 쓰는 것만 담았다. 새 이모지가 필요하면 같은 패키지의 `chars.json`(코드포인트 → 이름)으로 찾아 추가한다.
