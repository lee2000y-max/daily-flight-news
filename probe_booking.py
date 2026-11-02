#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P3 실험: 구글 플라이트 '예약 옵션(판매처별 가격)'을 실제 브라우저로 읽을 수 있는지 확인한다(수동 실행 전용).

  python probe_booking.py ICN-YNT 2026-12-10 2026-12-16 [ICN-KIX 2026-12-09 2026-12-15 ...]

- 화면이 보여 주는 대로만 클릭한다: 가는 편 목록 첫 줄(최저가) → 오는 편 목록 첫 줄 → 예약 옵션.
- CAPTCHA·차단 화면이 나오면 그 노선은 즉시 중단하고 그렇게 기록한다(우회하지 않음, CLAUDE.md 절대 규칙 6).
- 결과: 로그에 판매처·가격 줄, screenshots/booking_*.png
"""
import os
import re
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.makedirs("screenshots", exist_ok=True)
PRICE_RE = re.compile(r"(₩|KRW)\s?[\d,]{4,}")


def google_url(org, dst, dep, ret):
    from fast_flights import FlightData, Passengers, create_filter
    flt = create_filter(flight_data=[FlightData(date=dep, from_airport=org, to_airport=dst),
                                     FlightData(date=ret, from_airport=dst, to_airport=org)],
                        trip="round-trip", seat="economy", passengers=Passengers(adults=1), max_stops=0)
    return f"https://www.google.com/travel/flights?tfs={flt.as_b64().decode()}&hl=en&curr=KRW&gl=KR"


def blocked(page) -> bool:
    t = page.inner_text("body")[:3000].lower()
    return "unusual traffic" in t or "captcha" in t or "/sorry/" in page.url


def click_first_result(page, label: str) -> bool:
    """결과 목록에서 가격이 보이는 첫 항목을 누른다."""
    page.wait_for_timeout(2500)
    items = page.locator("li").filter(has_text=PRICE_RE)
    n = items.count()
    print(f"   {label}: 가격이 보이는 목록 {n}개")
    if n == 0:
        return False
    first = items.first
    print("   첫 항목:", " | ".join(first.inner_text().split("\n")[:8]))
    first.click()
    return True


def probe(page, org, dst, dep, ret, tag):
    url = google_url(org, dst, dep, ret)
    print(f"\n== {org}→{dst} {dep}~{ret}\n   {url}")
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    if blocked(page):
        print("   ⛔ 차단/확인 화면 → 이 노선 중단")
        page.screenshot(path=f"screenshots/booking_{tag}_blocked.png")
        return
    if not click_first_result(page, "가는 편"):
        page.screenshot(path=f"screenshots/booking_{tag}_0.png", full_page=True)
        return
    if not click_first_result(page, "오는 편"):
        page.screenshot(path=f"screenshots/booking_{tag}_1.png", full_page=True)
        return
    page.wait_for_timeout(5000)
    if blocked(page):
        print("   ⛔ 차단/확인 화면 → 중단")
        return
    body = page.inner_text("body")
    i = body.find("Booking options")
    seg = body[i:i + 2500] if i >= 0 else body[:2500]
    print("   예약 옵션 영역:", "있음" if i >= 0 else "못 찾음")
    rows = [ln.strip() for ln in seg.split("\n") if ln.strip()]
    sellers = []
    for k, ln in enumerate(rows):
        if ln.lower().startswith("book with"):
            price = next((x for x in rows[k:k + 6] if PRICE_RE.search(x)), "")
            sellers.append((ln, price))
    print(f"   판매처 {len(sellers)}곳")
    for s_, p_ in sellers:
        print(f"     · {s_} — {p_}")
    if not sellers:
        print("   (원문 일부)", " / ".join(rows[:40]))
    page.screenshot(path=f"screenshots/booking_{tag}.png", full_page=True)


def main():
    args = sys.argv[1:]
    trips = [(args[i], args[i + 1], args[i + 2]) for i in range(0, len(args) - 2, 3)]
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(locale="en-US", viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        for n, (route, dep, ret) in enumerate(trips):
            org, dst = route.split("-")
            try:
                probe(page, org, dst, dep, ret, f"{n}_{org}{dst}")
            except Exception as e:
                print(f"   오류 {type(e).__name__}: {str(e)[:200]}")
                try:
                    page.screenshot(path=f"screenshots/booking_{n}_error.png", full_page=True)
                except Exception:
                    pass
        b.close()


if __name__ == "__main__":
    main()
