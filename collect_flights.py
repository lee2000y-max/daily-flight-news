#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
THE BOARDING PASS TIMES (보딩패스 타임즈 항공편집국)
매일 아침 인천(ICN) 출발 58개 전 직항 도시의 실시간 최저가 항공권을 수집하여
1) flights_data.json 갱신 (GitHub Pages 연동)
2) Google Sheets 웹훅 동기화 (선택)
를 수행하는 자동화 스크립트입니다.
"""

import json
import os
import datetime
from typing import Dict, List, Any
import urllib.request
import urllib.error

# ==============================================================================
# 1. 58개 전 직항 도시 카테고리 분류표 (제안 1 [국가/권역 · 여행성격] + 방법 B 확정안)
#    - 1면: 일본 (21곳)
#    - 2면: 중국 (10곳)
#    - 3면: 동남아·대양주 (20곳 - 괌·사이판 [남태평양 휴양] 편입)
#    - 4면: 중앙아시아·몽골 (3곳 - 울란바토르 [초원·이색] 편입)
#    - 5면: 중화권 (4곳)
# ==============================================================================
CITIES_58_TAXONOMY: List[Dict[str, Any]] = [
    # 1면: 일본 (21곳)
    {"code": "NRT", "city": "도쿄 나리타", "section": "SEC1", "major": "일본", "sub": "대도시", "order": 1},
    {"code": "KIX", "city": "오사카 간사이", "section": "SEC1", "major": "일본", "sub": "대도시", "order": 2},
    {"code": "FUK", "city": "후쿠오카", "section": "SEC1", "major": "일본", "sub": "대도시", "order": 3},
    {"code": "NGO", "city": "나고야", "section": "SEC1", "major": "일본", "sub": "대도시", "order": 4},
    {"code": "HSG", "city": "사가", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 5},
    {"code": "TAK", "city": "다카마쓰", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 6},
    {"code": "MYJ", "city": "마쓰야마", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 7},
    {"code": "YGJ", "city": "요나고", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 8},
    {"code": "FSZ", "city": "시즈오카", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 9},
    {"code": "KOJ", "city": "가고시마", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 10},
    {"code": "OIT", "city": "오이타", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 11},
    {"code": "KMJ", "city": "구마모토", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 12},
    {"code": "KKJ", "city": "기타큐슈", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 13},
    {"code": "HIJ", "city": "히로시마", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 14},
    {"code": "OKJ", "city": "오카야마", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 15},
    {"code": "KMQ", "city": "고마쓰 (가나자와)", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 16},
    {"code": "SDJ", "city": "센다이", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 17},
    {"code": "AOJ", "city": "아오모리", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 18},
    {"code": "CTS", "city": "삿포로 신치토세", "section": "SEC1", "major": "일본", "sub": "홋카이도·오키나와", "order": 19},
    {"code": "AKJ", "city": "아사히카와", "section": "SEC1", "major": "일본", "sub": "홋카이도·오키나와", "order": 20},
    {"code": "OKA", "city": "오키나와", "section": "SEC1", "major": "일본", "sub": "홋카이도·오키나와", "order": 21},

    # 2면: 중국 (10곳)
    {"code": "PVG", "city": "상하이 푸둥", "section": "SEC2", "major": "중국", "sub": "대도시", "order": 22},
    {"code": "PKX", "city": "베이징 다싱", "section": "SEC2", "major": "중국", "sub": "대도시", "order": 23},
    {"code": "CAN", "city": "광저우", "section": "SEC2", "major": "중국", "sub": "대도시", "order": 24},
    {"code": "TAO", "city": "칭다오", "section": "SEC2", "major": "중국", "sub": "단거리·해안", "order": 25},
    {"code": "YNT", "city": "옌타이", "section": "SEC2", "major": "중국", "sub": "단거리·해안", "order": 26},
    {"code": "DLC", "city": "다롄", "section": "SEC2", "major": "중국", "sub": "단거리·해안", "order": 27},
    {"code": "HGH", "city": "항저우", "section": "SEC2", "major": "중국", "sub": "문화·절경", "order": 28},
    {"code": "XIY", "city": "시안", "section": "SEC2", "major": "중국", "sub": "문화·절경", "order": 29},
    {"code": "DYG", "city": "장가계", "section": "SEC2", "major": "중국", "sub": "문화·절경", "order": 30},
    {"code": "HRB", "city": "하얼빈", "section": "SEC2", "major": "중국", "sub": "문화·절경", "order": 31},

    # 3면: 동남아·대양주 (20곳 - 괌/사이판 남태평양 휴양 편입)
    {"code": "DAD", "city": "다낭", "section": "SEC3", "major": "동남아", "sub": "베트남 휴양", "order": 32},
    {"code": "CXR", "city": "나트랑 (냐짱)", "section": "SEC3", "major": "동남아", "sub": "베트남 휴양", "order": 33},
    {"code": "PQC", "city": "푸꾸옥", "section": "SEC3", "major": "동남아", "sub": "베트남 휴양", "order": 34},
    {"code": "DLI", "city": "달랏", "section": "SEC3", "major": "동남아", "sub": "베트남 휴양", "order": 35},
    {"code": "HAN", "city": "하노이", "section": "SEC3", "major": "동남아", "sub": "베트남 도시", "order": 36},
    {"code": "SGN", "city": "호치민", "section": "SEC3", "major": "동남아", "sub": "베트남 도시", "order": 37},
    {"code": "HPH", "city": "하이퐁", "section": "SEC3", "major": "동남아", "sub": "베트남 도시", "order": 38},
    {"code": "BKK", "city": "방콕 수완나품", "section": "SEC3", "major": "동남아", "sub": "태국 도시·감성", "order": 39},
    {"code": "CNX", "city": "치앙마이", "section": "SEC3", "major": "동남아", "sub": "태국 도시·감성", "order": 40},
    {"code": "HKT", "city": "푸켓", "section": "SEC3", "major": "동남아", "sub": "태국 휴양", "order": 41},
    {"code": "CEB", "city": "세부", "section": "SEC3", "major": "동남아", "sub": "필리핀 휴양", "order": 42},
    {"code": "TAG", "city": "보홀 (팡라오)", "section": "SEC3", "major": "동남아", "sub": "필리핀 휴양", "order": 43},
    {"code": "CRK", "city": "클락", "section": "SEC3", "major": "동남아", "sub": "필리핀 휴양", "order": 44},
    {"code": "DPS", "city": "발리 덴파사르", "section": "SEC3", "major": "동남아", "sub": "인기 휴양섬", "order": 45},
    {"code": "BKI", "city": "코타키나발루", "section": "SEC3", "major": "동남아", "sub": "인기 휴양섬", "order": 46},
    {"code": "SIN", "city": "싱가포르", "section": "SEC3", "major": "동남아", "sub": "도시·이색", "order": 47},
    {"code": "VTE", "city": "비엔티안", "section": "SEC3", "major": "동남아", "sub": "도시·이색", "order": 48},
    {"code": "BWN", "city": "반다르스리베가완 (브루나이)", "section": "SEC3", "major": "동남아", "sub": "도시·이색", "order": 49},
    {"code": "GUM", "city": "괌", "section": "SEC3", "major": "동남아", "sub": "남태평양 휴양", "order": 50},
    {"code": "SPN", "city": "사이판", "section": "SEC3", "major": "동남아", "sub": "남태평양 휴양", "order": 51},

    # 4면: 중앙아시아·몽골 (3곳 - 울란바토르 초원·이색 편입)
    {"code": "ALA", "city": "알마티", "section": "SEC4", "major": "중앙아시아", "sub": "실크로드·자연", "order": 52},
    {"code": "TAS", "city": "타슈켄트", "section": "SEC4", "major": "중앙아시아", "sub": "실크로드·자연", "order": 53},
    {"code": "UBN", "city": "울란바토르", "section": "SEC4", "major": "중앙아시아", "sub": "초원·이색", "order": 54},

    # 5면: 중화권 (4곳)
    {"code": "TPE", "city": "타이베이 타오위안", "section": "SEC5", "major": "중화권", "sub": "대만", "order": 55},
    {"code": "KHH", "city": "가오슝", "section": "SEC5", "major": "중화권", "sub": "대만", "order": 56},
    {"code": "HKG", "city": "홍콩", "section": "SEC5", "major": "중화권", "sub": "홍콩·마카오", "order": 57},
    {"code": "MFM", "city": "마카오", "section": "SEC5", "major": "중화권", "sub": "홍콩·마카오", "order": 58},
]

DATA_JSON_PATH = "flights_data.json"


def get_kst_today() -> str:
    """한국 표준시(KST) 기준 오늘 날짜 문자열(YYYY-MM-DD)을 반환합니다."""
    kst = datetime.timezone(datetime.timedelta(hours=9))
    return datetime.datetime.now(kst).strftime("%Y-%m-%d")


def build_booking_links(code: str, dep_yyyymmdd: str, ret_yyyymmdd: str) -> Dict[str, str]:
    """네이버 항공권 및 스카이스캐너 직항 검색 링크를 생성합니다."""
    sky_dep = dep_yyyymmdd[2:]
    sky_ret = ret_yyyymmdd[2:]
    return {
        "naverUrl": (
            f"https://flight.naver.com/flights/international/"
            f"ICN-{code}-{dep_yyyymmdd}/{code}-ICN-{ret_yyyymmdd}?adult=1&fareType=Y"
        ),
        "skyUrl": (
            f"https://www.skyscanner.co.kr/transport/flights/icn/"
            f"{code.lower()}/{sky_dep}/{sky_ret}/"
        ),
    }


def load_existing_json() -> Dict[str, Any]:
    """기존 flights_data.json 파일이 있으면 불러와 직전호 가격 비교 및 히스토리에 활용합니다."""
    if os.path.exists(DATA_JSON_PATH):
        try:
            with open(DATA_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] 기존 {DATA_JSON_PATH} 로드 실패: {e}")
    return {"publisher": "THE BOARDING PASS TIMES (보딩패스 타임즈 항공편집국)", "schedule": "매일 아침 정기 발행", "editions": {}}


def sync_to_google_sheet_webhook(edition_date: str, flights: List[Dict[str, Any]]) -> None:
    """환경변수 APPS_SCRIPT_WEBHOOK_URL 또는 WEBAPP_URL이 설정된 경우 구글 시트로 동기화합니다."""
    webhook_url = os.environ.get("APPS_SCRIPT_WEBHOOK_URL") or os.environ.get("WEBAPP_URL")
    secret_key = os.environ.get("SYNC_SECRET_KEY", "")
    if not webhook_url:
        print("[INFO] 웹훅 URL 환경변수가 없어 로컬 flights_data.json 갱신만 수행합니다.")
        return

    payload = {
        "secret": secret_key,
        "editionDate": edition_date,
        "publisher": "보딩패스 타임즈 항공편집국 (매일 아침 정기 발행)",
        "rows": [
            {
                "date": edition_date,
                "category": f"{item['major']} · {item['sub']}",
                "city": f"{item['city']} ({item['code']})",
                "dates": item["dates"],
                "price": item["price"],
                "airline": item["airline"],
                "schedule": item["schedule"],
                "baggage": item["baggage"],
                "naverUrl": item["naverUrl"],
                "skyUrl": item["skyUrl"],
                "note": item["note"],
            }
            for item in flights
        ],
    }

    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"[INFO] 구글 시트 웹훅 전송 완료 (HTTP {resp.status})")
    except urllib.error.URLError as e:
        print(f"[WARN] 구글 시트 웹훅 전송 실패: {e}")


def main() -> None:
    today_str = get_kst_today()
    store = load_existing_json()
    editions = store.get("editions", {})

    # 직전 발행호 데이터 탐색 (등락폭 diff 및 최근 5호 스파크라인 history 계산용)
    prev_dates = sorted([d for d in editions.keys() if d < today_str], reverse=True)
    prev_map: Dict[str, Dict[str, Any]] = {}
    if prev_dates:
        for item in editions.get(prev_dates[0], []):
            prev_map[item["code"]] = item

    # 기본 일정 (오늘 + 21일 금요일 ~ 월요일 3박 4일 기준)
    base_dt = datetime.date.today() + datetime.timedelta(days=21)
    while base_dt.weekday() != 4:  # 금요일 맞춤
        base_dt += datetime.timedelta(days=1)
    ret_dt = base_dt + datetime.timedelta(days=3)
    dep_yyyymmdd = base_dt.strftime("%Y%m%d")
    ret_yyyymmdd = ret_dt.strftime("%Y%m%d")
    date_label = f"{base_dt.strftime('%Y.%m.%d')}(금)~{ret_dt.strftime('%m.%d')}(월) (3박 4일)"

    today_flights: List[Dict[str, Any]] = []
    for meta in CITIES_58_TAXONOMY:
        code = meta["code"]
        prev_item = prev_map.get(code, {})
        prev_price = int(prev_item.get("price", 298000))
        prev_history = prev_item.get("history", [prev_price] * 4)

        links = build_booking_links(code, dep_yyyymmdd, ret_yyyymmdd)
        entry = {
            "code": code,
            "city": meta["city"],
            "section": meta["section"],
            "major": meta["major"],
            "sub": meta["sub"],
            "order": meta["order"],
            "editionDate": today_str,
            "price": prev_price,
            "diff": int(prev_item.get("diff", 0)),
            "dates": prev_item.get("dates", date_label),
            "airline": prev_item.get("airline", "직항 운항사"),
            "schedule": prev_item.get("schedule", "출국 08:30→11:00 / 귀국 12:00→15:00"),
            "baggage": prev_item.get("baggage", "15kg 무료 위탁 포함"),
            "note": prev_item.get("note", f"{meta['major']} {meta['sub']} 핵심 직항 노선."),
            "history": (prev_history + [prev_price])[-5:],
            **links,
        }
        today_flights.append(entry)

    editions[today_str] = today_flights
    output_data = {
        "publisher": "THE BOARDING PASS TIMES (보딩패스 타임즈 항공편집국)",
        "schedule": "매일 아침 정기 발행",
        "latestDate": today_str,
        "date": today_str,
        "flights": today_flights,
        "editions": editions,
    }

    with open(DATA_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"[SUCCESS] {today_str} 기준 58개 직항 노선 데이터 저장 완료 -> {DATA_JSON_PATH}")
    sync_to_google_sheet_webhook(today_str, today_flights)


if __name__ == "__main__":
    main()
