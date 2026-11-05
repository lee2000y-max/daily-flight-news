#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fli 0.9.0 공항 목록 보정(워크플로 'Patch fli airport aliases' 단계에서 실행).

1. 영문 이름이 같은 공항이 하나로 합쳐지는 문제: 오키나와 OKA("Naha Airport")가 인도네시아 NAH로 바뀜
   → OKA 이름을 "Naha Airport (Okinawa)"로 바꿔 따로 둔다.
2. 목록에 없는 공항: 비슈케크 FRU(마나스 국제공항)를 넣는다.
   fli는 요청에 공항 코드(이름 아님)를 보내므로 코드만 맞으면 조회된다.

그 뒤 routes.py의 모든 공항을 점검해 출력한다.
- 목록에 없거나 다른 공항으로 바뀌는 코드는 수집기가 그 공항만 빼고 조회한다
  (도시의 공항이 모두 그렇다면 그 도시는 failed "수집 도구가 공항 코드를 지원하지 않음(코드)").
  묶음 전체를 멈추지 않으려고 여기서는 실패로 끝내지 않는다.
- 단, 보정 1이 적용되지 않았으면(fli 파일 형식이 바뀐 경우) 실패로 끝내 바로 알 수 있게 한다.
"""
import re
import sys

import fli.models.airport as mod

F = mod.__file__
src = open(F, encoding="utf-8").read()
orig = src
src = src.replace('"OKA": "Naha Airport",', '"OKA": "Naha Airport (Okinawa)",')
ADD = {"FRU": "Manas International Airport (Bishkek)"}
for code, name in ADD.items():
    if f'"{code}":' not in src:
        m = re.search(r'^(\s*)"FUK": "Fukuoka Airport",\n', src, re.M)
        if m:
            src = src[:m.end()] + f'{m.group(1)}"{code}": "{name}",\n' + src[m.end():]
if src != orig:
    open(F, "w", encoding="utf-8").write(src)

# 새 프로세스처럼 다시 읽기
import importlib  # noqa: E402

importlib.reload(mod)
Airport = mod.Airport

sys.path.insert(0, ".")
import routes  # noqa: E402

codes = set(routes.ORIGINS) | {a for c in routes.CITY_MASTER for a in c["airports"]}
missing, merged = [], []
for c in sorted(codes):
    try:
        n = Airport[c].name
    except KeyError:
        missing.append(c)
        continue
    if n != c:
        merged.append((c, n))
print(f"공항 코드 확인: {len(codes)}개, 목록에 없음 {missing or '없음'}, 다른 공항으로 바뀜 {merged or '없음'}")
if missing or merged:
    print("⚠️ 위 공항은 수집에서 빠집니다(도시의 공항이 모두 해당하면 그 도시는 미발행·사유 기록)")
if Airport["OKA"].name != "OKA":
    print("[오류] OKA 보정이 적용되지 않았습니다(fli 파일 형식 변경?). 오키나와가 인도네시아로 조회될 수 있어 중단합니다.")
    sys.exit(1)
