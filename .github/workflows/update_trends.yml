name: Update Tech Trends

on:
  schedule:
    - cron: '*/30 * * * *' # 30분마다 실행
  workflow_dispatch: # 수동 실행 버튼 활성화

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Repository
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.x'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests

      - name: Run Collector
        run: python collector.py

      - name: Commit and Push if updated
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "github-actions[bot]@users.noreply.github.com"
          git add trending.json
          git diff --quiet && git diff --staged --quiet || (git commit -m "Auto update trends" && git push)
