import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
import requests

# IT/Tech 화이트리스트 & 블랙리스트
WHITE_LIST = [
    'ai', 'chatgpt', 'gpt', 'claude', 'gemini', 'llm', 'prompt', 'python', 
    'javascript', 'typescript', 'react', 'next.js', 'vue', 'node', 'wordpress', 
    'aws', 'docker', 'kubernetes', 'api', 'github', 'vscode', 'cloudflare', 
    'cursor', 'n8n', 'deepseek', 'nvida', 'gpu', 'agent'
]

BLACK_LIST = ['코스피', '코스닥', '쇼핑몰', '붕괴', '화재', '사고', '정치', '국회', '연예', '아이돌', '축구', '야구', '부동산']

def fetch_rss_keywords():
    urls = [
        "https://news.hada.io/rss/news", # GeekNews (IT 전문)
        "https://rss.donga.com/it.xml",  # IT 뉴스 RSS 예시
    ]
    
    words = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for url in urls:
        try:
            res = requests.get(url, headers=headers, timeout=10)
            root = ET.fromstring(res.content)
            for item in root.findall('.//item'):
                title = item.find('title').text if item.find('title') is not None else ''
                # 영문/한글 IT 키워드 단어 단위 추출
                clean_title = re.sub(r'[^\w\s\.-]', ' ', title)
                tokens = clean_title.split()
                for token in tokens:
                    token_l = token.lower()
                    if any(black in token_l for black in BLACK_LIST):
                        continue
                    if any(white in token_l for white in WHITE_LIST) or len(token) >= 3:
                        words.append(token)
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            
    return Counter(words).most_common(20)

def process_trends():
    # 1. 기존 데이터 로드 (순위 변동 비교용)
    try:
        with open('trending.json', 'r', 'utf-8') as f:
            old_data = json.load(f)
            old_ranks = {item['kw'].lower(): item['rank'] for item in old_data.get('keywords', [])}
    except FileNotFoundError:
        old_ranks = {}

    # 2. 신규 키워드 수집
    raw_keywords = fetch_rss_keywords()
    
    new_keywords = []
    rank = 1
    
    for kw, count in raw_keywords:
        if rank > 10:
            break
            
        kw_lower = kw.lower()
        delta_str = "NEW"
        delta_type = "new"
        
        # 실제 순위 변동 계산
        if kw_lower in old_ranks:
            prev_rank = old_ranks[kw_lower]
            diff = prev_rank - rank
            if diff > 0:
                delta_str = f"▲ {diff}"
                delta_type = "up"
            elif diff < 0:
                delta_str = f"▼ {abs(diff)}"
                delta_type = "down"
            else:
                delta_str = "-"
                delta_type = "same"

        new_keywords.append({
            "rank": rank,
            "top": rank <= 3,
            "kw": kw,
            "delta": delta_str,
            "type": delta_type
        })
        rank += 1

    # 3. JSON 저장
    result = {"updated_at": requests.get("http://worldtimeapi.org/api/timezone/Asia/Seoul").json().get("datetime"), "keywords": new_keywords}
    with open('trending.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    process_trends()
