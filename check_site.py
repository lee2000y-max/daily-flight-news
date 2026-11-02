#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
사이트 화면 검증(수동 실행 전용). 저장소 폴더를 로컬 서버로 띄워 실제 브라우저로 연다.
- 콘솔 오류, 카드 수, 발행 상태, 미발행 목록, 버튼 링크, 금지 문구(기준가·수하물) 검사
- 1면: 위치(발행 문구 아래·면 필터 위), 톱 기사, 전광판 5행·글자 크기(데스크톱 20px·모바일 16px 이상), 스탬프 상한
- 움직임 줄이기(prefers-reduced-motion) 설정에서도 전광판이 바로 채워지는지
- 데스크톱·모바일 전체 화면 스크린샷을 screenshots/ 에 저장
"""
import http.server, json, os, socketserver, sys, threading
from playwright.sync_api import sync_playwright

PORT = 8765
os.makedirs("screenshots", exist_ok=True)
handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=".", **k)
srv = socketserver.TCPServer(("127.0.0.1", PORT), handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

data = json.load(open("flights_data.json", encoding="utf-8"))
latest = data["latestDate"]
expected = len([r for r in data["flights"] if r["date"] == latest])
expected_failed = len([r for r in data["failed"] if r["date"] == latest])
problems = []
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, vp, motion in (("desktop", {"width": 1366, "height": 900}, "no-preference"),
                             ("mobile", {"width": 390, "height": 844}, "no-preference"),
                             ("reduced", {"width": 1366, "height": 900}, "reduce")):
        page = b.new_page(viewport=vp, reduced_motion=motion)
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="networkidle")
        if name == "reduced":
            page.wait_for_timeout(400)
            tiles = page.eval_on_selector_all(".fp-row .fp-tile", "els => els.map(e => e.textContent.trim()).join('')")
            print(f"[{name}] 0.4초 뒤 전광판 글자 수 {len(tiles)}")
            if len(tiles) < 40:
                problems.append(f"{name}: 움직임 줄이기에서 전광판이 바로 채워지지 않음")
            page.close()
            continue
        page.wait_for_timeout(3500)
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
        tiles_text = page.eval_on_selector_all(".fp-row", "els => els.map(e => Array.from(e.querySelectorAll('.fp-tile')).map(t => t.textContent).join('').replace(/\\s+/g, ' ').trim())")
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
        if name == "desktop":
            try:
                with page.expect_download(timeout=15000) as dl:
                    page.locator("article.newspaper-card button:has-text('공유 이미지')").first.click()
                path = dl.value.path()
                size = os.path.getsize(path)
                dl.value.save_as("screenshots/share_sample.png")
                print(f"   공유 이미지: {dl.value.suggested_filename} {size:,}바이트")
                if size < 20000:
                    problems.append("desktop: 공유 이미지가 너무 작음")
            except Exception as e:
                problems.append(f"desktop: 공유 이미지 저장 실패 {type(e).__name__}")
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
        page.screenshot(path=f"screenshots/{name}_full.png", full_page=True)
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
print("문제:", problems or "없음")
sys.exit(1 if problems else 0)
