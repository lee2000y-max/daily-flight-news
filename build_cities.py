#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
화면용 도시 표를 routes.py 하나에서 만든다(이중 관리 없애기, 2026-11-05).

  data/cities.json : {code: {city, section, major, sub, order}} — index.html 탭·배지·정렬
  js/common.js     : CITY_ISO2 줄(국기) — 모든 페이지 공용

routes.py를 고친 뒤 `python build_cities.py`를 실행해 함께 커밋한다.
check_site.py가 두 파일이 routes.py와 같은지 확인한다(`--check`).
"""
import json
import re
import sys

import routes

COMMON_JS = "js/common.js"
OUT = "data/cities.json"


def cities_json() -> str:
    d = {m["code"]: {k: m[k] for k in ("city", "section", "major", "sub", "order")} for m in routes.CITY_MASTER}
    return json.dumps(d, ensure_ascii=False, indent=1) + "\n"


def iso_line() -> str:
    return "  const CITY_ISO2 = " + json.dumps(routes.CITY_ISO2, ensure_ascii=False) + ";"


def common_js(src: str) -> str:
    out, n = re.subn(r"^  const CITY_ISO2 = \{.*\};$", lambda _: iso_line(), src, flags=re.M)
    assert n == 1, "js/common.js에서 CITY_ISO2 줄을 찾지 못함"
    return out


def main() -> int:
    check = "--check" in sys.argv
    want_json = cities_json()
    src = open(COMMON_JS, encoding="utf-8").read()
    want_js = common_js(src)
    try:
        have_json = open(OUT, encoding="utf-8").read()
    except FileNotFoundError:
        have_json = ""
    if check:
        bad = [p for p, a, b in ((OUT, have_json, want_json), (COMMON_JS, src, want_js)) if a != b]
        print("도시 표 일치" if not bad else f"routes.py와 다름: {bad} (python build_cities.py 실행 필요)")
        return 1 if bad else 0
    open(OUT, "w", encoding="utf-8").write(want_json)
    open(COMMON_JS, "w", encoding="utf-8").write(want_js)
    print(f"{OUT}·{COMMON_JS} 갱신: {len(routes.CITY_MASTER)}개 도시")
    return 0


if __name__ == "__main__":
    sys.exit(main())
