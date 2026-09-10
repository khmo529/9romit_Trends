import os
import json
import re
import datetime
import logging
from pathlib import Path
from collections import Counter
from dataclasses import dataclass, asdict
from typing import List, Dict

import requests
import xml.etree.ElementTree as ET

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# ================= CONFIG - 소스 확장 (IT 커뮤니티 기반) =================
RSS_URLS = [
    "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=ko&gl=KR&ceid=KR:ko",
    "https://news.hada.io/rss/news", # 긱뉴스
    "https://feeds.feedburner.com/TechCrunch", # 해외 테크
    "https://www.reddit.com/r/LocalLLaMA/.rss", # AI 커뮤니티
]

MEDIA_BLACK_LIST = {'매일경제','조선일보','핀포인트뉴스','한국경제','중앙일보','동아일보','한겨레','이데일리','디지털타임스','머니투데이','연합뉴스','뉴스1','뉴시스'}
GENERIC_BLACK_LIST = {'차세대','가격','실적','전망','분석','시장','기업','공개','출시','발표','사업','한국','세계','속보','주요','오늘','내일','올해','내년','상반기','하반기','기자','단독','종합'}

# 하드코딩 대신, 제품명 패턴을 동적으로 잡는 정규식 (버전 숫자 자동 인식)
DYNAMIC_PRODUCT_PATTERNS = [
    re.compile(r'(아이폰|iPhone)\s*\d+\s*(Pro Max|Pro|Air|Mini)?', re.I),
    re.compile(r'(갤럭시|Galaxy)\s*Z\s*(폴드|플립|Fold|Flip)\s*\d*', re.I),
    re.compile(r'(ChatGPT|GPT|Claude|Gemini|DeepSeek|LLaMA|Gemma)\s*[- ]?\d*(\.\d+)?\s*(Pro|Ultra|Sonnet|Opus|Flash)?', re.I),
    re.compile(r'(MacBook|iPad|Apple Watch|AirPods|NVIDIA|GeForce|RTX|Blackwell|HBM\d*)\s*[A-Za-z0-9 ]{0,10}', re.I),
    re.compile(r'(테슬라|Tesla)\s*(FSD|자율주행|로보택시)?', re.I),
]

@dataclass
class TrendingItem:
    rank: int; top: bool; kw: str; delta: str; type: str

def clean_title(raw_title: str) -> str:
    if not raw_title: return ""
    # 언론사 꼬리표 제거
    t = re.sub(r'\s*-\s*[^-]{2,30}$', '', raw_title).strip()
    # 대괄호 태그 제거 [속보]
    t = re.sub(r'^\[.*?\]\s*', '', t)
    return t

def extract_dynamic_keyword(title: str) -> str:
    """
    1. 제목에서 제품명/모델명이 있으면 그걸 키워드로
    2. 없으면 제목에서 불용어 제거 후 25자 이내로 잘라서 반환
    """
    # 1. 동적 제품명 추출
    for pat in DYNAMIC_PRODUCT_PATTERNS:
        m = pat.search(title)
        if m:
            kw = m.group(0).strip()
            # "아이폰 18 Pro" 처럼 깔끔하게 정리
            kw = re.sub(r'\s+', ' ', kw)
            return kw[:25]

    # 2. 제목 자체를 키워드로 - 불용어 제거
    cleaned = title
    for bad in MEDIA_BLACK_LIST | GENERIC_BLACK_LIST:
        cleaned = cleaned.replace(bad, ' ')

    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    # 너무 길면 25자 컷
    return cleaned[:25] if len(cleaned) > 2 else ""

