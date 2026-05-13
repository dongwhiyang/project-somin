import os
import json
import streamlit as st
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv
from pipeline import (
    TUNING_MODELS, check_api_key, collect_gov_data,
    generate_draft, critique_with_gemini, revise_draft,
    tune_with_model, generate_seo_metadata, create_docx,
)

# ─────────────────────────────────────────────
# 환경변수 로드 (.env 파일에서 API 키를 읽어옵니다)
# ─────────────────────────────────────────────
load_dotenv(override=True)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# ─────────────────────────────────────────────
# 로컬 LLM 서버 설정 (LM Studio 등)
# 필요 시 아래 값을 수정하세요
# ─────────────────────────────────────────────
LOCAL_LLM_BASE_URL = "http://localhost:1234/v1"
LOCAL_LLM_MODEL_NAME = "google/gemma-4-e4b"

# ─────────────────────────────────────────────
# 페이지 설정
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="프로젝트 소민 | 블로그 주제 대시보드",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────
# CSS 스타일 (프리미엄 디자인)
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700;900&display=swap');

/* 전역 스타일 */
html, body, [class*="css"] {
    font-family: 'Noto Sans KR', sans-serif;
}

.stApp {
    background: linear-gradient(135deg, #0f0c29 0%, #1a1a3e 40%, #24243e 100%);
}

/* 헤더 */
.hero-header {
    text-align: center;
    padding: 2.5rem 1rem 1.5rem 1rem;
    margin-bottom: 1rem;
}
.hero-header h1 {
    font-size: 2.4rem;
    font-weight: 900;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0.3rem;
    letter-spacing: -0.5px;
}
.hero-header p {
    font-size: 1.05rem;
    color: #a0a0c0;
    font-weight: 300;
}

/* 카드 스타일 */
.genre-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 1.5rem;
    backdrop-filter: blur(12px);
    transition: all 0.3s ease;
    margin-bottom: 1rem;
}
.genre-card:hover {
    border-color: rgba(102, 126, 234, 0.4);
    box-shadow: 0 8px 32px rgba(102, 126, 234, 0.15);
    transform: translateY(-2px);
}
.genre-title {
    font-size: 1.15rem;
    font-weight: 700;
    color: #e0e0ff;
    margin-bottom: 0.8rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.genre-badge {
    font-size: 0.7rem;
    background: linear-gradient(135deg, #667eea, #764ba2);
    color: white;
    padding: 3px 10px;
    border-radius: 20px;
    font-weight: 500;
}
.topic-item {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px;
    padding: 0.8rem 1rem;
    margin-bottom: 0.5rem;
    color: #c8c8e0;
    font-size: 0.92rem;
    line-height: 1.5;
    transition: all 0.2s ease;
}
.topic-item:hover {
    background: rgba(102, 126, 234, 0.08);
    border-color: rgba(102, 126, 234, 0.25);
}

/* 상태 배지 */
.status-box {
    text-align: center;
    padding: 1rem;
    border-radius: 12px;
    margin: 1rem 0;
}
.status-loading {
    background: rgba(255, 193, 7, 0.08);
    border: 1px solid rgba(255, 193, 7, 0.2);
    color: #ffc107;
}
.status-success {
    background: rgba(0, 230, 118, 0.08);
    border: 1px solid rgba(0, 230, 118, 0.25);
    color: #00e676;
}

/* 선택 결과 카드 */
.result-card {
    background: linear-gradient(135deg, rgba(0,230,118,0.06) 0%, rgba(102,126,234,0.06) 100%);
    border: 1px solid rgba(0,230,118,0.25);
    border-radius: 16px;
    padding: 2rem;
    text-align: center;
    margin-top: 1.5rem;
}
.result-card h3 {
    color: #00e676;
    font-size: 1.3rem;
    margin-bottom: 0.5rem;
}
.result-card p {
    color: #c8c8e0;
    font-size: 1rem;
}

/* 데이터 통계 바 */
.stat-bar {
    display: flex;
    justify-content: center;
    gap: 2rem;
    padding: 1rem;
    margin-bottom: 1.5rem;
}
.stat-item {
    text-align: center;
}
.stat-number {
    font-size: 1.8rem;
    font-weight: 700;
    background: linear-gradient(135deg, #667eea, #f093fb);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.stat-label {
    font-size: 0.78rem;
    color: #888;
    margin-top: 2px;
}

/* 버튼 스타일 */
div.stButton > button {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    color: white !important;
    border: none !important;
    border-radius: 12px !important;
    padding: 0.7rem 2.5rem !important;
    font-size: 1rem !important;
    font-weight: 600 !important;
    font-family: 'Noto Sans KR', sans-serif !important;
    transition: all 0.3s ease !important;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3) !important;
    width: 100% !important;
}
div.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.5) !important;
}

