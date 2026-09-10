name: Update Tech Trends

on:
  schedule:
    - cron: '*/30 * * * *'
  workflow_dispatch:

# GITHUB_TOKEN 권한 - 이게 최상단에 있어야 함
permissions:
  contents: write

# 30분마다 겹쳐서 도는 것 방지
concurrency:
  group: tech-trends-push
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 1

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          # requirements.txt 없으면 이 줄 넣으면 에러남 - 빼야 함
          # cache: 'pip'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests

      - name: Run Collector
        env:
          WP_URL: ${{ secrets.WP_URL }}
          WP_SECRET: ${{ secrets.WP_SECRET }}
        run: |
          set -e
          echo "=== Running collector.py ==="
          python collector.py

          echo "=== Result ==="
          ls -lh trending_history.json || echo "file missing!"
          cat trending_history.json | head -20
          echo ""

      - name: Commit and Push if updated
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "github-actions[bot]@users.noreply.github.com"

          # 중요: 커밋 전에 최신 코드를 먼저 가져와야 내 파일이 안 사라짐
          git pull --rebase origin ${{ github.ref_name }} || true

          # 파일 없으면 생성 (첫 실행 대응)
          if [! -f trending_history.json ]; then
            echo '{"updated_at":"init","keywords":[]}' > trending_history.json
          fi

          git add trending_history.json

          # 변경 없으면 종료
          if git diff --staged --quiet; then
            echo "No changes to commit"
            exit 0
          fi

          git commit -m "Auto update trends: $(date +'%Y-%m-%d %H:%M KST') [skip ci]"
          git push
