import os
import json
import re
import datetime
import xml.etree.ElementTree as ET
from collections import Counter
import requests

# 1. 뉴스 매체명 및 언론사 블랙리스트 (완전 제거)
MEDIA_BLACK_LIST = {
    '매일경제', '조선일보', '핀포인트뉴스', '한국경제', '중앙일보', '동아일보', '경향신문', 
    '한겨레', '이데일리', '디지털타임스', '머니투데이', '연합뉴스', '뉴스1', '뉴시스', 
    '전자신문', '지디넷', '블로터', '아이뉴스24', '지디넷코리아', '기자', '뉴스', 'daum', 
    'naver', 'zdnet', 'itworld', 'cio', 'bloter', 'seoul', 'donga'
}

# 2. 너무 광범위하거나 무의미한 일반 단어 블랙리스트
GENERIC_BLACK_LIST = {
    '차세대', '스마트폰', '가전', '가격', '인상', '하락', '상승', '실적', '전망', 
    '분석', 'it', '삼성', '기술', '시장', '기업', '대표', '공개', '출시', '발표', 
    '적용', '개발', '도입', '확대', '사업', '조선', '한국', '세계', '속보', '주요', 
    '대응', '우려', '이유', '결과', '위해', '통해', '관한', '대해', '오늘', '내일', 
    '올해', '내년', '상반기', '하반기', '특징주', '주식', '증시', '경찰', '수사'
}

# 3. 구글 SEO 최적화 전자기기/IT 키워드 매핑 테이블 (원문 -> 정제된 SEO 태그)
SEO_TECH_DICTIONARY = [
    (r'chatgpt|gpt-4o|gpt4o|open AI|openai', 'ChatGPT-4o'),
    (r'deepseek|딥시크', 'DeepSeek R1'),
    (r'claude|클로드', 'Claude 3.5 Sonnet'),
    (r'gemini|제미나이', 'Google Gemini'),
    (r'nvidia|엔비디아|blackwell|블랙웰', 'NVIDIA GPU'),
    (r'iphone|아이폰', '아이폰 16 Pro'),
    (r'galaxy|갤럭시|z플립|z폴드', '갤럭시 Z플립·폴드'),
    (r'macbook|맥북', 'MacBook Pro M4'),
    (r'온디바이스', '온디바이스 AI'),
    (r'hbm|에이치비엠', 'HBM3e 반도체'),
    (r'자율주행|fsd', '테슬라 자율주행 (FSD)'),
    (r'로봇|로보틱스', 'AI 로보틱스'),
    (r'양자|quantum', '양자 컴퓨터'),
    (r'클라우드|aws|azure', '클라우드 (AWS/Azure)'),
    (r'보안|해킹|사이버', '사이버 보안'),
    (r'애플|apple', '애플 인텔리전스'),
    (r'삼성전자|samsung', '삼성전자 AI'),
    (r'tsmc', 'TSMC 파운드리')
]

# 4. 실시간 수집 실패 시 표시될 백업용 검색어 (SEO 고품질 보장)
FALLBACK_SEO_KEYWORDS = [
    'ChatGPT-4o',
    '아이폰 16 Pro',
    'NVIDIA GPU',
    'DeepSeek R1',
    '갤럭시 Z플립·폴드',
    '온디바이스 AI',
    'Claude 3.5 Sonnet',
    'HBM3e 반도체',
    'MacBook Pro M4',
    '테슬라 자율주행 (FSD)'
]

def clean_and_extract_keywords():
    urls = [
        "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=ko&gl=KR&ceid=KR:ko", # 구글 뉴스 공식 테크 섹션
        "https://news.hada.io/rss/news"                                                             # GeekNews IT
    ]
    
    extracted_tags = []
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
                
                # 언론사 태그 및 노이즈 제거 (예: - 매일경제, [조선일보])
                title_clean = re.sub(r'\[.*?\]|\(.*?\)|<.*?>|-.*$', ' ', title).strip()
                title_lower = title_clean.lower()
                
                # 언론사 블랙리스트 단어가 제목에 포함되어 있으면 처리 Skip
                if any(media in title_lower for media in MEDIA_BLACK_LIST):
                    # 매체명 문자열만 구문에서 제거
                    for media in MEDIA_BLACK_LIST:
                        title_lower = title_lower.replace(media, '')
                
                # SEO 핵심 IT 엔티티 정규식 매칭
                for pattern, seo_tag in SEO_TECH_DICTIONARY:
                    if re.search(pattern, title_lower):
                        extracted_tags.append(seo_tag)

        except Exception as e:
            print(f"Error fetching {url}: {e}")
            
    # 빈도수 순으로 정렬
    counts = Counter(extracted_tags).most_common(10)
    
    final_keywords = []
    seen = set()
    
    for tag, score in counts:
        if tag not in seen:
            final_keywords.append(tag)
            seen.add(tag)
            
    # 10개가 안 채워졌거나 수집 결과가 부족할 경우 고품질 SEO 백업 키워드로 순차 채움
    if len(final_keywords) < 10:
        for fb_tag in FALLBACK_SEO_KEYWORDS:
            if fb_tag not in seen:
                final_keywords.append(fb_tag)
                seen.add(fb_tag)
            if len(final_keywords) >= 10:
                break
                
    return final_keywords[:10]

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

    raw_keywords = clean_and_extract_keywords()
    new_keywords = []
    rank = 1
    
    for kw in raw_keywords:
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