/* 라디오 버튼 스타일 */
div[data-testid="stRadio"] label {
    color: #c8c8e0 !important;
    font-size: 0.95rem !important;
}
div[data-testid="stRadio"] label:hover {
    color: #e0e0ff !important;
}

/* 구분선 */
.divider {
    border: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(102,126,234,0.3), transparent);
    margin: 1.5rem 0;
}

/* 사이드바 숨기기 */
[data-testid="stSidebar"] { display: none; }

/* footer 숨기기 */
footer { visibility: hidden; }

/* 비교 카드 */
.compare-card {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 16px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    max-height: 500px;
    overflow-y: auto;
}
.compare-card h4 {
    font-size: 1rem;
    font-weight: 700;
    margin-bottom: 0.8rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid rgba(255,255,255,0.1);
}
.model-badge {
    display: inline-block;
    font-size: 0.7rem;
    padding: 3px 10px;
    border-radius: 20px;
    font-weight: 600;
    color: white;
}
.pipeline-step {
    background: rgba(102,126,234,0.08);
    border: 1px solid rgba(102,126,234,0.2);
    border-radius: 12px;
    padding: 1rem 1.2rem;
    margin: 0.5rem 0;
    color: #c8c8e0;
}

</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# 1단계: 데이터 읽기 (anchor_data 폴더)
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_anchor_data():
    """anchor_data 폴더의 .txt 파일들을 읽어 하나의 문자열로 합칩니다."""
    anchor_dir = Path("anchor_data")
    if not anchor_dir.exists():
        return "", 0
    
    txt_files = sorted(anchor_dir.glob("*.txt"))
    all_texts = []
    for txt_file in txt_files:
        try:
            content = txt_file.read_text(encoding="utf-8")
            # 너무 짧은 파일(57바이트 이하 = 빈 파일/오류)은 건너뜁니다
            if len(content.strip()) > 60:
                all_texts.append(f"[파일: {txt_file.name}]\n{content[:2000]}")  # 각 파일 앞부분 2000자
        except Exception:
            pass
    
    combined = "\n\n---\n\n".join(all_texts)
    return combined, len(txt_files)


# ─────────────────────────────────────────────
# 1-2단계: 웹 기반 트렌드 검색 (네이버)
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=3600)  # 1시간 캐시
def fetch_web_trends():
    """네이버 검색에서 토목 시험 관련 최신 트렌드 제목들을 수집합니다."""
    keywords = [
        "토목기사 출제경향 최신",
        "토목기사 시험 공부",
        "토목시공기술사 기출문제",
        "토질및기초기술사 기출문제",
        "토목 기술사 합격 전략",
        "건설 스마트 기술 토목",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    all_trends = []
    for keyword in keywords:
        try:
            # 네이버 블로그 검색
            url = f"https://search.naver.com/search.naver?where=blog&query={requests.utils.quote(keyword)}"
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # 블로그 검색 결과의 제목 추출
            titles = []
            for tag in soup.select("a.lnk_head, a.title_link, a.api_txt_lines.total_tit"):
                title_text = tag.get_text(strip=True)
                if title_text and len(title_text) > 5:
                    titles.append(title_text)
            
            if titles:
                trend_block = f"[웹 트렌드: {keyword}]\n" + "\n".join(f"- {t}" for t in titles[:7])
                all_trends.append(trend_block)
        except Exception:
            pass
    
    combined_trends = "\n\n".join(all_trends)
    trend_count = sum(len(block.split("\n")) - 1 for block in all_trends)  # 제목 수
    return combined_trends, trend_count


# ─────────────────────────────────────────────
# 2단계: LLM API 호출 (DeepSeek / 로컬 Gemma 분기)
# ─────────────────────────────────────────────
def call_llm_for_topics(text_data: str, web_trends: str = "", model_choice: str = "DeepSeek V4") -> dict:
    """
    선택된 LLM 모델로 블로그 주제 후보 9개를 생성합니다.
    model_choice에 따라 DeepSeek API 또는 로컬 LLM 서버로 라우팅됩니다.
    반환 형식: { "genres": [ { "genre": "장르명", "topics": ["주제1", "주제2", "주제3"] }, ... ] }
    """
    # ── API 클라이언트 분기 ──
    if model_choice == "DeepSeek V4 (상용 API)":
        client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
        )
        model_name = "deepseek-v4-flash"
    else:  # Gemma 4 E4b (로컬 LLM)
        client = OpenAI(
            api_key="lm-studio",  # 로컬 서버는 키 검증을 하지 않음
            base_url=LOCAL_LLM_BASE_URL,
        )
        model_name = LOCAL_LLM_MODEL_NAME

    system_prompt = """당신은 토목·건설 분야 전문 블로그 에디터입니다.
사용자가 제공하는 기출문제 데이터와 웹 트렌드 데이터를 종합 분석하여, 오늘 블로그에 포스팅하기 좋은 주제를 추천합니다.

응답 규칙:
1. 반드시 3개의 장르(대분류)를 선정하세요.
2. 각 장르별로 구체적인 주제 후보(소분류) 3개씩, 총 9개를 추천하세요.
3. 【중요】 각 주제(소분류) 제목 맨 앞에 반드시 관련 시험 카테고리를 아래 3개 중 하나로 표시하세요:
   - (토목기사)
   - (토목시공기술사)
   - (토질및기초기술사)
   예시: "(토목시공기술사) 스마트 건설과 디지털 트윈의 현장 적용 사례"
4. 각 주제는 블로그 포스팅 제목으로 바로 사용할 수 있을 만큼 구체적이고 매력적이어야 합니다.
5. 반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트를 붙이지 마세요.

{
  "genres": [
    {
      "genre": "장르명 (대분류)",
      "topics": ["(시험명) 주제1", "(시험명) 주제2", "(시험명) 주제3"]
    },
    {
      "genre": "장르명 (대분류)",
      "topics": ["(시험명) 주제1", "(시험명) 주제2", "(시험명) 주제3"]
    },
    {
      "genre": "장르명 (대분류)",
      "topics": ["(시험명) 주제1", "(시험명) 주제2", "(시험명) 주제3"]
    }
  ]
}"""

    user_prompt = f"""아래는 두 가지 데이터 소스입니다.

【1. 기출문제 데이터 (anchor_data)】
{text_data[:10000]}

【2. 웹 트렌드 데이터 (네이버 최신 검색 결과)】
{web_trends if web_trends else '(웹 트렌드 데이터 없음)'}

위 두 데이터를 종합 분석하여, 토목기사·토목시공기술사·토질및기초기술사 수험생들이 관심을 가질 블로그 주제 후보 9개를 JSON으로 응답해 주세요.
각 주제 제목 앞에 반드시 (토목기사), (토목시공기술사), (토질및기초기술사) 중 하나를 붙여주세요."""

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.8,
        max_tokens=2000,
    )

    raw_text = response.choices[0].message.content.strip()
    
    # JSON 파싱 (코드블록으로 감싸져 있을 수 있으므로 처리)
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
    raw_text = raw_text.strip()
    
    return json.loads(raw_text)


