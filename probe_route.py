#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""노선 진단(수동 실행 전용).
사용: python probe_route.py OKA
      python probe_route.py OIT 2026-12-30 2027-01-05
      python probe_route.py GMP-HND 2026-12-04 2026-12-07
"""
import datetime, sys

arg = sys.argv[1] if len(sys.argv) > 1 else "OKA"
org, code = arg.split("-") if "-" in arg else ("ICN", arg)
if len(sys.argv) >= 4:
    dep = datetime.date.fromisoformat(sys.argv[2])
    ret = datetime.date.fromisoformat(sys.argv[3])
else:
    dep = datetime.date.today() + datetime.timedelta(days=21)
    ret = dep + datetime.timedelta(days=3)
print(f"== 노선 {org}→{code} {dep}~{ret}")

from fli.models import (Airport, DateSearchFilters, FlightSearchFilters, FlightSegment, MaxStops,
                        PassengerInfo, SortBy, TripType)
from fli.search import SearchDates, SearchFlights

A, B = getattr(Airport, org), getattr(Airport, code)
print("== fli 공항 코드:", A.name, A.value, "/", B.name, B.value)


def leg_desc(f):
    return [(l.airline.name, l.flight_number, str(l.departure_datetime)[:16]) for l in f.legs]


print("== 날짜 검색(왕복, 직항) — 해당 박수")
try:
    n = (ret - dep).days
    df = DateSearchFilters(
        trip_type=TripType.ROUND_TRIP, passenger_info=PassengerInfo(adults=1),
        flight_segments=[
            FlightSegment(departure_airport=[[A, 0]], arrival_airport=[[B, 0]], travel_date=dep.isoformat()),
            FlightSegment(departure_airport=[[B, 0]], arrival_airport=[[A, 0]], travel_date=ret.isoformat()),
        ],
        stops=MaxStops.NON_STOP,
        from_date=dep.isoformat(), to_date=dep.isoformat(), duration=n)
    rows = SearchDates().search(df, currency="KRW", language="en") or []
    print("   ", [(str(r.date), r.price) for r in rows[:3]])
except Exception as e:
    print(f"    오류 {type(e).__name__}: {str(e)[:200]}")

print("== 상세 검색 편도(가는 편·오는 편, 직항/경유 허용)")
for (x, y, d) in ((A, B, dep), (B, A, ret)):
    for stops in (MaxStops.NON_STOP, MaxStops.ANY):
        f = FlightSearchFilters(trip_type=TripType.ONE_WAY, passenger_info=PassengerInfo(adults=1),
            flight_segments=[FlightSegment(departure_airport=[[x, 0]], arrival_airport=[[y, 0]], travel_date=d.isoformat())],
            stops=stops, sort_by=SortBy.CHEAPEST)
        try:
            r = SearchFlights().search(f, currency="KRW", language="en") or []
            print(f"    {x.name}→{y.name} {d} {stops.name}: {len(r)}건", [(leg_desc(z), z.stops, z.price) for z in r[:3]])
        except Exception as e:
            print(f"    {x.name}→{y.name} {d} {stops.name}: 오류 {type(e).__name__}: {str(e)[:200]}")

print("== 상세 검색 왕복(수집기와 같은 조건)")
for stops in (MaxStops.NON_STOP, MaxStops.ANY):
    f = FlightSearchFilters(
        trip_type=TripType.ROUND_TRIP, passenger_info=PassengerInfo(adults=1),
        flight_segments=[
            FlightSegment(departure_airport=[[A, 0]], arrival_airport=[[B, 0]], travel_date=dep.isoformat()),
            FlightSegment(departure_airport=[[B, 0]], arrival_airport=[[A, 0]], travel_date=ret.isoformat()),
        ],
        stops=stops, sort_by=SortBy.CHEAPEST)
    try:
        r = SearchFlights().search(f, top_n=3, currency="KRW", language="en") or []
        out = []
        for it in r[:3]:
            if isinstance(it, tuple):
                out.append((leg_desc(it[0]), it[0].stops, leg_desc(it[1]), it[1].stops, it[0].price, it[1].price))
            else:
                out.append(("편도형", leg_desc(it), it.price))
        print(f"    {stops.name}: {len(r)}건", out)
    except Exception as e:
        print(f"    {stops.name}: 오류 {type(e).__name__}: {str(e)[:200]}")

print("== fast-flights 2.2 (왕복, 직항, 원화)")
try:
    from fast_flights import FlightData, Passengers, create_filter, get_flights_from_filter
    flt = create_filter(flight_data=[FlightData(date=dep.isoformat(), from_airport=org, to_airport=code),
                                     FlightData(date=ret.isoformat(), from_airport=code, to_airport=org)],
                        trip="round-trip", seat="economy", passengers=Passengers(adults=1), max_stops=0)
    print("    링크:", f"https://www.google.com/travel/flights?tfs={flt.as_b64().decode()}&hl=en&curr=KRW")
    res = get_flights_from_filter(flt, currency="KRW", mode="common")
    fl = list(res.flights or [])
    print(f"    {len(fl)}건", [(x.name, x.stops, x.price, x.departure) for x in fl[:4]])
except Exception as e:
    print(f"    오류 {type(e).__name__}: {str(e)[:300]}")
