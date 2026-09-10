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

RSS_URLS = [
    "https://news.hada.io/rss/news",
    "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=ko&gl=KR&ceid=KR:ko",
    "https://rss.etnews.com/Section029.xml",
]

STOPWORDS = {'매일경제','조선일보','한국경제','중앙일보','동아일보','한겨레','연합뉴스','뉴스1','뉴시스',
             '차세대','가격','실적','전망','분석','시장','기업','공개','출시','발표','사업','속보','단독','종합','기자'}

PATTERNS = [
    re.compile(r'(아이폰|iPhone)\s*\d+\s*(Pro Max|Pro|Air|Mini)?', re.I),
    re.compile(r'갤럭시\s*Z?\s*(폴드|플립|Fold|Flip)\s*\d*', re.I),
    re.compile(r'(ChatGPT|Claude|Gemini|DeepSeek|Gemma|Llama)\s*\d*\.?\d*\s*(Pro|Ultra|Sonnet|Opus|Flash)?', re.I),
    re.compile(r'(MacBook|iPad|AirPods|Apple Watch|Vision Pro|RTX\s*\d+|HBM\d*|Blackwell|Rubin)\s*[A-Za-z0-9 ]{0,8}', re.I),
    re.compile(r'(Tesla|테슬라)\s*(FSD|로보택시|Model\s*[A-Z])?', re.I),
]

# [수정1] link 필드 추가
@dataclass
class TrendingItem:
    rank: int; top: bool; kw: str; delta: str; type: str; link: str

def clean_title(s: str) -> str:
    if not s: return ""
    s = html.unescape(s)
    s = re.sub(r'\s*-\s*[^-]{2,25}$', '', s)
    s = re.sub(r'^\[.*?\]\s*', '', s)
    return s.strip()

TECH_ALLOW = {'아이폰','iPhone','갤럭시','Galaxy','애플','Apple','구글','Google','AI','ChatGPT','GPT','Claude','Gemini','NVIDIA','MacBook','iPad','폴드','플립','Fold','Flip','로봇','반도체','HBM','FSD','테슬라'}

def extract_kw(title: str) -> str:
    if not any(w.lower() in title.lower() for w in TECH_ALLOW):
        return ""
    for pat in PATTERNS:
        m = pat.search(title)
        if m:
            return re.sub(r'\s+', ' ', m.group(0).strip())[:25]
    tmp = title
    for w in STOPWORDS:
        tmp = tmp.replace(w, ' ')
    tmp = re.sub(r'\s+', ' ', tmp).strip()
    return tmp[:25]

# [수정2] fetch가 링크까지 같이 반환
def fetch() -> List[Dict]:
    headers = {'User-Agent': 'Mozilla/5.0 Chrome/120.0.0.0'}
    raw = [] # {kw, link}

    for url in RSS_URLS:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            items = root.findall('.//item')[:40]

            for it in items:
                t = it.find('title')
                l = it.find('link')
                if t is None or not t.text: continue
                title = clean_title(t.text)
                link = l.text.strip() if l is not None and l.text else ""
                if len(title) < 5: continue

                kw = extract_kw(title)
                if kw and link:
                    raw.append({"kw": kw, "link": link})
        except Exception as e:
            logging.warning(f"Fetch fail {url}: {e}")

    # 빈도수 + 링크 보존 (가장 많이 나온 링크 하나 선택)
    counts = Counter([x['kw'] for x in raw])
    logging.info(f"Counts: {counts.most_common(15)}")

    # kw별로 대표 링크 하나 고르기
    link_map = {}
    for item in raw:
        if item['kw'] not in link_map:
            link_map[item['kw']] = item['link']

    final = []
    seen = set()
    for kw, _ in counts.most_common(50):
        low = kw.lower()
        if low in seen: continue
        seen.add(low)
        final.append({"kw": kw, "link": link_map.get(kw, "")})
        if len(final) >= 10: break

    return final[:10]

def load_old(path: Path) -> Dict[str,int]:
    if not path.exists(): return {}
    try:
        with path.open('r', encoding='utf-8') as f:
            j = json.load(f)
            return {x['kw'].lower(): x['rank'] for x in j.get('keywords', [])}
    except: return {}

# [수정3] kws가 dict 리스트로 들어옴
def build_payload(kws: List[Dict], old: Dict[str,int]) -> Dict:
    items = []
    for rank, obj in enumerate(kws, 1):
        kw = obj['kw']
        link = obj.get('link','')
        orank = old.get(kw.lower())
        if orank is None:
            d, ty = "NEW", "new"
        else:
            diff = orank - rank
            if diff > 0: d, ty = f"▲ {diff}", "up"
            elif diff < 0: d, ty = f"▼ {abs(diff)}", "down"
            else: d, ty = "-", "same"
        items.append(TrendingItem(rank, rank<=3, kw, d, ty, link))

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

    if not kws:
        logging.error("No keywords! emergency")
        kws = [{"kw": f"IT 속보 {i}", "link": ""} for i in range(1, 11)]

    payload = build_payload(kws, old)
    with hist.open('w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    logging.info(f"Wrote {hist} with {len(kws)} keywords")
    push_wp(payload)

if __name__ == "__main__":
    process_and_push()
