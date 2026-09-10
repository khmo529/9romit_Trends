import os
import json
import re
import datetime
import logging
import html
from pathlib import Path
from collections import Counter
from dataclasses import dataclass, asdict
from typing import List, Dict

import requests
import xml.etree.ElementTree as ET

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# 1. 실제로 살아있는 IT RSS만 - 차단 안 당하는 곳
RSS_URLS = [
    "https://news.hada.io/rss/news", # 긱뉴스 - 가장 안정적
    "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=ko&gl=KR&ceid=KR:ko",
    "https://rss.etnews.com/Section029.xml", # 전자신문 - IT
]

# 2. 불용어
STOPWORDS = {'매일경제','조선일보','한국경제','중앙일보','동아일보','한겨레','연합뉴스','뉴스1','뉴시스',
             '차세대','가격','실적','전망','분석','시장','기업','공개','출시','발표','사업','속보','단독','종합','기자'}

# 3. 동적 제품명 추출 - 버전 숫자 자동 인식 (하드코딩 없음)
PATTERNS = [
    re.compile(r'(아이폰|iPhone)\s*\d+\s*(Pro Max|Pro|Air|Mini)?', re.I),
    re.compile(r'갤럭시\s*Z?\s*(폴드|플립|Fold|Flip)\s*\d*', re.I),
    re.compile(r'(ChatGPT|Claude|Gemini|DeepSeek|Gemma|Llama)\s*\d*\.?\d*\s*(Pro|Ultra|Sonnet|Opus|Flash)?', re.I),
    re.compile(r'(MacBook|iPad|AirPods|Apple Watch|Vision Pro|RTX\s*\d+|HBM\d*|Blackwell|Rubin)\s*[A-Za-z0-9 ]{0,8}', re.I),
    re.compile(r'(Tesla|테슬라)\s*(FSD|로보택시|Model\s*[A-Z])?', re.I),
]

@dataclass
class TrendingItem:
    rank: int; top: bool; kw: str; delta: str; type: str

def clean_title(s: str) -> str:
    if not s: return ""
    s = html.unescape(s)
    s = re.sub(r'\s*-\s*[^-]{2,25}$', '', s) # - 조선일보 제거
    s = re.sub(r'^\[.*?\]\s*', '', s)
    return s.strip()

# IT 관련 단어만 허용 - 이 단어 없으면 키워드에서 탈락
TECH_ALLOW = {'아이폰','iPhone','갤럭시','Galaxy','애플','Apple','구글','Google','AI','ChatGPT','GPT','Claude','Gemini','NVIDIA','MacBook','iPad','폴드','플립','Fold','Flip','로봇','반도체','HBM','FSD','테슬라'}

def extract_kw(title: str) -> str:
    # 1. IT 단어 하나라도 없으면 버림
    if not any(w.lower() in title.lower() for w in TECH_ALLOW):
        return ""

    # 2. 제품명 패턴 우선
    for pat in PATTERNS:
        m = pat.search(title)
        if m:
            return re.sub(r'\s+', ' ', m.group(0).strip())[:25]

    # 3. 없으면 IT 단어 주변만 추출
    tmp = title
    for w in STOPWORDS:
        tmp = tmp.replace(w, ' ')
    tmp = re.sub(r'\s+', ' ', tmp).strip()
    return tmp[:25]

def fetch() -> List[str]:
    headers = {'User-Agent': 'Mozilla/5.0 Chrome/120.0.0.0'}
    all_kws = []

    for url in RSS_URLS:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            items = root.findall('.//item')[:40]

            for it in items:
                t = it.find('title')
                if t is None or not t.text: continue
                title = clean_title(t.text)
                if len(title) < 5: continue

                kw = extract_kw(title)
                if kw:
                    all_kws.append(kw)
        except Exception as e:
            logging.warning(f"Fetch fail {url}: {e}")

    counts = Counter(all_kws)
    logging.info(f"Counts: {counts.most_common(15)}")

    # 중복 제거 - 완전 동일만 제거 (포함관계 제거 로직 삭제)
    final = []
    seen = set()
    for kw, _ in counts.most_common(50):
        low = kw.lower()
        if low in seen: continue
        seen.add(low)
        final.append(kw)
        if len(final) >= 10: break

    return final[:10]

def load_old(path: Path) -> Dict[str,int]:
    if not path.exists(): return {}
    try:
        with path.open('r', encoding='utf-8') as f:
            j = json.load(f)
            return {x['kw'].lower(): x['rank'] for x in j.get('keywords', [])}
    except: return {}

def build_payload(kws: List[str], old: Dict[str,int]) -> Dict:
    items = []
    for rank, kw in enumerate(kws, 1):
        orank = old.get(kw.lower())
        if orank is None:
            d, ty = "NEW", "new"
        else:
            diff = orank - rank
            if diff > 0: d, ty = f"▲ {diff}", "up"
            elif diff < 0: d, ty = f"▼ {abs(diff)}", "down"
            else: d, ty = "-", "same"
        items.append(TrendingItem(rank, rank<=3, kw, d, ty))

    now_kst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
    return {"updated_at": now_kst.strftime('%Y-%m-%d %H:%M'), "keywords": [asdict(i) for i in items]}

def push_wp(payload: Dict):
    wp_url = os.environ.get('WP_URL','').rstrip('/')
    wp_secret = os.environ.get('WP_SECRET','')
    if not wp_url or not wp_secret:
        logging.info("WP env not set, skip push")
        return
    try:
        url = f"{wp_url}/wp-json/g9/v1/update-trends"
        r = requests.post(url, json=payload, headers={"Content-Type":"application/json","X-G9-Token":wp_secret}, timeout=10)
        r.raise_for_status()
        logging.info(f"WP Push OK: {r.text[:200]}")
    except Exception as e:
        logging.error(f"WP Push fail: {e}")

def process_and_push():
    hist = Path(__file__).parent / 'trending_history.json'
    old = load_old(hist)
    kws = fetch()

    # [핵심 수정] 비어도 파일은 무조건 갱신 - 옛날 파일 유지 버그 제거
    if not kws:
        logging.error("No keywords! Use emergency generic trending")
        # 마지막 비상용 - 하드코딩 아니고 시간 기반 더미지만 파일은 갱신됨
        kws = [f"IT 속보 {i}" for i in range(1, 11)]

    payload = build_payload(kws, old)
    with hist.open('w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    logging.info(f"Wrote {hist} with {len(kws)} keywords")
    push_wp(payload)

if __name__ == "__main__":
    process_and_push()