# ═════════════════════════════════════════════
#                  메인 UI
# ═════════════════════════════════════════════

# 헤더
st.markdown("""
<div class="hero-header">
    <h1>📝 프로젝트 소민</h1>
    <p>AI 기반 토목·건설 블로그 주제 추천 대시보드</p>
</div>
""", unsafe_allow_html=True)

# ─── 데이터 로드 ───
combined_text, file_count = load_anchor_data()
web_trends_text, trend_count = fetch_web_trends()

if file_count == 0:
    st.error("⚠️ `anchor_data` 폴더에 텍스트 파일이 없습니다. 먼저 `extract_pdfs.py`를 실행해 주세요.")
    st.stop()

# 통계 바
st.markdown(f"""
<div class="stat-bar">
    <div class="stat-item">
        <div class="stat-number">{file_count}</div>
        <div class="stat-label">분석 대상 파일 수</div>
    </div>
    <div class="stat-item">
        <div class="stat-number">{len(combined_text):,}</div>
        <div class="stat-label">총 텍스트 (글자)</div>
    </div>
    <div class="stat-item">
        <div class="stat-number">{trend_count}</div>
        <div class="stat-label">웹 트렌드 수집</div>
    </div>
    <div class="stat-item">
        <div class="stat-number">9</div>
        <div class="stat-label">추천 주제 후보</div>
    </div>
</div>
<hr class="divider">
""", unsafe_allow_html=True)

# ─── 주제 선정 AI 모델 선택 ───
st.markdown("### 🤖 주제 선정 AI 모델 선택")
model_choice = st.radio(
    "분석에 사용할 LLM을 선택하세요:",
    options=["DeepSeek V4 (상용 API)", "Gemma 4 E4b (무료 로컬 LLM)"],
    index=0,
    horizontal=True,
    help="DeepSeek V4는 클라우드 API, Gemma 4 E4b는 내 컴퓨터의 LM Studio에서 구동되는 로컬 모델입니다.",
)

# ─── API 키 확인 (DeepSeek 선택 시에만) ───
if model_choice == "DeepSeek V4 (상용 API)":
    if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == "sk-여기에_본인_API_키를_넣으세요":
        st.warning("🔑 `.env` 파일에 DeepSeek API 키를 설정해 주세요.")
        st.code("# .env 파일을 열어 아래 내용을 수정하세요\nDEEPSEEK_API_KEY=sk-여기에_실제_API키를_입력", language="bash")
        st.info("💡 API 키는 https://platform.deepseek.com 에서 발급받을 수 있습니다.")
        st.stop()
