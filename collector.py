import os
import json
import re
import datetime
import xml.etree.ElementTree as ET
from collections import Counter
import requests

# 1. 언론사, 도메인, URL 등 무의미한 노이즈 블랙리스트
NOISE_PATTERNS = [
    r'[\w-]+\.(com|net|co\.kr|kr|io|org|me)',  # cio.com, v.daum.net 같은 도메인
    r'http[s]?://\S+',                         # URL
    r'\d{4}년', r'\d{1,2}월', r'\d{1,2}일',     # 2026년, 8월 등 날짜
    r'\[.*?\]', r'\(.*?\)', r'<.*?>',          # [속보], (종합) 등 태그
]

BLACK_LIST = [
    # 언론사 / 매체명
    '머니투데이', '데일리e뉴스', '지디넷', '전자신문', '조선일보', '중앙일보', '동아일보', 
    '연합뉴스', '뉴스1', '뉴시스', '매일경제', '한국경제', '디지털타임스', '블로터', 'bloter',
    'zdnet', 'itworld', 'cio', 'daum', 'naver', 'donga', 'seoul', 'news',
    # 무의미한 일반 단어 및 조사
    '기술로', '위한', '통해', '대해', '관한', '기준', '오늘', '내일', '올해', '내년', 
    '상반기', '하반기', '월드it쇼', 'it기술', '기술', '특징주', '공개', '출시', '발표', 
    '적용', '개발', '도입', '확대', '전망', '분석', '사업', '시장', '조선', '한국', '세계'
]

# 2. IT / 전자기기 / Tech 용어 표기 표준화 맵 (소문자 수집 -> 깔끔한 정식 명칭 변환)
TECH_DICTIONARY = {
    'chatgpt': 'ChatGPT',
    'gpt': 'ChatGPT',
    'claude': 'Claude 3.5',
    'gemini': 'Google Gemini',
    'deepseek': 'DeepSeek',
    'nvidia': 'NVIDIA',
    'gpu': 'NVIDIA GPU',
    'iphone': '아이폰 (iPhone)',
    '아이폰': '아이폰 (iPhone)',
    'galaxy': '갤럭시 (Galaxy)',
    '갤럭시': '갤럭시 (Galaxy)',
    'macbook': 'MacBook Pro/Air',
    '맥북': 'MacBook',
    'semiconductor': '반도체',
    '반도체': 'HBM 반도체',
    'hbm': 'HBM 메모리',
    'ai': '온디바이스 AI',
    'llm': '거대언어모델 (LLM)',
    'cloud': '클라우드',
    '클라우드': '클라우드 (AWS/Azure)',
    'apple': '애플 (Apple)',
    '애플': '애플 (Apple)',
    'samsung': '삼성전자',
    '삼성전자': '삼성전자',
    'robot': '로보틱스/AI로봇',
    '로봇': '로보틱스/AI로봇',
    'display': 'OLED 디스플레이',
    '디스플레이': 'OLED 디스플레이',
    'quantum': '양자 컴퓨팅',
    'security': '사이버 보안',
    '보안': '사이버 보안'
}

# 3. 비상시 사용할 프리미엄 전자기기 & IT 트렌드 키워드 (Fallback)
FALLBACK_KEYWORDS = [
    ('ChatGPT-4o', 10),
    ('아이폰 16 Pro', 9),
    ('NVIDIA Blackwell GPU', 8),
    ('갤럭시 Z플립6 / 폴드6', 7),
    ('온디바이스 AI', 6),
    ('DeepSeek R1', 5),
    ('Claude 3.5 Sonnet', 4),
    ('HBM3e 반도체', 3),
    ('MacBook M4', 2),
    ('테슬라 자율주행 (FSD)', 1)
]

def clean_text(text):
    """뉴스 제목에서 도메인, 태그, 노이즈를 정규식으로 완전 제거"""
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, ' ', text, flags=re.IGNORECASE)
    return text

def fetch_rss_keywords():
    urls = [
        "https://news.google.com/rss/search?q=IT+%EC%A0%84%EC%9E%90%EA%B8%B0%EA%B8%B0+AI+%EC%8A%A4%EB%A7%88%ED%8A%B8%ED%8F%B0&hl=ko&gl=KR&ceid=KR:ko", # 테크/디바이스 테마
        "https://news.hada.io/rss/news",                                                                                                         # GeekNews
        "https://rss.etnews.com/Section902.xml"                                                                                                  # 전자신문 IT/모바일
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
                cleaned_title = clean_text(title)
                
                # 단어별 토큰화 및 노이즈 검증
                for token in re.findall(r'[a-zA-Z가-힣0-9]{2,}', cleaned_title):
                    token_l = token.lower()
                    
                    # 블랙리스트 포함 여부 체크
                    if any(black in token_l for black in BLACK_LIST):
                        continue
                    
                    # 숫자만 있는 단어 제거
                    if token.isdigit():
                        continue
                    
                    # 사전 정의된 IT/테크 용어가 있으면 변환 후 저장
                    if token_l in TECH_DICTIONARY:
                        words.append(TECH_DICTIONARY[token_l])
                    elif len(token) >= 2 and not token_l.startswith(('http', 'www', 'v.')):
                        words.append(token)
                        
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            
    # 최다 빈도 단어 추출
    counts = Counter(words).most_common(20)
    
    # 추출된 단어가 유효하지 않거나 수가 부족하면 고품질 전자기기/테크 Fallback 적용
    if not counts or len(counts) < 5:
        print("IT keywords extraction returned empty or poor results. Applying Fallback keywords.")
        return FALLBACK_KEYWORDS
        
    return counts

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
