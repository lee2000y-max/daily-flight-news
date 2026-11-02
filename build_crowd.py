#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
한국인 쏠림 지수 만들기(수동 실행, 반기마다).

출처: 공공데이터포털 파일 데이터 15062056 「인천국제공항공사_항공사별 노선별 운송실적」(CSV, 키 없음, 이용 제한 없음)
  https://www.data.go.kr/data/15062056/fileData.do
  반기 갱신(7월: 당해 1~6월, 1월: 전년도 1~12월).

방법
  - 인천 출발(도착_출발=출발) 여객 운항의 유임승객 수를 도착 공항 → 도시로 묶어 월별로 더한다.
  - 도시의 '월별 출발 여객'을 그 달 전체 도시 중 순위로 5단계(1=가장 한적 … 5=가장 붐빔)로 나눈다(20%씩).
  - 김포 출발은 이 자료에 없다(인천공항 자료). 인천 출발 규모로 대표한다.
  - 여객 수에는 외국인도 포함된다(국적 구분 없음). '한국인 쏠림'의 근사치로 쓴다.
  - 자료의 '공항'은 IATA 코드, '월'은 "01월", '년도'는 "2026년" 형식(2026-11-03 확인).

네이버 데이터랩 검색어 트렌드(선택, 2026-11-03 추가)
  - GitHub Secrets NAVER_CLIENT_ID / NAVER_CLIENT_SECRET(네이버 클라우드 API HUB 또는 개발자센터 키)이 있으면 최근 8주 "○○ 여행·항공권" 검색량을 더한다.
  - 요청마다 기준 키워드(도쿄)를 함께 넣어 도시 간 비교가 되게 한다(요청당 도시 4개 + 기준 1개).
  - 호출 수: 실행 1번에 약 15회. 사용자가 정한 월 한도 30,000회(NAVER_MONTHLY_LIMIT)에 한참 못 미치게
    실행당 상한(NAVER_MAX_CALLS_PER_RUN=40)을 둔다. 주 1회 실행 기준 월 약 60회.
  - 최종 단계 = 인천공항 여객 순위와 검색량 순위의 평균을 5단계로 나눈 값. 키가 없으면 여객 수만 쓴다.

결과: data/crowd_index.json
  {"basis": "...", "period": "...", "months": {"1": {code: level}, ...}, "cities": {code: {"level": 연간 단계, "pax": 연간 여객}}}
