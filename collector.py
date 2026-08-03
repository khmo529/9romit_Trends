import os
import json
import re
import datetime
import xml.etree.ElementTree as ET
from collections import Counter
import requests

# IT/Tech 화이트리스트 & 블랙리스트
WHITE_LIST = [
    'ai', 'chatgpt', 'gpt', 'claude', 'gemini', 'llm', 'prompt', 'python', 
    'javascript', 'typescript', 'react', 'next.js', 'vue', 'node', 'wordpress', 
    'aws', 'docker', 'kubernetes', 'api', 'github', 'vscode', 'cloudflare', 
    'cursor', 'n8n', 'deepseek', 'nvidia', 'gpu', 'agent', 'macbook', '애플'
]

BLACK_LIST = ['코스피', '코스닥', '쇼핑몰', '붕괴', '화재', '사고', '정치', '국회', '연예', '아이돌', '축구', '야구', '부동산']

def fetch_rss_keywords():
    urls = [
        "https://news.hada.io/rss/news",  # GeekNews (IT 커뮤니티)
        "https://rss.donga.com/it.xml"    # IT 뉴스
    ]
    words = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for url in urls:
        try:
            res = requests.get(url, headers=headers, timeout=10)
            root = ET.fromstring(res.content)
            for item in root.findall('.//item'):
                title = item.find('title').text if item.find('title') is not None else ''
                clean_title = re.sub(r'[^\w\s\.-]', ' ', title)
                for token in clean_title.split():
                    token_l = token.lower()
                    if any(black in token_l for black in BLACK_LIST): 
                        continue
                    if any(white in token_l for white in WHITE_LIST) or len(token) >= 3:
                        words.append(token)
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            
    return Counter(words).most_common(20)

def process_and_push():
    # 1. 히스토리 파일 읽기 (순위 변동 비교)
    history_file = 'trending_history.json'
    old_ranks = {}
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                old_data = json.load(f)
                old_ranks = {item['kw'].lower(): item['rank'] for item in old_data.get('keywords', [])}
        except Exception as e:
            print(f"History load error: {e}")

    # 2. 키워드 정제 및 변동폭 계산
    raw_keywords = fetch_rss_keywords()
    new_keywords = []
    rank = 1
    
    for kw, count in raw_keywords:
        if rank > 10: 
            break
        kw_lower = kw.lower()
        delta_str, delta_type = "NEW", "new"
        
        if kw_lower in old_ranks:
            diff = old_ranks[kw_lower] - rank
            if diff > 0:
                delta_str, delta_type = f"▲ {diff}", "up"
            elif diff < 0:
                delta_str, delta_type = f"▼ {abs(diff)}", "down"
            else:
                delta_str, delta_type = "-", "same"

        new_keywords.append({
            "rank": rank,
            "top": rank <= 3,
            "kw": kw,
            "delta": delta_str,
            "type": delta_type
        })
        rank += 1

    # KST 현재 시간 생성
    now_kst = (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).strftime('%Y-%m-%d %H:%M')
    
    payload = {
        "updated_at": now_kst,
        "keywords": new_keywords
    }

    # 3. 로컬 히스토리 업데이트 저장
    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # 4. 워드프레스로 데이터 직접 전송 (REST API Push)
    wp_url = os.environ.get('WP_URL', '').rstrip('/')
    wp_secret = os.environ.get('WP_SECRET', '')

    if wp_url and wp_secret:
        target_api = f"{wp_url}/wp-json/g9/v1/update-trends"
        headers = {
            "Content-Type": "application/json",
            "X-G9-Token": wp_secret
        }
        try:
            res = requests.post(target_api, json=payload, headers=headers, timeout=10)
            print(f"WordPress Push Result: {res.status_code} - {res.text}")
        except Exception as e:
            print(f"Failed to push to WordPress: {e}")
    else:
        print("WP_URL or WP_SECRET is missing in environment variables.")

if __name__ == "__main__":
    process_and_push()
