name: Update Tech Trends

on:
  schedule:
    - cron: '*/30 * * * *'
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests

      - name: Run Collector
        env:
          WP_URL: ${{ secrets.WP_URL }}
          WP_SECRET: ${{ secrets.WP_SECRET }}
        run: python collector.py # 네 파일명이 main.py면 main.py로 바꿔

      - name: Commit and Push if updated
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "github-actions[bot]@users.noreply.github.com"
          # [수정] 파일명 통일 - 너의 파이썬이 만드는 파일명으로!
          git add trending_history.json
          # 만약 두 파일 다 쓴다면: git add trending.json trending_history.json
          git diff --quiet && git diff --staged --quiet || (git commit -m "Auto update trends: $(date +'%Y-%m-%d %H:%M KST')" && git push)
