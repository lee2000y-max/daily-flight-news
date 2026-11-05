#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
현지 메모·제철 '초안' 만들기(수동 실행 전용, 진단 워크플로 mode=drafts). 2026-11-05 사용자 결정.

화면에 바로 싣지 않는다. 결과(data/drafts.json)는 preview/drafts 브랜치에만 올리고,
사용자가 확인·수정·승인한 것만 routes.py(note, BEST_SEASONS)에 사람이 옮긴다.

도시마다:
  1) 근거 모으기: 월 기후 평년값(data/climate_normals.json) + 네이버 검색 API(백과·블로그) 상위 결과 제목·요약·주소
  2) Gemini(REST, JSON 응답)로 초안: 현지 메모 1문장(60자 안팎), 여행 적기 1~2개(출발월·짧은 이유)
  3) 근거 주소를 초안과 함께 저장(검토용)

규칙: 가격·운임·항공사·편명은 쓰지 않는다(절대 규칙 1, 날마다 바뀌는 값). 키는 GitHub Secrets(GEMINI_API_KEY,
NAVER_CLIENT_ID·NAVER_CLIENT_SECRET)에서만 읽고 출력하지 않는다. 네이버 키가 없으면 기후 근거만으로 만든다.

  python build_drafts.py new        # note가 빈 도시 전부(워크플로 route=new)
  python build_drafts.py UKB HKD    # 지정 도시만
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import routes

OUT = "data/drafts.json"
MODELS = [m for m in [os.environ.get("GEMINI_MODEL", "").strip(), "gemini-2.5-flash", "gemini-flash-latest"] if m]
GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
NAVER = "https://openapi.naver.com/v1/search/{}.json?"

EXAMPLES = [
    ("오사카", "간사이공항 귀국 수속 혼잡을 감안해 출발 2시간 30분 전 공항 도착 권장"),
    ("세부", "출발 72시간 이내 필리핀 이트래블(eTravel) 무료 QR코드 발급 필수 (유료 대행 사이트 주의)"),
    ("달랏", "해발 1,500m 고원 도시로 연중 봄 날씨이나 야간 기온이 12~15도로 내려가므로 긴팔 가디건 필수"),
    ("타슈켄트", "30일 무비자 입국 가능, 사마르칸트 고속열차(아프로시압) 사전 예매 및 호텔 거주등록증 출국 시까지 보관 필수"),
]


def strip(s):
    return re.sub(r"<[^>]+>", "", s or "").replace("&quot;", '"').replace("&amp;", "&").strip()


NAVER_OFF = False


