#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
배포 때 만드는 부가 파일(P5). 결과는 저장소에 커밋하지 않는다(pages.yml이 배포 묶음에 넣음, .gitignore).

  feed/<도시>.xml      도시별 RSS(P5-3). 글 하나 = 그 도시가 실린 날 1건(1위 실조회 가격·일정). 최근 30건.
  data/archive.json    지난 호 보관함(P5-4). 날짜별 발행 도시 수·최저가·하위 5곳(1위 가격 기준).
  data/leadtime.json   예약 시점 통계(P5-6). 지역별로 매일 1위 일정의 '출발까지 남은 날'(출발일 − 조회일) 분포.
                       예측이 아니라 지난 실조회 기록 요약. 실조회 90일 미만이면 ready=false(화면에서 숨김).

자료는 영구 이력 data/history/*.csv(1위만, 절대 규칙 4). source=live만 실조회로 보고,
이전 수집기 기록(source=sheet, 2026-10)은 보관함에만 '참고용'으로 싣고 RSS에는 넣지 않는다.
"""
import csv, datetime, glob, json, os
from email.utils import format_datetime
from xml.sax.saxutils import escape

import routes

SITE_URL = "https://lee2000y-max.github.io/daily-flight-news/"
KST = datetime.timezone(datetime.timedelta(hours=9))
FEED_DIR = "feed"
ARCHIVE_PATH = "data/archive.json"
LEADTIME_PATH = "data/leadtime.json"
LEAD_MIN_DAYS = 90      # 실조회 90일 이상부터 공개(P5 기획안 6장)
LEAD_BUCKETS = [(14, 20), (21, 27), (28, 34), (35, 41), (42, 48), (49, 55), (56, 60)]
FEED_ITEMS = 30
WEEK = "월화수목금토일"


def load_history():
    rows = []
    for path in sorted(glob.glob("data/history/*.csv")):
        with open(path, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                try:
                    r["price"] = int(float(r["price"]))
                except (TypeError, ValueError):
                    continue
                if r["price"] > 0 and r.get("date") and r.get("code"):
                    rows.append(r)
    return rows


def md(iso):
    try:
        y, m, d = map(int, iso.split("-"))
        return f"{m:02d}.{d:02d}({WEEK[datetime.date(y, m, d).weekday()]})"
    except Exception:
        return ""


def nights(dep, ret):
    try:
        return (datetime.date.fromisoformat(ret) - datetime.date.fromisoformat(dep)).days
    except Exception:
        return None


def pub_time(date, status):
    gen = (status.get(date) or {}).get("generatedAt") or f"{date} 07:30"
    try:
        return datetime.datetime.strptime(gen, "%Y-%m-%d %H:%M").replace(tzinfo=KST)
    except ValueError:
        return datetime.datetime.fromisoformat(date).replace(hour=7, minute=30, tzinfo=KST)


def build_feeds(hist, names, status):
    os.makedirs(FEED_DIR, exist_ok=True)
    by_code = {}
    for r in hist:
        if r.get("source") == "live":
            by_code.setdefault(r["code"], []).append(r)
    made = 0
    for c in routes.CITY_MASTER:
        code, city = c["code"], c["city"]
        rs = sorted(by_code.get(code, []), key=lambda r: r["date"], reverse=True)[:FEED_ITEMS]
        items = []
        for r in rs:
            n = nights(r.get("dep", ""), r.get("ret", ""))
            y, m, d = r["date"].split("-")
            title = f"{city} 왕복 {r['price']:,}원 · {md(r.get('dep', ''))}~{md(r.get('ret', ''))}" + (f" {n}박" if n else "") + f" ({int(m)}/{int(d)} 조회)"
            desc = (f"{int(y)}년 {int(m)}월 {int(d)}일 아침 실제 조회한 {city} 직항 왕복 최저가입니다."
                    + (f" 항공사 코드 {r['airline']}." if r.get("airline") else "")
                    + " 예약 시점에 가격이 바뀔 수 있습니다.")
            items.append(
                "    <item>\n"
                f"      <title>{escape(title)}</title>\n"
                f"      <link>{SITE_URL}city.html?code={code}</link>\n"
                f"      <guid isPermaLink=\"false\">boarding-pass-times-{code}-{r['date']}</guid>\n"
                f"      <pubDate>{format_datetime(pub_time(r['date'], status))}</pubDate>\n"
                f"      <description>{escape(desc)}</description>\n"
                "    </item>")
        xml = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<rss version=\"2.0\">\n  <channel>\n"
               f"    <title>{escape(city)} — 보딩패스 타임즈 직항 최저가</title>\n"
               f"    <link>{SITE_URL}city.html?code={code}</link>\n"
               f"    <description>{escape(city)}행 인천·김포 출발 직항 왕복 최저가. 매일 아침 실제 조회값, 실린 날만 새 글.</description>\n"
               "    <language>ko</language>\n" + "\n".join(items) + ("\n" if items else "") + "  </channel>\n</rss>\n")
        with open(f"{FEED_DIR}/{code}.xml", "w", encoding="utf-8") as fh:
            fh.write(xml)
        made += 1
    return made


def build_archive(hist, names, status):
    by_date = {}
    for r in hist:
        by_date.setdefault(r["date"], []).append(r)
    issues = []
    for date in sorted(by_date, reverse=True):
        rs = sorted(by_date[date], key=lambda r: (r["price"], r["code"]))
        live = all(r.get("source") == "live" for r in rs)
        st = status.get(date) or {}
        issues.append({
            "date": date,
            "published": len(rs),
            "total": st.get("total"),
            "source": "live" if live else "reference",   # reference = 이전 수집기 기록(참고용)
            "top": [{"code": r["code"], "city": names.get(r["code"], r["code"]), "price": r["price"],
                     "dep": r.get("dep", ""), "ret": r.get("ret", "")} for r in rs[:5]],
        })
    out = {"generatedAt": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "issues": issues}
    with open(ARCHIVE_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    return len(issues)


def build_leadtime(hist):
    import statistics
    major = {c["code"]: c["major"] for c in routes.CITY_MASTER}
    live = [r for r in hist if r.get("source") == "live" and r.get("dep")]
    days = sorted({r["date"] for r in live})
    regions = {}
    for r in live:
        try:
            lead = (datetime.date.fromisoformat(r["dep"]) - datetime.date.fromisoformat(r["date"])).days
        except ValueError:
            continue
        reg = major.get(r["code"], "기타")
        for lo, hi in LEAD_BUCKETS:
            if lo <= lead <= hi:
                regions.setdefault(reg, {}).setdefault(f"{lo}-{hi}", []).append(r["price"])
                break
    out_regions = {}
    for reg, bk in regions.items():
        total = sum(len(v) for v in bk.values())
        out_regions[reg] = {"n": total, "buckets": [
            {"range": f"{lo}-{hi}", "count": len(bk.get(f"{lo}-{hi}", [])),
             "share": round(len(bk.get(f"{lo}-{hi}", [])) / total, 3) if total else 0,
             "median": int(statistics.median(bk[f"{lo}-{hi}"])) if bk.get(f"{lo}-{hi}") else None}
            for lo, hi in LEAD_BUCKETS]}
    out = {"liveDays": len(days), "firstDay": days[0] if days else "", "lastDay": days[-1] if days else "",
           "minDays": LEAD_MIN_DAYS, "ready": len(days) >= LEAD_MIN_DAYS, "regions": out_regions}
    with open(LEADTIME_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    return out


def main():
    hist = load_history()
    names = {c["code"]: c["city"] for c in routes.CITY_MASTER}
    status = {}
    try:
        status = json.load(open("flights_data.json", encoding="utf-8")).get("status", {}) or {}
    except Exception:
        pass
    n_feeds = build_feeds(hist, names, status)
    n_issues = build_archive(hist, names, status)
    lt = build_leadtime(hist)
    print(f"도시별 RSS {n_feeds}개({FEED_DIR}/), 보관함 {n_issues}개 호({ARCHIVE_PATH}), "
          f"예약 시점 통계 실조회 {lt['liveDays']}일({'공개' if lt['ready'] else str(LEAD_MIN_DAYS) + '일 전 숨김'}) · 이력 {len(hist)}행")


if __name__ == "__main__":
    main()
