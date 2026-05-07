"""
프로젝트 소민 — 실시간 실무 뉴스 스크래퍼
구글 뉴스 RSS를 사용하여 최신 건설/토목 실무 기사를 수집합니다.
키워드 풀에서 랜덤 3개를 선택하여 각각 최신 기사 제목 10개를 가져옵니다.
"""
import random
import requests
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# 실무 키워드 풀 (Pool)
# ─────────────────────────────────────────────
KEYWORD_POOL = [
    "설계변경",
    "물가변동 ESC",
    "산업안전보건관리비",
    "공사원가계산",
    "공기연장 간접비",
    "하도급법 유권해석",
    "표준품셈 개정",
    "중대재해처벌법 판례",
    "건설 품질관리계획서",
    "하자담보책임",
    "BIM 실무",
    "스마트 건설 신기술",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def scrape_google_news_rss(keyword: str, max_results: int = 10) -> list[str]:
    """
    구글 뉴스 RSS에서 키워드 관련 최신 기사 제목을 수집합니다.

    Args:
        keyword: 검색 키워드
        max_results: 최대 수집 기사 수

    Returns:
        기사 제목 리스트 (최대 max_results개)
    """
    try:
        encoded = requests.utils.quote(keyword)
        url = (
            f"https://news.google.com/rss/search"
            f"?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
        )
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.content, "xml")
        items = soup.find_all("item", limit=max_results)

        titles = []
        for item in items:
            title_tag = item.find("title")
            if title_tag and title_tag.text:
                # "기사 제목 - 언론사" 형식에서 제목만 추출
                raw = title_tag.text.strip()
                # 마지막 " - 언론사" 부분 제거
                if " - " in raw:
                    raw = raw.rsplit(" - ", 1)[0].strip()
                if len(raw) > 5:
                    titles.append(raw)

        return titles

    except Exception:
        return []


def scrape_all_keywords(n_random: int = 3) -> dict[str, list[str]]:
    """
    키워드 풀에서 랜덤으로 n_random개 선택 후 각각 구글 뉴스 RSS 수집.

    Args:
        n_random: 랜덤 선택 키워드 수 (기본 3)

    Returns:
        {keyword: [title1, title2, ...]} 딕셔너리
    """
    selected = random.sample(KEYWORD_POOL, min(n_random, len(KEYWORD_POOL)))
    results = {}
    for kw in selected:
        titles = scrape_google_news_rss(kw, max_results=10)
        results[kw] = titles
    return results


def format_news_for_prompt(news_dict: dict[str, list[str]]) -> str:
    """
    수집된 뉴스를 LLM 프롬프트용 텍스트로 변환합니다.

    Args:
        news_dict: scrape_all_keywords() 반환값

    Returns:
        포맷된 뉴스 텍스트 문자열
    """
    if not news_dict:
        return "(최신 실무 뉴스 수집 실패)"

    lines = ["[최신 실무 뉴스 헤드라인 (구글 뉴스 RSS)]"]
    total = 0
    for kw, titles in news_dict.items():
        if not titles:
            continue
        lines.append(f"\n▶ 키워드: {kw}")
        for i, t in enumerate(titles, 1):
            lines.append(f"  {i}. {t}")
            total += 1
    lines.append(f"\n(총 {total}건 수집)")
    return "\n".join(lines)


# ═════════════════════════════════════════════
#  신규: 경쟁 블로그 스크래핑 로직 (벤치마킹용)
# ═════════════════════════════════════════════
def scrape_competitor_blogs(topic: str, max_results: int = 2) -> list[str]:
    """
    DuckDuckGo를 통해 주어진 주제와 관련된 상위 블로그 게시글 2~3개를 검색하고,
    해당 블로그의 본문 텍스트를 추출하여 반환합니다.
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return []

    try:
        query = f"{topic} 블로그"
        # ddgs 패키지 버전 호환성 고려
        try:
            results = DDGS().text(query, max_results=max_results)
        except AttributeError:
            # 구버전
            results = DDGS().text(keywords=query, max_results=max_results)
            
        texts = []
        for r in results:
            url = r.get('href', r.get('link', ''))
            if not url:
                continue
            try:
                resp = requests.get(url, timeout=10, headers=HEADERS)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.content, 'html.parser')
                    # 블로그 본문일 확률이 높은 태그 위주로 수집 (p, div.se-main-container 등)
                    paragraphs = soup.find_all('p')
                    text = ' '.join([p.text.strip() for p in paragraphs if p.text.strip()])
                    if len(text) > 100:
                        # 너무 길면 토큰 제한을 위해 1500자로 제한
                        texts.append(f"【출처: {url}】\n{text[:1500]}")
            except Exception:
                pass
        return texts
    except Exception as e:
        print(f"Competitor scraping error: {e}")
        return []


def load_anchor_data():
    from pathlib import Path
    anchor_dir = Path("anchor_data")
    if not anchor_dir.exists():
        return "", 0
    txt_files = sorted(anchor_dir.glob("*.txt"))
    all_texts = []
    for f in txt_files:
        try:
            content = f.read_text(encoding="utf-8")
            if len(content.strip()) > 60:
                all_texts.append(f"[파일: {f.name}]\n{content[:2000]}")
        except Exception:
            pass
    return "\n\n---\n\n".join(all_texts), len(txt_files)


def fetch_news_data():
    """실무 키워드 풀에서 랜덤 3개로 구글 뉴스 RSS 수집"""
    news_dict = scrape_all_keywords(n_random=3)
    news_text = format_news_for_prompt(news_dict)
    
    total_count = sum(len(v) for v in news_dict.values())
    selected_kws = list(news_dict.keys())
    
    return news_text, total_count, selected_kws
