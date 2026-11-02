#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""노선 진단(수동 실행 전용). 사용: python probe_route.py OKA"""
import datetime, sys, time
code = sys.argv[1] if len(sys.argv) > 1 else "OKA"
dep = datetime.date.today() + datetime.timedelta(days=21)
ret = dep + datetime.timedelta(days=3)

print("== fli 공항 코드 확인")
from fli.models import Airport
a = getattr(Airport, code)
print("   ", a, getattr(a, "value", ""))

print("== fli 상세 검색(직항/경유 허용)")
from fli.models import FlightSearchFilters, FlightSegment, MaxStops, PassengerInfo, SortBy, TripType
from fli.search import SearchFlights
for stops in (MaxStops.NON_STOP, MaxStops.ANY):
    f = FlightSearchFilters(trip_type=TripType.ONE_WAY, passenger_info=PassengerInfo(adults=1),
        flight_segments=[FlightSegment(departure_airport=[[Airport.ICN, 0]], arrival_airport=[[a, 0]], travel_date=dep.isoformat())],
        stops=stops, sort_by=SortBy.CHEAPEST)
    try:
        r = SearchFlights().search(f, currency="KRW", language="en") or []
        print(f"    {stops.name}: {len(r)}건", [(x.legs[0].airline.name, x.legs[0].flight_number, x.stops, x.price) for x in r[:3]])
    except Exception as e:
        print(f"    {stops.name}: 오류 {type(e).__name__}: {str(e)[:200]}")

print("== fast-flights 2.2 (직항, 원화)")
try:
    from fast_flights import FlightData, Passengers, create_filter, get_flights_from_filter
    flt = create_filter(flight_data=[FlightData(date=dep.isoformat(), from_airport="ICN", to_airport=code),
                                     FlightData(date=ret.isoformat(), from_airport=code, to_airport="ICN")],
                        trip="round-trip", seat="economy", passengers=Passengers(adults=1), max_stops=0)
    res = get_flights_from_filter(flt, currency="KRW", mode="common")
    fl = list(res.flights or [])
    print(f"    {len(fl)}건", [(x.name, x.stops, x.price) for x in fl[:4]])
    print("    링크:", f"https://www.google.com/travel/flights?tfs={flt.as_b64().decode()}&hl=en&curr=KRW")
except Exception as e:
    print(f"    오류 {type(e).__name__}: {str(e)[:300]}")
