import os
import json
import re
import datetime
import logging
from pathlib import Path
from collections import Counter
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple

import requests
import xml.etree.ElementTree as ET

# ================= CONFIG =================
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

RSS_URLS = [
    "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=ko&gl=KR&ceid=KR:ko",
    "https://news.hada.io/rss/news"
]

MEDIA_BLACK_LIST = {
    '매일경제', '조선일보', '핀포인트뉴스', '한국경제', '중앙일보', '동아일보',
    '한겨레', '이데일리', '디지털타임스', '머니투데이', '연합뉴스', '뉴스1', '뉴시스'
}

# 구체적인 패턴이 위로 오도록 정렬 필수
RAW_SEO_MAP = [
    (r'iphone 17|아이폰 17', '아이폰 17 Pro'),
    (r'iphone|아이폰', '아이폰 17 Pro'),
    (r'galaxy.*fold.*7|갤럭시.*폴드.*7|z.*폴드.*7', '갤럭시 Z폴드7'),
    (r'galaxy.*flip.*7|갤럭시.*플립.*7|z.*플립.*7', '갤럭시 Z플립7'),
    (r'galaxy|갤럭시', '갤럭시 Z플립·폴드'),
    (r'gpt-5|gpt 5|chatgpt-5', 'ChatGPT-5'),
    (r'chatgpt|gpt-4o|openai', 'ChatGPT-4o'),
    (r'claude.*4|클로드.*4', 'Claude 4 Sonnet'),
    (r'claude|클로드', 'Claude 3.5 Sonnet'),
    (r'gemini.*2|제미나이.*2', 'Google Gemini 2.0'),
    (r'gemini|제미나이', 'Google Gemini'),
    (r'deepseek.*v3|딥시크.*v3', 'DeepSeek V3'),
    (r'deepseek|딥시크', 'DeepSeek R1'),
    (r'blackwell.*ultra|블랙웰.*울트라', 'NVIDIA Blackwell Ultra'),
    (r'nvidia|엔비디아|b200|h200', 'NVIDIA GPU'),
    (r'hbm4|hbm3e', 'HBM3e 반도체'),
    (r'macbook.*m4|맥북.*m4', 'MacBook Pro M4'),
    (r'온디바이스', '온디바이스 AI'),
    (r'로봇|로보틱스', 'AI 로보틱스'),
    (r'양자|quantum', '양자 컴퓨터'),
]

# 컴파일은 앱 시작시 1번만
SEO_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(p, re.IGNORECASE), tag) for p, tag in RAW_SEO_MAP
]

FALLBACK_KEYWORDS = [
    'ChatGPT-5', '아이폰 17 Pro', 'NVIDIA Blackwell Ultra',
    '갤럭시 Z폴드7', 'Google Gemini 2.0', '온디바이스 AI',
    'Claude 4 Sonnet', 'HBM3e 반도체', 'DeepSeek V3', '테슬라 자율주행 (FSD)'
]

@dataclass
class TrendingItem:
    rank: int
    top: bool
    kw: str
    delta: str
    type: str

# ================= CORE LOGIC =================
def clean_title(raw_title: str) -> str:
    """ '속보: ~ - 조선일보' 같은 꼬리표 제거 """
    if not raw_title:
        return ""
    # 뒤에 ' - 언론사' 패턴 제거
    cleaned = re.sub(r'\s*-\s*[^-]{2,20}$', '', raw_title).strip()
    return cleaned

def map_to_seo_keyword(title: str) -> str | None:
    """ 제목 1개를 SEO 키워드 1개로 매핑 """
    title_lower = title.lower()
    # 언론사명은 키워드 매핑 방해 안되게 공백 처리
    for bad in MEDIA_BLACK_LIST:
        if bad.lower() in title_lower:
            title_lower = title_lower.replace(bad.lower(), ' ')

    for pattern, seo_tag in SEO_PATTERNS:
        if pattern.search(title_lower):
            return seo_tag
    return None

def fetch_keywords_from_rss() -> List[str]:
    headers = {'User-Agent': 'Mozilla/5.0 Chrome/120.0.0.0'}
    extracted = []

    for url in RSS_URLS:
        try:
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()
            root = ET.fromstring(res.content)

            for item in root.findall('.//item'):
                title_node = item.find('title')
                if title_node is None or not title_node.text:
                    continue

                title = clean_title(title_node.text)
                seo_kw = map_to_seo_keyword(title)
                if seo_kw:
                    extracted.append(seo_kw)

        except Exception as e:
            logging.warning(f"RSS fetch failed {url}: {e}")
            continue

    # 빈도수 기반 랭킹
    counts = Counter(extracted)
    # 많이 나온 순으로 정렬
    sorted_tags = [tag for tag, _ in counts.most_common(20)]

    # 중복 제거 + Fallback으로 10개 채우기
    final, seen = [], set()
    for tag in sorted_tags + FALLBACK_KEYWORDS:
        if tag not in seen:
            final.append(tag)
            seen.add(tag)
        if len(final) >= 10:
            break

    logging.info(f"Extracted: {final}")
    return final[:10]

def load_old_ranks(history_file: Path) -> Dict[str, int]:
    if not history_file.exists():
        return {}
    try:
        with history_file.open('r', encoding='utf-8') as f:
            data = json.load(f)
            return {item['kw'].lower(): item['rank'] for item in data.get('keywords', [])}
    except Exception:
        return {}

def build_payload(new_keywords: List[str], old_ranks: Dict[str, int]) -> Dict:
    items: List[TrendingItem] = []
    for rank, kw in enumerate(new_keywords, 1):
        old_rank = old_ranks.get(kw.lower())
        if old_rank is None:
            delta, type_ = "NEW", "new"
        else:
            diff = old_rank - rank
            if diff > 0:
                delta, type_ = f"▲ {diff}", "up"
            elif diff < 0:
                delta, type_ = f"▼ {abs(diff)}", "down"
            else:
                delta, type_ = "-", "same"

        items.append(TrendingItem(rank=rank, top=rank<=3, kw=kw, delta=delta, type=type_))

    now_kst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
    return {
        "updated_at": now_kst.strftime('%Y-%m-%d %H:%M'),
        "keywords": [asdict(i) for i in items]
    }

def push_to_wordpress(payload: Dict):
    wp_url = os.environ.get('WP_URL','').rstrip('/')
    wp_secret = os.environ.get('WP_SECRET','')

    if not wp_url or not wp_secret:
        logging.info("WP_URL or WP_SECRET not set - skip push")
        return

    # 저장 위치 2곳: repo 루트 + uploads 경로용 json도 같이 푸시되므로 WP가 알아서 저장
    try:
        url = f"{wp_url}/wp-json/g9/v1/update-trends"
        res = requests.post(url, json=payload, headers={"Content-Type":"application/json","X-G9-Token":wp_secret}, timeout=10)
        res.raise_for_status()
        logging.info(f"WP Push OK: {res.json()}")
    except Exception as e:
        logging.error(f"WP Push fail: {e}")
        # 실패해도 로컬 파일은 저장해야 하므로 raise 안함

def process_and_push():
    history_file = Path(__file__).parent / 'trending_history.json'

    old_ranks = load_old_ranks(history_file)
    raw_keywords = fetch_keywords_from_rss()

    if not raw_keywords:
        logging.warning("No keywords extracted, using fallback")
        raw_keywords = FALLBACK_KEYWORDS[:10]

    payload = build_payload(raw_keywords, old_ranks)

    # 로컬 저장
    with history_file.open('w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    push_to_wordpress(payload)

if __name__ == "__main__":
    process_and_push()
