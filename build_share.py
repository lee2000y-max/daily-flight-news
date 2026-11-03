#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
카드별 링크 공유 페이지(P4). 매일 수집의 publish 단계에서 flights_data.json 저장 뒤에 실행한다.

  s/<도시>/index.html : 링크 미리보기용 정보(og:title·og:description·og:image)만 담고, 사람이 열면 본 사이트 ./#<도시>로 이동
  s/<도시>/thumb.jpg  : 1200×630 썸네일(도시 사진 + 제호 + 도시명 + 왕복 가격 + 일정 + 조회 시각)
  s/og.jpg            : 사이트 전체 주소의 기본 미리보기(오늘 최저가 도시 썸네일)

- 카카오톡 등은 링크 미리보기를 만들 때 자바스크립트를 실행하지 않으므로 도시마다 정적 페이지가 필요하다.
- 가격·일정은 그날 실제 조회값만(절대 규칙 1). 오늘 발행되지 않은 도시는 "오늘은 발행되지 않았습니다"와
  가격 없는 썸네일(사진·제호·도시명)만 둔다(이월 금지).
- 썸네일은 날짜별로 쌓지 않고 매일 덮어쓴다. 메신저 캐시는 링크의 ?d=YYYYMMDD와 썸네일 주소의 ?v=로 피한다.
- 사진은 images/cities/<도시>.jpg(위키미디어 공용, data/photos.json에 출처). 없으면 사진 없이 지면 색 배경.
- 한글 글꼴: Noto Serif/Sans CJK(서버에 fonts-noto-cjk 설치). 없으면 다른 CJK 글꼴, 그것도 없으면 썸네일 생략.
"""
import html, json, os, shutil, sys
from datetime import date

import routes

SITE_URL = "https://lee2000y-max.github.io/daily-flight-news/"
OUT_DIR = "s"
W, H = 1200, 630
WEEK = "월화수목금토일"

FONT_CANDIDATES = {
    "serif": [("/usr/share/fonts/opentype/noto/NotoSerifCJK-Black.ttc", 1), ("/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc", 1)],
    "sans": [("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 1)],
    "sans_r": [("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 1), ("/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc", 1)],
}
FALLBACK_FONTS = [("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0), ("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf", 0)]


def font_path(kind):
    for p, i in FONT_CANDIDATES[kind] + FALLBACK_FONTS:
        if os.path.exists(p):
            return p, i
    return None


def md(iso):
    y, m, d = map(int, iso.split("-"))
    return f"{m:02d}.{d:02d}"


def md_week(iso):
    y, m, d = map(int, iso.split("-"))
    return f"{m:02d}.{d:02d}({WEEK[date(y, m, d).weekday()]})"


def origin_label(code):
    return "김포" if code == "GMP" else "인천"


def won(n):
    return f"{int(n):,}원"


def share_texts(f, edition):
    """링크 미리보기 제목·설명(index.html의 shareInfo와 같은 문장)."""
    _, em, ed = edition.split("-")
    title = f"{f['city']} 왕복 {won(f['price'])} · {origin_label(f['origin'])} 출발 직항"
    airline = (f.get("airline") or "").strip()
    desc = (f"{md_week(f['depDate'])}–{md_week(f['retDate'])} {f['nights']}박"
            + (f" · {airline}" if airline else "")
            + f" · {int(em)}월 {int(ed)}일 아침 실제 조회가. 예약 시점에 가격이 바뀔 수 있어요.")
    return title, desc


def page_html(code, city, title, desc, version, published):
    e = html.escape
    url = f"{SITE_URL}{OUT_DIR}/{code}/"
    img = f"{url}thumb.jpg?v={version}"
    target = f"../../#{code}"
    body = (f"<p><strong>{e(title)}</strong></p><p>{e(desc)}</p>" if published
            else f"<p><strong>{e(city)}</strong> · 오늘은 발행되지 않았습니다.</p>")
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)} · THE BOARDING PASS TIMES</title>
<meta name="description" content="{e(desc)}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="THE BOARDING PASS TIMES">
<meta property="og:locale" content="ko_KR">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(url)}">
<meta property="og:image" content="{e(img)}">
<meta property="og:image:width" content="{W}">
<meta property="og:image:height" content="{H}">
<meta property="og:image:alt" content="{e(city)} · THE BOARDING PASS TIMES">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(desc)}">
<meta name="twitter:image" content="{e(img)}">
<script>location.replace({json.dumps(target)});</script>
<style>body{{margin:0;padding:24px 16px;background:#EFECE4;color:#1E1B18;font-family:'Noto Sans KR',sans-serif;line-height:1.6}}a{{color:#1E3A5F;font-weight:700}}</style>
</head>
<body>
<p style="font-family:serif;font-weight:900;letter-spacing:.08em">THE BOARDING PASS TIMES</p>
{body}
<p><a href="{target}">보딩패스 타임즈에서 보기 →</a></p>
</body>
</html>
"""


