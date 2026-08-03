import os
import json
import re
import datetime
import xml.etree.ElementTree as ET
from collections import Counter
import requests

# 1. 뉴스 제목에서 무조건 제거할 일반 단어/조사/언론사/노이즈 블랙리스트
GENERIC_BLACK_LIST = {
    '가격', '인상', '하락', '상승', '실적', '전망', '분석', '가전', 'it', '삼성', 
    '기술', '시장', '기업', '대표', '공개', '출시', '발표', '적용', '개발', '도입', 
    '확대', '사업', '조선', '한국', '세계', '속보', '주요', '대응', '우려', '이유', 
    '결과', '위해', '통해', '관한', '대해', '오늘', '내일', '올해', '내년', '상반기', 
    '하반기', '특징주', '주식', '증시', '경찰', '수사', '논란', '경쟁', '전략', '추진'
}

# 2. IT/Tech 전용 핵심 엔티티 사전 (매칭 시 정제된 표기명으로 변환)
TECH_ENTITIES = {
    'chatgpt': 'ChatGPT',
    'gpt': 'ChatGPT',
    'claude': 'Claude AI',
    'gemini': 'Google Gemini',
    'deepseek': 'DeepSeek',
    'nvidia': 'NVIDIA GPU',
    '엔비디아': 'NVIDIA',
    'iphone': '아이폰 (iPhone)',
    '아이폰': '아이폰 (iPhone)',
    'galaxy': '갤럭시 (Galaxy)',
    '갤럭시': '갤럭시 (Galaxy)',
    'macbook': 'MacBook Pro/Air',
    '맥북': 'MacBook',
    '온디바이스': '온디바이스 AI',
    'hbm': 'HBM 반도체',
    '반도체': '차세대 반도체',
    'llm': '거대언어모델 (LLM)',
    '자율주행': '자율주행 (FSD)',
    '로봇': 'AI 로보틱스',
    '로보틱스': 'AI 로보틱스',
    '양자': '양자 컴퓨팅',
    '클라우드': '클라우드 (AWS/Azure)',
    '보안': '사이버 보안',
    '해킹': '사이버 보안',
    '애플': '애플 (Apple)',
    '삼성전자': '삼성전자 (MX/DS)',
    'openal': 'OpenAI',
    'openai': 'OpenAI',
    'tsmc': 'TSMC 파운드리',
    '스마트폰': '차세대 스마트폰'
}

# 3. 데이터 부족 시 표출될 고품질 예비 트렌드 (Fallback)
FALLBACK_TRENDS = [
    ('ChatGPT-4o', 10),
    ('아이폰 16 Pro', 9),
    ('NVIDIA Blackwell', 8),
    ('DeepSeek R1', 7),
    ('갤럭시 Z플립6', 6),
    ('온디바이스 AI', 5),
    ('Claude 3.5 Sonnet', 4),
    ('HBM3e 반도체', 3),
    ('MacBook M4', 2),
    ('테슬라 자율주행', 1)
]

def fetch_clean_it_keywords():
    urls = [
        "https://news.google.com/rss/search?q=IT+%EC%A0%84%EC%9E%90%EA%B8%B0%EA%B8%B0+AI+%EC%8A%A4%EB%A7%88%ED%8A%B8%ED%8F%B0+AI%EB%B0%98%EB%8F%84%EC%B2%B4&hl=ko&gl=KR&ceid=KR:ko",
        "https://news.hada.io/rss/news",
        "https://rss.etnews.com/Section902.xml"
    ]
    
    found_keywords = []
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
                
                # HTML 태그, 괄호, 언론사 태그 제거
                clean_title = re.sub(r'\[.*?\]|\(.*?\)|<.*?>', ' ', title).lower()
                
                # 1) 엔티티 사전 기반 엄격 매칭
                matched_in_title = set()
                for key, display_name in TECH_ENTITIES.items():
                    if key in clean_title:
                        matched_in_title.add(display_name)
                
                found_keywords.extend(list(matched_in_title))
                
                # 2) 일반 단어 중 IT 특화 단어 정제 (블랙리스트 엄격 적용)
                tokens = re.findall(r'[a-zA-Z가-힣]{2,}', clean_title)
                for token in tokens:
                    if token in GENERIC_BLACK_LIST or len(token) < 2:
                        continue
                    # 엔티티에 등록된 핵심 키워드가 아니더라도 3글자 이상의 명확한 영문/한글 테크 용어 수집
                    if token.isupper() or len(token) >= 4:
                        if token not in GENERIC_BLACK_LIST:
                            found_keywords.append(token.upper() if len(token) <= 4 else token.capitalize())

        except Exception as e:
            print(f"Error fetching {url}: {e}")
            
    # 빈도수 계산
    counts = Counter(found_keywords).most_common(15)
    
    # 일반 단어가 필터링되어 수집 수가 적을 경우 고품질 IT 트렌드 백업 데이터 결합
    final_list = []
    seen = set()
    
    for kw, count in counts:
        if kw.lower() not in GENERIC_BLACK_LIST and kw not in seen:
            final_list.append((kw, count))
            seen.add(kw)
            
    # 10개가 안 채워지면 Fallback 항목으로 채움
    if len(final_list) < 10:
        for fb_kw, fb_score in FALLBACK_TRENDS:
            if fb_kw not in seen:
                final_list.append((fb_kw, fb_score))
                seen.add(fb_kw)
            if len(final_list) >= 10:
                break
                
    return final_list[:10]

def process_and_push():
    history_file = 'trending_history.json'
    old_ranks = {}
    
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                old_data = json.load(f)
                old_ranks = {item['kw'].lower(): item['rank'] for item in old_data.get('keywords', [])}
        except Exception as e:
            print(f"History load error: {e}")

    raw_keywords = fetch_clean_it_keywords()
    new_keywords = []
    rank = 1
    
    for kw, count in raw_keywords:
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

    # KST 현재 시간
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_kst = (now_utc + datetime.timedelta(hours=9)).strftime('%Y-%m-%d %H:%M')
    
    payload = {
        "updated_at": now_kst,
        "keywords": new_keywords
    }

    # 히스토리 저장
    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # 워드프레스 REST API 전송
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
