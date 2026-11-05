#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
THE BOARDING PASS TIMES 수집기 (v2, docs/PLAN.md 2장)

매일 아침 도시마다 다음을 한다.
1) 날짜 검색(fli, 구글 항공권 달력): 출발 ICN·GMP × 도착 공항 × 여행 길이 2~8박,
   출발일 D+14~D+60의 직항 왕복 가격을 받는다.
2) 주말(토·일 모두 포함)·연차(공휴일 아닌 평일 5일 이하) 조건을 통과한 일정만 남긴다.
3) 최저가(1위)와, 1위와 출발일이 3일 이상 떨어진 최저가(2위)를 고른다.
4) 1위는 상세 검색으로 다시 조회해 항공사·편명·출도착 시각을 채운다.
5) 직항이 없거나 조회에 실패한 도시는 발행하지 않고 사유를 남긴다.

가격·항공편 정보는 전부 그날 실제로 조회한 값이다. 기준가·이월·고정값은 없다.
구글 요청에 hl=ko 를 넣지 않는다(언어는 en).

환경 변수(선택)
  ONLY_CITIES=KIX,FUK   지정한 도시만 수집(검증용)
  DRY_RUN=1             파일을 저장하지 않고 결과만 출력
  FAIL_ON_LOW_LIVE=1    발행 도시가 절반 미만이면 저장 후 종료 코드 1(알림용)
