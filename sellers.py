#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
판매처별 가격(구글 플라이트 '예약 옵션') 수집. 사용자 결정(2026-11-03)으로 매일 수집에 포함.

- 도시별 1위 일정(상세 검색으로 확인된 가는 편·오는 편)을 실제 브라우저로 열고,
  화면에서 같은 출발 시각의 직항을 골라 예약 옵션의 판매처·가격을 읽는다.
- 화면 값만 저장한다(추정 없음). 같은 편을 못 찾으면 그 도시는 판매처 정보를 비운다.
- 차단·확인(CAPTCHA) 화면이 나오면 그 묶음의 남은 도시는 건너뛴다(우회하지 않음, 절대 규칙 6).
- 수집 요청과 달리 화면 언어는 영어(hl=en)로 연다(문구 "Book with"·"Booking options"로 읽기 때문).
"""
import re
import time
from typing import Any, Dict, List, Optional

PRICE_RE = re.compile(r"(?:₩|KRW)\s?([\d,]{4,})")


def _ampm(hhmm: str) -> str:
    h, m = int(hhmm[:2]), hhmm[3:5]
    return f"{(h % 12) or 12}:{m} {'AM' if h < 12 else 'PM'}"


def _url(org: str, dst: str, dep: str, ret: str) -> str:
    from fast_flights import FlightData, Passengers, create_filter  # type: ignore
    flt = create_filter(flight_data=[FlightData(date=dep, from_airport=org, to_airport=dst),
                                     FlightData(date=ret, from_airport=dst, to_airport=org)],
                        trip="round-trip", seat="economy", passengers=Passengers(adults=1), max_stops=0)
    return f"https://www.google.com/travel/flights?tfs={flt.as_b64().decode()}&hl=en&curr=KRW&gl=KR"


def _blocked(page) -> bool:
    try:
        t = page.inner_text("body")[:3000].lower()
    except Exception:
        return False
    return "unusual traffic" in t or "captcha" in t or "/sorry/" in page.url


def _pick(page, dep_hhmm: str) -> bool:
    """가격이 보이는 목록에서 출발 시각이 같은 직항 줄을 누른다. 못 찾으면 False(다른 편을 누르지 않음)."""
    page.wait_for_timeout(2500)
    items = page.locator("li").filter(has_text=PRICE_RE)
    n = items.count()
    want = _ampm(dep_hhmm)
    alt = want.replace(" ", " ")
    for i in range(min(n, 40)):
        t = items.nth(i).inner_text()
        first_line = t.split("\n")[0].replace(" ", " ")
        if (first_line.startswith(alt)) and "Nonstop" in t:
            items.nth(i).click()
            return True
    return False


def _read_booking(page) -> List[Dict[str, Any]]:
    # 예약 옵션이 늦게 뜨는 경우가 있어 'Book with' 문구가 보일 때까지 최대 15초 기다린다(2026-11-03: 4초 고정 대기로 14곳 놓침)
    try:
        page.get_by_text(re.compile(r"^Book with", re.I)).first.wait_for(timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(800)
    body = page.inner_text("body")
    i = body.find("Booking options")
    if i < 0:
        return []
    rows = [ln.strip() for ln in body[i:i + 3000].split("\n") if ln.strip()]
    out = []
    for k, ln in enumerate(rows):
        if not ln.lower().startswith("book with"):
            continue
        name = ln[len("Book with"):].strip()
        is_airline = name.endswith("Airline")
        if is_airline:
            name = name[: -len("Airline")].strip()
        # 가격은 이 판매처 줄부터 다음 'Book with' 전까지에서, 수하물·요금 안내 문구가 아닌 줄의 첫 원화 값
        nxt = next((j for j in range(k + 1, len(rows)) if rows[j].lower().startswith("book with")), min(len(rows), k + 6))
        m = None
        for x in rows[k:nxt]:
            low = x.lower()
            if any(w in low for w in ("bag", "fee", "cheaper", "less", "save", "carry-on")):
                continue
            m = PRICE_RE.search(x)
            if m:
                break
        if m and int(m.group(1).replace(",", "")) >= 30000:   # 왕복 직항 운임이 3만 원 미만일 수는 없음(수수료·수하물 금액 오인 방지)
            out.append({"name": name, "price": int(m.group(1).replace(",", "")), "airline": is_airline})
    return out


def collect_sellers(rows: List[Dict[str, Any]], log=print, budget_sec: float = 600) -> Dict[str, Dict[str, Any]]:
    """{도시 코드: {"items": [...], "checkedAt": "HH:MM"}}. 실패한 도시는 넣지 않는다."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as e:
        log(f"⚠️ 판매처 수집 생략(브라우저 없음): {e}")
        return {}
    t0 = time.time()
    out: Dict[str, Dict[str, Any]] = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(locale="en-US", viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        for r in rows:
            ob, ib = r.get("outbound"), r.get("inbound")
            if not ob or not ib:
                continue
            if time.time() - t0 > budget_sec:
                log("   판매처: 시간 예산 초과로 나머지 생략")
                break
            try:
                page.goto(_url(r["origin"], r["dest"], r["depDate"], r["retDate"]), wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                if _blocked(page):
                    log("   ⛔ 판매처: 차단·확인 화면 → 이 묶음의 나머지 생략")
                    break
                if not _pick(page, ob["dep"]) or not _pick(page, ib["dep"]):
                    log(f"   판매처 {r['city']}: 같은 편을 화면에서 못 찾음")
                    continue
                items = _read_booking(page)
                if items:
                    items.sort(key=lambda x: x["price"])
                    out[r["code"]] = {"items": items, "checkedAt": time.strftime("%H:%M", time.gmtime(time.time() + 9 * 3600))}
                    log(f"   판매처 {r['city']}: {len(items)}곳 " + ", ".join(f"{x['name']} {x['price']:,}" for x in items[:4]))
                else:
                    log(f"   판매처 {r['city']}: 예약 옵션을 못 읽음")
            except Exception as e:
                log(f"   판매처 {r['city']}: 오류 {type(e).__name__}: {str(e)[:120]}")
        b.close()
    return out
