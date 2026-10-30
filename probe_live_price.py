#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
실조회 진단 도구 (가격을 저장하지 않고 상태만 출력합니다)

  python probe_live_price.py access   # 구글 항공권 페이지에 GitHub 서버가 접근 가능한지
  python probe_live_price.py v2       # fast-flights 2.x 로 3개 노선 시험
  python probe_live_price.py v3       # fast-flights 3.x(KRW 통화 지정 가능) 로 3개 노선 시험
"""
import datetime
import sys
import urllib.request

ROUTES = ["KIX", "FUK", "NRT"]


def trip_dates():
    dep = datetime.date.today() + datetime.timedelta(days=21)
    return dep.isoformat(), (dep + datetime.timedelta(days=3)).isoformat()


def probe_access():
    url = "https://www.google.com/travel/flights?hl=ko&curr=KRW"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "ignore")
            low = body.lower()
            print(f"HTTP {r.status}, 최종 주소: {r.geturl()[:120]}, 길이 {len(body)}")
            print("동의 화면 흔적:", "consent" in low, "| 비정상 트래픽/캡차 흔적:", ("unusual traffic" in low or "captcha" in low))
    except Exception as e:
        print(f"접근 실패: {type(e).__name__}: {str(e)[:200]}")


def probe_v2():
    try:
        import fast_flights
        from fast_flights import FlightData, Passengers, get_flights
        print("fast_flights 불러오기 성공, 버전:", getattr(fast_flights, "__version__", "알 수 없음"))
    except Exception as e:
        print("fast_flights(v2) 불러오기 실패:", type(e).__name__, str(e)[:200]); return
    dep, ret = trip_dates()
    for code in ROUTES:
        try:
            res = get_flights(
                flight_data=[FlightData(date=dep, from_airport="ICN", to_airport=code), FlightData(date=ret, from_airport=code, to_airport="ICN")],
                trip="round-trip", seat="economy", passengers=Passengers(adults=1), fetch_mode="common")
            fl = list(getattr(res, "flights", []) or [])
            print(f"[v2 {code}] 항공편 {len(fl)}건")
            for f in fl[:3]:
                print("   ", getattr(f, "name", "?"), "| 가격:", getattr(f, "price", "?"), "| 경유:", getattr(f, "stops", "?"))
        except Exception as e:
            print(f"[v2 {code}] 실패: {type(e).__name__}: {str(e)[:200]}")


def probe_v3():
    try:
        import fast_flights
        from fast_flights import FlightQuery, Passengers, create_query, get_flights
        print("fast_flights 불러오기 성공, 버전:", getattr(fast_flights, "__version__", "알 수 없음"))
    except Exception as e:
        print("fast_flights(v3) 불러오기 실패:", type(e).__name__, str(e)[:200]); return
    dep, ret = trip_dates()
    for code in ROUTES:
        for a, b, d in (("ICN", code, dep), (code, "ICN", ret)):
            try:
                q = create_query(flights=[FlightQuery(date=d, from_airport=a, to_airport=b)], trip="one-way", seat="economy",
                                 passengers=Passengers(adults=1), language="en-US", currency="KRW")
                res = get_flights(q)
                print(f"[v3 {a}->{b}] 결과 {len(res)}건")
                for f in list(res)[:3]:
                    print("   ", getattr(f, "airlines", "?"), "| 가격:", getattr(f, "price", "?"), "| 원문:", repr(f)[:140])
            except Exception as e:
                print(f"[v3 {a}->{b}] 실패: {type(e).__name__}: {str(e)[:200]}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "access"
    {"access": probe_access, "v2": probe_v2, "v3": probe_v3}[mode]()