else:
    st.info(f"💻 로컬 LLM 서버 주소: `{LOCAL_LLM_BASE_URL}` | 모델: `{LOCAL_LLM_MODEL_NAME}`")

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# ─── LLM API 호출 (세션 상태로 캐싱) ───
if "topics_data" not in st.session_state:
    st.session_state.topics_data = None
if "selected_topic" not in st.session_state:
    st.session_state.selected_topic = None

# 분석 시작 버튼
col_left, col_center, col_right = st.columns([1, 2, 1])
with col_center:
    if st.session_state.topics_data is None:
        model_label = "DeepSeek V4" if "DeepSeek" in model_choice else "Gemma 4 E4b"
        if st.button(f"🚀 AI 주제 분석 시작 ({model_label})", use_container_width=True):
            with st.spinner(f"{model_label}가 기출문제 + 웹 트렌드를 종합 분석하고 있습니다..."):
                try:
                    data = call_llm_for_topics(combined_text, web_trends_text, model_choice)
                    st.session_state.topics_data = data
                    st.rerun()
                except ConnectionError:
                    st.error(f"🔌 로컬 LLM 서버({LOCAL_LLM_BASE_URL})에 연결할 수 없습니다.\nLM Studio가 켜져 있는지 확인해 주세요.")
                except Exception as e:
                    error_msg = str(e)
                    if "Connection" in error_msg or "refused" in error_msg or "connect" in error_msg.lower():
                        st.error(f"🔌 로컬 LLM 서버({LOCAL_LLM_BASE_URL})가 켜져 있는지 확인해 주세요.\n\n(상세 오류: {e})")
                    else:
                        st.error(f"API 호출 중 오류가 발생했습니다: {e}")
        st.stop()

# ─── 주제 후보 표시 ───
data = st.session_state.topics_data
genres = data.get("genres", [])

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# 아이콘 배열
genre_icons = ["🏗️", "🌊", "🔬"]
genre_colors = ["#667eea", "#f093fb", "#00e676"]

# 3열 레이아웃으로 장르별 카드 표시
cols = st.columns(3, gap="large")

# 모든 주제를 평탄화하여 라디오 버튼용 리스트 생성
all_topics = []
for g_idx, genre_info in enumerate(genres):
    genre_name = genre_info.get("genre", f"장르 {g_idx+1}")
    topics = genre_info.get("topics", [])
    
    icon = genre_icons[g_idx % len(genre_icons)]
    
    with cols[g_idx]:
        # 장르 카드 HTML
        topics_html = ""
        for t_idx, topic in enumerate(topics):
            label = f"{genre_name} → {topic}"
            all_topics.append(label)
            topics_html += f'<div class="topic-item">📌 {topic}</div>'
        
        st.markdown(f"""
        <div class="genre-card">
            <div class="genre-title">
                {icon} {genre_name}
                <span class="genre-badge">대분류 {g_idx+1}</span>
            </div>
            {topics_html}
        </div>
        """, unsafe_allow_html=True)

# ─── 주제 선택 인터랙션 ───
st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown("### 🎯 주제를 선택해 주세요")

selected = st.radio(
    "아래 9개의 후보 중 오늘 포스팅할 주제 1개를 선택하세요:",
    options=all_topics,
    index=0,
    label_visibility="collapsed",
)

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# ─── 문체 튜닝 AI 선택 ───
st.markdown("### 🎨 문체 튜닝 AI 모델 선택 (최대 3개)")
st.caption("초안은 DeepSeek V4가 작성하고, 아래에서 선택한 AI가 문체를 다듬습니다.")

tuning_cols = st.columns(len(TUNING_MODELS))
selected_models = []
for idx, (name, info) in enumerate(TUNING_MODELS.items()):
    with tuning_cols[idx]:
        has_key = check_api_key(info["env_key"])
        key_status = "✅" if has_key else "❌ 키 없음"
        disabled = not has_key
        if st.checkbox(f"{info['icon']} {name} {key_status}", disabled=disabled, key=f"tune_{name}"):
            selected_models.append(name)
            
        if info["env_key"] == "NVIDIA_API_KEY" and not has_key:
            st.caption("NVIDIA 무료 API 키가 필요합니다.")

if len(selected_models) > 3:
    st.warning("⚠️ 최대 3개까지만 선택할 수 있습니다. 처음 3개만 사용됩니다.")
    selected_models = selected_models[:3]

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# ─── 세션 상태 초기화 ───
for key, default in [
    ("draft_text", None), ("critique_text", None), ("revised_text", None),
    ("tuned_results", {}), ("seo_data", None), ("selected_topic", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

