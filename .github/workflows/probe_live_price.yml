name: Probe live price (진단용, 수동 실행)

on:
  workflow_dispatch:

jobs:
  probe:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: '3.11'

      - name: 1) 구글 항공권 페이지 접근 확인
        continue-on-error: true
        run: python probe_live_price.py access

      - name: 2) fast-flights 2.x 시험
        continue-on-error: true
        run: |
          python -m venv v2
          v2/bin/pip install "fast-flights==2.2" "primp==0.6.2"
          v2/bin/python probe_live_price.py v2

      - name: 3) fast-flights 3.x 시험 (KRW 지정)
        continue-on-error: true
        run: |
          python -m venv v3
          v3/bin/pip install --pre fast-flights
          v3/bin/pip show fast-flights | head -3
          v3/bin/python probe_live_price.py v3
