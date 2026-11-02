#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P0 사전 검증(수동 실행 전용). 가격은 저장하지 않는다.

  python probe_calendar.py fli      # fli 날짜 검색: 왕복(직항, KRW) 10일치 소요 시간·결과 수
  python probe_calendar.py browser  # 실제 브라우저로 구글 항공권 달력을 열어 달력 가격 응답을 캡처
"""
import datetime
import json
import os
import re
import sys
import time

OUT = "probe_out"
os.makedirs(OUT, exist_ok=True)


def dates(offset_days, nights):
    dep = datetime.date.today() + datetime.timedelta(days=offset_days)
    return dep.isoformat(), (dep + datetime.timedelta(days=nights)).isoformat()


def probe_fli():
    from fli.models import Airport, DateSearchFilters, FlightSegment, PassengerInfo, TripType, MaxStops
    from fli.search import SearchDates
    for code, nights in (("KIX", 3), ("DAD", 4)):
        dep, ret = dates(21, nights)
        f = DateSearchFilters(
            trip_type=TripType.ROUND_TRIP,
            passenger_info=PassengerInfo(adults=1),
            flight_segments=[
                FlightSegment(departure_airport=[[Airport.ICN, 0]], arrival_airport=[[getattr(Airport, code), 0]], travel_date=dep),
                FlightSegment(departure_airport=[[getattr(Airport, code), 0]], arrival_airport=[[Airport.ICN, 0]], travel_date=ret),
            ],
            stops=MaxStops.NON_STOP,
            from_date=dep,
            to_date=(datetime.date.fromisoformat(dep) + datetime.timedelta(days=9)).isoformat(),
            duration=nights,
        )
        t = time.time()
        try:
            res = SearchDates().search(f, currency="KRW", language="en")
            el = time.time() - t
            print(f"[fli {code} {nights}박] 10일치 {el:.1f}초, 결과 {len(res or [])}건")
            for r in (res or [])[:10]:
                print("    ", r.date, r.price)
        except Exception as e:
            print(f"[fli {code}] 실패 {time.time()-t:.1f}초: {type(e).__name__}: {str(e)[:300]}")


def probe_browser():
    from fast_flights import FlightData, Passengers, create_filter
    from playwright.sync_api import sync_playwright
    dep, ret = dates(21, 3)
    flt = create_filter(
        flight_data=[FlightData(date=dep, from_airport="ICN", to_airport="KIX"),
                     FlightData(date=ret, from_airport="KIX", to_airport="ICN")],
        trip="round-trip", seat="economy", passengers=Passengers(adults=1), max_stops=0)
    url = f"https://www.google.com/travel/flights?tfs={flt.as_b64().decode()}&hl=en&curr=KRW"
    print("URL:", url[:160])
    captured = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(locale="en-US", timezone_id="Asia/Seoul", viewport={"width": 1366, "height": 900})
        page = ctx.new_page()

        def on_resp(resp):
            u = resp.url
            if re.search(r"GetCalendar|GetShoppingResults|GetBooking", u):
                try:
                    body = resp.text()
                except Exception as e:
                    body = f"<읽기 실패 {e}>"
                captured.append((u.split("?")[0].rsplit("/", 1)[-1], resp.status, body))
        page.on("response", on_resp)
        t = time.time()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)
        print(f"페이지 로딩 {time.time()-t:.1f}초, 제목: {page.title()[:80]}")
        page.screenshot(path=f"{OUT}/1_loaded.png")
        steps = [
            ("출발일 입력 클릭", lambda: page.locator('input[aria-label*="Departure"]').first.click(timeout=8000)),
            ("Date grid 버튼", lambda: page.get_by_role("button", name=re.compile("Date grid", re.I)).first.click(timeout=8000)),
            ("Price graph 버튼", lambda: page.get_by_role("button", name=re.compile("Price graph", re.I)).first.click(timeout=8000)),
        ]
        for name, act in steps:
            before = len(captured)
            try:
                act()
                page.wait_for_timeout(6000)
                print(f"[{name}] 성공, 새 응답 {len(captured)-before}건")
            except Exception as e:
                print(f"[{name}] 실패: {type(e).__name__}: {str(e)[:150]}")
            page.screenshot(path=f"{OUT}/2_{name.split()[0]}.png")
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(1500)
            except Exception:
                pass
        b.close()
    print(f"캡처한 응답 {len(captured)}건")
    for i, (name, st, body) in enumerate(captured):
        print(f"  #{i} {name} HTTP {st} 길이 {len(body)}")
        print("     앞부분:", body[:600].replace("\n", " "))
        with open(f"{OUT}/resp_{i}_{name}.txt", "w", encoding="utf-8") as fh:
            fh.write(body)


if __name__ == "__main__":
    {"fli": probe_fli, "browser": probe_browser}[sys.argv[1]]()
