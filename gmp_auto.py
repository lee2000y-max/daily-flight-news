# -*- coding: utf-8 -*-
"""
신규 김포 노선 자동 추가(P5-5, 2026-11-03 사용자 결정 P5-c).

- 월요일(또는 FULL_GMP_SCAN=1) 김포 전체 공항 점검에서 routes.GMP_DESTINATIONS에 없는 공항으로 김포 직항이 보이면
  data/gmp_auto.json에 넣고, 다음 수집부터 매일 김포 출발도 조회한다.
- 월요일 점검에서 4번 연속 안 보이면 뺀다(운항 중단·계절 노선). 조회 오류로 확인을 못 한 날은 세지 않는다.
- 감지된 주(감지일 포함 7일)에는 그날 실제 조회한 김포 출발 최저 일정을 flights_data.json의 newRoutes에 남긴다
  (1면 신규 취항 기사용. 월요일 가격을 다른 날 다시 쓰지 않는다 = 절대 규칙 1).
"""
import datetime, json, os
from typing import Any, Dict, Optional, Set

PATH = "data/gmp_auto.json"
MISS_LIMIT = 4          # 월요일 점검 연속 미감지 횟수 → 제외
NEW_DAYS = 7            # 감지일부터 며칠 동안 '신규 취항'으로 1면 후보


def load(path: Optional[str] = None) -> Dict[str, Any]:
    try:
        with open(path or PATH, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("routes"), dict):
            return d
    except (OSError, ValueError):
        pass
    return {"routes": {}}


def save(state: Dict[str, Any], path: Optional[str] = None) -> None:
    path = path or PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)


def active(state: Dict[str, Any]) -> Set[str]:
    return set(state.get("routes", {}))


def update(state: Dict[str, Any], checks: Dict[str, Dict[str, Any]], static: Set[str], today: str) -> Dict[str, list]:
    """
    월요일 전체 점검 결과로 상태를 고친다. checks = {공항: {"seen": True/False/None, "code", "city"}}
    seen=None은 조회 오류로 확인 못 함(세지 않음). 돌려주는 값: {"added": [...], "removed": [...]}.
    """
    routes = state.setdefault("routes", {})
    added, removed = [], []
    for dst, c in sorted(checks.items()):
        if dst in static:
            continue
        seen = c.get("seen")
        if seen is True:
            if dst not in routes:
                routes[dst] = {"code": c.get("code", ""), "city": c.get("city", ""), "addedOn": today, "lastSeen": today, "missed": 0}
                added.append(dst)
            else:
                routes[dst].update({"lastSeen": today, "missed": 0})
        elif seen is False and dst in routes:
            routes[dst]["missed"] = int(routes[dst].get("missed", 0)) + 1
            if routes[dst]["missed"] >= MISS_LIMIT:
                removed.append(dst)
                del routes[dst]
    state["updatedAt"] = today
    return {"added": added, "removed": removed}


def is_new(entry: Dict[str, Any], today: str) -> bool:
    try:
        d0 = datetime.date.fromisoformat(entry["addedOn"])
        return 0 <= (datetime.date.fromisoformat(today) - d0).days < NEW_DAYS
    except (KeyError, ValueError):
        return False


def new_route_record(dst: str, entry: Dict[str, Any], best: Optional[Dict[str, Any]], today: str,
                     published: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """그날 실제 조회한 김포 출발 최저 일정(best: 날짜 검색 후보)으로 1면용 기록을 만든다. 없으면 None(그날은 기사 없음)."""
    if not best or not best.get("price"):
        return None
    rec = {"date": today, "origin": "GMP", "dest": dst, "code": entry.get("code", ""), "city": entry.get("city", ""),
           "addedOn": entry.get("addedOn", today), "price": int(best["price"]),
           "depDate": str(best["dep"]), "retDate": str(best["ret"]), "nights": int(best["nights"]), "leaveDays": int(best.get("leave", 0))}
    # 그날 1위가 바로 이 김포 노선이면 항공편 정보도 함께(같은 날 상세 조회값)
    if published and published.get("origin") == "GMP" and published.get("dest") == dst and published.get("airline"):
        rec["airline"] = published["airline"]
        rec["googleUrl"] = published.get("googleUrl", "")
    return rec
