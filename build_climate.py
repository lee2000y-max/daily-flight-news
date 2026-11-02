#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
도시별 월 기후 평년값 만들기(수동 실행, 1년에 한 번이면 충분).

출처: NASA POWER 기후값(Climatology) API — 키 없음, 위치당 요청 1번.
  https://power.larc.nasa.gov/api/temporal/climatology/point
  T2M(월 평균기온, ℃), PRECTOTCORR(강수량, mm/일 → 월 합계로 환산)
  ※ 기후값 API의 T2M_MAX/T2M_MIN은 "그 달의 극값"이라(오사카 1월 19℃ 등) 쓰지 않는다(2026-11-03 확인).

결과: data/climate_normals.json
  {"source": "...", "period": "...", "cities": {"KIX": {"tmean": [12개], "precipMm": [12개(월 합계)]}}}
"""
import calendar
import json
import os
import sys
import time
import urllib.request

from routes import CITY_COORDS

URL = ("https://power.larc.nasa.gov/api/temporal/climatology/point"
       "?parameters=T2M,PRECTOTCORR&community=RE&longitude={lon}&latitude={lat}&format=JSON")
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
OUT = os.path.join("data", "climate_normals.json")


def fetch(lat: float, lon: float) -> dict:
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(URL.format(lat=lat, lon=lon), timeout=60) as r:
                return json.load(r)
        except Exception as e:  # 네트워크 일시 오류 재시도
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"조회 실패: {last}")


def main() -> int:
    cities, period, failed = {}, "", []
    for code, (lat, lon) in sorted(CITY_COORDS.items()):
        try:
            d = fetch(lat, lon)
            p = d["properties"]["parameter"]
            days = [calendar.monthrange(2001, i + 1)[1] for i in range(12)]
            cities[code] = {
                "tmean": [round(p["T2M"][m], 1) for m in MONTHS],
                "precipMm": [round(p["PRECTOTCORR"][m] * days[i]) for i, m in enumerate(MONTHS)],
            }
            hdr = d.get("header", {})
            period = period or str(hdr.get("range") or f"{hdr.get('start', '')}~{hdr.get('end', '')}")
            print(f"✓ {code} 평균기온 {cities[code]['tmean']} 강수 {cities[code]['precipMm']}")
        except Exception as e:
            failed.append(code)
            print(f"✗ {code}: {e}")
        time.sleep(0.5)
    if failed:
        print("실패:", failed)
    if not cities:
        return 1
    os.makedirs("data", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"source": "NASA POWER 기후값(T2M, PRECTOTCORR)",
                   "period": period, "cities": cities}, f, ensure_ascii=False, indent=1)
    print(f"저장: {OUT} ({len(cities)}개 도시, 기간 {period})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
