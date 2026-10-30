#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
월간/분기/연간 리포트 생성 (history_store 의 CSV → 정적 JSON)

  data/reports/monthly/YYYY-MM.json
  data/reports/quarterly/YYYY-Qn.json
  data/reports/annual/YYYY.json
  data/reports/index.json              (존재하는 기간 목록)

사이트는 이 JSON 만 읽으면 됩니다. (GitHub Pages 정적 파일)
통계에는 history_store 에 저장된 신뢰 관측(live/sheet)만 쓰이며, coverage 항목으로 데이터 충실도를 함께 제공합니다.

사용법
  python build_reports.py --all            # 전체 재생성
  python build_reports.py --period 2026-10 # 한 기간만 (2026-10 / 2026-Q4 / 2026)
"""

import argparse
import calendar
import collections
import datetime
import json
import os
import statistics
from typing import Any, Dict, List, Optional, Tuple

import history_store as hs

REPORT_DIR = os.path.join("data", "reports")
MIN_OBS_TREND = 2   # 변동(첫값→끝값) 계산 최소 관측 수
MIN_OBS_VOL = 3     # 변동성 계산 최소 관측 수
KST = datetime.timezone(datetime.timedelta(hours=9))


# ------------------------------------------------------------------ 기간 유틸
def months_of(kind: str, key: str) -> List[str]:
    if kind == "monthly":
        return [key]
    if kind == "quarterly":
        y, q = key.split("-Q")
        start = (int(q) - 1) * 3 + 1
        return [f"{y}-{m:02d}" for m in range(start, start + 3)]
    if kind == "annual":
        return [f"{key}-{m:02d}" for m in range(1, 13)]
    raise ValueError(kind)


def quarter_key(ym: str) -> str:
    return f"{ym[:4]}-Q{(int(ym[5:7]) - 1) // 3 + 1}"


def days_in_period(months: List[str]) -> int:
    return sum(calendar.monthrange(int(m[:4]), int(m[5:7]))[1] for m in months)


def report_path(kind: str, key: str) -> str:
    return os.path.join(REPORT_DIR, kind, f"{key}.json")


# ------------------------------------------------------------------ 통계
def _pt(date: str, price: int) -> Dict[str, Any]:
    return {"date": date, "price": price}


def route_stats(points: List[Tuple[str, int]], with_series: bool) -> Dict[str, Any]:
    pts = sorted(points)
    prices = [p for _, p in pts]
    n = len(prices)
    lo = min(pts, key=lambda x: (x[1], x[0]))
    hi = max(pts, key=lambda x: (x[1], -int(x[0].replace("-", ""))))
    mean = statistics.mean(prices)
    out: Dict[str, Any] = {
        "n": n,
        "min": _pt(*lo),
        "max": _pt(*hi),
        "mean": round(mean),
        "median": round(statistics.median(prices)),
        "first": _pt(*pts[0]),
        "last": _pt(*pts[-1]),
        "change": None,
        "change_pct": None,
        "volatility_pct": None,
    }
    if n >= MIN_OBS_TREND:
        out["change"] = prices[-1] - prices[0]
        out["change_pct"] = round((prices[-1] - prices[0]) / prices[0] * 100, 1)
    if n >= MIN_OBS_VOL and mean > 0:
        out["volatility_pct"] = round(statistics.pstdev(prices) / mean * 100, 1)
    if with_series:
        out["series"] = [[d, p] for d, p in pts]
    return out


def _top(routes: Dict[str, Dict[str, Any]], field: str, reverse: bool, limit: int = 5) -> List[Dict[str, Any]]:
    items = [(code, r[field]) for code, r in routes.items() if r.get(field) is not None]
    items.sort(key=lambda x: (x[1], x[0]), reverse=reverse)
    return [{"code": c, "value": v} for c, v in items[:limit]]


def build_report(kind: str, key: str, meta: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    months = months_of(kind, key)
    per_route: Dict[str, List[Tuple[str, int]]] = collections.defaultdict(list)
    per_route_month: Dict[str, Dict[str, List[int]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    by_source: collections.Counter = collections.Counter()
    dates = set()
    for ym in months:
        for r in hs.read_month(ym).values():
            per_route[r["code"]].append((r["date"], r["price"]))
            per_route_month[r["code"]][ym].append(r["price"])
            by_source[r["source"]] += 1
            dates.add(r["date"])
    if not per_route:
        return None

    with_series = kind == "monthly"
    routes: Dict[str, Dict[str, Any]] = {}
    for code in sorted(per_route):
        st = route_stats(per_route[code], with_series)
        m = meta.get(code, {})
        st.update({"city": m.get("city", code), "section": m.get("section", ""),
                   "major": m.get("major", ""), "sub": m.get("sub", "")})
        if not with_series:
            st["monthly_means"] = [[ym, round(statistics.mean(v))] for ym, v in sorted(per_route_month[code].items())]
        routes[code] = st

    sections: Dict[str, Dict[str, Any]] = {}
    grouped: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for r in routes.values():
        grouped[r["section"] or "-"].append(r)
    for sec, items in sorted(grouped.items()):
        sections[sec] = {"major": items[0]["major"], "routes": len(items),
                         "mean_price": round(statistics.mean(i["mean"] for i in items))}

    return {
        "type": kind,
        "period": key,
        "generatedAt": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "coverage": {
            "days_with_data": len(dates),
            "days_in_period": days_in_period(months),
            "first_date": min(dates),
            "last_date": max(dates),
            "observations": sum(by_source.values()),
            "routes_with_data": len(routes),
            "by_source": dict(by_source),
        },
        "highlights": {
            "cheapest_mean": _top(routes, "mean", False),
            "biggest_drop_pct": [x for x in _top(routes, "change_pct", False) if x["value"] < 0],
            "biggest_rise_pct": [x for x in _top(routes, "change_pct", True) if x["value"] > 0],
            "most_volatile_pct": _top(routes, "volatility_pct", True),
        },
        "sections": sections,
        "routes": routes,
    }


# ------------------------------------------------------------------ 쓰기/인덱스
def _write_json(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def write_report(kind: str, key: str, meta: Dict[str, Dict[str, Any]]) -> bool:
    rep = build_report(kind, key, meta)
    if rep is None:
        return False
    _write_json(report_path(kind, key), rep)
    return True


def rebuild_index() -> Dict[str, Any]:
    idx: Dict[str, Any] = {"updatedAt": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")}
    for kind in ("monthly", "quarterly", "annual"):
        d = os.path.join(REPORT_DIR, kind)
        names = sorted((n[:-5] for n in os.listdir(d) if n.endswith(".json")), reverse=True) if os.path.isdir(d) else []
        idx[kind] = names
    _write_json(os.path.join(REPORT_DIR, "index.json"), idx)
    return idx


def update_current(today: str, meta: Dict[str, Dict[str, Any]]) -> List[str]:
    """오늘이 속한 월/분기/연 리포트와 인덱스를 갱신합니다. (매일 실행용)"""
    ym = today[:7]
    built = []
    for kind, key in (("monthly", ym), ("quarterly", quarter_key(ym)), ("annual", ym[:4])):
        if write_report(kind, key, meta):
            built.append(f"{kind}:{key}")
    rebuild_index()
    return built


def rebuild_all(meta: Dict[str, Dict[str, Any]]) -> List[str]:
    months = hs.months_available()
    built = []
    for ym in months:
        if write_report("monthly", ym, meta):
            built.append(f"monthly:{ym}")
    for q in sorted({quarter_key(m) for m in months}):
        if write_report("quarterly", q, meta):
            built.append(f"quarterly:{q}")
    for y in sorted({m[:4] for m in months}):
        if write_report("annual", y, meta):
            built.append(f"annual:{y}")
    rebuild_index()
    return built


def _load_meta() -> Dict[str, Dict[str, Any]]:
    from collect_flights import CITIES_58_MASTER
    return {m["code"]: m for m in CITIES_58_MASTER}


def main() -> None:
    ap = argparse.ArgumentParser(description="월간/분기/연간 리포트 생성")
    ap.add_argument("--all", action="store_true", help="저장된 모든 기간을 다시 생성")
    ap.add_argument("--period", help="2026-10 / 2026-Q4 / 2026")
    args = ap.parse_args()
    meta = _load_meta()
    if args.all or not args.period:
        print("생성:", ", ".join(rebuild_all(meta)) or "(데이터 없음)")
        return
    p = args.period
    kind = "monthly" if len(p) == 7 else "quarterly" if "Q" in p else "annual"
    print("생성:" if write_report(kind, p, meta) else "데이터 없음:", p)
    rebuild_index()


if __name__ == "__main__":
    main()
