#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
도시 카드 사진(위키미디어 공용) 후보 찾기 · 내려받기. 수동 실행 전용(진단 워크플로 mode=photos / photos_fetch).
이 작업 환경(Claude 세션)에서는 위키미디어 접속이 막혀 있어 GitHub Actions에서 돌린다.

  python build_photos.py candidates
      도시마다 검색어(PHOTO_QUERIES)로 공용 사진을 찾아 후보 3장을 고른다.
      조건: 가로 사진(가로 ≥ 세로 × 1.25), 가로 1600px 이상, 라이선스 PD·CC0·CC BY·CC BY-SA.
      결과: data/photo_candidates.json, 미리보기 썸네일 photo_preview/<code>_<n>.jpg (가로 480px)

  python build_photos.py fetch "YGJ:2 SDJ:1 ..."
      고른 후보를 images/cities/<code>.jpg(가로 1600) · <code>_640.jpg(가로 640)로 저장하고
      출처(작가·라이선스·원본 주소)를 data/photos.json에 기록한다. 입력에 없는 도시는 기존 기록 유지.

사진은 가격 정보가 아니므로 고정 파일로 두어도 절대 규칙 1과 무관하다. 출처 표기는 라이선스 조건이라 필수.
"""
import io, json, os, re, sys, time, urllib.parse, urllib.request

API = "https://commons.wikimedia.org/w/api.php"
UA = "BoardingPassTimes/1.0 (https://github.com/lee2000y-max/daily-flight-news; photo picker, manual run)"
CAND_PATH = "data/photo_candidates.json"
PHOTOS_PATH = "data/photos.json"
PREVIEW_DIR = "photo_preview"
IMG_DIR = "images/cities"
N_CAND = 3

# 도시별 검색어(카드 캡션의 장소와 같은 곳). 앞의 검색어일수록 우선.
PHOTO_QUERIES = {
    "KIX": ["Osaka Castle", "Dotonbori Glico sign", "Osaka Castle main tower"],
    "FUK": ["Ohori Park Fukuoka", "Nakasu Fukuoka yatai", "Fukuoka skyline"],
    "NRT": ["Tokyo Tower skyline", "Senso-ji Asakusa", "Tokyo skyline"],
    "CTS": ["Otaru Canal", "Odori Park Sapporo", "Sapporo TV Tower"],
    "NGO": ["Nagoya Castle", "Nagoya TV Tower Sakae", "Nagoya skyline"],
    "OKA": ["Manzamo", "Okinawa beach emerald", "Kerama Islands beach"],
    "HSG": ["Takeo Onsen romon gate", "Ureshino tea plantation", "Mifuneyama Rakuen"],
    "TAK": ["Ritsurin Garden Engetsu-kyo", "Ritsurin Garden", "Naoshima yellow pumpkin"],
    "FSZ": ["Mount Fuji tea plantation", "Mount Fuji Shizuoka", "Nihondaira Mount Fuji"],
    "KOJ": ["Sakurajima Kagoshima", "Sakurajima", "Ibusuki"],
    "OIT": ["Kinrinko Yufuin", "Umi Jigoku Beppu", "Yufuin Mount Yufu"],
    "YGJ": ["Tottori Sand Dunes", "Mount Daisen", "Yonago Castle ruins"],
    "KKJ": ["Mojiko Retro", "Kokura Castle", "Kanmon Strait"],
    "SDJ": ["Matsushima Bay", "Matsushima Miyagi islands", "Godaido Matsushima"],
    "MYJ": ["Dogo Onsen Honkan", "Matsuyama Castle", "Matsuyama Castle ropeway"],
    "HIJ": ["Itsukushima Shrine torii", "Miyajima torii", "Hiroshima Peace Memorial"],
    "KMJ": ["Kumamoto Castle", "Mount Aso caldera", "Daikanbo Aso"],
    "NGS": ["Meganebashi Nagasaki", "Mount Inasa night view Nagasaki", "Nagasaki harbor"],
    "KMQ": ["Kenroku-en", "Higashi Chaya Kanazawa", "Shirakawa-go"],
    "AOJ": ["Oirase Gorge", "Nebuta Matsuri", "Lake Towada"],
    "AKJ": ["Shirogane Blue Pond", "Biei hills", "Furano"],
    "DAD": ["Golden Bridge Ba Na Hills", "My Khe beach Da Nang", "Dragon Bridge Da Nang"],
    "CXR": ["Nha Trang beach", "Po Nagar Nha Trang", "Nha Trang bay"],
    "PQC": ["Hon Thom cable car", "Phu Quoc beach", "Sao beach Phu Quoc"],
    "HAN": ["Hoan Kiem Lake", "Hanoi train street", "Turtle Tower Hoan Kiem"],
    "SGN": ["Saigon Central Post Office", "Notre-Dame Cathedral Basilica of Saigon", "Ho Chi Minh City skyline"],
    "HPH": ["Lan Ha Bay", "Cat Ba island", "Ha Long Bay"],
    "DLI": ["Xuan Huong Lake Da Lat", "Da Lat city", "Da Lat railway station"],
    "TPE": ["Taipei 101", "Jiufen", "Taipei skyline"],
    "KHH": ["Lotus Pond Dragon Tiger Pagodas", "Pier-2 Art Center", "Kaohsiung skyline"],
    "HKG": ["Victoria Harbour Hong Kong", "Hong Kong skyline junk boat", "Victoria Harbour night"],
    "MFM": ["Ruins of St. Paul's Macau", "Senado Square Macau", "Macau skyline"],
    "TAO": ["May Fourth Square Qingdao", "Zhanqiao Pier Qingdao", "Qingdao skyline"],
    "PVG": ["The Bund Shanghai Pudong", "Oriental Pearl Tower", "Lujiazui skyline"],
    "PKX": ["Great Wall Mutianyu", "Hall of Supreme Harmony Forbidden City", "Forbidden City"],
    "YNT": ["Penglai Pavilion", "Yantai coast", "Yantai"],
    "DLC": ["Xinghai Square Dalian", "Dalian skyline", "Dalian"],
    "HGH": ["West Lake Hangzhou", "Leifeng Pagoda", "Su Causeway West Lake"],
    "XIY": ["Terracotta Army", "Xi'an City Wall", "Giant Wild Goose Pagoda"],
    "DYG": ["Zhangjiajie National Forest Park", "Tianmen Mountain", "Yuanjiajie"],
    "CAN": ["Canton Tower", "Pearl River Guangzhou night", "Guangzhou skyline"],
    "HRB": ["Saint Sophia Cathedral Harbin", "Harbin Ice and Snow World", "Harbin ice festival"],
    "BKK": ["Wat Arun", "Wat Arun Chao Phraya night", "Grand Palace Bangkok"],
    "CNX": ["Wat Phra That Doi Suthep", "Tha Phae Gate", "Chiang Mai old city"],
    "HKT": ["Maya Bay Phi Phi", "Phi Phi Islands longtail boat", "Phuket beach"],
    "CEB": ["Mactan beach", "Cebu beach resort", "Oslob Cebu"],
    "TAG": ["Chocolate Hills Bohol", "Alona Beach Panglao", "Balicasag Island"],
    "CRK": ["Lake Pinatubo", "Mount Pinatubo crater lake", "Clark Pampanga"],
    "BKI": ["Tanjung Aru sunset", "Kota Kinabalu City Mosque", "Kota Kinabalu"],
    "SIN": ["Marina Bay Sands", "Gardens by the Bay Supertree Grove", "Singapore skyline night"],
    "UBN": ["Gorkhi-Terelj National Park", "Terelj ger", "Mongolian steppe ger"],
    "ALA": ["Big Almaty Lake", "Almaty Tian Shan", "Medeu"],
    "TAS": ["Hazrati Imam Complex Tashkent", "Kukeldash Madrasa", "Tashkent"],
    "VTE": ["Pha That Luang", "Patuxai Vientiane", "Vang Vieng"],
    "BWN": ["Omar Ali Saifuddien Mosque", "Jame' Asr Hassanil Bolkiah Mosque", "Bandar Seri Begawan"],
    "GUM": ["Tumon Bay Guam", "Two Lovers Point Guam", "Guam beach"],
    "SPN": ["Managaha Island", "Grotto Saipan", "Saipan beach"],
    "DPS": ["Tegallalang rice terraces", "Uluwatu Temple", "Pura Ulun Danu Bratan"],
}

ALLOWED = re.compile(r"^(public domain|pd|cc0|cc[- ]by( |-)?(sa)?[- ]?\d(\.\d)?.*|cc[- ]by(-sa)?)$", re.I)


def api(params: dict, tries: int = 4) -> dict:
    params = {**params, "format": "json", "formatversion": "2"}
    url = API + "?" + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # 429·일시 오류는 쉬었다 재시도
            print(f"   ! API 재시도 {i + 1}: {e}", flush=True)
            time.sleep(2 * (i + 1))
    raise RuntimeError("위키미디어 API 응답 없음")


def download(url: str, tries: int = 4) -> bytes:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:
            print(f"   ! 내려받기 재시도 {i + 1}: {e}", flush=True)
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"내려받기 실패: {url}")


def strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", s).strip()


def license_ok(short: str) -> bool:
    s = (short or "").strip()
    if not s or re.search(r"\bNC\b|\bND\b|non-?commercial|no ?deriv", s, re.I):
        return False
    return bool(ALLOWED.match(s)) or s.lower().startswith(("cc by", "cc-by", "cc0", "public domain"))


def search(query: str, width: int, extra: str = "", limit: int = 20) -> list:
    """공용 파일 검색 + 이미지 정보. 조건에 맞는 것만 검색 순서대로 돌려준다."""
    data = api({
        "action": "query", "generator": "search", "gsrnamespace": 6, "gsrlimit": limit,
        "gsrsearch": f"{query} filetype:bitmap filew:>1599 {extra}".strip(),
        "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": width,
        "iiextmetadatafilter": "LicenseShortName|Artist|ImageDescription|Credit|AttributionRequired|UsageTerms",
    })
    pages = sorted((data.get("query") or {}).get("pages") or [], key=lambda p: p.get("index", 0))
    out = []
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        w, h = ii.get("width", 0), ii.get("height", 0)
        if ii.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
            continue
        if w < 1600 or w < h * 1.25:
            continue
        md = ii.get("extmetadata") or {}
        lic = (md.get("LicenseShortName") or {}).get("value", "")
        if not license_ok(lic):
            continue
        out.append({
            "title": p["title"],
            "page": ii.get("descriptionurl", ""),
            "thumb": ii.get("thumburl", ""),
            "width": w, "height": h,
            "license": lic,
            "artist": strip_html((md.get("Artist") or {}).get("value", "")) or "작자 미상",
            "description": strip_html((md.get("ImageDescription") or {}).get("value", ""))[:200],
            "query": query,
        })
    return out


def candidates() -> None:
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    result, short = {}, []
    for code, queries in PHOTO_QUERIES.items():
        picked, seen = [], set()
        # 1차: 공용 '우수 사진(Quality images)' 안에서, 2차: 전체에서. 검색어마다 1장씩 돌아가며 채운다.
        pools = []
        for q in queries:
            try:
                pools.append(search(q, 480, 'incategory:"Quality_images"') + search(q, 480))
            except RuntimeError as e:
                print(f"   ! {code} '{q}': {e}")
                pools.append([])
            time.sleep(0.3)
        while len(picked) < N_CAND and any(pools):
            for pool in pools:
                while pool and pool[0]["title"] in seen:
                    pool.pop(0)
                if pool and len(picked) < N_CAND:
                    c = pool.pop(0)
                    seen.add(c["title"])
                    picked.append(c)
        for n, c in enumerate(picked, 1):
            try:
                with open(f"{PREVIEW_DIR}/{code}_{n}.jpg", "wb") as fh:
                    fh.write(download(c["thumb"]))
            except RuntimeError as e:
                print(f"   ! {code} {n}번 썸네일: {e}")
        result[code] = picked
        flag = "" if len(picked) == N_CAND else "  ← 후보 부족"
        print(f"{code}: {len(picked)}장 " + " | ".join(f"{c['title'][5:60]} ({c['license']})" for c in picked) + flag, flush=True)
        if len(picked) < N_CAND:
            short.append(code)
    json.dump({"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "cities": result},
              open(CAND_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n후보 저장: {CAND_PATH} ({len(result)}개 도시, 부족 {len(short)}: {' '.join(short) or '없음'})")


def fetch(selection: str) -> None:
    from PIL import Image
    cand = json.load(open(CAND_PATH, encoding="utf-8"))["cities"]
    photos = json.load(open(PHOTOS_PATH, encoding="utf-8")) if os.path.exists(PHOTOS_PATH) else {"cities": {}}
    os.makedirs(IMG_DIR, exist_ok=True)
    for tok in selection.replace(",", " ").split():
        code, _, n = tok.partition(":")
        code = code.upper()
        c = cand[code][int(n) - 1]
        info = api({"action": "query", "titles": c["title"], "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 1600})
        url = info["query"]["pages"][0]["imageinfo"][0]["thumburl"]
        img = Image.open(io.BytesIO(download(url))).convert("RGB")
        for w, suffix in ((1600, ""), (640, "_640")):
            im = img if img.width <= w else img.resize((w, round(img.height * w / img.width)), Image.LANCZOS)
            im.save(f"{IMG_DIR}/{code}{suffix}.jpg", "JPEG", quality=82, optimize=True, progressive=True)
        photos["cities"][code] = {k: c[k] for k in ("title", "page", "license", "artist", "description")}
        print(f"{code}: {c['title']} ({c['license']}, {c['artist']})", flush=True)
        time.sleep(0.3)
    photos["updatedAt"] = time.strftime("%Y-%m-%d")
    json.dump(photos, open(PHOTOS_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "candidates"
    if cmd == "candidates":
        candidates()
    elif cmd == "fetch":
        fetch(" ".join(sys.argv[2:]))
    else:
        sys.exit(f"알 수 없는 명령: {cmd}")
