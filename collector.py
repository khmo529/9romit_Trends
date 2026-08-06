import os, json, re, datetime, xml.etree.ElementTree as ET
from collections import Counter
import requests

MEDIA_BLACK_LIST = {
    '매일경제', '조선일보', '핀포인트뉴스', '한국경제', '중앙일보', '동아일보',
    '한겨레', '이데일리', '디지털타임스', '머니투데이', '연합뉴스', '뉴스1', '뉴시스'
}
GENERIC_BLACK_LIST = {
    '차세대','가격','실적','전망','분석','시장','기업','공개','출시','발표','사업',
    '한국','세계','속보','주요','오늘','내일','올해','내년','상반기','하반기'
}

# 2026년 기준 최신 매핑 - 구체적인 것부터 위로!
SEO_TECH_DICTIONARY = [
    (r'iphone 17|아이폰 17', '아이폰 17 Pro'),
    (r'iphone|아이폰', '아이폰 17 Pro'), # 구형 16 대신 17로 통일
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

FALLBACK_SEO_KEYWORDS = [
    'ChatGPT-5', '아이폰 17 Pro', 'NVIDIA Blackwell Ultra',
    '갤럭시 Z폴드7', 'Google Gemini 2.0', '온디바이스 AI',
    'Claude 4 Sonnet', 'HBM3e 반도체', 'DeepSeek V3', '테슬라 자율주행 (FSD)'
]

def clean_and_extract_keywords():
    urls = [
        "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=ko&gl=KR&ceid=KR:ko",
        "https://news.hada.io/rss/news"
    ]
    extracted_tags = []
    headers = {'User-Agent': 'Mozilla/5.0 Chrome/120.0.0.0'}
    
    for url in urls:
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code != 200: continue
            root = ET.fromstring(res.content)
            for item in root.findall('.//item'):
                title = (item.find('title').text or '')
                # 언론사 꼬리표만 제거, 본문은 유지
                title_clean = re.sub(r'\s*-\s*[^-]{2,20}$', '', title).strip()
                title_lower = title_clean.lower()

                # 블랙리스트는 단어 경계로만 제거
                skip = False
                for bad in MEDIA_BLACK_LIST:
                    if bad.lower() in title_lower and len(bad) > 2:
                        # 기자명이면 스킵하지 말고 단어만 제거
                        title_lower = title_lower.replace(bad.lower(), '')

                for pattern, seo_tag in SEO_TECH_DICTIONARY:
                    if re.search(pattern, title_lower, re.IGNORECASE):
                        extracted_tags.append(seo_tag)
                        break # 한 제목당 1개만
        except Exception as e:
            print(f"Error {url}: {e}")

    counts = Counter(extracted_tags).most_common(10)
    final_keywords, seen = [], set()
    for tag, _ in counts:
        if tag not in seen:
            final_keywords.append(tag)
            seen.add(tag)

    # 10개 못 채우면 FALLBACK으로 채움
    for fb in FALLBACK_SEO_KEYWORDS:
        if fb not in seen:
            final_keywords.append(fb)
            seen.add(fb)
        if len(final_keywords) >= 10: break
            
    return final_keywords[:10]

def process_and_push():
    history_file = 'trending_history.json'
    old_ranks = {}
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                old_data = json.load(f)
                old_ranks = {item['kw'].lower(): item['rank'] for item in old_data.get('keywords', [])}
        except: pass

    raw_keywords = clean_and_extract_keywords()
    new_keywords = []
    for rank, kw in enumerate(raw_keywords, 1):
        kw_lower = kw.lower()
        if kw_lower in old_ranks:
            diff = old_ranks[kw_lower] - rank
            delta_str, delta_type = (f"▲ {diff}", "up") if diff>0 else (f"▼ {abs(diff)}", "down") if diff<0 else ("-", "same")
        else:
            delta_str, delta_type = "NEW", "new"
        new_keywords.append({"rank": rank, "top": rank<=3, "kw": kw, "delta": delta_str, "type": delta_type})

    now_kst = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).strftime('%Y-%m-%d %H:%M')
    payload = {"updated_at": now_kst, "keywords": new_keywords}

    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # WordPress 푸시
    wp_url = os.environ.get('WP_URL','').rstrip('/')
    wp_secret = os.environ.get('WP_SECRET','')
    if wp_url and wp_secret:
        try:
            requests.post(f"{wp_url}/wp-json/g9/v1/update-trends",
                          json=payload, headers={"Content-Type":"application/json","X-G9-Token":wp_secret}, timeout=10)
        except Exception as e:
            print(f"WP Push fail: {e}")

if __name__ == "__main__":
    process_and_push()
