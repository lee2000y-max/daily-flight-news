#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
기존 데이터를 전체 이력 저장소(data/history)로 옮깁니다. (한 번만 실행)

  python migrate_history.py --json flights_data.json
  python migrate_history.py --sheet-csv 항공권_시트.csv --json flights_data.json

--sheet-csv : 구글 시트 [파일 > 다운로드 > CSV]. 열 순서는 Code.gs 기준
              (기준일, 구분, 도시(공항코드), 일정, 최저가, 항공사, 출도착, 수하물, 네이버, 스카이, 키워드, 노트)
--json      : 현재 flights_data.json
--cutoff    : 이 날짜 '이전'(미포함) 데이터만 옮깁니다. 기본 2026-10-29.
              (그 이후는 실조회가 아닌 고정 기준가가 기록된 구간이라 이력으로 쓰면 안 됨. 'none' 이면 제한 없음)
같은 (날짜, 노선)이 여러 번 나오면 시트 CSV 를 우선하고, 시트 안에서 중복이면 최저가를 씁니다.
옮겨진 행의 source 는 'sheet' 입니다.
"""

import argparse
import csv
import json
import re
from typing import Any, Dict, List, Optional

import build_reports
import history_store as hs


def _norm_date(s: str) -> str:
    m = re.match(r"^\s*(\d{4})[-./](\d{1,2})[-./](\d{1,2})", str(s or ""))
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""


def _code(city: str) -> str:
    m = re.search(r"\(([A-Z]{3})\)", str(city or ""))
    return m.group(1) if m else ""


def from_sheet_csv(path: str) -> List[Dict[str, Any]]:
    best: Dict[tuple, Dict[str, Any]] = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 5:
                continue
            date, code = _norm_date(row[0]), _code(row[2])
            digits = re.sub(r"[^\d]", "", row[4])
            if not date or not code or not digits:
                continue          # 헤더/빈 줄
            price = int(digits)
            dep, ret = hs.parse_label_dates(row[3])
            obs = {"date": date, "code": code, "price": price, "source": "sheet", "dep": dep, "ret": ret}
            key = (date, code)
            if key not in best or price < best[key]["price"]:
                best[key] = obs
    return list(best.values())


def from_json(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for r in data.get("flights", []):
        code = r.get("code") or _code(r.get("city", ""))
        dep = r.get("depDate") or ""
        ret = r.get("retDate") or ""
        if not dep:
            dep, ret = hs.parse_label_dates(r.get("dates") or r.get("schedule") or "")
        out.append({"date": _norm_date(r.get("date", "")), "code": code, "price": r.get("price"),
                    "source": "sheet", "dep": dep, "ret": ret})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--sheet-csv")
    ap.add_argument("--cutoff", default="2026-10-29")
    args = ap.parse_args()
    if not (args.json or args.sheet_csv):
        ap.error("--json 또는 --sheet-csv 중 하나는 필요합니다.")
    cutoff: Optional[str] = None if args.cutoff.lower() == "none" else args.cutoff

    merged: Dict[tuple, Dict[str, Any]] = {}
    for loader, path in ((from_sheet_csv, args.sheet_csv), (from_json, args.json)):
        if not path:
            continue
        items = loader(path)
        kept = 0
        for o in items:
            if cutoff and o["date"] >= cutoff:
                continue
            merged.setdefault((o["date"], o["code"]), o)   # 먼저 들어온(시트 CSV) 값 우선
            kept += 1
        print(f"읽음 {path}: {len(items)}행 중 컷오프 이전 {kept}행")

    res = hs.upsert_observations(merged.values())
    print(f"이력 저장소 반영: 인정 {res['accepted']} / 제외 {res['skipped']} / 변경 {res['changed']}")
    from build_reports import _load_meta
    print("리포트 생성:", ", ".join(build_reports.rebuild_all(_load_meta())) or "(없음)")


if __name__ == "__main__":
    main()