def naver(kind, query, n=4):
    global NAVER_OFF
    cid, sec = os.environ.get("NAVER_CLIENT_ID", ""), os.environ.get("NAVER_CLIENT_SECRET", "")
    if not (cid and sec) or NAVER_OFF:
        return []
    req = urllib.request.Request(NAVER.format(kind) + urllib.parse.urlencode({"query": query, "display": n}),
                                 headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": sec})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            items = json.load(r).get("items", [])
    except Exception as e:
        body = ""
        try:
            body = json.loads(e.read().decode()).get("errorMessage", "")[:80]   # 키 값은 응답에 없음
        except Exception:
            pass
        print(f"   ! 네이버 {kind} '{query}': {type(e).__name__} {getattr(e, 'code', '')} {body}")
        if getattr(e, "code", None) in (401, 403):
            NAVER_OFF = True
            print("   ! 네이버 키 인증 실패: 이번 실행에서는 네이버 근거 없이 진행")
        return []
    return [{"kind": kind, "title": strip(i.get("title")), "desc": strip(i.get("description"))[:220], "link": i.get("link", "")} for i in items]


def gemini(prompt):
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise SystemExit("GEMINI_API_KEY 없음")
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"}}).encode()
    errs = []
    for model in MODELS:
        for attempt in range(3):
            req = urllib.request.Request(GEMINI.format(model), data=body,
                                         headers={"Content-Type": "application/json", "x-goog-api-key": key})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    d = json.load(r)
                text = d["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text), model
            except Exception as e:
                code = getattr(e, "code", None)
                errs.append(f"{model}: {type(e).__name__} {str(e)[:80]}")
                if code in (400, 401, 402, 403, 404):
                    break   # 키·결제·모델 문제는 다시 시도해도 같음
                time.sleep(3 + 5 * attempt)
    raise RuntimeError(" | ".join(errs))


def climate_line(clim, code):
    c = (clim.get("cities") or {}).get(code)
    if not c:
        return "기후 자료 없음"
    t, p = c.get("tmean") or [], c.get("precipMm") or []
    return " / ".join(f"{i + 1}월 {t[i]:.0f}℃ {p[i]:.0f}mm" for i in range(min(12, len(t), len(p))))


def main():
    only = {a.upper() for a in sys.argv[1:]} - {"NEW"}   # "new" = 메모가 빈 도시 전부(워크플로 route 기본값을 피하려고)
    clim = json.load(open("data/climate_normals.json", encoding="utf-8")) if os.path.exists("data/climate_normals.json") else {}
    out = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {"cities": {}}
    done = set(out.get("cities", {}))
    # 지정 도시는 다시 만들고, 'new'는 이미 만든 초안을 건너뜀(시간 제한으로 끊겨도 이어서)
    targets = [m for m in routes.CITY_MASTER if (m["code"] in only) or (not only and not m.get("note") and m["code"] not in done)]
    print(f"초안 대상 {len(targets)}곳 · 네이버 근거 {'사용' if os.environ.get('NAVER_CLIENT_ID') else '없음'}")
    for i, m in enumerate(targets, 1):
        code, city = m["code"], m["city"]
        refs = naver("encyc", f"{city} 여행") + naver("blog", f"{city} 여행 주의사항", 5) + naver("blog", f"{city} 여행 날씨 추천 시기", 3)
        ref_txt = "\n".join(f"- [{r['kind']}] {r['title']}: {r['desc']}" for r in refs) or "(검색 결과 없음)"
        ex = "\n".join(f"- {c}: {n}" for c, n in EXAMPLES)
        prompt = f"""한국인 여행자를 위한 항공권 신문의 도시 카드에 들어갈 문구 초안을 만든다. 사람이 검토한 뒤 싣는다.
도시: {city} ({code}, {m['major']}{(' · ' + m['sub']) if m['sub'] else ''}, 도착 공항 {', '.join(m['airports'])})
월 평년 기후(NASA POWER): {climate_line(clim, code)}
참고 검색 결과(네이버, 정확하지 않을 수 있음):
{ref_txt}

규칙
- note: 한국어 1문장, 40~65자. 공항 이동·입국 절차·기후 대비·현지 교통처럼 실제로 쓸모 있는 안내 하나. 기존 예시와 같은 말투(명사형 종결).
- 가격·운임·항공사·편명·특정 업체 이름은 쓰지 않는다. 비자·입국 규정은 바뀔 수 있으니 확실하지 않으면 쓰지 말고, 쓰면 '출발 전 확인'을 붙인다.
- seasons: 여행 적기 1~2개. months는 출발월 정수 배열(1~12), label은 6자 이내 짧은 이유(예: 벚꽃, 건기, 단풍, 선선한 가을), why는 기후 자료에 근거한 한 줄.
- 근거가 약하면 confidence를 low로.
기존 메모 예시:
{ex}

JSON만 출력: {{"note": "...", "seasons": [{{"months": [3,4], "label": "...", "why": "..."}}], "confidence": "high|medium|low", "noteBasis": "메모 근거 한 줄"}}"""
        try:
            d, model = gemini(prompt)
        except Exception as e:
            print(f" ✗ [{i}/{len(targets)}] {city}: {e}")
            continue
        out["cities"][code] = {"city": city, "note": str(d.get("note", "")).strip(), "seasons": d.get("seasons") or [],
                               "confidence": d.get("confidence", ""), "noteBasis": d.get("noteBasis", ""),
                               "refs": [{"title": r["title"], "link": r["link"]} for r in refs if r["link"]][:8], "model": model}
        print(f" ✓ [{i}/{len(targets)}] {city}: {out['cities'][code]['note']} | " +
              ", ".join(f"{s.get('months')} {s.get('label')}" for s in out["cities"][code]["seasons"]))
        save(out)   # 도시마다 저장(작업 시간 제한에 걸려도 만든 것까지는 남김)
        time.sleep(1.0)
    save(out)
    print(f"저장: {OUT} ({len(out['cities'])}곳)")


def save(out):
    out["generatedAt"] = time.strftime("%Y-%m-%d %H:%M")
    os.makedirs("data", exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