"""

import datetime
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from routes import BEST_SEASONS, CITY_CURRENCY, CITY_MASTER, CURRENCY_NAME, CURRENCY_UNIT, ORIGINS, GMP_DESTINATIONS

DATA_JSON_PATH = "flights_data.json"

import gmp_auto  # noqa: E402  신규 김포 노선 자동 추가(P5-5)
# 매일 김포 출발로도 조회할 공항 = routes.GMP_DESTINATIONS + 자동 추가(data/gmp_auto.json). collect_phase에서 채움
GMP_QUERY = set(GMP_DESTINATIONS)
SCHEMA_VERSION = 2
KEEP_EDITIONS = 14            # flights_data.json 에 담을 최근 발행일 수(영구 이력은 data/history)
WINDOW_START, WINDOW_END = 14, 60
NIGHTS = range(2, 9)          # 2박3일 ~ 8박9일(도시별 최소 박수 routes의 minNights: 유럽·미주 4, 장거리 대양주 3)
MAX_NIGHTS = 8
MAX_LEAVE_DAYS = 5
ALT_MIN_GAP_DAYS = 3          # 2위는 1위와 출발일이 3일 이상 떨어져야 함
DETAIL_CANDIDATES = 6         # 1·2위를 상세 검색으로 확인할 때 시도하는 최대 후보 수
LEAVE_SAVER_MIN_NIGHTS = 3    # LEAVE SAVER·1면 B: 3박 이상
LEAVE_SAVER_MAX_LEAVE = 1     #                   연차 1일 이하
EMPTY_RETRY_SLEEP = 8          # 상세 검색 결과 0건일 때 재시도 전 대기(초, 회차마다 배수)
DATE_SEARCH_DELAY = 0.1       # 날짜 검색 사이 대기(초)
# 병렬 처리는 쓰지 않는다: fli 내부 병렬 처리와 겹쳐 전체 실행이 멈춘 적이 있음(2026-11-02)
CITY_WORKERS = 1
DETAIL_WORKERS = 1
TIME_BUDGET_SEC = 40 * 60     # 전체 시간 예산. 넘으면 남은 도시의 상세 확인을 건너뛰고 날짜 검색 실가격으로 발행
KST = datetime.timezone(datetime.timedelta(hours=9))
_START = time.monotonic()


def over_budget() -> bool:
    return time.monotonic() - _START > TIME_BUDGET_SEC

AIRLINE_KO = {
    "7C": "제주항공", "LJ": "진에어", "TW": "티웨이항공", "BX": "에어부산", "RS": "에어서울",
    "ZE": "이스타항공", "KE": "대한항공", "OZ": "아시아나항공", "YP": "에어프레미아", "RF": "에어로케이",
    "VJ": "비엣젯항공", "VN": "베트남항공", "MM": "피치항공", "NH": "전일본공수", "JL": "일본항공",
    "CI": "중화항공", "BR": "에바항공", "IT": "타이거에어 타이완", "CX": "캐세이퍼시픽", "UO": "홍콩익스프레스",
    "NX": "마카오항공", "MU": "중국동방항공", "CZ": "중국남방항공", "CA": "중국국제항공", "FM": "상하이항공",
    "SC": "산둥항공", "TG": "타이항공", "PR": "필리핀항공", "5J": "세부퍼시픽", "Z2": "필리핀 에어아시아",
    "MH": "말레이시아항공", "D7": "에어아시아X", "SQ": "싱가포르항공", "TR": "스쿠트", "GA": "가루다인도네시아",
    "OM": "몽골항공", "KC": "에어아스타나", "HY": "우즈베키스탄항공", "QV": "라오항공", "BI": "로열브루나이항공",
    "UA": "유나이티드항공", "HO": "준야오항공", "8L": "럭키항공", "GS": "톈진항공", "JD": "베이징캐피털항공",
    "9C": "춘추항공", "VZ": "타이 비엣젯", "AK": "에어아시아", "FD": "타이 에어아시아", "QZ": "인도네시아 에어아시아",
    "XJ": "타이 에어아시아X", "SL": "타이 라이언에어", "DD": "녹에어", "BL": "퍼시픽항공", "7G": "스타플라이어",
}
FSC = {"KE", "OZ", "JL", "NH", "CI", "BR", "CX", "MU", "CZ", "CA", "FM", "TG", "PR", "MH", "SQ", "GA",
       "VN", "OM", "KC", "HY", "BI", "UA", "QV", "NX", "SC"}


# ------------------------------------------------------------------------------
# 날짜·일정 규칙
# ------------------------------------------------------------------------------
def kst_today() -> datetime.date:
    return datetime.datetime.now(KST).date()


_HOLIDAYS = None


def kr_holidays():
    global _HOLIDAYS
    if _HOLIDAYS is None:
        import holidays  # type: ignore
        y = kst_today().year
        _HOLIDAYS = holidays.country_holidays("KR", years=[y, y + 1], language="ko")  # 이름을 한국어로(기본은 영어)
    return _HOLIDAYS


def city_nights(meta: Dict[str, Any]) -> range:
    """도시별 여행 길이(박). 기본 2~8박, routes의 minNights가 있으면 그 박수부터."""
    return range(int(meta.get("minNights") or NIGHTS.start), MAX_NIGHTS + 1)


def trip_end(meta: Dict[str, Any], ret: datetime.date, arr_offset: Optional[int] = None) -> datetime.date:
    """연차·주말을 셀 마지막 날. 귀국편이 다음 날 인천에 도착하는 도시(routes의 arrNextDay)는 도착일까지.
    arr_offset(상세 검색으로 확인한 귀국편 도착 날짜 차이)이 있으면 그 값을 쓴다. 기존 58곳은 arrNextDay가 없어 귀국 출발일까지(변경 없음)."""
    if not meta.get("arrNextDay"):
        return ret
    off = 1 if arr_offset is None else max(0, int(arr_offset))
    return ret + datetime.timedelta(days=off)


def trip_rules(dep: datetime.date, ret: datetime.date) -> Tuple[bool, int]:
    """(주말 조건 통과 여부, 연차 일수). 주말 = 토요일과 그다음 일요일이 모두 일정 안에 있음.
    ret는 셀 마지막 날(trip_end 결과)."""
    days = [dep + datetime.timedelta(days=i) for i in range((ret - dep).days + 1)]
    has_weekend = any(d.weekday() == 5 and (d + datetime.timedelta(days=1)) <= ret for d in days)
    hol = kr_holidays()
    leave = sum(1 for d in days if d.weekday() < 5 and d not in hol)
    return has_weekend, leave


# ------------------------------------------------------------------------------
# 링크
# ------------------------------------------------------------------------------
def google_url(org: str, dst: str, dep: str, ret: str) -> str:
    from fast_flights import FlightData, Passengers, create_filter  # type: ignore  (주소 인코딩만, 네트워크 없음)
    flt = create_filter(
        flight_data=[FlightData(date=dep, from_airport=org, to_airport=dst),
                     FlightData(date=ret, from_airport=dst, to_airport=org)],
        trip="round-trip", seat="economy", passengers=Passengers(adults=1), max_stops=0)
    # hl=ko 는 사용자 화면용 링크에만 쓴다(수집 요청과 무관)
    return f"https://www.google.com/travel/flights?tfs={flt.as_b64().decode()}&hl=ko&curr=KRW"


def naver_url(org: str, dst: str, dep: str, ret: str) -> str:
    d, r = dep.replace("-", ""), ret.replace("-", "")
    return f"https://flight.naver.com/flights/international/{org}-{dst}-{d}/{dst}-{org}-{r}?adult=1&fareType=Y"


def sky_url(org: str, dst: str, dep: str, ret: str) -> str:
    d, r = dep.replace("-", "")[2:], ret.replace("-", "")[2:]
    return (f"https://www.skyscanner.co.kr/transport/flights/{org.lower()}/{dst.lower()}/{d}/{r}/"
            f"?adultsv2=1&cabinclass=economy&rtn=1&preferdirects=true")


def links(org: str, dst: str, dep: str, ret: str) -> Dict[str, str]:
    out = {"naverUrl": naver_url(org, dst, dep, ret), "skyUrl": sky_url(org, dst, dep, ret)}
    try:
        out["googleUrl"] = google_url(org, dst, dep, ret)
    except Exception as e:  # 주소 생성 실패는 발행을 막지 않음
        print(f"   [안내] 구글 링크 생성 실패 {org}-{dst}: {e}")
        out["googleUrl"] = ""
    return out


# ------------------------------------------------------------------------------
# 1) 날짜 검색
# ------------------------------------------------------------------------------
def date_search(org: str, dst: str, nights: int, today: datetime.date, nonstop: bool = True) -> List[Tuple[datetime.date, datetime.date, int]]:
    """직항 왕복 (출발일, 귀국일, 가격원) 목록. 실패하면 예외."""
    from fli.models import Airport, DateSearchFilters, FlightSegment, MaxStops, PassengerInfo, TripType
    from fli.search import SearchDates
    d0 = today + datetime.timedelta(days=WINDOW_START)
    d1 = today + datetime.timedelta(days=WINDOW_END)
    A, B = getattr(Airport, org), getattr(Airport, dst)
    f = DateSearchFilters(
        trip_type=TripType.ROUND_TRIP, passenger_info=PassengerInfo(adults=1),
        flight_segments=[
            FlightSegment(departure_airport=[[A, 0]], arrival_airport=[[B, 0]], travel_date=d0.isoformat()),
            FlightSegment(departure_airport=[[B, 0]], arrival_airport=[[A, 0]],
                          travel_date=(d0 + datetime.timedelta(days=nights)).isoformat()),
        ],
        stops=MaxStops.NON_STOP if nonstop else MaxStops.ANY, from_date=d0.isoformat(), to_date=d1.isoformat(), duration=nights)
    res = SearchDates().search(f, currency="KRW", language="en") or []
    out = []
    for r in res:
        dep, ret = r.date[0].date(), r.date[1].date()
        price = int(round(r.price))
        if price > 0:
            out.append((dep, ret, price))
    return out


# ------------------------------------------------------------------------------
# 2) 상세 검색
# ------------------------------------------------------------------------------
def _leg_info(fr) -> Dict[str, Any]:
    legs = fr.legs or []
    first, last = legs[0], legs[-1]
    code = first.airline.name.lstrip("_")
    return {
        "airlineCode": code,
        "airline": AIRLINE_KO.get(code, f"{code}편"),  # fli 항공사 목록이 오래돼 모르는 코드는 이름 대신 코드로 표시
        "flightNo": f"{code}{first.flight_number}",
        "dep": first.departure_datetime.strftime("%H:%M"),
        "arr": last.arrival_datetime.strftime("%H:%M"),
        "arrDayOffset": (last.arrival_datetime.date() - first.departure_datetime.date()).days,  # 다음 날 도착이면 1
        "durationMin": int(fr.duration) if getattr(fr, "duration", None) else int(sum(l.duration for l in legs)),
        "stops": int(fr.stops),
    }


def _arr(leg: Dict[str, Any]) -> str:
    """도착 시각. 출발 다음 날 도착이면 '(+1)'을 붙인다."""
    n = int(leg.get("arrDayOffset") or 0)
    return leg["arr"] + (f"(+{n})" if n > 0 else "")


def detail_search(org: str, dst: str, dep: datetime.date, ret: datetime.date) -> Tuple[Optional[Dict[str, Any]], str]:
    """(직항 왕복 최저가 1건의 실제 정보 또는 None, 진단 문구). 조회 오류는 1회 재시도 후 예외."""
    from fli.models import Airport, FlightSearchFilters, FlightSegment, MaxStops, PassengerInfo, SortBy, TripType
    from fli.search import SearchFlights
    A, B = getattr(Airport, org), getattr(Airport, dst)
    f = FlightSearchFilters(
        trip_type=TripType.ROUND_TRIP, passenger_info=PassengerInfo(adults=1),
        flight_segments=[
            FlightSegment(departure_airport=[[A, 0]], arrival_airport=[[B, 0]], travel_date=dep.isoformat()),
            FlightSegment(departure_airport=[[B, 0]], arrival_airport=[[A, 0]], travel_date=ret.isoformat()),
        ],
        stops=MaxStops.NON_STOP, sort_by=SortBy.CHEAPEST)
    res = None
    for attempt in range(3):
        try:
            # top_n=1: 가는 편 최저가 1건 + 그에 맞는 오는 편(구글 왕복가). 호출 수를 줄여 응답 지연을 피함
            res = SearchFlights().search(f, top_n=1, currency="KRW", language="en") or []
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 + 6 * attempt)
            continue
        if res or attempt == 2:
            break
        # 결과 0건: 같은 서버에서 연속 조회가 쌓이면 구글이 빈 결과를 주는 경우가 있어(2026-11-03 실측) 쉬었다가 재시도
        time.sleep(EMPTY_RETRY_SLEEP * (attempt + 1))
    best, total, non_tuple, with_stops, no_price = None, 0, 0, 0, 0
    for it in res:
        total += 1
        if not isinstance(it, tuple) or len(it) != 2:
            non_tuple += 1
            continue
        out, back = it
        if out.stops != 0 or back.stops != 0:
            with_stops += 1
            continue
        if out.price is None or out.price <= 0:
            no_price += 1
            continue
        price = int(round(out.price))
        if best is None or price < best["price"]:
            best = {"price": price, "outbound": _leg_info(out), "inbound": _leg_info(back)}
    diag = f"결과 {total}건(왕복 아님 {non_tuple}, 경유 {with_stops}, 가격 없음 {no_price})"
    return best, diag


# ------------------------------------------------------------------------------
# 도시 단위 처리
# ------------------------------------------------------------------------------
_AIRPORT_OK: Dict[str, bool] = {}


def airport_supported(code: str) -> bool:
    """fli 0.9.0 공항 목록에 그 코드가 있고 다른 공항으로 합쳐지지 않았는지(워크플로 'Patch fli airport aliases' 참고)."""
    if code not in _AIRPORT_OK:
        try:
            from fli.models import Airport
            _AIRPORT_OK[code] = Airport[code].name == code
        except Exception:
            _AIRPORT_OK[code] = False
    return _AIRPORT_OK[code]


def collect_city(meta: Dict[str, Any], today: datetime.date, full_gmp: bool = False) -> Dict[str, Any]:
    """도시 하나의 후보 일정 수집. {'candidates': [...], 'errors': n, 'calls': n, 'raw': n}"""
    cands, errors, calls, raw = [], 0, 0, 0
    last_err = ""
    gmp_found = []
    gmp_checks = {}   # 김포 출발로 조회한 공항별 직항 확인 결과(월요일 전체 점검·자동 추가 판정용)
    unsupported = [a for a in meta["airports"] if not airport_supported(a)]
    airports = [a for a in meta["airports"] if a not in unsupported]
    if not airports:
        # 수집 도구가 모르는 공항뿐: 조회하지 않고 사유만 남긴다(묶음 전체는 계속)
        return {"candidates": [], "errors": 0, "calls": 0, "raw": 0, "lastError": "", "unsupported": unsupported,
                "newGmp": [], "gmpChecks": {}, "gmpBest": {}, "diag": ""}
    for org in ORIGINS:
        for dst in airports:
            if org == "GMP" and not full_gmp and dst not in GMP_QUERY:
                continue
            before, err_before = raw, errors
            for n in city_nights(meta):
                calls += 1
                try:
                    rows = date_search(org, dst, n, today)
                except Exception as e:
                    errors += 1
                    last_err = f"{type(e).__name__}: {str(e)[:120]}"
                    rows = []
                raw += len(rows)
                for dep, ret, price in rows:
                    ok_weekend, leave = trip_rules(dep, trip_end(meta, ret))
                    if ok_weekend and leave <= MAX_LEAVE_DAYS:
                        cands.append({"origin": org, "dest": dst, "dep": dep, "ret": ret,
                                      "nights": (ret - dep).days, "leave": leave, "price": price})
                time.sleep(DATE_SEARCH_DELAY)
            if org == "GMP" and raw > before and dst not in GMP_DESTINATIONS:
                gmp_found.append(dst)
            if org == "GMP":
                seen = True if raw > before else (False if errors == err_before else None)
                gmp_checks[dst] = {"seen": seen, "code": meta["code"], "city": meta["city"]}
    if raw == 0 and errors < calls and not meta.get("_retried"):
        # 일시적인 빈 응답 대비: 잠시 후 1회 다시 조회
        time.sleep(5)
        return collect_city(dict(meta, _retried=True), today, full_gmp)
    cands.sort(key=lambda c: (c["price"], c["leave"], c["dep"], c["origin"] != "ICN"))
    diag = ""
    if raw == 0 and errors < calls:
        # 직항 결과가 0건일 때만: 경유 허용 조회 1회로 '노선 자체가 조회되는지' 확인(진단용, 발행에는 쓰지 않음)
        try:
            n0 = max(3, city_nights(meta).start)
            any_rows = date_search("ICN", airports[0], n0, today, nonstop=False)
            diag = f"진단: ICN→{airports[0]} {n0}박 경유 포함 조회 {len(any_rows)}건"
        except Exception as e:
            diag = f"진단 조회 오류 {type(e).__name__}"
    gmp_best = {}
    for c in cands:   # 가격순 정렬됨: 공항별 첫 김포 출발 후보가 그날 김포 최저(날짜 검색 실조회값)
        if c["origin"] == "GMP" and c["dest"] not in gmp_best:
            gmp_best[c["dest"]] = {"price": c["price"], "dep": str(c["dep"]), "ret": str(c["ret"]), "nights": c["nights"], "leave": c["leave"]}
    if unsupported:
        diag = (diag + " | " if diag else "") + f"수집 도구 미지원 공항 제외: {', '.join(unsupported)}"
    return {"candidates": cands, "errors": errors, "calls": calls, "raw": raw, "lastError": last_err,
            "unsupported": unsupported, "newGmp": gmp_found, "gmpChecks": gmp_checks, "gmpBest": gmp_best, "diag": diag}


def pick_alt(cands: List[Dict[str, Any]], first: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for c in cands:
        if abs((c["dep"] - first["dep"]).days) >= ALT_MIN_GAP_DAYS:
            return c
    return None


def schedule_label(dep: datetime.date, ret: datetime.date) -> str:
    wd = "월화수목금토일"
    n = (ret - dep).days
    return f"{dep:%Y.%m.%d}({wd[dep.weekday()]})~{ret:%m.%d}({wd[ret.weekday()]}) ({n}박 {n + 1}일)"


def trip_holidays(dep: datetime.date, ret: datetime.date) -> List[str]:
    """일정 안에 든 한국 공휴일 이름(중복 제거, 날짜순)."""
    hol = kr_holidays()
    names: List[str] = []
    for i in range((ret - dep).days + 1):
        d = dep + datetime.timedelta(days=i)
        n = hol.get(d)
        if n and n not in names:
            names.append(str(n))
    return names


def trip_fields(c: Dict[str, Any]) -> Dict[str, Any]:
    dep, ret = c["dep"].isoformat(), c["ret"].isoformat()
    out = {"origin": c["origin"], "dest": c["dest"], "depDate": dep, "retDate": ret,
           "nights": c["nights"], "leaveDays": c["leave"], "price": c["price"],
           "dates": schedule_label(c["dep"], c["ret"]),
           "holidays": trip_holidays(c["dep"], c["ret"])}
    out.update(links(c["origin"], c["dest"], dep, ret))
    return out


def _apply_detail(row: Dict[str, Any], detail: Optional[Dict[str, Any]]) -> None:
    if detail:
        ob, ib = detail["outbound"], detail["inbound"]
        row["outbound"], row["inbound"] = ob, ib
        row["airline"] = ob["airline"] if ob["airline"] == ib["airline"] else f"{ob['airline']} / {ib['airline']}"
        row["flightNos"] = f"{ob['flightNo']} / {ib['flightNo']}"
        row["timeSlot"] = f"출국 {ob['dep']}→{_arr(ob)} / 귀국 {ib['dep']}→{_arr(ib)}"
        row["isFSC"] = ob["airlineCode"] in FSC and ib["airlineCode"] in FSC
    else:
        row["outbound"] = row["inbound"] = None
        row["airline"], row["flightNos"], row["timeSlot"], row["isFSC"] = "", "", "", False


def finalize_city(meta: Dict[str, Any], found: Dict[str, Any], today_str: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """(발행 행, 실패 행) 중 하나를 돌려준다.

    날짜 검색 후보를 가격순으로 상세 검색해 '직항이 실제로 확인된 일정'을 모은다.
    1위 = 확인된 일정 중 최저가, 2위 = 1위와 출발일이 3일 이상 떨어진 확인된 일정 중 최저가.
    화면 가격은 상세 검색 가격이다. 상세 검색이 오류로만 끝나면 날짜 검색 가격으로 발행(항공편 정보 없이).
    """
    base = {"date": today_str, "code": meta["code"], "city": meta["city"]}
    cands = found["candidates"]
    if not cands:
        if found.get("unsupported") and not found["calls"]:
            return None, dict(base, reason=f"수집 도구가 공항 코드를 지원하지 않음({', '.join(found['unsupported'])})", diag="")
        if found["calls"] and found["errors"] == found["calls"]:
            reason = f"조회 오류({found['lastError']})"
        elif found["raw"] == 0:
            reason = "탐색 기간(D+14~60) 내 ICN·GMP 직항 없음"
        else:
            reason = "주말 포함·연차 5일 이하 조건에 맞는 직항 일정 없음"
        return None, dict(base, reason=reason, diag=found.get("diag", ""))

    verified: List[Dict[str, Any]] = []
    errors: List[str] = []
    diags: List[str] = []
    tried = 0
    for c in cands:
        if tried >= DETAIL_CANDIDATES:
            break
        if over_budget():
            errors.append("시간 예산 초과로 상세 확인 생략")
            tried += 1
            break
        # 이미 확인된 1위 후보와 출발일이 같은 후보는 2위가 될 수 없으므로 건너뜀(1위 확인 전에는 모두 시도)
        if verified and all(abs((c["dep"] - v["dep"]).days) < ALT_MIN_GAP_DAYS for v in verified):
            continue
        tried += 1
        try:
            d, diag = detail_search(c["origin"], c["dest"], c["dep"], c["ret"])
        except Exception as e:
            errors.append(f"{type(e).__name__}: {str(e)[:80]}")
            continue
        if d is None:
            diags.append(f"{c['dep']}~{c['ret']} {diag}")
            # 확인된 일정 없이 빈 응답이 2번 연속이면 더 조회해도 같을 가능성이 커 중단(시간 절약)
            if not verified and len(diags) >= 2 and all(x.split(" ", 1)[1].startswith("결과 0건(") for x in diags[-2:]):
                break
            continue
        verified.append(dict(c, price=d["price"], detail=d))
        if len(verified) >= 2 and any(abs((x["dep"] - y["dep"]).days) >= ALT_MIN_GAP_DAYS
                                      for x in verified for y in verified):
            break

    if verified:
        verified.sort(key=lambda v: (v["price"], v["leave"], v["dep"]))
        first = verified[0]
        alt = next((v for v in verified[1:] if abs((v["dep"] - first["dep"]).days) >= ALT_MIN_GAP_DAYS), None)
        if alt is None:
            # 상세 확인된 2위가 없으면 날짜 검색의 실제 가격 중 1위 이상인 일정(출발일 3일 이상 차이)을 쓴다
            alt = next((c for c in cands if abs((c["dep"] - first["dep"]).days) >= ALT_MIN_GAP_DAYS
                        and c["price"] >= first["price"]), None)
        detail = first["detail"]
    elif errors and (len(errors) == tried or errors[-1].startswith("시간 예산")):
        # 상세 조회가 모두 오류: 날짜 검색의 실제 가격으로 발행(항공편 정보 없이)
        first, detail = cands[0], None
        alt = pick_alt(cands, first)
    elif diags and all(x.split(" ", 1)[1].startswith("결과 0건(") for x in diags):
        # 상세 조회가 모두 '결과 0건'(경유만 있거나 가격 없음이 아님): 일시적 빈 응답으로 보고
        # 날짜 검색(직항 필터)의 실제 가격으로 발행한다(항공편 정보 없이).
        # 근거: 2026-11-03 OIT·HPH를 새 서버에서 같은 날짜로 상세 조회하니 직항이 나왔고 가격이 날짜 검색과 같았음.
        first, detail = cands[0], None
        alt = pick_alt(cands, first)
        errors.append("상세 조회 결과 없음(일시적 빈 응답 추정)")
    else:
        return None, dict(base, reason="상세 조회에서 직항 확인 실패", diag=" | ".join(diags[:3]))

    row = dict(base)
    row.update({k: meta[k] for k in ("section", "major", "sub", "order")})
    row["note"] = meta.get("note", "")
    row["priceSource"] = "live"
    _apply_detail(row, detail)
    if detail is None:
        row["detailError"] = errors[-1] if errors else ""
    row.update(trip_fields(first))
    if meta.get("arrNextDay"):
        # 귀국편이 다음 날 도착하는 도시: 상세 검색으로 확인한 실제 인천 도착일로 연차를 다시 센다(모르면 날짜 검색 때의 +1일 값)
        off = detail["inbound"].get("arrDayOffset") if detail else None
        end = trip_end(meta, first["ret"], off)
        row["leaveDays"] = trip_rules(first["dep"], end)[1]
        row["retArrDate"] = end.isoformat()
        row["retArrSource"] = "detail" if (detail and off is not None) else "assumed"
    row["alt"] = trip_fields(alt) if alt else None
    if row["alt"] is not None:
        row["alt"]["verified"] = bool(alt.get("detail"))
    # 1면 B(연차 효율)용: 3박 이상 + 연차 1일 이하 일정 중 최저가(날짜 검색 실제 가격, 항공편 정보 없음)
    ls = next((c for c in cands if c["nights"] >= LEAVE_SAVER_MIN_NIGHTS and c["leave"] <= LEAVE_SAVER_MAX_LEAVE), None)
    if ls:
        same = next((v for v in verified if (v["origin"], v["dest"], v["dep"], v["ret"]) == (ls["origin"], ls["dest"], ls["dep"], ls["ret"])), None)
        row["leaveSaver"] = dict(trip_fields(same or ls), source="detail" if same else "calendar")
    else:
        row["leaveSaver"] = None
    row["bestSeasons"] = [{"months": m, "label": lb} for m, lb in BEST_SEASONS.get(meta["code"], [])]
    return row, None


# ------------------------------------------------------------------------------
# 저장
# ------------------------------------------------------------------------------
def load_previous(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) and d.get("schemaVersion") == SCHEMA_VERSION else {}
    except Exception:
        return {}


def archive_and_report(rows: List[Dict[str, Any]], failed: List[Dict[str, Any]], today_str: str) -> None:
    """1위 실가격만 영구 이력에 누적하고 월간·분기·연간 리포트를 갱신(2위는 넣지 않음)."""
    import build_reports
    import history_store
    removed = history_store.remove_observations(today_str, [f["code"] for f in failed])
    if removed:
        print(f"🗄️ [전체 이력] 오늘 발행하지 못한 도시의 같은 날 기록 {removed}건 삭제")
    obs = [{"date": r["date"], "code": r["code"], "price": r["price"], "source": "live",
            "dep": r["depDate"], "ret": r["retDate"],
            "airline": (f"{r['outbound']['airlineCode']}/{r['inbound']['airlineCode']}" if r.get("outbound") else ""),
            "fsc": (bool(r["isFSC"]) if r.get("outbound") else None)} for r in rows]
    res = history_store.upsert_observations(obs)
    print(f"🗄️ [전체 이력] {res['accepted']}건 보관, 새로 쓰거나 바뀐 행 {res['changed']}건")
    meta = {m["code"]: m for m in CITY_MASTER}
    print("📊 [리포트 갱신]", ", ".join(build_reports.update_current(today_str, meta)) or "(없음)")


def series_from_history(codes: List[str]) -> Dict[str, Dict[str, List[Any]]]:
    import history_store
    per: Dict[str, List[Tuple[str, int, str]]] = {}
    for r in history_store.iter_all():
        # 화면 추이·판정은 v2 수집기 실조회(live)만. 이전 수집기(sheet, 2026-10)는 탐색 조건이 달라 섞지 않는다(파일에는 보존)
        if r["code"] in codes and r.get("source") == "live":
            per.setdefault(r["code"], []).append((r["date"], r["price"], r.get("fsc", "")))
    out = {}
    for c, v in per.items():
        v.sort()
        out[c] = {"fullDates": [d for d, _, _ in v], "dates": [d for d, _, _ in v],
                  "prices": [p for _, p, _ in v], "fsc": [f for _, _, f in v]}
    return out


SITE_URL = "https://lee2000y-max.github.io/daily-flight-news/"
FEED_PATH = "feed.xml"


def write_feed(data: Dict[str, Any]) -> None:
    """RSS 2.0(feed.xml): 발행호마다 1건. 내용은 그날 실제 조회한 최저가 상위 5개 도시."""
    from email.utils import format_datetime
    from xml.sax.saxutils import escape
    items = []
    for d in data.get("availableDates", []):
        rows = sorted([r for r in data.get("flights", []) if r.get("date") == d], key=lambda r: r["price"])
        if not rows:
            continue
        st = data.get("status", {}).get(d, {})
        y, m, dd = d.split("-")
        title = f"{y}년 {int(m)}월 {int(dd)}일 발행호 — 최저가 {rows[0]['city']} {rows[0]['price']:,}원 외 {len(rows) - 1}개 도시"
        lines = [f"{i + 1}. {r['city']} ({r['origin']}→{r['dest']}) {r['price']:,}원 · {r['dates']}" for i, r in enumerate(rows[:5])]
        lines.append(f"오늘 발행 {st.get('published', len(rows))}/{st.get('total', '-')}개 도시. 가격은 발행일 아침 실제 조회값입니다.")
        gen = st.get("generatedAt") or f"{d} 07:30"
        pub = datetime.datetime.strptime(gen, "%Y-%m-%d %H:%M").replace(tzinfo=KST)
        items.append(
            "    <item>\n"
            f"      <title>{escape(title)}</title>\n"
            f"      <link>{SITE_URL}</link>\n"
            f"      <guid isPermaLink=\"false\">boarding-pass-times-{d}</guid>\n"
            f"      <pubDate>{format_datetime(pub)}</pubDate>\n"
            f"      <description>{escape(chr(10).join(lines))}</description>\n"
            "    </item>")
    xml = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<rss version=\"2.0\">\n  <channel>\n"
           "    <title>보딩패스 타임즈 — 인천·김포 출발 직항 최저가</title>\n"
           f"    <link>{SITE_URL}</link>\n"
           "    <description>매일 아침 인천·김포 출발 직항 노선의 실제 왕복 최저가</description>\n"
           "    <language>ko</language>\n" + "\n".join(items) + "\n  </channel>\n</rss>\n")
    with open(FEED_PATH, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"📰 {FEED_PATH} 저장 ({len(items)}건)")


FX_URL = "https://open.er-api.com/v6/latest/KRW"


def fetch_fx() -> Dict[str, Any]:
    """오늘의 원화 환율(키 없는 ExchangeRate-API 공개 엔드포인트). 실패하면 빈 값 — 이월하지 않는다(절대 규칙 1)."""
    import urllib.request
    try:
        with urllib.request.urlopen(FX_URL, timeout=20) as r:
            d = json.load(r)
        if d.get("result") != "success":
            raise ValueError(d.get("error-type") or "result != success")
        rates = d.get("rates", {})
        out = {}
        for cur in sorted(set(CITY_CURRENCY.values())):
            per_krw = rates.get(cur)
            if not per_krw:
                continue
            unit = CURRENCY_UNIT.get(cur, 1)
            out[cur] = {"krw": round(unit / per_krw, 2), "unit": unit, "name": CURRENCY_NAME.get(cur, cur)}
        print(f"💱 환율 {len(out)}종 ({d.get('time_last_update_utc', '')})")
        return {"source": "ExchangeRate-API (open.er-api.com)", "sourceUrl": "https://www.exchangerate-api.com",
                "updated": d.get("time_last_update_utc", ""), "rates": out, "cityCurrency": CITY_CURRENCY}
    except Exception as e:
        print(f"⚠️ 환율 조회 실패(환율 박스 생략): {type(e).__name__}: {str(e)[:120]}")
        return {}


def load_climate() -> Dict[str, Any]:
    """도시별 월 기후 평년값(build_climate.py 결과). 없으면 빈 값(1면 F는 편집 제철 정보만 사용)."""
    try:
        with open(os.path.join("data", "climate_normals.json"), "r", encoding="utf-8") as f:
            d = json.load(f)
        return {"source": d.get("source", ""), "period": d.get("period", ""), "cities": d.get("cities", {})}
    except Exception:
        return {}


def collect_phase(cities: List[Dict[str, Any]], today: datetime.date) -> Dict[str, Any]:
    """날짜 검색 + 상세 검색. 결과(발행·미발행)를 돌려준다(저장은 하지 않음)."""
    today_str = today.isoformat()
    full_gmp = today.weekday() == 0 or os.environ.get("FULL_GMP_SCAN", "").strip() == "1"
    auto = gmp_auto.active(gmp_auto.load())
    GMP_QUERY.clear()
    GMP_QUERY.update(set(GMP_DESTINATIONS) | auto)
    if auto:
        print(f"➕ 자동 추가된 김포 노선도 조회: {', '.join(sorted(auto))}")
    if full_gmp:
        print("🔎 오늘은 김포 출발 전체 공항을 다시 확인합니다(월요일 정기 점검)")
    t0 = time.time()
    found = {}
    for i, m in enumerate(cities, 1):
        found[m["code"]] = collect_city(m, today, full_gmp)
        f = found[m["code"]]
        best = f["candidates"][0] if f["candidates"] else None
        print(f" · [{i:02d}/{len(cities)}] {m['city']} ({m['code']}): 날짜 검색 {f['calls']}회(오류 {f['errors']}), "
              f"조건 통과 {len(f['candidates'])}건" + (f", 최저 {best['price']:,}원 {best['origin']}→{best['dest']} {best['dep']}~{best['ret']}" if best else ""))
    print(f"⏱️ 날짜 검색 {time.time() - t0:.0f}초")
    new_gmp = sorted({d for f in found.values() for d in f.get("newGmp", [])})
    if new_gmp:
        print(f"🆕 김포 직항 목록에 없는 공항에서 김포 직항 발견: {', '.join(new_gmp)} → 자동 추가(data/gmp_auto.json), 확정하려면 routes.py GMP_DESTINATIONS로")

    t1 = time.time()
    results = []
    for m in cities:
        results.append(finalize_city(m, found[m["code"]], today_str))
        r, f = results[-1]
        print(f"   상세 {m['city']}: " + (f"{r['price']:,}원" if r else f"미발행({f['reason']})"), flush=True)
    print(f"⏱️ 상세 검색 {time.time() - t1:.0f}초")
    gmp_checks, gmp_best = {}, {}
    for f in found.values():
        gmp_checks.update(f.get("gmpChecks", {}))
        gmp_best.update(f.get("gmpBest", {}))
    return {"date": today_str,
            "published": [r for r, _ in results if r],
            "failed": [f for _, f in results if f],
            "codes": [m["code"] for m in cities],
            "fullGmp": full_gmp, "gmpChecks": gmp_checks, "gmpBest": gmp_best}


def apply_gmp_auto(shards: List[Dict[str, Any]], published: List[Dict[str, Any]], today_str: str, dry: bool) -> List[Dict[str, Any]]:
    """묶음 결과로 자동 추가 목록을 고치고(월요일 전체 점검일 때만), 감지된 주의 신규 노선 기록(newRoutes, 오늘 조회값)을 만든다."""
    state = gmp_auto.load()
    if any(s.get("fullGmp") for s in shards):
        checks = {}
        for s in shards:
            checks.update(s.get("gmpChecks", {}))
        ch = gmp_auto.update(state, checks, set(GMP_DESTINATIONS), today_str)
        for d in ch["added"]:
            print(f"🆕 김포 신규 직항 자동 추가: GMP→{d} ({state['routes'][d].get('city', '')}) — 다음 수집부터 매일 조회")
        for d in ch["removed"]:
            print(f"➖ 김포 노선 자동 제외: GMP→{d} (월요일 점검 {gmp_auto.MISS_LIMIT}번 연속 직항 없음)")
        if not dry:
            gmp_auto.save(state)
    best = {}
    for s in shards:
        best.update(s.get("gmpBest", {}))
    by_code = {r["code"]: r for r in published}
    recs = []
    for dst, e in sorted(state.get("routes", {}).items()):
        if not gmp_auto.is_new(e, today_str):
            continue
        rec = gmp_auto.new_route_record(dst, e, best.get(dst), today_str, by_code.get(e.get("code")))
        if rec:
            recs.append(rec)
            print(f"📰 신규 취항 기사 후보: GMP→{dst} {rec['city']} {rec['price']:,}원 {rec['depDate']}~{rec['retDate']}")
        else:
            print(f"   신규 노선 GMP→{dst}: 오늘 조건에 맞는 김포 출발 일정이 없어 기사 없음")
    return recs


def print_summary(published: List[Dict[str, Any]], failed: List[Dict[str, Any]], total: int) -> None:
    for r in published:
        tag = "" if r.get("outbound") else " (항공편 정보 없음: " + r.get("detailError", "")[:60] + ")"
        alt = f" | 2위 {r['alt']['price']:,}원 {r['alt']['depDate']}" if r.get("alt") else ""
        print(f" ✓ {r['city']}: {r['price']:,}원 {r['origin']}→{r['dest']} {r['dates']} {r['airline']} {r['timeSlot']}{tag}{alt}")
    for f in failed:
        print(f" ✗ {f['city']}: {f['reason']}" + (f" [{f['diag']}]" if f.get("diag") else ""))
    print(f"📌 발행 {len(published)}/{total}개 도시, 미발행 {len(failed)}개")


def main() -> None:
    """
    MODE=collect  SHARD_INDEX=i SHARD_COUNT=n : 도시의 i번째 묶음만 수집해 shard_out/shard_i.json 에 저장
    MODE=merge                                 : shard_out/*.json 을 합쳐 flights_data.json·이력 저장
    MODE 없음                                  : 한 번에 수집 + 저장(로컬·소규모 검증용)
    여러 서버에 나누는 이유: 한 서버에서 수백 번 연속 조회하면 구글이 응답을 20배 가까이 늦춤(2026-11-02 실측).
    """
    today = kst_today()
    today_str = today.isoformat()
    mode = os.environ.get("MODE", "").strip()
    only = {c.strip() for c in os.environ.get("ONLY_CITIES", "").split(",") if c.strip()}
    all_cities = [m for m in CITY_MASTER if not only or m["code"] in only]
    dry = os.environ.get("DRY_RUN", "").strip() == "1"

    if mode == "sellers":
        # 판매처별 가격: API 조회를 하지 않은 새 서버에서 실행(같은 서버에서 수백 번 조회한 뒤에는 구글이 확인 화면을 띄움, 2026-11-03 실측)
        import sellers
        idx = int(os.environ.get("SHARD_INDEX", "0"))
        path = f"shard_out/shard_{idx}.json"
        if not os.path.exists(path):
            print(f"묶음 결과 없음: {path}")
            return
        with open(path, encoding="utf-8") as f:
            res = json.load(f)
        t1 = time.time()
        got = sellers.collect_sellers(res.get("published", []), budget_sec=float(os.environ.get("SELLERS_BUDGET", "600")))
        os.makedirs("sellers_out", exist_ok=True)
        with open(f"sellers_out/sellers_{idx}.json", "w", encoding="utf-8") as f:
            json.dump(got, f, ensure_ascii=False)
        print(f"🏷️ 판매처 {len(got)}/{len(res.get('published', []))}개 도시, {time.time() - t1:.0f}초")
        return

    if mode in ("", "collect"):
        cities = all_cities
        if mode == "collect":
            idx, cnt = int(os.environ.get("SHARD_INDEX", "0")), int(os.environ.get("SHARD_COUNT", "1"))
            cities = all_cities[idx::cnt]
            print(f"🧩 묶음 {idx + 1}/{cnt}: {len(cities)}개 도시")
        print(f"📰 [{today_str}] {len(cities)}개 도시 수집 시작 (출발 {', '.join(ORIGINS)} · D+{WINDOW_START}~{WINDOW_END} · 2~8박(유럽·미주 4~8, 장거리 대양주 3~8) · 직항)")
        res = collect_phase(cities, today)
        if mode == "collect":
            os.makedirs("shard_out", exist_ok=True)
            with open(f"shard_out/shard_{idx}.json", "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False)
            print_summary(res["published"], res["failed"], len(cities))
            return
        published, failed = res["published"], res["failed"]
        gmp_shards = [res]
    else:  # merge
        shards = []
        for name in sorted(os.listdir("shard_out")) if os.path.isdir("shard_out") else []:
            with open(os.path.join("shard_out", name), encoding="utf-8") as f:
                shards.append(json.load(f))
        if shards:
            # 발행일은 묶음 수집이 시작된 날짜(자정 직전에 시작해 합치기가 자정을 넘겨도 같은 호로 묶음)
            from collections import Counter
            today_str = Counter(s["date"] for s in shards).most_common(1)[0][0]
        published, failed, seen = [], [], set()
        for res in shards:
            for r in res["published"]:
                r["date"] = today_str
            for r in res["failed"]:
                r["date"] = today_str
            published += res["published"]
            failed += res["failed"]
            seen |= set(res["codes"])
        for m in all_cities:
            if m["code"] not in seen:
                failed.append({"date": today_str, "code": m["code"], "city": m["city"], "reason": "수집 작업 실패(해당 묶음 결과 없음)"})
        print(f"🧩 묶음 결과 합치기: 수집된 도시 {len(seen)}/{len(all_cities)}")
        gmp_shards = shards
        got = {}
        for name in sorted(os.listdir("sellers_out")) if os.path.isdir("sellers_out") else []:
            try:
                with open(os.path.join("sellers_out", name), encoding="utf-8") as f:
                    got.update(json.load(f))
            except Exception as e:
                print(f"판매처 결과 읽기 실패 {name}: {e}")
        for r in published:
            sv = got.get(r["code"])
            if not sv or not sv.get("items"):
                continue
            lo = min(x["price"] for x in sv["items"])
            # 판매처 최저가가 카드 가격과 5% 넘게 다르면 다른 편을 읽었을 가능성이 커 싣지 않는다(2026-11-03 도쿄 281,300 vs 300,300)
            if abs(lo - r["price"]) > r["price"] * 0.05:
                print(f"   판매처 제외 {r['city']}: 카드 {r['price']:,} vs 판매처 최저 {lo:,}")
                continue
            r["sellers"] = sv
        print(f"🏷️ 판매처 정보 {sum(1 for r in published if r.get('sellers'))}/{len(published)}개 도시")
    cities = all_cities
    print_summary(published, failed, len(cities))
    new_routes = apply_gmp_auto(gmp_shards, published, today_str, dry)

    if dry:
        print("DRY_RUN=1: 저장하지 않음")
        return
    if not published:
        print("[오류] 발행 도시가 0개라 저장하지 않습니다(이전 지면 유지).")
        sys.exit(1)

    prev = load_previous(DATA_JSON_PATH)
    keep_flights = [r for r in prev.get("flights", []) if r.get("date") != today_str]
    keep_failed = [r for r in prev.get("failed", []) if r.get("date") != today_str]
    status = dict(prev.get("status", {}))
    status[today_str] = {"published": len(published), "total": len(cities),
                         "generatedAt": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")}
    dates = sorted({r["date"] for r in keep_flights + published} | set(status), reverse=True)[:KEEP_EDITIONS]
    keep = set(dates)
    flights = sorted([r for r in keep_flights + published if r["date"] in keep],
                     key=lambda r: (r["date"], -r.get("order", 0)), reverse=True)
    failed_all = [r for r in keep_failed + failed if r["date"] in keep]

    archive_and_report(published, failed, today_str)
    series = series_from_history([m["code"] for m in CITY_MASTER])

    out = {
        "schemaVersion": SCHEMA_VERSION,
        "publisher": "THE BOARDING PASS TIMES (보딩패스 타임즈 항공편집국)",
        "updatedAt": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "latestDate": today_str,
        "availableDates": dates,
        "status": {d: status[d] for d in dates if d in status},
        "flights": flights,
        "failed": failed_all,
        "newRoutes": sorted([r for r in prev.get("newRoutes", []) if r.get("date") in keep and r.get("date") != today_str] + new_routes,
                            key=lambda r: (r["date"], r["dest"]), reverse=True),
        "historicalSeries": series,
        "climate": load_climate(),
        "fx": fetch_fx(),
    }
    tmp = DATA_JSON_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    os.replace(tmp, DATA_JSON_PATH)
    print(f"✅ {DATA_JSON_PATH} 저장 (발행일 {len(dates)}개)")
    write_feed(out)

    if os.environ.get("FAIL_ON_LOW_LIVE", "").strip() == "1" and len(published) < len(cities) / 2:
        print(f"[경고] 발행 도시 {len(published)}/{len(cities)} — 절반 미만이라 작업을 실패로 표시합니다(데이터는 저장됨)")
        sys.exit(1)


if __name__ == "__main__":
    main()
