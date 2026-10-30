#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
THE BOARDING PASS TIMES (보딩패스 타임즈 항공편집국)

매일 아침 인천(ICN) 출발 58개 직항 노선 데이터를 만들어 flights_data.json 으로 저장합니다.

동작 순서
1) 노선별 왕복 최저가 확보
   - fast-flights(구글 항공권 조회)가 설치되어 있으면 실제 조회를 시도합니다. (원화 ₩ 표기 + 직항만 인정)
   - 조회에 실패한 노선은 직전 발행호 가격을 이월(carry)하고, 이력이 없으면 마스터 기준가(base)를 씁니다.
   - 각 행의 priceSource 값: "live"(실조회) / "carry"(이월) / "base"(기준가)
2) (선택) Google Sheets 웹훅(Apps Script)으로 전송하고 시트 히스토리를 수신
3) (선택) ENABLE_GEMINI_NOTES=1 일 때만 Gemini 로 에디터 노트 보강
4) 직전 flights_data.json 과 합쳐 최근 HISTORY_DAYS일 이력, 전일 대비 등락(priceDiff), 가격 추이(historicalSeries)를 계산해 저장
"""

import json
import os
import re
import time
import datetime
from typing import Dict, List, Any, Optional
import urllib.request
import urllib.error

# ==============================================================================
# 1. 58개 전 직항 도시 마스터 목록 (제안 1 [국가/권역 · 여행성격] + 방법 B 확정안)
# ==============================================================================
CITIES_58_MASTER: List[Dict[str, Any]] = [
    # 1면: 일본 (21곳 - NGS 나가사키 포함)
    {"code": "KIX", "city": "오사카 간사이", "section": "SEC1", "major": "일본", "sub": "대도시", "order": 1, "base_price": 291400, "airline": "진에어 (LJ231/LJ232)", "timeSlot": "출국 07:55→09:40 / 귀국 11:00→13:00", "baggage": "15kg 무료 위탁 기본 포함", "note": "간사이공항 귀국 수속 혼잡을 감안해 출발 2시간 30분 전 공항 도착 권장"},
    {"code": "FUK", "city": "후쿠오카", "section": "SEC1", "major": "일본", "sub": "대도시", "order": 2, "base_price": 269400, "airline": "진에어 (LJ261/LJ262)", "timeSlot": "출국 07:15→08:40 / 귀국 09:50→11:15", "baggage": "15kg 무료 위탁 기본 포함", "note": "후쿠오카공항에서 하카타역까지 지하철 2정거장(5분)으로 도심 접근성 최고"},
    {"code": "NRT", "city": "도쿄 나리타", "section": "SEC1", "major": "일본", "sub": "대도시", "order": 3, "base_price": 304000, "airline": "제주항공 (7C1102/7C1101)", "timeSlot": "출국 06:00→08:25 / 귀국 11:50→14:30", "baggage": "FLYBAG 15kg 포함", "note": "도심 이동용 스카이라이너 또는 나리타 익스프레스(N'EX) 사전 예매 시 할인 혜택"},
    {"code": "CTS", "city": "삿포로 신치토세", "section": "SEC1", "major": "일본", "sub": "홋카이도·오키나와", "order": 4, "base_price": 354600, "airline": "진에어 (LJ301/LJ302)", "timeSlot": "출국 08:20→11:05 / 귀국 12:20→15:05", "baggage": "15kg 무료 위탁 기본 포함", "note": "동절기 설경 및 화이트 일루미네이션 시즌으로 방한 부츠·아이젠 준비 권장"},
    {"code": "NGO", "city": "나고야", "section": "SEC1", "major": "일본", "sub": "대도시", "order": 5, "base_price": 295600, "airline": "진에어 (LJ269/LJ270)", "timeSlot": "출국 07:35→09:30 / 귀국 18:25→20:35", "baggage": "15kg 무료 위탁 기본 포함", "note": "지브리 파크 및 나바나노사토 일루미네이션 방문 시 사전 예약 권장"},
    {"code": "OKA", "city": "오키나와", "section": "SEC1", "major": "일본", "sub": "홋카이도·오키나와", "order": 6, "base_price": 376200, "airline": "진에어 (LJ341/LJ342)", "timeSlot": "출국 09:45→12:15 / 귀국 13:00→15:30", "baggage": "15kg 무료 위탁 기본 포함", "note": "온화한 기후로 렌터카 해안 드라이브 및 츄라우미 수족관 관람에 최적"},
    {"code": "HSG", "city": "사가", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 7, "base_price": 210200, "airline": "티웨이항공 (TW295/TW296)", "timeSlot": "출국 07:45→09:10 / 귀국 10:10→11:40", "baggage": "스마트운임 15kg 포함 (특가 미포함)", "note": "우레시노·다케오 온천 및 후쿠오카 텐진 연계 리무진 버스 시간표 사전 확인 필수"},
    {"code": "TAK", "city": "다카마쓰", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 8, "base_price": 246800, "airline": "에어서울 (RS741/RS742)", "timeSlot": "출국 08:45→10:30 / 귀국 11:30→13:15", "baggage": "할인운임 15kg 포함 (특가 미포함)", "note": "나오시마·쇼도시마 세토내해 예술섬 페리 운항표 및 무료 공항 리무진 쿠폰 확인"},
    {"code": "FSZ", "city": "시즈오카", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 9, "base_price": 260800, "airline": "제주항공 (7C1601/7C1602)", "timeSlot": "출국 07:05→09:00 / 귀국 10:20→12:15", "baggage": "FLYBAG 15kg 포함 (FLY 미포함)", "note": "후지산 조망 희망 시 출국편 좌측 창가(A열), 귀국편 우측 창가(F열) 좌석 지정 권장"},
    {"code": "KOJ", "city": "가고시마", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 10, "base_price": 294400, "airline": "제주항공 (7C1821/7C1822)", "timeSlot": "출국 10:05→11:45 / 귀국 12:35→14:25", "baggage": "FLYBAG 15kg 포함 (FLY 미포함)", "note": "사쿠라지마 화산섬 페리 및 이부스키 검은 모래찜질 온천 이동 시 엔화 소액권 지참"},
    {"code": "OIT", "city": "오이타", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 11, "base_price": 319400, "airline": "제주항공 (7C1811/7C1812)", "timeSlot": "출국 10:00→11:45 / 귀국 12:50→14:35", "baggage": "FLYBAG 15kg 포함 (FLY 미포함)", "note": "벳푸·유후인 온천 직행 공항 리무진 버스 시간표 및 료칸 송영 서비스 사전 확인"},
    {"code": "YGJ", "city": "요나고", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 12, "base_price": 225000, "airline": "에어서울 (RS745/RS746)", "timeSlot": "출국 12:40→14:05 / 귀국 15:05→16:45", "baggage": "할인운임 15kg 포함 (특가 미포함)", "note": "돗토리 사구·미즈키 시게루 로드·마쓰에성 이동 시 산인 패스 활용 추천"},
    {"code": "KKJ", "city": "기타큐슈", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 13, "base_price": 298600, "airline": "진에어 (LJ367/LJ368)", "timeSlot": "출국 07:15→08:45 / 귀국 09:45→11:15", "baggage": "15kg 무료 위탁 기본 포함", "note": "고쿠라역까지 공항버스 35분, 모지코 레트로 및 시모노세키 가라토 시장 당일 코스 최적"},
    {"code": "SDJ", "city": "센다이", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 14, "base_price": 386600, "airline": "아시아나항공 (OZ152/OZ151)", "timeSlot": "출국 09:35→11:45 / 귀국 12:45→15:10", "baggage": "무료 위탁수하물 23kg 1개 포함 (FSC)", "note": "일본 3대 절경 마쓰시마 유람선 및 긴잔 온천·자오 수빙 연계 여행 추천"},
    {"code": "MYJ", "city": "마쓰야마", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 15, "base_price": 265200, "airline": "제주항공 (7C1701/7C1702)", "timeSlot": "출국 07:35→09:10 / 귀국 10:00→11:35", "baggage": "FLYBAG 15kg 포함", "note": "한국인 여행객 대상 마쓰야마 공항 무료 셔틀버스 및 도고온천 쿠폰북 수령 필수"},
    {"code": "HIJ", "city": "히로시마", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 16, "base_price": 269200, "airline": "제주항공 (7C1502/7C1501)", "timeSlot": "출국 07:45→09:30 / 귀국 10:30→12:20", "baggage": "FLYBAG 15kg 포함", "note": "미야지마 이쓰쿠시마 신사 해상 도리이 관람 시 만조·간조 시간표 사전 확인 권장"},
    {"code": "KMJ", "city": "구마모토", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 17, "base_price": 288800, "airline": "티웨이항공 (TW275/TW276)", "timeSlot": "출국 07:50→09:25 / 귀국 10:25→12:00", "baggage": "스마트운임 15kg 포함", "note": "아소산 화구 참관 가능 여부(화산가스 경보) 및 구로카와 온천 버스 사전 예약 필수"},
    {"code": "NGS", "city": "나가사키", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 18, "base_price": 304800, "airline": "대한항공 (KE797/KE798)", "timeSlot": "출국 08:00→09:30 / 귀국 10:40→12:20", "baggage": "무료 위탁수하물 23kg 포함 (FSC)", "note": "이나사야마 전망대 야경 및 하우스텐보스 테마파크 연계 이동 시 공항 페리 활용 추천"},
    {"code": "KMQ", "city": "코마쓰", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 19, "base_price": 350400, "airline": "대한항공 (KE775/KE776)", "timeSlot": "출국 07:55→09:40 / 귀국 10:50→12:50", "baggage": "무료 위탁수하물 23kg 포함 (FSC)", "note": "가나자와 겐로쿠엔 정원 및 시라카와고 합장촌 투어 이동에 가장 편리한 관문 공항"},
    {"code": "AOJ", "city": "아오모리", "section": "SEC1", "major": "일본", "sub": "소도시·온천", "order": 20, "base_price": 388400, "airline": "대한항공 (KE767/KE768)", "timeSlot": "출국 10:05→12:30 / 귀국 13:30→16:30", "baggage": "무료 위탁수하물 23kg 포함 (FSC)", "note": "오이라세 계류·도와다호 및 핫코다산 로프웨이 관람 시 JR 도호쿠 패스 연계 추천"},
    {"code": "AKJ", "city": "아사히카와", "section": "SEC1", "major": "일본", "sub": "홋카이도·오키나와", "order": 21, "base_price": 419000, "airline": "아시아나항공 (OZ158/OZ157)", "timeSlot": "출국 11:15→14:00 / 귀국 15:00→18:20", "baggage": "무료 위탁수하물 23kg 포함 (FSC)", "note": "비에이·후라노 설원 투어 및 아사히야마 동물원 펭귄 산책 관람 시 신치토세보다 이동 시간 대폭 단축"},

    # 3면: 동남아·대양주 (베트남 7곳)
    {"code": "DAD", "city": "다낭", "section": "SEC3", "major": "동남아", "sub": "베트남 휴양", "order": 22, "base_price": 216600, "airline": "에어서울 (RS511/RS512)", "timeSlot": "출국 20:20→23:05 / 귀국 00:05→06:40", "baggage": "할인운임 15kg 포함 (특가 미포함)", "note": "귀국편 자정 출발 스케줄로 마지막 날 마사지 샵 짐 보관 및 공항 샌딩 패키지 활용 추천"},
    {"code": "CXR", "city": "나트랑", "section": "SEC3", "major": "동남아", "sub": "베트남 휴양", "order": 23, "base_price": 211600, "airline": "에어서울 (RS525/RS526)", "timeSlot": "출국 20:10→23:20 / 귀국 00:20→07:15", "baggage": "할인운임 15kg 포함 (특가 미포함)", "note": "깜란 국제공항에서 나트랑 시내까지 차량 40분 소요되므로 심야 도착 픽업 차량 사전 예약 권장"},
    {"code": "PQC", "city": "푸꾸옥", "section": "SEC3", "major": "동남아", "sub": "베트남 휴양", "order": 24, "base_price": 296200, "airline": "비엣젯항공 (VJ975/VJ974)", "timeSlot": "출국 02:10→06:00 / 귀국 17:45→00:55(+1)", "baggage": "기내 7kg 포함 (위탁수하물 사전 추가 권장)", "note": "45일 무비자 입국 가능, 건기 해양 액티비티 최적기이며 새벽 도착 모닝 투어 활용 추천"},
    {"code": "HAN", "city": "하노이", "section": "SEC3", "major": "동남아", "sub": "베트남 도시", "order": 25, "base_price": 290200, "airline": "제주항공 (7C2801/7C2802)", "timeSlot": "출국 21:10→00:20(+1) / 귀국 01:45→07:55", "baggage": "FLYBAG 15kg 포함", "note": "11월~3월 하노이는 선선한 건기로 하롱베이 크루즈 및 닌빈 투어 최적기이나 얇은 외투 지참 권장"},
    {"code": "SGN", "city": "호치민", "section": "SEC3", "major": "동남아", "sub": "베트남 도시", "order": 26, "base_price": 322800, "airline": "비엣젯항공 (VJ863/VJ862)", "timeSlot": "출국 11:40→15:10 / 귀국 02:35→09:40", "baggage": "Eco 기내 7kg 포함 (사전 수하물 추가 권장)", "note": "떤선녓 국제공항 출국 심사 대기열이 매우 길어 귀국 시 최소 3시간 전 공항 도착 필수"},
    {"code": "HPH", "city": "하이퐁", "section": "SEC3", "major": "동남아", "sub": "베트남 도시", "order": 27, "base_price": 334800, "airline": "비엣젯항공 (VJ925/VJ926)", "timeSlot": "출국 07:15→10:40 / 귀국 23:55→06:15(+1)", "baggage": "Eco 기내 7kg 포함 (Deluxe 20kg 선택 권장)", "note": "하롱베이 선착장 및 깟바섬까지 고속도로로 45분 거리여서 북부 크루즈 여행 시 하노이보다 이동 편리"},
    {"code": "DLI", "city": "달랏", "section": "SEC3", "major": "동남아", "sub": "베트남 휴양", "order": 28, "base_price": 327400, "airline": "제주항공 (7C2903/7C2904)", "timeSlot": "출국 20:30→23:50 / 귀국 00:50→07:55", "baggage": "FLYBAG 15kg 포함", "note": "해발 1,500m 고원 도시로 연중 봄 날씨이나 야간 기온이 12~15도로 내려가므로 긴팔 가디건 필수"},

    # 5면: 중화권 (4곳)
    {"code": "TPE", "city": "타이베이 타오위안", "section": "SEC5", "major": "중화권", "sub": "대만", "order": 29, "base_price": 288400, "airline": "스쿠트항공 (TR897/TR896)", "timeSlot": "출국 22:30→00:15(+1) / 귀국 17:10→20:45", "baggage": "기내 10kg 포함 (FlyBag 20kg 선택 가능)", "note": "출국 1~7일 전 대만 관광청 온라인 여행지원금(Lucky Land) 추첨 신청 및 온라인 입국신고서 작성 필수"},
    {"code": "KHH", "city": "가오슝", "section": "SEC5", "major": "중화권", "sub": "대만", "order": 30, "base_price": 276000, "airline": "티웨이항공 (TW671/TW672)", "timeSlot": "출국 11:25→13:25 / 귀국 14:25→18:10", "baggage": "스마트운임 15kg 포함", "note": "겨울에도 20~25도의 따뜻한 날씨로 보얼예술특구·치진섬 자전거 여행 및 컨딩 당일치기 추천"},
    {"code": "HKG", "city": "홍콩", "section": "SEC5", "major": "중화권", "sub": "홍콩·마카오", "order": 31, "base_price": 274600, "airline": "홍콩익스프레스 (UO619/UO618)", "timeSlot": "출국 08:15→11:15 / 귀국 17:50→22:20", "baggage": "Lite 기내 7kg 포함 (위탁수하물 옵션 확인)", "note": "옥토퍼스 카드 모바일 앱 충전 및 공항철도(AEL) 그룹 티켓 사전 할인 예매 추천"},
    {"code": "MFM", "city": "마카오", "section": "SEC5", "major": "중화권", "sub": "홍콩·마카오", "order": 32, "base_price": 256600, "airline": "제주항공 (7C2001/7C2002)", "timeSlot": "출국 11:00→14:00 / 귀국 15:00→19:35", "baggage": "FLYBAG 15kg 포함", "note": "코타이 스트립 주요 호텔 무료 셔틀버스 운행 노선 및 홍콩 페리·강주아오 대교 버스 연계 확인"},

    # 2면: 중국 (10곳)
    {"code": "TAO", "city": "칭다오", "section": "SEC2", "major": "중국", "sub": "단거리·해안", "order": 33, "base_price": 205200, "airline": "진에어 (LJ725/LJ726)", "timeSlot": "출국 08:30→09:05 / 귀국 10:05→12:40", "baggage": "15kg 무료 위탁 기본 포함", "note": "비행시간 1시간 30분 초단거리 노선, 중국 무비자 입국 요건 및 알리페이 한국 카드 사전 연동 필수"},
    {"code": "PVG", "city": "상하이 푸둥", "section": "SEC2", "major": "중국", "sub": "대도시", "order": 34, "base_price": 263200, "airline": "중국동방항공 (MU5042/MU5041)", "timeSlot": "출국 08:55→10:05 / 귀국 17:45→20:45", "baggage": "무료 위탁수하물 23kg 포함 (FSC)", "note": "와이탄 야경 및 상하이 디즈니랜드 방문 시 공식 앱 사전 다운로드 및 여권 지참 필수"},
    {"code": "PKX", "city": "베이징 다싱", "section": "SEC2", "major": "중국", "sub": "대도시", "order": 35, "base_price": 283800, "airline": "중국남방항공 (CZ316/CZ315)", "timeSlot": "출국 11:25→12:35 / 귀국 15:30→18:25", "baggage": "무료 위탁수하물 23kg 포함 (FSC)", "note": "자금성(고궁박물원) 및 만리장성 입장권은 방문 7일 전 위챗 미니프로그램 사전 예약 필수"},
    {"code": "YNT", "city": "옌타이", "section": "SEC2", "major": "중국", "sub": "단거리·해안", "order": 36, "base_price": 177800, "airline": "진에어 (LJ741/LJ742)", "timeSlot": "출국 15:35→16:25 / 귀국 17:25→20:00", "baggage": "15kg 무료 위탁 기본 포함", "note": "비행시간 1시간 15분 최단거리 가성비 노선으로 장유 와이너리 및 펑라이각 관광 추천"},
    {"code": "DLC", "city": "다롄", "section": "SEC2", "major": "중국", "sub": "단거리·해안", "order": 37, "base_price": 207400, "airline": "중국남방항공 (CZ676/CZ675)", "timeSlot": "출국 12:00→12:15 / 귀국 08:45→11:00", "baggage": "무료 위탁수하물 23kg 포함 (FSC)", "note": "동방수성 베네치아 수로 및 성해광장 야경 명소로 짧은 주말 미식 여행에 최적"},
    {"code": "HGH", "city": "항저우", "section": "SEC2", "major": "중국", "sub": "문화·절경", "order": 38, "base_price": 288400, "airline": "중국동방항공 (MU5044/MU5043)", "timeSlot": "출국 12:55→14:15 / 귀국 08:40→11:55", "baggage": "무료 위탁수하물 23kg 포함 (FSC)", "note": "서호 유람선·송성가무쇼 및 우전 수향마을 1박 연계 코스로 인기가 높은 노선"},
    {"code": "XIY", "city": "시안", "section": "SEC2", "major": "중국", "sub": "문화·절경", "order": 39, "base_price": 415000, "airline": "아시아나항공 (OZ347/OZ348)", "timeSlot": "출국 21:40→00:45(+1) / 귀국 01:50→06:05", "baggage": "무료 위탁수하물 23kg 포함 (FSC)", "note": "진시황 병마용갱·화청지 장한가 공연 및 시안 성벽 야경 투어 사전 예약 권장"},
    {"code": "DYG", "city": "장가계", "section": "SEC2", "major": "중국", "sub": "문화·절경", "order": 40, "base_price": 398600, "airline": "에어서울 (RS811/RS812)", "timeSlot": "출국 12:25→15:20 / 귀국 16:20→20:30", "baggage": "할인운임 15kg 포함", "note": "천문산 케이블카·원가계 엘리베이터 대기 시간을 줄이기 위해 VIP 패스트트랙 티켓 사전 확인"},
    {"code": "CAN", "city": "광저우", "section": "SEC2", "major": "중국", "sub": "대도시", "order": 41, "base_price": 326600, "airline": "중국남방항공 (CZ338/CZ337)", "timeSlot": "출국 10:55→13:55 / 귀국 16:20→20:55", "baggage": "무료 위탁수하물 23kg 포함 (FSC)", "note": "겨울철 온화한 기후와 정통 딤섬 미식 여행, 주강 나이트 크루즈 코스로 추천"},
    {"code": "HRB", "city": "하얼빈", "section": "SEC2", "major": "중국", "sub": "문화·절경", "order": 42, "base_price": 325200, "airline": "아시아나항공 (OZ339/OZ340)", "timeSlot": "출국 12:40→14:00 / 귀국 15:05→18:20", "baggage": "무료 위탁수하물 23kg 포함 (FSC)", "note": "빙설대세계 축제 및 성 소피아 성당 관람 시 영하 25도 대비 발열 내의·방한 용품 철저히 준비"},

    # 3면: 동남아·대양주 (태국·필리핀·말레이·싱가포르·라오스·브루나이·괌·사이판·발리) & 4면: 중앙아시아·몽골
    {"code": "BKK", "city": "방콕 수완나품", "section": "SEC3", "major": "동남아", "sub": "태국 도시·감성", "order": 43, "base_price": 384200, "airline": "제주항공 (7C2201/7C2202)", "timeSlot": "출국 19:30→23:40 / 귀국 01:00→08:35", "baggage": "FLYBAG 15kg 포함", "note": "수완나품(BKK)과 돈므앙(DMK) 공항 코드 혼동 주의 및 심야 도착 그랩/볼트 픽업 위치 확인"},
    {"code": "CNX", "city": "치앙마이", "section": "SEC3", "major": "동남아", "sub": "태국 도시·감성", "order": 44, "base_price": 416800, "airline": "진에어 (LJ007/LJ008)", "timeSlot": "출국 18:00→22:30 / 귀국 23:40→06:50(+1)", "baggage": "15kg 무료 위탁 기본 포함", "note": "11월~2월 건기는 치앙마이 최고 성수기로 올드시티·님만해민 숙소 조기 예약 권장"},
    {"code": "HKT", "city": "푸켓", "section": "SEC3", "major": "동남아", "sub": "태국 휴양", "order": 45, "base_price": 420800, "airline": "진에어 (LJ023/LJ024)", "timeSlot": "출국 17:35→22:30 / 귀국 23:45→07:50(+1)", "baggage": "15kg 무료 위탁 기본 포함", "note": "건기 시즌 피피섬·시밀란섬 호핑투어 최적기이며 공항-빠통 비치 미니밴/택시 사전 예약 추천"},
    {"code": "CEB", "city": "세부", "section": "SEC3", "major": "동남아", "sub": "필리핀 휴양", "order": 46, "base_price": 240400, "airline": "진에어 (LJ025/LJ026)", "timeSlot": "출국 19:45→23:30 / 귀국 01:25→06:50", "baggage": "15kg 무료 위탁 기본 포함", "note": "출발 72시간 이내 필리핀 이트래블(eTravel) 무료 QR코드 발급 필수 (유료 대행 사이트 주의)"},
    {"code": "TAG", "city": "보홀 팡라오", "section": "SEC3", "major": "동남아", "sub": "필리핀 휴양", "order": 47, "base_price": 268400, "airline": "제주항공 (7C2455/7C2456)", "timeSlot": "출국 20:25→00:05(+1) / 귀국 01:05→06:45", "baggage": "FLYBAG 15kg 포함", "note": "발리카삭 거북이 스노클링 투어 사전 예약 및 필리핀 eTravel 입국 QR코드 사전 등록 필수"},
    {"code": "CRK", "city": "클락", "section": "SEC3", "major": "동남아", "sub": "필리핀 휴양", "order": 48, "base_price": 229000, "airline": "진에어 (LJ031/LJ032)", "timeSlot": "출국 21:15→00:20(+1) / 귀국 01:35→06:30", "baggage": "15kg 무료 위탁 기본 포함", "note": "피나투보 화산 지프 투어 및 푸닝 온천·골프 리조트 이동 시 클락 공항 공식 픽업 차량 이용 권장"},
    {"code": "BKI", "city": "코타키나발루", "section": "SEC3", "major": "동남아", "sub": "인기 휴양섬", "order": 49, "base_price": 307600, "airline": "진에어 (LJ061/LJ062)", "timeSlot": "출국 18:10→22:30 / 귀국 23:40→06:00(+1)", "baggage": "15kg 무료 위탁 기본 포함", "note": "입국 3일 전 말레이시아 디지털 입국카드(MDAC) 온라인 등록 필수, 탄중아루 선셋 및 반딧불 투어 추천"},
    {"code": "SIN", "city": "싱가포르 창이", "section": "SEC3", "major": "동남아", "sub": "도시·이색", "order": 50, "base_price": 376600, "airline": "티웨이항공 (TW171/TW172)", "timeSlot": "출국 19:00→00:45(+1) / 귀국 02:15→09:50", "baggage": "스마트운임 15kg 포함", "note": "입국 3일 전 싱가포르 전자입국신고서(SG Arrival Card) 작성 필수 및 창이공항 쥬얼 폭포 운영 시간 확인"},
    {"code": "UBN", "city": "울란바토르", "section": "SEC4", "major": "중앙아시아", "sub": "초원·이색", "order": 51, "base_price": 452200, "airline": "제주항공 (7C5203/7C5204)", "timeSlot": "출국 08:20→11:10 / 귀국 12:10→16:10", "baggage": "FLYBAG 15kg 포함 (FSC 23kg)", "note": "신월(그믐) 주간 달빛 없는 은하수 관측 최적기이나 야간 영하권 한파에 대비한 방한 장비 필수"},
    {"code": "ALA", "city": "알마티", "section": "SEC4", "major": "중앙아시아", "sub": "실크로드·자연", "order": 52, "base_price": 980200, "airline": "에어아스타나 (KC910/KC909)", "timeSlot": "출국 11:15→15:35 / 귀국 01:10→09:45", "baggage": "무료 위탁수하물 23kg 포함 (FSC)", "note": "대한민국 여권 30일 무비자 입국 가능, 톈산 산맥 침불락 스키 리조트 및 차른 캐니언 투어 추천"},
    {"code": "TAS", "city": "타슈켄트", "section": "SEC4", "major": "중앙아시아", "sub": "실크로드·자연", "order": 53, "base_price": 1194800, "airline": "대한항공 (KE941/KE942)", "timeSlot": "출국 15:55→19:40 / 귀국 21:10→07:25(+1)", "baggage": "무료 위탁수하물 23kg 포함 (FSC)", "note": "30일 무비자 입국 가능, 사마르칸트 고속열차(아프로시압) 사전 예매 및 호텔 거주등록증 출국 시까지 보관 필수"},
    {"code": "VTE", "city": "비엔티안", "section": "SEC3", "major": "동남아", "sub": "도시·이색", "order": 54, "base_price": 457800, "airline": "제주항공 (7C4303/7C4304)", "timeSlot": "출국 19:10→22:45 / 귀국 23:45→06:45(+1)", "baggage": "FLYBAG 15kg 포함", "note": "11월~2월 건기 진입으로 방비엥 블루라군·카약 및 루앙프라방 고속철도 여행 최적기"},
    {"code": "BWN", "city": "반다르스리베가완", "section": "SEC3", "major": "동남아", "sub": "도시·이색", "order": 55, "base_price": 677400, "airline": "로열브루나이항공 (BI652/BI651)", "timeSlot": "출국 11:50→16:35 / 귀국 02:05→08:35", "baggage": "무료 위탁수하물 20kg 포함 (FSC)", "note": "30일 무비자 입국 가능, 7성급 엠파이어 호텔 호캉스 추천 및 주류 반입 시 세관 신고 규정 확인"},
    {"code": "GUM", "city": "괌", "section": "SEC3", "major": "동남아", "sub": "남태평양 휴양", "order": 56, "base_price": 305400, "airline": "진에어 (LJ913/LJ914)", "timeSlot": "출국 09:15→14:45 / 귀국 16:00→19:55", "baggage": "무료 위탁수하물 23kg 1개 기본 포함", "note": "출발 72시간 전 괌 전자 세관신고서 및 G-CNMI ETA(또는 유효 ESTA) 사전 발급 필수"},
    {"code": "SPN", "city": "사이판", "section": "SEC3", "major": "동남아", "sub": "남태평양 휴양", "order": 57, "base_price": 329000, "airline": "제주항공 (7C3402/7C3401)", "timeSlot": "출국 10:10→15:35 / 귀국 16:40→20:30", "baggage": "FLYBAG 23kg 포함", "note": "마나가하섬 스노클링 및 그로토 투어 명소, 출발 전 G-CNMI ETA 사전 전자여행허가 등록 필수"},
    {"code": "DPS", "city": "발리 덴파사르", "section": "SEC3", "major": "동남아", "sub": "인기 휴양섬", "order": 58, "base_price": 537600, "airline": "제주항공 (7C5301/7C5302)", "timeSlot": "출국 15:40→21:50 / 귀국 23:05→07:10(+1)", "baggage": "FLYBAG 15kg 포함 (대한항공·가루다 23kg)", "note": "LCC 취항으로 발리 직항 운임 대폭 인하, 전자도착비자(e-VOA) 및 발리 관광세 온라인 사전 납부 권장"},
]

DATA_JSON_PATH = "flights_data.json"
HISTORY_DAYS = 14                 # flights_data.json 에 보관할 최근 발행일 수
LIVE_PRICE_BUDGET_SEC = 8 * 60    # 실조회에 쓸 최대 시간(초). 초과하면 나머지는 이월/기준가
LIVE_PRICE_DELAY_SEC = 1.0        # 실조회 사이 대기(차단 방지)
KST = datetime.timezone(datetime.timedelta(hours=9))


def get_kst_today() -> str:
    """한국 표준시(KST) 기준 오늘 날짜 문자열(YYYY-MM-DD)을 반환합니다."""
    return datetime.datetime.now(KST).strftime("%Y-%m-%d")


def build_schedule_window(idx: int) -> Dict[str, str]:
    """오늘 기준 2~4주 뒤 목/금/토 주말 포함 일정을 순환 생성합니다."""
    today = datetime.datetime.now(KST).date()

    base_friday = today + datetime.timedelta(days=14)
    while base_friday.weekday() != 4:
        base_friday += datetime.timedelta(days=1)

    pattern = idx % 3
    if pattern == 0:
        dep_dt = base_friday + datetime.timedelta(days=(idx % 2) * 7)
        ret_dt = dep_dt + datetime.timedelta(days=3)
        label = f"{dep_dt.strftime('%Y.%m.%d')}(금)~{ret_dt.strftime('%m.%d')}(월) (3박 4일)"
    elif pattern == 1:
        dep_dt = base_friday + datetime.timedelta(days=1 + (idx % 2) * 7)
        ret_dt = dep_dt + datetime.timedelta(days=3)
        label = f"{dep_dt.strftime('%Y.%m.%d')}(토)~{ret_dt.strftime('%m.%d')}(화) (3박 4일)"
    else:
        dep_dt = base_friday - datetime.timedelta(days=1) + datetime.timedelta(days=(idx % 2) * 7)
        ret_dt = dep_dt + datetime.timedelta(days=4)
        label = f"{dep_dt.strftime('%Y.%m.%d')}(목)~{ret_dt.strftime('%m.%d')}(월) (4박 5일)"

    return {
        "schedule": label,
        "dep_yyyymmdd": dep_dt.strftime("%Y%m%d"),
        "ret_yyyymmdd": ret_dt.strftime("%Y%m%d"),
        "keyword_date": f"{dep_dt.month}월 {dep_dt.day}일 {ret_dt.month}월 {ret_dt.day}일",
    }


# ------------------------------------------------------------------------------
# 가격 확보
# ------------------------------------------------------------------------------
def parse_krw(text: Any) -> Optional[int]:
    """'₩291,400' 같은 원화 표기만 정수로 변환합니다. (달러 등 다른 통화는 버림)"""
    if text is None:
        return None
    s = str(text)
    if "₩" not in s and "KRW" not in s.upper():
        return None
    digits = re.sub(r"[^\d]", "", s)
    if not digits:
        return None
    value = int(digits)
    return value if 30_000 <= value <= 5_000_000 else None


def fetch_live_price(code: str, dep_yyyymmdd: str, ret_yyyymmdd: str) -> Optional[int]:
    """fast-flights 로 ICN↔code 왕복 직항 최저가(원)를 조회합니다. 실패하면 None."""
    try:
        from fast_flights import FlightData, Passengers, get_flights  # type: ignore
    except Exception:
        return None

    def iso(d: str) -> str:
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"

    try:
        result = get_flights(
            flight_data=[
                FlightData(date=iso(dep_yyyymmdd), from_airport="ICN", to_airport=code),
                FlightData(date=iso(ret_yyyymmdd), from_airport=code, to_airport="ICN"),
            ],
            trip="round-trip",
            seat="economy",
            passengers=Passengers(adults=1, children=0, infants_in_seat=0, infants_on_lap=0),
            fetch_mode="fallback",
        )
    except Exception as e:  # 네트워크/차단/라이브러리 버전 차이 등
        print(f"   [실조회 실패] {code}: {type(e).__name__}: {str(e)[:120]}")
        return None

    prices: List[int] = []
    for f in getattr(result, "flights", None) or []:
        if getattr(f, "stops", 0) not in (0, None):
            continue  # 직항만
        p = parse_krw(getattr(f, "price", None))
        if p:
            prices.append(p)
    return min(prices) if prices else None


# ------------------------------------------------------------------------------
# 이력 계산 (전일 대비 등락, 가격 추이)
# ------------------------------------------------------------------------------
def row_code(row: Dict[str, Any]) -> str:
    code = row.get("code")
    if code:
        return str(code)
    m = re.search(r"\(([A-Z]{3})\)\s*$", str(row.get("city", "")))
    return m.group(1) if m else ""


def load_previous(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def trim_to_recent_dates(rows: List[Dict[str, Any]], keep_days: int) -> List[Dict[str, Any]]:
    dates = sorted({str(r.get("date")) for r in rows if r.get("date")}, reverse=True)[:keep_days]
    keep = set(dates)
    return [r for r in rows if str(r.get("date")) in keep]


def derive_history(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, List[Any]]]:
    """
    rows 에 priceDiff 가 없으면 같은 노선의 직전 기록 대비 등락을 채우고,
    노선별 {dates, prices} 가격 추이를 반환합니다. (같은 날짜 중복은 마지막 값 사용)
    """
    per_code: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for r in rows:
        code, date = row_code(r), r.get("date")
        if not code or not date:
            continue
        per_code.setdefault(code, {})[str(date)] = r

    series: Dict[str, Dict[str, List[Any]]] = {}
    for code, by_date in per_code.items():
        dates = sorted(by_date)
        prices: List[int] = []
        for i, d in enumerate(dates):
            row = by_date[d]
            price = int(row.get("price") or 0)
            if "priceDiff" not in row:
                row["priceDiff"] = (price - prices[-1]) if prices else 0
            prices.append(price)
        series[code] = {"dates": dates, "prices": prices}
    return series


# ------------------------------------------------------------------------------
# (선택) Gemini 에디터 노트 보강
# ------------------------------------------------------------------------------
def enrich_notes_with_gemini(flights: List[Dict[str, Any]]) -> None:
    """
    ENABLE_GEMINI_NOTES=1 이고 GEMINI_API_KEY 가 있을 때만 동작합니다.
    기본값은 꺼짐입니다. (큐레이션된 노트를 AI 문장이 덮어쓰지 않도록)
    모델은 GEMINI_MODEL 환경 변수로 바꿀 수 있습니다.
    """
    if os.environ.get("ENABLE_GEMINI_NOTES", "").strip() != "1":
        return
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return

    try:
        from google import genai  # type: ignore
        client = genai.Client(api_key=api_key)
    except Exception as e:
        print(f"[안내] Gemini 라이브러리 사용 불가, 기본 노트 유지: {e}")
        return

    models = [m for m in [os.environ.get("GEMINI_MODEL", "").strip(), "gemini-2.5-flash", "gemini-flash-latest"] if m]
    batch_size = 10
    for b_idx in range(0, len(flights), batch_size):
        batch = flights[b_idx: b_idx + batch_size]
        cities = ", ".join(f"{it['city']}({it['code']})" for it in batch)
        prompt = (
            "다음 도시들로 가는 한국인 직항 여행객을 위한 핵심 유의사항을 도시 코드별로 1문장(60자 이내) 작성해줘. "
            "확실하지 않은 입국 규정·요금은 쓰지 말고, 반드시 {\"코드\": \"문장\"} 형태의 JSON 객체만 출력해: " + cities
        )
        text = ""
        for model_name in models:
            try:
                resp = client.models.generate_content(model=model_name, contents=prompt)
                text = (getattr(resp, "text", "") or "").strip()
                if text:
                    break
            except Exception as e:
                print(f"[안내] Gemini({model_name}) 실패: {str(e)[:100]}")
        if not text:
            continue
        try:
            text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
            tips = json.loads(text)
        except Exception:
            print(f"[안내] Gemini 배치 {b_idx // batch_size + 1} 응답 파싱 실패, 기본 노트 유지")
            continue
        if not isinstance(tips, dict):
            continue
        for it in batch:
            tip = tips.get(it["code"])
            if isinstance(tip, str) and 5 <= len(tip.strip()) <= 120:
                it["notes"] = it["note"] = tip.strip()


# ------------------------------------------------------------------------------
# 메인
# ------------------------------------------------------------------------------
def main() -> None:
    today_str = get_kst_today()
    print(f"📰 [{today_str}] 총 {len(CITIES_58_MASTER)}개 직항 도시 항공권 조간 브리핑 수집을 시작합니다...")

    prev = load_previous(DATA_JSON_PATH)
    prev_rows: List[Dict[str, Any]] = [r for r in (prev.get("flights") or []) if isinstance(r, dict)]

    # 노선별 '오늘 이전' 가장 최근 기록 (가격 이월용)
    last_before_today: Dict[str, Dict[str, Any]] = {}
    for r in sorted(prev_rows, key=lambda x: str(x.get("date", ""))):
        if str(r.get("date")) < today_str and row_code(r):
            last_before_today[row_code(r)] = r

    started = time.monotonic()
    collected_rows: List[Dict[str, Any]] = []
    counts = {"live": 0, "carry": 0, "base": 0}

    for idx, meta in enumerate(CITIES_58_MASTER):
        code = meta["code"]
        sched = build_schedule_window(idx)

        live_price: Optional[int] = None
        if time.monotonic() - started < LIVE_PRICE_BUDGET_SEC:
            live_price = fetch_live_price(code, sched["dep_yyyymmdd"], sched["ret_yyyymmdd"])
            if live_price is not None:
                time.sleep(LIVE_PRICE_DELAY_SEC)

        prev_row = last_before_today.get(code)
        if live_price is not None:
            price, source = live_price, "live"
        elif prev_row and int(prev_row.get("price") or 0) > 0:
            price = int(prev_row["price"])
            source = "carry" if prev_row.get("priceSource") in ("live", "carry") else "base"
        else:
            price, source = int(meta["base_price"]), "base"
        counts[source] += 1

        sky_dep = sched["dep_yyyymmdd"][2:]
        sky_ret = sched["ret_yyyymmdd"][2:]
        naver_url = (
            f"https://flight.naver.com/flights/international/"
            f"ICN-{code}-{sched['dep_yyyymmdd']}/{code}-ICN-{sched['ret_yyyymmdd']}?adult=1&fareType=Y"
        )
        sky_url = f"https://www.skyscanner.co.kr/transport/flights/icn/{code.lower()}/{sky_dep}/{sky_ret}/"

        collected_rows.append({
            "date": today_str,
            "month": today_str[:7],
            "category": f"{meta['major']} ({meta['sub']})",
            "countryGroup": meta["major"],
            "city": f"{meta['city']} ({code})",
            "code": code,
            "section": meta["section"],
            "major": meta["major"],
            "sub": meta["sub"],
            "order": meta["order"],
            "schedule": sched["schedule"],
            "dates": sched["schedule"],
            "price": price,
            "priceSource": source,
            "airline": meta["airline"],
            "timeSlot": meta["timeSlot"],
            "baggage": meta["baggage"],
            "naverUrl": naver_url,
            "skyUrl": sky_url,
            "keyword": f"인천 {meta['city']} 직항 {sched['keyword_date']}",
            "notes": meta["note"],
            "note": meta["note"],
        })
        print(f" ✓ [{idx + 1:02d}/{len(CITIES_58_MASTER)}] {meta['city']} ({code}): {price:,}원 [{source}] ({sched['schedule']})")

    print(f"💱 가격 출처 집계: 실조회 {counts['live']} / 이월 {counts['carry']} / 기준가 {counts['base']}")
    if counts["live"] == 0:
        print("[주의] 오늘은 실조회 가격이 한 건도 없습니다. (fast-flights 미설치/차단/버전 차이 가능) 로그의 [실조회 실패] 줄을 확인하세요.")

    enrich_notes_with_gemini(collected_rows)

    # ---- (선택) 구글 시트 웹훅 ----
    webhook_url = (os.environ.get("APPS_SCRIPT_WEBHOOK_URL") or os.environ.get("WEBAPP_URL") or "").strip()
    secret_key = os.environ.get("SYNC_SECRET_KEY", "").strip()
    sheet_payload: Dict[str, Any] = {}

    if webhook_url:
        req_body = {
            "secret": secret_key,
            "secretKey": secret_key,
            "date": today_str,
            "editionDate": today_str,
            "flights": collected_rows,
            "rows": collected_rows,
        }
        try:
            req = urllib.request.Request(
                webhook_url,
                data=json.dumps(req_body, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                raw_text = resp.read().decode("utf-8")
            print(f"🎉 [시트 기록 완료] 응답 수신 ({len(raw_text)} bytes)")
            parsed = json.loads(raw_text)
            if isinstance(parsed, dict):
                inner = parsed.get("payload")
                sheet_payload = inner if isinstance(inner, dict) else parsed
        except Exception as e:
            print(f"[WARN] 구글 시트 웹훅 연동 오류 (로컬 이력으로 flights_data.json 저장은 계속 진행): {e}")

    # ---- 이력 병합 ----
    sheet_rows = [r for r in (sheet_payload.get("flights") or []) if isinstance(r, dict)]
    if sheet_rows:
        rows_all = list(sheet_rows)
        if not any(str(r.get("date")) == today_str for r in rows_all):
            rows_all += collected_rows       # 시트 응답에 오늘 호가 없으면 방금 수집분을 추가
    else:
        rows_all = [r for r in prev_rows if str(r.get("date")) != today_str] + collected_rows

    rows_all = trim_to_recent_dates(rows_all, HISTORY_DAYS)
    series = derive_history(rows_all)
    sheet_series = sheet_payload.get("historicalSeries")
    if isinstance(sheet_series, dict):
        series.update({k: v for k, v in sheet_series.items() if v})

    rows_all.sort(key=lambda r: (str(r.get("date")), -int(r.get("order") or 0)), reverse=True)
    available_dates = sorted({str(r["date"]) for r in rows_all if r.get("date")}, reverse=True)

    output_json: Dict[str, Any] = {
        "publisher": "THE BOARDING PASS TIMES (보딩패스 타임즈 항공편집국)",
        "schedule": "매일 아침 정기 발행",
        "updatedAt": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "latestDate": today_str,
        "date": today_str,
        "flights": rows_all,
        "historicalSeries": series,
        "availableDates": available_dates,
        "payload": None,   # 프런트는 최상위 값을 사용합니다 (시트 payload 는 위에서 이미 병합)
    }

    tmp_path = DATA_JSON_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(output_json, f, ensure_ascii=False, indent=1)
    os.replace(tmp_path, DATA_JSON_PATH)
    print(f"✅ [{today_str}] {DATA_JSON_PATH} 저장 완료 (발행일 {len(available_dates)}개, 행 {len(rows_all)}개)")


if __name__ == "__main__":
    main()