class Thumb:
    def __init__(self):
        from PIL import Image, ImageDraw, ImageFont, ImageOps  # noqa: F401
        self.Image, self.ImageDraw, self.ImageFont, self.ImageOps = Image, ImageDraw, ImageFont, ImageOps
        self.paths = {k: font_path(k) for k in FONT_CANDIDATES}
        self.ok = all(self.paths.values())
        self._cache = {}

    def font(self, kind, size):
        key = (kind, size)
        if key not in self._cache:
            p, i = self.paths[kind]
            self._cache[key] = self.ImageFont.truetype(p, size, index=i)
        return self._cache[key]

    def fit(self, draw, text, kind, size, max_w, min_size=24):
        while size > min_size and draw.textlength(text, font=self.font(kind, size)) > max_w:
            size -= 2
        return self.font(kind, size)

    def render(self, code, city, out_path, price=None, sched=None, checked=None):
        Image, ImageDraw = self.Image, self.ImageDraw
        photo = f"images/cities/{code}.jpg"
        if os.path.exists(photo):
            base = self.ImageOps.fit(Image.open(photo).convert("RGB"), (W, H), Image.LANCZOS, centering=(0.5, 0.45))
        else:
            base = Image.new("RGB", (W, H), "#EFECE4")
        img = base.convert("RGBA")
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        d.rectangle([0, 0, W, 64], fill=(20, 18, 16, 215))                 # 위: 제호 띠
        band_top = 410 if price else 470
        d.rectangle([0, band_top, W, H], fill=(20, 18, 16, 222))          # 아래: 기사 띠
        d.rectangle([0, band_top, W, band_top + 4], fill=(184, 51, 42, 255))
        img = Image.alpha_composite(img, ov)
        d = ImageDraw.Draw(img)
        paper, sub, amber = (250, 247, 240, 255), (222, 214, 200, 255), (251, 191, 36, 255)
        d.text((40, 32), "THE BOARDING PASS TIMES", font=self.font("serif", 30), fill=paper, anchor="lm")
        if checked:
            d.text((W - 40, 32), checked, font=self.font("sans_r", 24), fill=sub, anchor="rm")
        if price:
            pf = self.fit(d, price, "serif", 84, 560)
            pw = d.textlength(price, font=pf)
            cf = self.fit(d, city, "serif", 76, W - 80 - pw - 40)
            d.text((40, band_top + 92), city, font=cf, fill=paper, anchor="ls")
            d.text((W - 40, band_top + 96), price, font=pf, fill=amber, anchor="rs")
            d.text((40, band_top + 160), sched, font=self.fit(d, sched, "sans", 34, W - 80), fill=sub, anchor="ls")
            d.text((40, band_top + 204), "왕복 · 발행일 아침 실제 조회 가격 · 예약 시점에 바뀔 수 있음",
                   font=self.font("sans_r", 22), fill=(170, 160, 146, 255), anchor="ls")
        else:
            d.text((40, band_top + 84), city, font=self.fit(d, city, "serif", 76, W - 80), fill=paper, anchor="ls")
            d.text((40, band_top + 132), "오늘은 발행되지 않았습니다", font=self.font("sans", 30), fill=sub, anchor="ls")
        img.convert("RGB").save(out_path, "JPEG", quality=76, optimize=True, progressive=True)


def main():
    data = json.load(open("flights_data.json", encoding="utf-8"))
    edition = data["latestDate"]
    version = edition.replace("-", "")
    gen = (data.get("status", {}).get(edition) or {}).get("generatedAt") or data.get("updatedAt") or ""
    _, em, ed = edition.split("-")
    checked = f"{int(em)}.{int(ed)} {gen[11:16]} 조회" if len(gen) >= 16 else f"{int(em)}.{int(ed)} 조회"
    today = {f["code"]: f for f in data["flights"] if f.get("date") == edition}

    try:
        thumb = Thumb()
        if not thumb.ok:
            print("⚠️ 한글 글꼴 없음: 썸네일 생략(공유 페이지만 만듦)")
            thumb = None
    except ImportError:
        print("⚠️ Pillow 없음: 썸네일 생략(공유 페이지만 만듦)")
        thumb = None

    made = 0
    for c in routes.CITY_MASTER:
        code, city = c["code"], c["city"]
        f = today.get(code)
        os.makedirs(f"{OUT_DIR}/{code}", exist_ok=True)
        if f:
            title, desc = share_texts(f, edition)
            sched = f"{md(f['depDate'])}-{md(f['retDate'])} · {f['nights']}박 · {origin_label(f['origin'])} 출발 직항"
        else:
            title = f"{city} · 오늘은 발행되지 않았습니다"
            desc = "보딩패스 타임즈는 그날 실제로 조회된 직항 가격만 싣습니다. 오늘 이 노선은 조회되지 않았거나 조건에 맞는 직항이 없었습니다."
            sched = None
        with open(f"{OUT_DIR}/{code}/index.html", "w", encoding="utf-8") as fh:
            fh.write(page_html(code, city, title, desc, version, bool(f)))
        if thumb:
            thumb.render(code, city, f"{OUT_DIR}/{code}/thumb.jpg",
                         price=won(f["price"]) if f else None, sched=sched, checked=checked if f else None)
        made += 1

    if thumb and today:
        low = min(today.values(), key=lambda x: (x["price"], x["code"]))
        shutil.copyfile(f"{OUT_DIR}/{low['code']}/thumb.jpg", f"{OUT_DIR}/og.jpg")
    print(f"공유 페이지 {made}개(발행 {len(today)}개) · 썸네일 {'만듦' if thumb else '생략'} · 기준 {edition} {checked}")


if __name__ == "__main__":
    sys.exit(main())
