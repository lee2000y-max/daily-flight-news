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


def probe_fli2():
    """(1) 직항 필터 적용 여부 (2) 47일 x 7길이 소요 시간 (3) 날짜 검색 가격 vs 상세 검색 가격"""
    from fli.models import Airport, DateSearchFilters, FlightSegment, PassengerInfo, TripType, MaxStops
    from fli.search import SearchDates
    today = datetime.date.today()

    def run(code, nights, stops, d0=14, d1=60):
        dep = (today + datetime.timedelta(days=d0)).isoformat()
        ret = (today + datetime.timedelta(days=d0 + nights)).isoformat()
        f = DateSearchFilters(
            trip_type=TripType.ROUND_TRIP, passenger_info=PassengerInfo(adults=1),
            flight_segments=[
                FlightSegment(departure_airport=[[getattr(Airport, "ICN"), 0]], arrival_airport=[[getattr(Airport, code), 0]], travel_date=dep),
                FlightSegment(departure_airport=[[getattr(Airport, code), 0]], arrival_airport=[[getattr(Airport, "ICN"), 0]], travel_date=ret)],
            stops=stops, from_date=dep, to_date=(today + datetime.timedelta(days=d1)).isoformat(), duration=nights)
        return SearchDates().search(f, currency="KRW", language="en") or []

    # (1) 경유 허용 vs 직항만: 직항 없는 노선(ICN-LHR 등)으로 확인
    for code in ("KIX", "BKK"):
        a = {r.date[0].date(): r.price for r in run(code, 3, MaxStops.ANY, 14, 30)}
        n = {r.date[0].date(): r.price for r in run(code, 3, MaxStops.NON_STOP, 14, 30)}
        diff = sum(1 for k in a if k in n and a[k] != n[k])
        print(f"[직항필터 {code}] 경유허용 {len(a)}일, 직항만 {len(n)}일, 같은 날짜 가격이 다른 날 {diff}일, 경유허용 최저 {min(a.values()) if a else None}, 직항 최저 {min(n.values()) if n else None}")
    for code in ("LHR", "CDG"):
        try:
            n = run(code, 3, MaxStops.NON_STOP, 14, 30)
            a = run(code, 3, MaxStops.ANY, 14, 30)
            print(f"[직항없음 확인 {code}] 경유허용 {len(a)}일, 직항만 {len(n)}일 (직항만이 0에 가까우면 필터 작동)")
        except Exception as e:
            print(f"[직항없음 확인 {code}] 오류 {type(e).__name__}: {str(e)[:150]}")

    # (2) 47일 x 7길이 소요 시간
    t = time.time(); cnt = 0; best = None
    for nights in range(2, 9):
        rs = run("FUK", nights, MaxStops.NON_STOP)
        cnt += len(rs)
        for r in rs:
            if best is None or r.price < best[2]:
                best = (r.date[0].date(), r.date[1].date(), r.price)
    print(f"[전수 FUK] 7길이 x 47일 {time.time()-t:.1f}초, 가격 {cnt}건, 최저 {best}")

    # (3) 최저 일정을 상세 검색(fast-flights는 별도 venv라 여기선 fli 상세 검색)으로 재조회
    try:
        from fli.models import FlightSearchFilters, SortBy
        from fli.search import SearchFlights
        d, r, p = best
        ff = FlightSearchFilters(
            trip_type=TripType.ROUND_TRIP, passenger_info=PassengerInfo(adults=1),
            flight_segments=[
                FlightSegment(departure_airport=[[Airport.ICN, 0]], arrival_airport=[[Airport.FUK, 0]], travel_date=d.isoformat()),
                FlightSegment(departure_airport=[[Airport.FUK, 0]], arrival_airport=[[Airport.ICN, 0]], travel_date=r.isoformat())],
            stops=MaxStops.NON_STOP, sort_by=SortBy.CHEAPEST)
        t = time.time()
        res = SearchFlights().search(ff, currency="KRW", language="en") or []
        print(f"[상세 FUK {d}~{r}] {time.time()-t:.1f}초, 결과 {len(res)}건, 날짜검색 가격 {p}")
        for it in res[:3]:
            legs = it if isinstance(it, tuple) else (it,)
            desc = " / ".join(f"{l.legs[0].airline.name if l.legs else '?'} {l.legs[0].flight_number if l.legs else ''} {l.legs[0].departure_datetime if l.legs else ''} 경유{l.stops}" for l in legs)
            print(f"     가격 {legs[0].price} | {desc}")
    except Exception as e:
        print(f"[상세] 오류 {type(e).__name__}: {str(e)[:300]}")


if __name__ == "__main__":
    {"fli": probe_fli, "fli2": probe_fli2, "browser": probe_browser}[sys.argv[1]]()