def fetch_keywords_from_rss() -> List[str]:
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'}
    extracted = []

    for url in RSS_URLS:
        try:
            res = requests.get(url, headers=headers, timeout=15)
            res.raise_for_status()
            # Reddit은 json일 수도 있어서 xml 파싱 실패하면 스킵
            try:
                root = ET.fromstring(res.content)
            except ET.ParseError:
                logging.warning(f"XML Parse fail {url} - maybe JSON RSS, skip")
                continue

            for item in root.findall('.//item')[:30]: # 최신 30개만
                title_node = item.find('title')
                if not title_node or not title_node.text:
                    continue
                title = clean_title(title_node.text)
                if len(title) < 4: continue

                kw = extract_dynamic_keyword(title)
                if kw and len(kw) >= 2:
                    extracted.append(kw)

        except Exception as e:
            logging.warning(f"RSS fetch failed {url}: {e}")
            continue

    # 빈도수 기반 + 중복 유사어 제거
    counts = Counter(extracted)
    logging.info(f"Raw extracted: {counts.most_common(15)}")

    # 유사어 병합 (예: 아이폰 18 Pro, 아이폰 18 프로 -> 하나로)
    final, seen_lower = [], set()
    for kw, _ in counts.most_common(30):
        low = kw.lower()
        if low in seen_lower: continue
        # 포함 관계면 스킵 (예: 갤럭시 Z폴드 vs 갤럭시 Z폴드7)
        if any(low in s or s in low for s in seen_lower):
            continue
        final.append(kw)
        seen_lower.add(low)
        if len(final) >= 10:
            break

    # 만약 10개도 못 채우면? 그냥 많이 나온 제목 그대로라도 채움 (FALLBACK 하드코딩 없음)
    if len(final) < 10:
        logging.warning(f"Only {len(final)} keywords found, filling with remaining titles")
        for kw, _ in counts.most_common(50):
            if kw not in final:
                final.append(kw)
            if len(final) >= 10: break

    return final[:10]

def load_old_ranks(history_file: Path) -> Dict[str, int]:
    if not history_file.exists(): return {}
    try:
        with history_file.open('r', encoding='utf-8') as f:
            data = json.load(f)
            return {item['kw'].lower(): item['rank'] for item in data.get('keywords', [])}
    except Exception:
        return {}

def build_payload(new_keywords: List[str], old_ranks: Dict[str, int]) -> Dict:
    items = []
    for rank, kw in enumerate(new_keywords, 1):
        old_rank = old_ranks.get(kw.lower())
        if old_rank is None:
            delta, type_ = "NEW", "new"
        else:
            diff = old_rank - rank
            if diff > 0: delta, type_ = f"▲ {diff}", "up"
            elif diff < 0: delta, type_ = f"▼ {abs(diff)}", "down"
            else: delta, type_ = "-", "same"
        items.append(TrendingItem(rank=rank, top=rank<=3, kw=kw, delta=delta, type=type_))

    now_kst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
    return {"updated_at": now_kst.strftime('%Y-%m-%d %H:%M'), "keywords": [asdict(i) for i in items]}

def push_to_wordpress(payload: Dict):
    wp_url = os.environ.get('WP_URL','').rstrip('/')
    wp_secret = os.environ.get('WP_SECRET','')
    if not wp_url or not wp_secret:
        logging.info("WP_URL or WP_SECRET not set - skip push")
        return
    try:
        url = f"{wp_url}/wp-json/g9/v1/update-trends"
        res = requests.post(url, json=payload, headers={"Content-Type":"application/json","X-G9-Token":wp_secret}, timeout=10)
        res.raise_for_status()
        logging.info(f"WP Push OK: {res.json()}")
    except Exception as e:
        logging.error(f"WP Push fail: {e}")

def process_and_push():
    history_file = Path(__file__).parent / 'trending_history.json'
    old_ranks = load_old_ranks(history_file)
    raw_keywords = fetch_keywords_from_rss()

    if not raw_keywords:
        logging.error("No keywords extracted at all! Keep old file")
        return # 아예 없으면 파일 덮지 않음 - 옛날 데이터라도 유지

    payload = build_payload(raw_keywords, old_ranks)
    with history_file.open('w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    push_to_wordpress(payload)

if __name__ == "__main__":
    process_and_push()
