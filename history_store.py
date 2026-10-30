#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
전체 이력 저장소 (월별 CSV 파티션)

  data/history/YYYY-MM.csv   컬럼: date,code,price,source,dep,ret

- 노선·날짜당 1행(date+code)만 보관합니다. 같은 날 다시 실행하면 그 행을 덮어씁니다.
- 신뢰할 수 있는 관측값(source = live 또는 sheet)만 저장합니다.
  이월(carry)·기준가(base)는 실제 관측이 아니므로 저장하지 않습니다. (분석이 오염되지 않도록)
- 고정 메타데이터(도시명, 항공사, 수하물 등)는 저장하지 않습니다. 노선 마스터에서 가져옵니다.
  그래서 1년치가 약 1MB 안팎이며, 몇 년치를 쌓아도 저장소 부담이 거의 없습니다.
"""

import csv
import os
import re
from typing import Any, Dict, Iterable, Iterator, List, Tuple

HISTORY_DIR = os.path.join("data", "history")
FIELDS = ["date", "code", "price", "source", "dep", "ret"]
TRUSTED_SOURCES = ("live", "sheet")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CODE_RE = re.compile(r"^[A-Z]{3}$")


def month_path(ym: str) -> str:
    return os.path.join(HISTORY_DIR, f"{ym}.csv")


def months_available() -> List[str]:
    if not os.path.isdir(HISTORY_DIR):
        return []
    out = []
    for name in os.listdir(HISTORY_DIR):
        m = re.match(r"^(\d{4}-\d{2})\.csv$", name)
        if m:
            out.append(m.group(1))
    return sorted(out)


def read_month(ym: str) -> Dict[Tuple[str, str], Dict[str, Any]]:
    path = month_path(ym)
    rows: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8", newline="") as f:
        for rec in csv.DictReader(f):
            try:
                date, code = rec["date"], rec["code"]
                if not (_DATE_RE.match(date) and _CODE_RE.match(code)):
                    continue
                rows[(date, code)] = {
                    "date": date,
                    "code": code,
                    "price": int(rec["price"]),
                    "source": rec.get("source") or "",
                    "dep": rec.get("dep") or "",
                    "ret": rec.get("ret") or "",
                }
            except (KeyError, ValueError, TypeError):
                continue  # 깨진 줄은 건너뜀
    return rows


def write_month(ym: str, rows: Dict[Tuple[str, str], Dict[str, Any]]) -> None:
    os.makedirs(HISTORY_DIR, exist_ok=True)
    path = month_path(ym)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(FIELDS)
        for key in sorted(rows):
            r = rows[key]
            w.writerow([r["date"], r["code"], r["price"], r["source"], r["dep"], r["ret"]])
    os.replace(tmp, path)


def _clean(obs: Dict[str, Any]) -> Dict[str, Any]:
    """유효하고 신뢰할 수 있는 관측이면 정규화해서 반환, 아니면 None."""
    try:
        date, code = str(obs.get("date", "")), str(obs.get("code", ""))
        price = int(obs.get("price"))
        source = str(obs.get("source", ""))
    except (TypeError, ValueError):
        return None  # type: ignore[return-value]
    if not (_DATE_RE.match(date) and _CODE_RE.match(code)) or price <= 0:
        return None  # type: ignore[return-value]
    if source not in TRUSTED_SOURCES:
        return None  # type: ignore[return-value]
    return {"date": date, "code": code, "price": price, "source": source,
            "dep": str(obs.get("dep") or ""), "ret": str(obs.get("ret") or "")}


def upsert_observations(observations: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """
    관측값을 월별 CSV 에 반영합니다.
    반환: accepted(저장 대상으로 인정된 수), skipped(제외된 수), changed(실제로 새로 쓰거나 바뀐 수)
    """
    accepted = skipped = changed = 0
    by_month: Dict[str, List[Dict[str, Any]]] = {}
    for obs in observations:
        c = _clean(obs)
        if c is None:
            skipped += 1
            continue
        accepted += 1
        by_month.setdefault(c["date"][:7], []).append(c)

    for ym, items in by_month.items():
        rows = read_month(ym)
        dirty = False
        for c in items:
            key = (c["date"], c["code"])
            if rows.get(key) != c:
                rows[key] = c
                changed += 1
                dirty = True
        if dirty:
            write_month(ym, rows)
    return {"accepted": accepted, "skipped": skipped, "changed": changed}


def iter_all() -> Iterator[Dict[str, Any]]:
    for ym in months_available():
        rows = read_month(ym)
        for key in sorted(rows):
            yield rows[key]


_LABEL_RE = re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})[^~]*~\s*(\d{1,2})[.\-/](\d{1,2})")


def parse_label_dates(label: str) -> Tuple[str, str]:
    """'2026.11.13(금)~11.16(월) (3박 4일)' → ('2026-11-13', '2026-11-16'). 실패하면 ('', '')."""
    m = _LABEL_RE.search(str(label or ""))
    if not m:
        return "", ""
    y, mo, d, rm, rd = (int(x) for x in m.groups())
    try:
        import datetime
        dep = datetime.date(y, mo, d)
        ret = datetime.date(y, rm, rd)
        if ret < dep:
            ret = datetime.date(y + 1, rm, rd)
        return dep.isoformat(), ret.isoformat()
    except ValueError:
        return "", ""
