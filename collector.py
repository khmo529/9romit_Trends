import os
import json
import re
import datetime
from collections import Counter
import xml.etree.ElementTree as ET
import requests

# IT/Tech 화이트리스트 & 블랙리스트
WHITE_LIST = [
    'ai', 'chatgpt', 'gpt', 'claude', 'gemini', 'llm', 'prompt', 'python', 
    'javascript', 'typescript', 'react', 'next.js', 'vue', 'node', 'wordpress', 
    'aws', 'docker', 'kubernetes', 'api', 'github', 'vscode', 'cloudflare', 
    'cursor', 'n8n', 'deepseek', 'nvidia', 'gpu', 'agent', 'macbook', '애플',
    '클라우드', '보안', '네트워크', '서버', '반도체', '로봇', '스마트폰', '소프트웨어'
]

BLACK_LIST = [
    '코스피', '코스닥', '쇼핑몰', '붕괴', '화재', '사고', '정치', '국회', 
    '연예', '아이돌', '축구', '야구', '부동산', '주식', '증시', '경찰'
]

# 기본 예비 키워드 (RSS 실패 시 상시 보장용 Fallback)
FALLBACK_KEYWORDS = [
    ('ChatGPT', 10), ('Generative AI', 9), ('NVIDIA GPU', 8), 
    ('Claude 3.5', 7), ('DeepSeek', 6), ('Python 3.12', 5), 
    ('Cursor AI', 4), ('Agentic AI', 3), ('Docker', 2), ('WordPress', 1)
]

def fetch_rss_keywords():
    # 더 안정적이고 풍부한 IT RSS 피드 URL 목록
    urls = [
        "https://news.google.com/rss/search?q=IT+%EA%B8%B0%EC%88%A0&hl=ko&gl=KR&ceid=KR:ko", # 구글 뉴스 IT 검색
        "https://news.hada.io/rss/news",                                                      # GeekNews
        "https://rss.etnews.com/Section902.xml"                                               # 전자신문 IT
    ]
    words = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    for url in urls:
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code != 200:
                continue
            
            root = ET.fromstring(res.content)
            for item in root.findall('.//item'):
                title = item.find('title').text if item.find('title') is not None else ''
                
                # 기자 이름, 언론사 이름 등 불필요한 서식 제거
                title = re.sub(r'\[.*?\]|\(.*?\)|<.*?>', ' ', title)
                clean_title = re.sub(r'[^\w\s\.-]', ' ', title)
                
                for token in clean_title.split():
                    token_clean = token.strip('.,-')
                    token_l = token_clean.lower()
                    
                    if len(token_clean) < 2:
                        continue
                    if any(black in token_l for black in BLACK_LIST): 
                        continue
                    
                    # 화이트리스트 매칭 혹은 특정 길 이상의 의미 있는 단어
                    if any(white in token_l for white in WHITE_LIST) or len(token_clean) >= 3:
                        words.append(token_clean)
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            
    extracted = Counter(words).most_common(20)
    
    # 만약 뉴스 수집 결과가 부족하거나 비어있다면 Fallback 데이터 사용
    if not extracted or len(extracted) < 5:
        print("RSS feed returned empty or insufficient items. Using fallback keywords.")
        return FALLBACK_KEYWORDS
        
    return extracted

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

    # KST 현재 시간 생성 (최신 파이썬 타임존 방식 적용)
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_kst = (now_utc + datetime.timedelta(hours=9)).strftime('%Y-%m-%d %H:%M')
    
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
