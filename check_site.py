#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
사이트 화면 검증(수동 실행 전용). 저장소 폴더를 로컬 서버로 띄워 실제 브라우저로 연다.
- 콘솔 오류, 카드 수, 발행 상태, 미발행 목록, 버튼 링크, 금지 문구(기준가·수하물) 검사
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
    for name, vp in (("desktop", {"width": 1366, "height": 900}), ("mobile", {"width": 390, "height": 844})):
        page = b.new_page(viewport=vp)
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="networkidle")
        page.wait_for_timeout(2500)
        cards = page.locator("article.newspaper-card").count()
        body = page.inner_text("body")
        g = page.locator("a:has-text('구글 플라이트')")
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
        page.screenshot(path=f"screenshots/{name}_top.png")
        page.screenshot(path=f"screenshots/{name}_full.png", full_page=True)
        page.close()
    b.close()
srv.shutdown()
print("문제:", problems or "없음")
sys.exit(1 if problems else 0)