"""
import csv
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from routes import CITY_MASTER

PAGE = "https://www.data.go.kr/data/15062056/fileData.do"
OUT = os.path.join("data", "crowd_index.json")
UA = {"User-Agent": "Mozilla/5.0 (compatible; boarding-pass-times/1.0; +https://lee2000y-max.github.io/daily-flight-news/)"}


def get(url: str, data: bytes = None, headers: dict = None, tries: int = 3) -> bytes:
    """요청 1회. 공공데이터포털은 가끔 응답이 늦어(2026-11-03 시간 초과) 연결 오류만 몇 번 다시 시도한다(HTTP 오류는 바로 올림)."""
    import time
    last = None
    for k in range(tries):
        req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError:
            raise
        except Exception as e:
            last = e
            time.sleep(5 * (k + 1))
    raise last


def download_csv() -> bytes:
    html = get(PAGE).decode("utf-8", "replace")
    # 페이지 안의 다운로드 정보(uddi, 파일 번호)를 찾는다
    uddi = re.findall(r"uddi:[0-9a-f\-]{20,}", html)
    atch = re.findall(r"FILE_\d{6,}", html)
    print("uddi 후보:", uddi[:3], "| 첨부 번호 후보:", atch[:3])
    tries = []
    if atch:
        tries.append(f"https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId={atch[0]}&fileDetailSn=1")
    if uddi:
        q = urllib.parse.urlencode({"publicDataPk": "15062056", "publicDataDetailPk": uddi[0], "fileDetailSn": "1"})
        try:
            meta = json.loads(get("https://www.data.go.kr/tcs/dss/selectFileDataDownload.do?" + q).decode("utf-8", "replace"))
            print("다운로드 메타:", {k: meta.get(k) for k in list(meta)[:8]})
            af = (meta.get("fileDataRegistVO") or {}).get("atchFileId") or meta.get("atchFileId")
            sn = (meta.get("fileDataRegistVO") or {}).get("fileDetailSn") or 1
            if af:
                tries.insert(0, f"https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId={af}&fileDetailSn={sn}")
        except Exception as e:
            print("다운로드 메타 실패:", type(e).__name__, str(e)[:200])
    for url in tries:
        try:
            body = get(url)
            print(f"받음 {len(body):,}바이트 ← {url}")
            if body[:2] == b"PK":
                z = zipfile.ZipFile(io.BytesIO(body))
                name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
                return z.read(name)
            if len(body) > 10000:
                return body
        except Exception as e:
            print("다운로드 실패:", url, type(e).__name__, str(e)[:200])
    snippet = re.findall(r"fileDownload[^\"']{0,200}|fn_fileData[^\"']{0,200}|download[^\"']{0,120}", html)[:10]
    print("페이지 속 다운로드 관련 조각:", snippet)
    raise RuntimeError("CSV를 받지 못함")


# 네이버 키는 두 종류가 있다. 사용자 키는 네이버 클라우드 'NAVER API HUB' 형식(Client ID 10자, 2026-11-03 확인)
NAVER_ENDPOINTS = [
    ("https://naverapihub.apigw.ntruss.com/search-trend/v1/search", "X-NCP-APIGW-API-KEY-ID", "X-NCP-APIGW-API-KEY"),
    ("https://openapi.naver.com/v1/datalab/search", "X-Naver-Client-Id", "X-Naver-Client-Secret"),   # 네이버 개발자센터 키
]
NAVER_MONTHLY_LIMIT = 30000        # 사용자 설정 월 한도(무료). 이 스크립트는 실행당 아래 상한만 쓴다
NAVER_MAX_CALLS_PER_RUN = 40
SHORT_NAME = {"BKK": "방콕", "CTS": "삿포로", "SIN": "싱가포르", "TAG": "보홀", "DPS": "발리", "BWN": "브루나이"}


def search_interest() -> dict:
    """{도시 코드: 기준(도쿄) 대비 최근 8주 검색량 비율}. 키가 없거나 실패하면 빈 값."""
    import datetime
    cid, sec = os.environ.get("NAVER_CLIENT_ID", ""), os.environ.get("NAVER_CLIENT_SECRET", "")
    if not cid or not sec:
        print("네이버 키 없음: 검색량 보정 생략")
        return {}
    end = datetime.date.today() - datetime.timedelta(days=1)
    start = end - datetime.timedelta(weeks=8)
    name = {c["code"]: SHORT_NAME.get(c["code"], c["city"].split()[0]) for c in CITY_MASTER}
    anchor = "NRT"
    others = [c for c in name if c != anchor]
    out, calls = {}, 0
    endpoint = None
    for i in range(0, len(others), 4):
        if calls >= NAVER_MAX_CALLS_PER_RUN:
            print(f"네이버 호출 상한({NAVER_MAX_CALLS_PER_RUN}회) 도달, 나머지 생략")
            break
        group = [anchor] + others[i:i + 4]
        body = json.dumps({
            "startDate": start.isoformat(), "endDate": end.isoformat(), "timeUnit": "week",
            "keywordGroups": [{"groupName": c, "keywords": [f"{name[c]} 여행", f"{name[c]} 항공권"]} for c in group],
        }).encode("utf-8")
        d = None
        for ep in ([endpoint] if endpoint else NAVER_ENDPOINTS):
            url, hid, hsec = ep
            try:
                calls += 1
                d = json.loads(get(url, data=body, headers={hid: cid, hsec: sec, "Content-Type": "application/json"}))
                if endpoint is None:
                    print(f"네이버 API: {url}")
                endpoint = ep
                break
            except Exception as e:
                print(f"네이버 요청 실패({url.split('/')[2]}): {type(e).__name__}: {str(e)[:160]}")
        if d is None:
            if endpoint is None and calls >= 4:
                print("네이버 인증이 두 방식 모두 실패 → 검색량 보정 생략")
                break
            continue
        avg = {}
        for res in d.get("results", []):
            vals = [x.get("ratio", 0) for x in res.get("data", [])]
            avg[res.get("title")] = sum(vals) / len(vals) if vals else 0
        base = avg.get(anchor) or 0
        if base <= 0:
            continue
        out[anchor] = 1.0
        for c in group[1:]:
            out[c] = round(avg.get(c, 0) / base, 4)
    print(f"네이버 검색량: {len(out)}개 도시, 호출 {calls}회(월 한도 {NAVER_MONTHLY_LIMIT:,}회)")
    return out


def pct_rank(values: dict) -> dict:
    ranked = sorted(values, key=lambda k: values[k])
    n = len(ranked)
    return {k: (i + 0.5) / n for i, k in enumerate(ranked)}


def decode(b: bytes) -> str:
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", "replace")


def main() -> int:
    text = decode(download_csv())
    rows = list(csv.DictReader(io.StringIO(text)))
    print("열:", list(rows[0].keys()) if rows else "없음", "| 행 수:", len(rows))
    for r in rows[:3]:
        print("  예:", r)
    if os.environ.get("CROWD_DISCOVER") == "1":
        airports = sorted({(r.get("공항") or "").strip() for r in rows})
        print("공항 값 예:", airports[:80])
        return 0

    # 도시 매핑: 자료의 '공항' 값이 IATA 코드인지 이름인지에 따라 맞춘다(첫 실행 로그로 확인 후 고정)
    code_of = {a: c["code"] for c in CITY_MASTER for a in c["airports"]}
    def city_of(r):
        a = (r.get("공항") or "").strip().upper()
        m = re.search(r"\b([A-Z]{3})\b", a)
        return code_of.get(m.group(1)) if m else None

    pax_m = {}   # (city, month) -> pax
    years = set()
    for r in rows:
        if "출발" not in (r.get("도착_출발") or "") or "여객" not in (r.get("여객_화물") or ""):
            continue
        city = city_of(r)
        if not city:
            continue
        try:
            n = int(float(str(r.get("유임승객(명)") or r.get("유임승객") or "0").replace(",", "").strip() or 0))
            mon = int(re.sub(r"\D", "", r.get("월") or ""))
            years.add(re.sub(r"\D", "", r.get("년도") or ""))
        except (TypeError, ValueError):
            continue
        pax_m[(city, mon)] = pax_m.get((city, mon), 0) + n
    if not pax_m:
        print("집계 0건: 열·값 형식을 확인할 것")
        return 1

    def levels(values: dict) -> dict:
        ranked = sorted(values, key=lambda k: values[k])
        n = len(ranked)
        return {k: min(5, 1 + (i * 5) // n) for i, k in enumerate(ranked)}

    search = search_interest()
    s_pct = pct_rank(search) if search else {}

    def blend(pax: dict) -> dict:
        """여객 순위와 검색량 순위의 평균(검색량이 없는 도시는 여객 순위만)."""
        p = pct_rank(pax)
        return {c: (p[c] + s_pct[c]) / 2 if c in s_pct else p[c] for c in p}

    months = {}
    for m in range(1, 13):
        vals = {c: p for (c, mm), p in pax_m.items() if mm == m}
        if vals:
            months[str(m)] = levels(blend(vals))
    total = {}
    for (c, _), p in pax_m.items():
        total[c] = total.get(c, 0) + p
    lv = levels(blend(total))
    cities = {c: {"level": lv[c], "pax": total[c], **({"search": search[c]} if c in search else {})} for c in total}
    missing = sorted({c["code"] for c in CITY_MASTER} - set(cities))
    print(f"도시 {len(cities)}개 집계, 자료에 없는 도시 {missing}")
    os.makedirs("data", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        basis = "인천공항 노선별 출발 여객(공공데이터 15062056)" + (" + 네이버 검색량(최근 8주)" if search else "")
        json.dump({"basis": basis, "period": "~".join(sorted(years)),
                   "months": months, "cities": cities}, f, ensure_ascii=False, indent=1)
    print("저장:", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
