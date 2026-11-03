#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
사이트 화면 검증(수동 실행 전용). 저장소 폴더를 로컬 서버로 띄워 실제 브라우저로 연다.
- 콘솔 오류, 카드 수, 발행 상태, 미발행 목록, 버튼 링크, 금지 문구(기준가·수하물) 검사
- 1면: 위치(발행 문구 아래·면 필터 위), 톱 기사, 전광판 5행·글자 크기(데스크톱 20px·모바일 16px 이상), 스탬프 상한
- 움직임 줄이기(prefers-reduced-motion) 설정에서도 전광판이 바로 채워지는지
- P4: 전광판 머리글·일정(MM.DD-MM.DD)·도착 공항(데이터 대조), 화면 절반 이상 보이기 전 미재생·보이면 재생,
  CPU 4배 느림 프레임 간격(참고 수치), 360·390·768·1024·1366px 가로 넘침, 톱기사 아래 빈 공간·사진 불러오기·출처,
  링크 공유 버튼, 공유 페이지(s/<도시>/) og 값 대조·썸네일 크기
- 데스크톱·모바일 전체 화면 스크린샷을 screenshots/ 에 저장
"""
import http.server, json, os, re, socketserver, sys, threading
from playwright.sync_api import sync_playwright

PORT = 8765
os.makedirs("screenshots", exist_ok=True)
handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=".", **k)
socketserver.TCPServer.allow_reuse_address = True   # 연달아 실행할 때 포트 대기(TIME_WAIT) 오류 방지
srv = socketserver.TCPServer(("127.0.0.1", PORT), handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

data = json.load(open("flights_data.json", encoding="utf-8"))
latest = data["latestDate"]
expected = len([r for r in data["flights"] if r["date"] == latest])
expected_failed = len([r for r in data["failed"] if r["date"] == latest])
problems = []
notes = []      # 목표 미달이지만 실패로 치지 않는 참고 항목(환경에 따라 달라지는 수치)
photos = (json.load(open("data/photos.json", encoding="utf-8")).get("cities") or {}) if os.path.exists("data/photos.json") else {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, vp, motion in (("desktop", {"width": 1366, "height": 900}, "no-preference"),
                             ("mobile", {"width": 390, "height": 844}, "no-preference"),
                             ("reduced", {"width": 1366, "height": 900}, "reduce")):
        ctx = b.new_context(viewport=vp, reduced_motion=motion, has_touch=(name == "mobile"),
                            permissions=["clipboard-read", "clipboard-write"])
        page = ctx.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="networkidle")
        if name == "reduced":
            page.wait_for_timeout(400)
            tiles = page.eval_on_selector_all(".fp-row .fp-tile > .b:not(.f) i", "els => els.map(e => e.textContent.trim()).join('')")
            print(f"[{name}] 0.4초 뒤 전광판 글자 수 {len(tiles)}")
            if len(tiles) < 40:
                problems.append(f"{name}: 움직임 줄이기에서 전광판이 바로 채워지지 않음")
            ctx.close()
            continue
        page.wait_for_timeout(2500)
        # 전광판: 화면에 절반 이상 들어오기 전에는 재생하지 않음 → 보이게 스크롤하면 재생
        vis0 = page.evaluate("""() => { const r = document.querySelector('.fp-rows').getBoundingClientRect();
            const h = Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0)); return h / r.height; }""")
        plays0 = page.evaluate("window.__flapStats ? window.__flapStats.plays + (window.__flapStats.playing ? 1 : 0) : -1")
        print(f"   열었을 때 전광판 보임 {vis0:.0%}, 재생 {plays0}회")
        if vis0 < 0.5 and plays0 != 0:
            problems.append(f"{name}: 전광판이 보이기 전에 재생됨")
        page.evaluate("document.querySelector('.fp-board').scrollIntoView({block: 'center'})")
        page.wait_for_timeout(2600)
        plays1 = page.evaluate("window.__flapStats.plays")
        if plays1 < 1:
            problems.append(f"{name}: 전광판이 보여도 재생되지 않음")
        # 부드러움(참고): CPU 4배 느리게 하고 다시 재생, 재생 중 프레임 간격 기록
        cdp = ctx.new_cdp_session(page)
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
        smooth = page.evaluate("""async () => {
            const fr = []; let last = performance.now(), on = true;
            const f = t => { if (window.__flapStats.playing) fr.push(t - last); last = t; if (on) requestAnimationFrame(f); };
            requestAnimationFrame(f);
            window.__flapBoard.play();
            await new Promise(r => setTimeout(r, 2600));
            on = false;
            const x = fr.slice(1);
            return { ms: window.__flapStats.lastMs, n: x.length,
                     p20: x.length ? Math.round(100 * x.filter(v => v <= 20).length / x.length) : 0,
                     max: x.length ? Math.round(Math.max(...x)) : 0 };
        }""")
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": 1})
        print(f"   전광판(CPU 4배 느림) 재생 {smooth['ms']}ms, 프레임 {smooth['n']}개 중 20ms 이하 {smooth['p20']}%, 최대 {smooth['max']}ms (목표 95%·1.8초, 참고 수치)")
        if smooth["ms"] > 1800 or smooth["p20"] < 95:
            notes.append(f"{name}: 전광판 부드러움 목표 미달(4배 느림) {smooth}")
        board = page.evaluate("""() => ({
            head: [...document.querySelectorAll('.fp-head .fp-htext')].map(e => e.textContent.trim()),
            rows: [...document.querySelectorAll('.fp-row')].map(r => ({
              aria: r.getAttribute('aria-label'),
              cols: [...r.querySelectorAll('.fp-col')].map(c => [...c.querySelectorAll('.fp-tile > .b:not(.f) i')].map(e => e.textContent).join(''))
            }))
        })""")
        if board["head"] != ["유형", "도시", "도착", "일정", "왕복 가격"]:
            problems.append(f"{name}: 전광판 머리글 {board['head']}")
        by_city = {}
        for r_ in data["flights"]:
            if r_["date"] == latest:
                by_city[r_["city"].split(" ")[0][:7]] = r_
        for row in board["rows"]:
            city_t, dest_t, sched_t = row["cols"][1].strip(), row["cols"][2].strip(), row["cols"][3].strip()
            if not re.fullmatch(r"\d\d\.\d\d-\d\d\.\d\d", sched_t):
                problems.append(f"{name}: 일정 형식 '{sched_t}'")
            f_ = by_city.get(city_t)
            if f_ and dest_t != f_["dest"] and not ((row["aria"] or "").find(f"도착 {dest_t}") >= 0 and f_.get("leaveSaver")):
                problems.append(f"{name}: {city_t} 도착 {dest_t} != 데이터 {f_['dest']}")
            price_t = row["cols"][4].strip()
            if not price_t.startswith("₩") or "원" not in (row["aria"] or ""):
                problems.append(f"{name}: 전광판 가격 표기 이상 '{price_t}'")
        cards = page.locator("article.newspaper-card").count()
        body = page.inner_text("body")
        # 1면
        fp = page.locator("section[aria-labelledby='fpTitle']")
        top_h = page.locator("section[aria-labelledby='fpTitle'] h3").first.inner_text() if fp.count() else ""
        sides = page.locator("section[aria-labelledby='fpTitle'] h4").count()
        rows = page.locator(".fp-row").count()
        fsize = page.eval_on_selector(".fp-row .fp-tile", "e => parseFloat(getComputedStyle(e).fontSize)") if rows else 0
        y_pill = page.locator("text=항공편집국 발행").first.bounding_box()["y"]
        y_fp = fp.bounding_box()["y"] if fp.count() else -1
        y_tabs = page.locator("button:has-text('전체 호외')").first.bounding_box()["y"]
        board_aria = page.eval_on_selector_all(".fp-row", "els => els.map(e => e.getAttribute('aria-label'))")
        tiles_text = page.eval_on_selector_all(".fp-row", "els => els.map(e => Array.from(e.querySelectorAll('.fp-tile > .b:not(.f) i')).map(t => t.textContent).join('').replace(/\\s+/g, ' ').trim())")
        stamps = page.locator("article.newspaper-card .passport-stamp:visible").count()
        supers = page.locator("article.newspaper-card .passport-stamp:visible:has-text('SUPER DEAL')").count()
        print(f"   1면 톱: {top_h} | 사이드 {sides}건 | 전광판 {rows}행, 글자 {fsize}px | 스탬프 {stamps}개(SUPER {supers})")
        for a_, t_ in zip(board_aria, tiles_text):
            print(f"     · {t_}   ({a_})")
        if not top_h:
            problems.append(f"{name}: 1면 톱 기사 없음")
        if not (y_pill < y_fp < y_tabs):
            problems.append(f"{name}: 1면 위치 이상(발행 문구 {y_pill}, 1면 {y_fp}, 면 필터 {y_tabs})")
        if rows != min(5, expected):
            problems.append(f"{name}: 전광판 {rows}행")
        min_px = 20 if name == "desktop" else 16
        if fsize < min_px:
            problems.append(f"{name}: 전광판 글자 {fsize}px < {min_px}px")
        if stamps - supers > expected // 4:
            problems.append(f"{name}: 스탬프 상한 초과 {stamps - supers} > {expected // 4}")
        overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        if overflow > 0:
            problems.append(f"{name}: 가로 넘침 {overflow}px")
        page.evaluate("window.scrollTo(0, 0)")
        page.screenshot(path=f"screenshots/{name}_top.png")
        if fp.count():
            fp.screenshot(path=f"screenshots/{name}_front.png")
        # 1면 톱기사 사진: 데스크톱 빈 공간 40px 이하, 사진 불러옴, 사진 설명
        ph = page.evaluate("""() => { const art = document.querySelector("section[aria-labelledby='fpTitle'] article");
            const img = art && art.querySelector('.fp-photo img'); const cap = art && art.querySelector('.fp-photo figcaption');
            if (!art || !img) return null;
            const last = [...art.children].filter(e => e.offsetParent !== null).pop();
            return { gap: Math.round(art.getBoundingClientRect().bottom - last.getBoundingClientRect().bottom - parseFloat(getComputedStyle(art).paddingBottom)),
                     w: img.naturalWidth, h: Math.round(img.getBoundingClientRect().height), cap: cap ? cap.textContent.trim() : '' }; }""")
        print(f"   톱기사 사진: {ph}")
        if ph and name == "desktop" and ph["h"] > 640:
            problems.append(f"{name}: 톱기사 사진이 너무 큼 {ph['h']}px")
        if not ph or ph["w"] <= 0:
            problems.append(f"{name}: 톱기사 사진을 불러오지 못함")
        elif name == "desktop" and ph["gap"] > 40:
            problems.append(f"{name}: 톱기사 아래 빈 공간 {ph['gap']}px > 40px")
        if ph and not ph["cap"]:
            problems.append(f"{name}: 톱기사 사진 설명 없음")
        # 링크 공유 버튼(이미지 공유 버튼은 없앰)
        if page.locator("article.newspaper-card button:has-text('이 특가 공유')").count() != cards:
            problems.append(f"{name}: 링크 공유 버튼 수 이상")
        if page.locator("button:has-text('공유 이미지')").count():
            problems.append(f"{name}: 이전 '공유 이미지' 버튼이 남아 있음")
        if name == "desktop":
            page.locator("article.newspaper-card button:has-text('이 특가 공유')").first.click()
            page.wait_for_timeout(300)
            toast = page.locator("[role=status]").inner_text()
            clip = page.evaluate("navigator.clipboard.readText().catch(() => '')")
            print(f"   공유 버튼: 안내 '{toast}' / 복사 '{clip[:110]}'")
            if "링크를 복사" not in toast or "/s/" not in clip or "?d=" not in clip:
                problems.append("desktop: 링크 공유(복사) 이상")
            fx_rows = page.locator("section[aria-labelledby='fxTitle'] li").count()
            print(f"   환율 박스 {fx_rows}종")
        g = page.locator("article.newspaper-card a:has-text('구글 플라이트')")
        g_count = g.count()
        g_href = g.first.get_attribute("href") if g_count else ""
        print(f"[{name}] 카드 {cards}개(데이터 {expected}개), 구글 버튼 {g_count}개, 콘솔 오류 {len(errors)}건")
        print(f"   첫 구글 링크: {g_href[:120]}")
        status_line = [l for l in body.splitlines() if "오늘 발행" in l]
        print("   발행 상태:", status_line[:1])
        print("   미발행 목록 표시:", "오늘 발행하지 못한 노선" in body)
        for word in ("기준가", "수하물 규정", "무료 위탁수하물", "DIRECT PASS"):
            if word in body:
                problems.append(f"{name}: 금지 문구 '{word}' 노출")
        if cards != expected:
            problems.append(f"{name}: 카드 수 {cards} != 데이터 {expected}")
        if g_count == 0 or "tfs=" not in (g_href or ""):
            problems.append(f"{name}: 구글 플라이트 버튼 링크 이상")
        if errors:
            problems.append(f"{name}: 콘솔 오류 {errors[:3]}")
        if expected_failed and "오늘 발행하지 못한 노선" not in body:
            problems.append(f"{name}: 미발행 목록 미표시")
        page.evaluate("""async () => { for (let y = 0; y < document.body.scrollHeight; y += 600) { scrollTo(0, y); await new Promise(r => setTimeout(r, 60)); } }""")
        # 늦게 오는 사진(지연 불러오기)은 최대 10초 기다린다
        page.wait_for_function("[...document.querySelectorAll('article.newspaper-card img')].every(i => i.complete)", timeout=10000)
        imgs = page.evaluate("[...document.querySelectorAll('article.newspaper-card img')].map(i => i.naturalWidth)")
        bad = sum(1 for w in imgs if not w)
        print(f"   카드 사진 {len(imgs)}장 중 불러오지 못함 {bad}장")
        if bad:
            problems.append(f"{name}: 카드 사진 {bad}장 불러오지 못함")
        if photos:
            no_credit = page.evaluate("""(codes) => codes.filter(c => { const el = document.getElementById('card-' + c);
                return el && !/위키미디어 공용/.test(el.innerText); })""", list(photos))
            if no_credit:
                problems.append(f"{name}: 출처 표기 없는 카드 {no_credit[:5]}")
        page.screenshot(path=f"screenshots/{name}_full.png", full_page=True)
        ctx.close()
    # 가로 넘침(360·768·1024px)
    for w in (360, 768, 1024):
        page = b.new_page(viewport={"width": w, "height": 900})
        page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="networkidle")
        page.wait_for_timeout(1500)
        page.evaluate("document.querySelector('.fp-board').scrollIntoView({block: 'center'})")
        page.wait_for_timeout(2200)
        ov = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        rov = page.evaluate("Math.max(0, ...[...document.querySelectorAll('.fp-row')].map(r => r.scrollWidth - r.clientWidth))")
        print(f"[{w}px] 가로 넘침 {ov}px, 전광판 행 넘침 {rov}px")
        if ov > 0 or rov > 2:
            problems.append(f"{w}px: 가로 넘침 {ov}px / 전광판 {rov}px")
        page.locator("section[aria-labelledby='fpTitle']").screenshot(path=f"screenshots/w{w}_front.png")
        page.close()
    # 공유 페이지(s/<도시>/): og 값이 오늘 카드 값과 같은지, 썸네일 1200×630
    if os.path.isdir("s"):
        import build_share
        from PIL import Image
        today = [r_ for r_ in data["flights"] if r_["date"] == latest]
        bad_og = []
        for r_ in today:
            title, _ = build_share.share_texts(r_, latest)
            page_src = open(f"s/{r_['code']}/index.html", encoding="utf-8").read()
            if f'property="og:title" content="{title}"' not in page_src.replace("&#x27;", "'") or f"thumb.jpg?v={latest.replace('-', '')}" not in page_src:
                bad_og.append(r_["code"])
            if os.path.exists(f"s/{r_['code']}/thumb.jpg") and Image.open(f"s/{r_['code']}/thumb.jpg").size != (1200, 630):
                bad_og.append(r_["code"] + "(크기)")
        print(f"[공유 페이지] {len(os.listdir('s'))}개 항목, 오늘 카드 {len(today)}개 중 불일치 {bad_og or '없음'}")
        if bad_og:
            problems.append(f"공유 페이지 불일치 {bad_og[:5]}")
        page = b.new_page(viewport={"width": 390, "height": 844})
        code0 = today[0]["code"]
        page.goto(f"http://127.0.0.1:{PORT}/s/{code0}/?d={latest.replace('-', '')}", wait_until="networkidle")
        page.wait_for_timeout(2500)
        print(f"   공유 페이지 이동: {page.url}")
        if not page.url.endswith(f"/#{code0}"):
            problems.append(f"공유 페이지가 본 사이트 카드로 이동하지 않음: {page.url}")
        page.close()
        import shutil
        for r_ in today[:4]:
            shutil.copyfile(f"s/{r_['code']}/thumb.jpg", f"screenshots/thumb_{r_['code']}.jpg")
    # 만드는 방법(P5-1): 사진 출처 목록 = data/photos.json, 원본 링크는 모두 위키미디어 공용
    page = b.new_page(viewport={"width": 390, "height": 844})
    aerr = []
    page.on("pageerror", lambda e: aerr.append(str(e)))
    page.on("console", lambda m: aerr.append(m.text) if m.type == "error" else None)
    page.goto(f"http://127.0.0.1:{PORT}/about.html", wait_until="networkidle")
    page.wait_for_timeout(1500)
    rows_a = page.locator("#photoList li").count()
    links = page.eval_on_selector_all("#photoList a.lic-src", "els => els.map(a => a.href)")
    lic_links = page.eval_on_selector_all("#photoList a[href*=creativecommons]", "els => els.length")
    failed_a = page.locator("#rules li").count()
    ov_a = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    print(f"[about] 사진 출처 {rows_a}행(데이터 {len(photos)}), 라이선스 링크 {lic_links}개, 미발행 {failed_a}건(데이터 {expected_failed}), 가로 넘침 {ov_a}px, 오류 {len(aerr)}건")
    if rows_a != len(photos):
        problems.append(f"about: 사진 출처 {rows_a}행 != {len(photos)}")
    if any("commons.wikimedia.org" not in u for u in links):
        problems.append("about: 위키미디어 공용이 아닌 원본 링크")
    if failed_a != expected_failed:
        problems.append(f"about: 미발행 목록 {failed_a} != {expected_failed}")
    if ov_a > 0:
        problems.append(f"about: 가로 넘침 {ov_a}px")
    if aerr:
        problems.append(f"about: 오류 {aerr[:3]}")
    page.screenshot(path="screenshots/about.png", full_page=True)
    page.close()
    # 도시 상세(P5-2): 발행 도시는 오늘 가격 = 데이터, 미발행 도시는 '오늘은 발행되지 않았습니다'(가격 없음)
    today_f = sorted([r_ for r_ in data["flights"] if r_["date"] == latest], key=lambda r_: r_["price"])
    failed_today = [r_ for r_ in data["failed"] if r_["date"] == latest]
    cases = [("pub", today_f[0])] + ([("fail", failed_today[0])] if failed_today else [])
    for kind, rec in cases:
        for vw in (390, 1280):
            page = b.new_page(viewport={"width": vw, "height": 900})
            cerr = []
            page.on("pageerror", lambda e: cerr.append(str(e)))
            page.on("console", lambda m: cerr.append(m.text) if m.type == "error" else None)
            page.goto(f"http://127.0.0.1:{PORT}/city.html?code={rec['code']}", wait_until="networkidle")
            page.wait_for_timeout(1500)
            h1 = page.locator("h1").inner_text().strip()
            today_txt = page.locator("#today").inner_text()
            opts = page.locator("#citySel option").count()
            ov_c = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            hist_n = len((data.get("historicalSeries", {}).get(rec["code"]) or {}).get("prices", []))
            chart = page.locator("#histChart svg").count()
            wait_vis = page.locator("#histWait").is_visible()
            img_w = page.evaluate("(() => { const i = document.getElementById('heroImg'); return i ? i.naturalWidth : -1; })()")
            print(f"[city {rec['code']} {kind} {vw}px] 제목 {h1}, 도시 목록 {opts}개, 이력 {hist_n}일(그래프 {chart}, 대기 문구 {wait_vis}), 사진 {img_w}px, 넘침 {ov_c}px, 오류 {len(cerr)}건")
            if h1 != rec["city"]:
                problems.append(f"city {rec['code']}: 제목 '{h1}' != {rec['city']}")
            if kind == "pub" and f"{rec['price']:,}" not in today_txt:
                problems.append(f"city {rec['code']}: 오늘 가격 {rec['price']:,} 없음")
            if kind == "fail" and ("오늘은 발행되지 않았습니다" not in today_txt or "₩" in today_txt):
                problems.append(f"city {rec['code']}: 미발행 표시 이상")
            if (hist_n >= 7) != (chart == 1) or (hist_n < 7) != wait_vis:
                problems.append(f"city {rec['code']}: 가격 이력 표시 이상(이력 {hist_n}일)")
            if photos.get(rec["code"]) and img_w <= 0:
                problems.append(f"city {rec['code']}: 사진을 불러오지 못함")
            if opts < 58:
                problems.append(f"city: 도시 목록 {opts}개")
            if ov_c > 0:
                problems.append(f"city {rec['code']} {vw}px: 가로 넘침 {ov_c}px")
            if cerr:
                problems.append(f"city {rec['code']}: 오류 {cerr[:3]}")
            page.screenshot(path=f"screenshots/city_{rec['code']}_{vw}.png", full_page=True)
            page.close()
    # 관심 도시(P5-3): ☆ 누르면 띠에 나타나고, 새로고침해도 남고, 다시 누르면 빠짐
    page = b.new_page(viewport={"width": 390, "height": 844})
    page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="networkidle")
    page.wait_for_timeout(1500)
    first = page.locator("article.newspaper-card").first
    fav_city = first.locator("h3").inner_text().strip()
    first.locator("button.fav-star").click()
    page.wait_for_timeout(200)
    strip1 = page.locator("#favStrip").is_visible() and fav_city in page.locator("#favStrip").inner_text()
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(1500)
    strip2 = page.locator("#favStrip").is_visible() and fav_city in page.locator("#favStrip").inner_text()
    page.locator("article.newspaper-card").first.locator("button.fav-star").click()
    page.wait_for_timeout(200)
    strip3 = page.locator("#favStrip").is_visible()
    print(f"[관심 도시] {fav_city}: 넣기 {strip1}, 새로고침 뒤 {strip2}, 빼기 뒤 띠 보임 {strip3}")
    if not (strip1 and strip2 and not strip3):
        problems.append("관심 도시 넣기·저장·빼기 이상")
    rss_links = page.locator("article.newspaper-card a[href*='feed/']").count()
    if rss_links != expected:
        problems.append(f"카드 RSS 링크 {rss_links} != {expected}")
    # 보관함에서 들어오는 ?d= (최근 14발행일 안)
    avail = data.get("availableDates", [])
    if len(avail) > 1:
        page.goto(f"http://127.0.0.1:{PORT}/index.html?d={avail[1]}", wait_until="networkidle")
        page.wait_for_timeout(1500)
        sel_d = page.eval_on_selector("select[x-model='selectedDate']", "e => e.value")
        print(f"[?d=] {avail[1]} → 선택된 호 {sel_d}")
        if sel_d != avail[1]:
            problems.append(f"?d={avail[1]} 로 그날 호가 열리지 않음({sel_d})")
    page.close()
    # 도시별 RSS(P5-3)·보관함(P5-4): 배포 때 만드는 파일(build_extras.py)
    if os.path.isdir("feed"):
        import xml.etree.ElementTree as ET
        bad_feed = []
        for c in [r_["code"] for r_ in data["flights"] if r_["date"] == latest] + [r_["code"] for r_ in data["failed"] if r_["date"] == latest]:
            try:
                ET.parse(f"feed/{c}.xml")
            except Exception:
                bad_feed.append(c)
        print(f"[도시별 RSS] {len(os.listdir('feed'))}개, 읽기 실패 {bad_feed or '없음'}")
        if bad_feed:
            problems.append(f"도시별 RSS 이상 {bad_feed[:5]}")
    if os.path.exists("data/archive.json"):
        arc = json.load(open("data/archive.json", encoding="utf-8"))["issues"]
        page = b.new_page(viewport={"width": 390, "height": 844})
        perr = []
        page.on("pageerror", lambda e: perr.append(str(e)))
        page.goto(f"http://127.0.0.1:{PORT}/archive.html", wait_until="networkidle")
        page.wait_for_timeout(1500)
        n_items = page.locator("#issueList > li").count()
        n_links = page.locator("#issueList a:visible:has-text('그날 호 보기')").count()
        exp_links = sum(1 for i in arc if i["date"] in avail)
        n_ref = page.locator("#issueList h2 span:visible:has-text('참고용')").count()
        exp_ref = sum(1 for i in arc if i["source"] == "reference")
        ov_r = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        print(f"[보관함] {n_items}개 호(데이터 {len(arc)}), 그날 호 링크 {n_links}(기대 {exp_links}), 참고용 {n_ref}(기대 {exp_ref}), 넘침 {ov_r}px, 오류 {len(perr)}건")
        if n_items != len(arc) or n_links != exp_links or n_ref != exp_ref or ov_r > 0 or perr:
            problems.append("보관함 표시 이상")
        if os.path.exists("data/leadtime.json"):
            lt = json.load(open("data/leadtime.json", encoding="utf-8"))
            bars = page.locator("#leadtime div[aria-label]:visible").count()
            print(f"[예약 시점 통계] 실조회 {lt['liveDays']}일, 공개 {lt['ready']}, 화면 막대 묶음 {bars}")
            if lt["ready"] != (bars > 0):
                problems.append("예약 시점 통계: 공개 조건과 화면이 다름(90일 전에는 숨김)")
        page.screenshot(path="screenshots/archive.png", full_page=True)
        page.close()
    # 하위 페이지 로딩·오류 문구(01 §10): 5초 뒤 '불러오는 중'·'불러오지 못했' 문구가 보이면 안 됨
    for sub in ("archive.html", "about.html", "monthly.html", f"city.html?code={today_f[0]['code']}"):
        for vw in (375, 1366):
            page = b.new_page(viewport={"width": vw, "height": 900})
            serr = []
            page.on("pageerror", lambda e: serr.append(str(e)))
            page.goto(f"http://127.0.0.1:{PORT}/{sub}", wait_until="networkidle")
            page.wait_for_timeout(5000)
            stuck = page.evaluate("""() => [...document.querySelectorAll('body *')]
                .filter(e => e.children.length === 0 && e.offsetParent !== null && /불러오는 중|불러오지 못했/.test(e.textContent))
                .map(e => e.textContent.trim().slice(0, 40))""")
            ver = page.evaluate("window.Alpine ? Alpine.version : ''")
            print(f"[하위 페이지 {sub} {vw}px] Alpine {ver}, 남은 로딩·오류 문구 {stuck or '없음'}, 오류 {len(serr)}건")
            if stuck:
                problems.append(f"{sub} {vw}px: 로딩·오류 문구가 남음 {stuck[:2]}")
            if serr:
                problems.append(f"{sub}: 페이지 오류 {serr[:2]}")
            page.close()
    # 월간지
    page = b.new_page(viewport={"width": 1366, "height": 900})
    merr = []
    page.on("pageerror", lambda e: merr.append(str(e)))
    idx = json.load(open("data/reports/index.json", encoding="utf-8"))
    for ym in idx.get("monthly", [])[:2]:
        page.goto(f"http://127.0.0.1:{PORT}/monthly.html?m={ym}", wait_until="networkidle")
        page.wait_for_timeout(1200)
        rows = page.locator("tbody tr").count()
        body = page.inner_text("body")
        rep = json.load(open(f"data/reports/monthly/{ym}.json", encoding="utf-8"))
        cov = rep.get("coverage", {})
        should_ref = bool(cov.get("by_source", {}).get("sheet")) or cov.get("days_with_data", 0) < cov.get("days_in_period", 0)
        print(f"[monthly {ym}] 표 {rows}행(데이터 {len(rep.get('routes', {}))}), 참고용 표시 {'참고용' in body}(기대 {should_ref})")
        if rows != len(rep.get("routes", {})):
            problems.append(f"monthly {ym}: 표 행 수 불일치")
        if should_ref != ("참고용" in body):
            problems.append(f"monthly {ym}: 참고용 표시 이상")
        page.screenshot(path=f"screenshots/monthly_{ym}.png", full_page=True)
    if merr:
        problems.append(f"monthly: 오류 {merr[:3]}")
    page.close()
    b.close()
srv.shutdown()
print("참고:", notes or "없음")
print("문제:", problems or "없음")
sys.exit(1 if problems else 0)
