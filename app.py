import os
import json
import re
import random
import concurrent.futures
import streamlit as st
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv
from scraper import scrape_all_keywords, format_news_for_prompt, scrape_competitor_blogs
from pipeline import (
    TUNING_MODELS, check_api_key, collect_gov_data,
    analyze_competitors_with_deepseek, generate_draft, critique_with_qwen, critique_with_mistral_small,
    generate_image_from_nvidia,
    revise_with_deepseek, tune_with_mistral, generate_seo_metadata, create_docx,
    auto_pick_topic,
)
from tistory_publisher import TistoryPublisher
from blogger_publisher import BloggerPublisher
import base64

# ⚙️ 자동화 상태 관리 함수
STATUS_FILE = "automation_status.json"

def load_automation_status():
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"enabled": False, "last_run": 0, "next_run": 0}

def save_automation_status(status):
    # 1. 로컬 저장
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f, indent=2)
    # 2. 깃허브 동기화
    is_streamlit = os.getenv("STREAMLIT_RUNTIME", "") != "" or "STREAMLIT_SERVER_PORT" in os.environ
    if is_streamlit:
        try:
            import streamlit as st
            token = st.secrets.get("GITHUB_TOKEN", "")
            if token:
                repo = "dongwhiyang/project-somin"
                url = f"https://api.github.com/repos/{repo}/contents/{STATUS_FILE}"
                headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
                get_resp = requests.get(url, headers=headers)
                sha = get_resp.json().get("sha", "") if get_resp.status_code == 200 else ""
                content = json.dumps(status, indent=2).encode("utf-8")
                b64_content = base64.b64encode(content).decode("utf-8")
                requests.put(url, headers=headers, json={"message": "Sync status from UI", "content": b64_content, "sha": sha})
        except: pass

# ─────────────────────────────────────────────
# 환경변수 로드
# ─────────────────────────────────────────────
load_dotenv(override=True)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

LOCAL_LLM_BASE_URL  = "http://localhost:1234/v1"
LOCAL_LLM_MODEL_NAME = "google/gemma-4-e4b"

# ─────────────────────────────────────────────
# 페이지 설정
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="프로젝트 소민 V2.2 | 실무 융합형 원스톱 파이프라인",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────
# CSS 스타일
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700;900&display=swap');

html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }

.stApp { background: linear-gradient(135deg, #0f0c29 0%, #1a1a3e 40%, #24243e 100%); }

.hero-header { text-align: center; padding: 2.5rem 1rem 1.5rem 1rem; margin-bottom: 1rem; }
.hero-header h1 {
    font-size: 2.4rem; font-weight: 900;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
    margin-bottom: 0.3rem; letter-spacing: -0.5px;
}
.hero-header p { font-size: 1.05rem; color: #a0a0c0; font-weight: 300; }

.section-title {
    font-size: 1.1rem; font-weight: 700; color: #e0e0ff;
    padding: 0.6rem 1rem; border-radius: 10px; margin-bottom: 0.8rem;
    display: flex; align-items: center; gap: 0.5rem;
}
.section-exam { background: rgba(102,126,234,0.15); border-left: 3px solid #667eea; }
.section-field { background: rgba(240,147,251,0.12); border-left: 3px solid #f093fb; }

.topic-radio label { color: #c8c8e0 !important; font-size: 0.93rem !important; }
.topic-radio label:hover { color: #ffffff !important; }

.stat-bar { display: flex; justify-content: center; gap: 2rem; padding: 1rem; margin-bottom: 1.5rem; }
.stat-item { text-align: center; }
.stat-number {
    font-size: 1.8rem; font-weight: 700;
    background: linear-gradient(135deg, #667eea, #f093fb);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.stat-label { font-size: 0.78rem; color: #888; margin-top: 2px; }

div.stButton > button {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    color: white !important; border: none !important; border-radius: 12px !important;
    padding: 0.7rem 2.5rem !important; font-size: 1rem !important;
    font-weight: 600 !important; font-family: 'Noto Sans KR', sans-serif !important;
    transition: all 0.3s ease !important; box-shadow: 0 4px 15px rgba(102,126,234,0.3) !important;
    width: 100% !important;
}
div.stButton > button:hover { transform: translateY(-2px) !important; box-shadow: 0 6px 20px rgba(102,126,234,0.5) !important; }

.model-badge {
    display: inline-block; font-size: 0.7rem; padding: 3px 10px;
    border-radius: 20px; font-weight: 600; color: white; margin: 2px;
}
.divider { border: 0; height: 1px; background: linear-gradient(90deg, transparent, rgba(102,126,234,0.3), transparent); margin: 1.5rem 0; }
[data-testid="stSidebar"] { display: none; }
footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# 데이터 로딩 함수들
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=300)
def load_anchor_data():
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


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_news_data():
    """실무 키워드 풀에서 랜덤 3개로 구글 뉴스 RSS 수집"""
    news_dict = scrape_all_keywords(n_random=3)
    formatted = format_news_for_prompt(news_dict)
    total = sum(len(v) for v in news_dict.values())
    return formatted, total, list(news_dict.keys())


def md_to_html(md_text):
    import re
    html = md_text
    
    # 1. 굵게 **text** -> <b>text</b>
    html = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', html)
    
    # 2. 이미지 마크다운 ![alt](url) -> <img src="url" alt="alt">
    html = re.sub(r'!\[(.*?)\]\((.*?)\)', r'<img src="\2" alt="\1" style="max-width:100%; height:auto;"><br>', html)
    
    # 3. 제목 처리 (### -> <h3>, ## -> <h2>)
    html = re.sub(r'^### (.*?)$', r'<h3 style="color: #2c3e50; border-left: 5px solid #667eea; padding-left: 10px; margin-top: 25px;">\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.*?)$', r'<h2 style="color: #1a1a3e; background: #f8f9fa; padding: 10px; border-radius: 5px; margin-top: 30px;">\1</h2>', html, flags=re.MULTILINE)
    
    # 4. 리스트 처리 (- item -> <li>item</li>)
    html = re.sub(r'^\- (.*?)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    
    # 5. 줄바꿈 처리
    html = html.replace("\n", "<br>")
    
    # 리스트 태그 감싸기 (간단한 처리)
    if "<li>" in html:
        html = html.replace("<li>", "<ul><li>", 1).replace("</li><br><ul>", "</li>")
        
    return html

# ─────────────────────────────────────────────
# 주제 생성: NVIDIA Llama 3 70B 사용
# ─────────────────────────────────────────────
def call_llama_for_topics(anchor_text: str, news_text: str) -> dict:
    """
    NVIDIA Llama 3 70B 모델로 수험 4개 + 실무 2개, 총 6개 주제 생성.
    반환: {"exam": ["주제1",...], "field": ["주제5","주제6"]}
    """
    from litellm import completion

    system_prompt = """Role: 너는 10년 차 파워블로거이자, 건설사 공무 출신으로 현재 토목건설 계약 및 감독 업무를 총괄하는 현직 공무원이야.
Goal: 제공된 기출문제 데이터와 웹 스크래핑 뉴스를 조합해서, 수험생과 실무자 모두의 이목을 끌 수 있는 아주 흥미롭고 실용적인 블로그 주제 6개를 제안해 줘.

규칙:
1. "exam" 키: 기출문제 기반 수험 정보 주제 4개 (토목기사/토목시공기술사/토질및기초기술사 중 하나를 앞에 태그)
2. "field" 키: 최신 실무 뉴스 기반 현장 가이드 주제 2개 (실무 태그 붙임)
3. 각 주제는 블로그 제목으로 쓸 수 있을 정도로 구체적이고 매력적이어야 함
4. 반드시 아래 JSON 형식으로만 응답 (다른 텍스트 금지):

{
  "exam": [
    "(토목기사) 주제1",
    "(토목시공기술사) 주제2",
    "(토질및기초기술사) 주제3",
    "(토목기사) 주제4"
  ],
  "field": [
    "(실무가이드) 주제5",
    "(실무가이드) 주제6"
  ]
}"""

    user_prompt = f"""【기출문제 데이터】\n{anchor_text[:6000]}\n\n【최신 실무 뉴스 헤드라인】\n{news_text[:2000]}\n\n위 데이터를 종합해서 수험 주제 4개 + 실무 주제 2개를 JSON으로 응답하세요."""

    kwargs = {
        "model": "openai/meta/llama-3.1-70b-instruct",
        "api_base": "https://integrate.api.nvidia.com/v1",
        "api_key": os.getenv("NVIDIA_API_KEY", ""),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.8,
        "max_tokens": 1500,
    }

    response = completion(**kwargs)
    raw = response.choices[0].message.content.strip()
    
    # JSON 추출 (코드블록 제거)
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        raw = match.group(1)
    else:
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1:
            raw = raw[start:end + 1]

    parsed = json.loads(raw.strip())
    # 최소 보장
    if "exam" not in parsed:
        parsed["exam"] = []
    if "field" not in parsed:
        parsed["field"] = []
    return parsed


# ─────────────────────────────────────────────
# 세션 상태 초기화
# ─────────────────────────────────────────────
defaults = {
    "topics_data": None,
    "selected_topic": None,
    "draft_text": None,
    "combined_critique": None,
    "final_report": None,
    "tuned_text": None,
    "seo_data": None,
    "image_paths": [],
    "phase": 0,
    "auto_mode": False,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

if 'auto_pilot' not in st.session_state:
    st.session_state.auto_pilot = load_automation_status()["enabled"]


# ═════════════════════════════════════════════
#  헤더
# ═════════════════════════════════════════════
st.markdown("""
<div class="hero-header">
    <h1>📝 프로젝트 소민 V2.2</h1>
    <p>실무 융합형 원스톱 AI 블로그 파이프라인 | 수험 정보 + 현장 실무를 한 번에</p>
</div>
""", unsafe_allow_html=True)

# ─── 데이터 로드 ───
combined_text, file_count = load_anchor_data()

if file_count == 0:
    st.error("⚠️ `anchor_data` 폴더에 텍스트 파일이 없습니다. 먼저 `extract_pdfs.py`를 실행해 주세요.")
    st.stop()

with st.spinner("📡 최신 실무 뉴스를 수집하고 있습니다..."):
    news_text, news_count, selected_kws = fetch_news_data()

# 통계 바
st.markdown(f"""
<div class="stat-bar">
    <div class="stat-item">
        <div class="stat-number">{file_count}</div>
        <div class="stat-label">기출문제 파일</div>
    </div>
    <div class="stat-item">
        <div class="stat-number">{len(combined_text):,}</div>
        <div class="stat-label">텍스트 글자수</div>
    </div>
    <div class="stat-item">
        <div class="stat-number">{news_count}</div>
        <div class="stat-label">실무 뉴스 수집</div>
    </div>
    <div class="stat-item">
        <div class="stat-number">6</div>
        <div class="stat-label">주제 후보</div>
    </div>
</div>
<hr class="divider">
""", unsafe_allow_html=True)

# ── [신규] 상단 바로가기 링크 섹션 ──
link_col1, link_col2, link_col3, link_auto = st.columns([1, 1, 1, 1.5])
with link_col1:
    st.markdown(f'<a href="https://project-somin.blogspot.com/" target="_blank" style="text-decoration: none;"><div style="background: rgba(102,126,234,0.1); padding: 10px; border-radius: 10px; text-align: center; color: #667eea; border: 1px solid #667eea; font-weight: bold;">📝 블로그 바로가기</div></a>', unsafe_allow_html=True)
with link_col2:
    st.markdown(f'<a href="https://www.blogger.com/blog/posts/8783571704512221638?hl=ko&tab=jj" target="_blank" style="text-decoration: none;"><div style="background: rgba(240,147,251,0.1); padding: 10px; border-radius: 10px; text-align: center; color: #f093fb; border: 1px solid #f093fb; font-weight: bold;">⚙️ 블로그 관리/편집</div></a>', unsafe_allow_html=True)
with link_col3:
    st.markdown(f'<a href="https://github.com/dongwhiyang/project-somin" target="_blank" style="text-decoration: none;"><div style="background: rgba(255,255,255,0.05); padding: 10px; border-radius: 10px; text-align: center; color: #ffffff; border: 1px solid #ffffff; font-weight: bold;">🐙 깃허브 저장소</div></a>', unsafe_allow_html=True)
with link_auto:
    auto_val = st.toggle("🤖 **완전 자동화 가동**", value=st.session_state.auto_pilot, help="4~5시간 간격 무인 발행 모드")
    if auto_val != st.session_state.auto_pilot:
        st.session_state.auto_pilot = auto_val
        status = load_automation_status()
        status["enabled"] = auto_val
        save_automation_status(status)
        st.rerun()

if st.session_state.auto_pilot:
    st.info("🚀 **현재 완전 자동화 파이프라인이 가동 중입니다.** (수동 버튼 잠금)")

st.markdown('<div style="height: 20px;"></div>', unsafe_allow_html=True)

if selected_kws:
    st.caption(f"📡 오늘의 실무 키워드: {' | '.join(selected_kws)}")

# ═════════════════════════════════════════════
#  Phase 0: 주제 선정
# ═════════════════════════════════════════════
if st.session_state.phase == 0:

    # 주제 생성 버튼
    if st.session_state.topics_data is None:
        col_l, col_c1, col_c2, col_r = st.columns([0.5, 2, 2, 0.5])
        with col_c1:
            if st.button("🧠 AI 주제 분석 시작", use_container_width=True, disabled=st.session_state.auto_pilot):
                with st.spinner(f"NVIDIA Llama 3 70B가 기출문제 + 실무 뉴스를 분석 중..."):
                    try:
                        data = call_llama_for_topics(combined_text, news_text)
                        st.session_state.topics_data = data
                        st.session_state.auto_mode = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"오류 발생: {e}")
        
        with col_c2:
            if st.button("🚀 자동 주제 선정 및 즉시 발행", use_container_width=True, disabled=st.session_state.auto_pilot):
                with st.spinner(f"AI가 최적의 주제를 선정하고 발행까지 자동으로 진행합니다..."):
                    try:
                        # 1. 주제 생성
                        data = call_llama_for_topics(combined_text, news_text)
                        st.session_state.topics_data = data
                        
                        # 2. 최적 주제 선정
                        picked_topic = auto_pick_topic(data)
                        st.session_state.selected_topic = picked_topic
                        st.session_state.auto_mode = True
                        
                        # 3. 페이지 리로드하여 즉시 파이프라인 진입 유도 (Phase 1으로 변경)
                        st.session_state.phase = 1
                        st.rerun()
                    except Exception as e:
                        st.error(f"자동 진행 중 오류 발생: {e}")
        
        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        st.markdown("### ✍️ 커스텀 주제/프롬프트 직접 입력")
        user_prompt = st.text_area(
            "AI 분석 대신 직접 원하는 주제나 상세 요청 사항을 입력할 수 있습니다.",
            placeholder="예: 서울시 고용개선지원비 개정 지침을 활용하여 실무자용 원가계산 예시를 포함한 글을 써줘.",
            height=120,
            key="user_custom_prompt"
        )
        col_la, col_ca, col_ra = st.columns([1, 2, 1])
        with col_ca:
            if st.button("🚀 커스텀 주제로 즉시 발행", use_container_width=True, disabled=st.session_state.auto_pilot):
                if user_prompt.strip():
                    st.session_state.selected_topic = user_prompt.strip()
                    st.session_state.auto_mode = True
                    st.session_state.phase = 1
                    st.rerun()
                else:
                    st.warning("내용을 입력해 주세요.")
        st.stop()

    # ─── 주제 목록 표시 ───
    data = st.session_state.topics_data
    exam_topics = data.get("exam", [])
    field_topics = data.get("field", [])
    all_topics = exam_topics + field_topics

    if not all_topics:
        st.warning("주제 생성에 실패했습니다. 다시 시도해 주세요.")
        if st.button("🔄 다시 시도"):
            st.session_state.topics_data = None
            st.rerun()
        st.stop()

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    col_left, col_right = st.columns(2, gap="large")

    with col_left:
        st.markdown('<div class="section-title section-exam">📘 수험 정보 주제 (기출문제 분석)</div>', unsafe_allow_html=True)
        exam_choice = st.radio(
            "수험 정보",
            options=exam_topics if exam_topics else ["(수험 주제 없음)"],
            label_visibility="collapsed",
            key="radio_exam",
        )

    with col_right:
        st.markdown('<div class="section-title section-field">👷 실무 가이드 주제 (최신 뉴스 기반)</div>', unsafe_allow_html=True)
        field_choice = st.radio(
            "실무 가이드",
            options=field_topics if field_topics else ["(실무 주제 없음)"],
            label_visibility="collapsed",
            key="radio_field",
        )

    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown("### 🎯 최종 주제 선택")

    # 통합 라디오: 두 그룹 합쳐서 최종 1개 선택
    selected_recommendation = st.radio(
        "위에서 관심 가는 주제를 선택하세요 (수험 4개 + 실무 2개):",
        options=all_topics,
        index=0,
        key="radio_final",
    )

    # 자동 선택 모드일 경우 즉시 실행 로직 적용
    auto_trigger = False
    if st.session_state.auto_mode and st.session_state.selected_topic:
        auto_trigger = True
        final_choice = st.session_state.selected_topic
        st.success(f"🤖 선정된 주제/프롬프트: **{final_choice}**")
    else:
        # AI 분석 후 선택 모드일 경우 라디오 버튼 값 사용
        final_choice = selected_recommendation

    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.info("✍️ 4단계 파이프라인: 수집 → 초안 → 병렬 비판 → 이미지 생성 및 최종 수정")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🚀 원스톱 블로그 자동 생성", use_container_width=True, disabled=st.session_state.auto_pilot):
            st.session_state.selected_topic = final_choice
            st.session_state.phase = 1
            st.rerun()

    # 주제 재생성 버튼
# ─────────────────────────────────────────────
# Phase 1: 파이프라인 자동 실행
# ─────────────────────────────────────────────
if st.session_state.phase == 1:
    final_choice = st.session_state.selected_topic
    if not final_choice:
        st.error("선택된 주제가 없습니다.")
        st.session_state.phase = 0
        st.rerun()

    topic_only = re.sub(r"^\(.*?\)\s*", "", final_choice).strip()

    st.info(f"🎯 **선택된 주제:** {final_choice}")

    # ── 1단계: 공공 API 데이터 수집 ──
    with st.status("⚙️ 원스톱 파이프라인 실행 중...", expanded=True) as status:
        st.write("🏢 정부 공공 API 데이터 수집 중...")
        gov_data_text, gov_count = collect_gov_data(topic_only)

        # ── 1.5단계: 경쟁 블로그 벤치마킹 ──
        st.write("🕵️ 상위 노출 경쟁 블로그 벤치마킹 분석 중...")
        try:
            comp_texts = scrape_competitor_blogs(topic_only)
            comp_analysis = analyze_competitors_with_deepseek(topic_only, comp_texts) if comp_texts else ""
        except Exception as e:
            comp_analysis = ""
            st.warning(f"경쟁 블로그 분석 실패 (진행은 계속됩니다): {e}")

        # ── 2단계: DeepSeek V4 초안 ──
        st.write("📝 [1/5] DeepSeek V4 기술 초안 작성 중...")
        try:
            draft = generate_draft(topic_only, combined_text, gov_data_text, comp_analysis)
            st.session_state.draft_text = draft
        except Exception as e:
            status.update(label="❌ 초안 작성 실패", state="error")
            st.error(f"초안 작성 오류: {e}")
            st.stop()

        # ── 3단계: Qwen + Mistral Small 병렬 비판 ──
        st.write("🔍 [2/5] Qwen & Mistral Small 교차 비판 중 (병렬)...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            fut_q = executor.submit(critique_with_qwen, draft, topic_only)
            fut_m = executor.submit(critique_with_mistral_small, draft, topic_only)
            try:
                critique_q = fut_q.result()
            except Exception as e:
                critique_q = f"[Qwen 비판 실패] {e}"
            try:
                critique_m = fut_m.result()
            except Exception as e:
                critique_m = f"[Mistral Small 비판 실패] {e}"

        combined_crit = (
            f"【팩트/논리 비판 (Qwen 2.5 72B)】\n{critique_q}"
            f"\n\n---\n\n【구조/가독성 비판 (Mistral Small)】\n{critique_m}"
        )
        st.session_state.combined_critique = combined_crit

        # ── 4단계: 이미지 자동 생성 ──
        st.write("🎨 [3/5] AI가 블로그용 삽화를 생성하는 중 (NVIDIA SDXL)...")
        image_prompts = re.findall(r'\[IMAGE_PROMPT:\s*(.*?)\]', combined_crit, re.DOTALL)
        image_paths = []
        for idx, prompt in enumerate(image_prompts[:3]):
            with st.spinner(f"이미지 {idx+1} 생성 중..."):
                path = generate_image_from_nvidia(prompt, idx)
                if path:
                    image_paths.append(path)
        st.session_state.image_paths = image_paths

        # ── 5단계: DeepSeek 최종 수정 및 이미지 삽입 ──
        st.write("🤖 [4/4] DeepSeek V4 최종 블로그 포스팅 작성 중...")
        try:
            final_report = revise_with_deepseek(draft, combined_crit, topic_only, image_paths=image_paths)
            st.session_state.final_report = final_report
            st.session_state.tuned_text = final_report
        except Exception as e:
            status.update(label="❌ 최종 보고서 작성 실패", state="error")
            st.error(f"최종 보고서 오류: {e}")
            st.stop()

        # ── SEO ──
        st.write("🔍 SEO 메타데이터 생성 중...")
        try:
            st.session_state.seo_data = generate_seo_metadata(topic_only, st.session_state.tuned_text)
        except Exception:
            st.session_state.seo_data = None

        status.update(label="✅ 원스톱 파이프라인 완료!", state="complete", expanded=False)

        # ── [신규] 자동 발행 모드이 경우 즉시 블로그 발행 실행 ──
        if st.session_state.get("auto_mode"):
            st.write("🚀 [자동 모드] 구글 블로그에 즉시 발행 중...")
            try:
                html_content = md_to_html(st.session_state.tuned_text)
                seo_tags = st.session_state.seo_data.get("seo_tags", []) if st.session_state.seo_data else []
                
                # Streamlit Secrets 또는 환경 변수에서 BLOGGER_BLOG_ID 가져오기
                blog_id = os.getenv("BLOGGER_BLOG_ID", "")
                if not blog_id and "BLOGGER_BLOG_ID" in st.secrets:
                    blog_id = st.secrets["BLOGGER_BLOG_ID"]

                if blog_id:
                    pub = BloggerPublisher()
                    pub_result = pub.publish(title=topic_only, html_content=html_content, tags=seo_tags)
                    if pub_result["success"]:
                        st.success(f"🎊 블로그 자동 발행 성공! {pub_result['message']}")
                    else:
                        st.error(f"❌ 자동 발행 실패: {pub_result['message']}")
                else:
                    st.warning("⚠️ 자동 발행 실패: BLOGGER_BLOG_ID가 설정되지 않았습니다.")
            except Exception as e:
                st.error(f"자동 발행 중 오류: {e}")

    st.session_state.phase = 2
    st.rerun()


# ═════════════════════════════════════════════
#  Phase 2: 결과 대시보드
# ═════════════════════════════════════════════
if st.session_state.phase == 2:
    topic_full = st.session_state.selected_topic or ""
    topic_short = re.sub(r"^\(.*?\)\s*", "", topic_full).strip()
    tuned_text  = st.session_state.tuned_text or ""
    seo         = st.session_state.seo_data

    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown(f"### ✅ 원스톱 파이프라인 완료 — **{topic_short}**")

    # ── 최종 결과물 ──
    st.markdown("#### ✍️ 완성된 블로그 포스팅")
    st.markdown(tuned_text)

    # ── 단계별 중간 결과 (접기) ──
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    with st.expander("📝 1단계 — DeepSeek 초안 (원본)", expanded=False):
        st.markdown(st.session_state.draft_text or "_초안 없음_")

    with st.expander("🔍 2단계 — Qwen + Mistral Small 교차 비판", expanded=False):
        st.markdown(st.session_state.combined_critique or "_비판 데이터 없음_")

    with st.expander("🤖 3단계 — DeepSeek 최종 수정본", expanded=False):
        st.markdown(st.session_state.final_report or "_최종 보고서 없음_")

    with st.expander("🎨 4단계 — AI 생성 이미지 목록", expanded=False):
        imgs = st.session_state.image_paths
        if imgs:
            cols = st.columns(len(imgs))
            for i, p in enumerate(imgs):
                cols[i].image(p, caption=f"생성된 이미지 {i+1}")
        else:
            st.info("생성된 이미지가 없습니다. API 상태를 확인해 주세요.")

    # ── SEO ──
    with st.expander("🔍 SEO 메타데이터", expanded=False):
        if seo:
            tag_html = " ".join([
                f'<span class="model-badge" style="background:#667eea;">#{t}</span>'
                for t in seo.get("seo_tags", [])
            ])
            st.markdown(tag_html, unsafe_allow_html=True)
            st.markdown(f"**메타 설명:** {seo.get('meta_description', '')}")
            for i, alt in enumerate(seo.get("image_alt_texts", []), 1):
                st.markdown(f"{i}. {alt}")
        else:
            st.caption("SEO 데이터 생성 실패")

    # ── 내보내기 버튼 ──
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    col_d1, col_d2, col_d3 = st.columns(3)

    with col_d1:
        # 워드 다운로드 이슈로 인해 마크다운(.md) 파일로 저장하도록 변경
        md_content = f"# {topic_short}\n\n{tuned_text}"
        if seo:
            md_content += f"\n\n## SEO 메타데이터\n- 태그: {', '.join(seo.get('seo_tags', []))}\n- 설명: {seo.get('meta_description', '')}"
            
        # 파일명에서 특수문자 제거 (안전한 파일명 생성)
        safe_filename = re.sub(r'[\\/*?:"<>|]', "", topic_short)[:30]
        if not safe_filename: safe_filename = "블로그_포스팅"
        
        st.download_button(
            label="📥 마크다운(.md) 다운로드",
            data=md_content.encode('utf-8'),
            file_name=f"{safe_filename}.md",
            mime="text/markdown",
            use_container_width=True,
        )

    with col_d2:
        seo_tags = seo.get("seo_tags", []) if seo else []
        
        html_content = md_to_html(tuned_text)
        
        # Streamlit Secrets 또는 환경 변수에서 BLOGGER_BLOG_ID 가져오기
        blog_id = os.getenv("BLOGGER_BLOG_ID", "")
        if not blog_id and "BLOGGER_BLOG_ID" in st.secrets:
            blog_id = st.secrets["BLOGGER_BLOG_ID"]
            
        can_publish = bool(blog_id)

        if not can_publish:
            st.warning("⚠️ 환경 변수 또는 Streamlit Secrets에 BLOGGER_BLOG_ID를 설정하세요")

        if st.button("🚀 구글 블로그 자동 발행", use_container_width=True, disabled=not can_publish):
            with st.spinner("Blogger API를 통해 안전하게 발행 중..."):
                try:
                    pub = BloggerPublisher()
                    result = pub.publish(title=topic_short, html_content=html_content, tags=seo_tags)
                    if result["success"]:
                        st.success(f"✅ {result['message']}")
                    else:
                        st.error(f"❌ 발행 실패: {result['message']}")
                except Exception as e:
                    st.error(f"❌ 시스템 오류: {e}")

    with col_d3:
        with st.expander("💻 HTML 코드 복사", expanded=False):
            preview = f"<h2>{topic_short}</h2>\n\n{tuned_text}"
            if seo:
                preview += f"\n\n<p><b>태그:</b> {', '.join(seo.get('seo_tags', []))}</p>"
            st.code(preview, language="html")

    # ── 새로 시작 버튼 ──
    st.markdown("")
    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_b:
        if st.button("🔄 새로운 주제 분석하기", use_container_width=True):
            for k in defaults:
                st.session_state[k] = defaults[k]
            fetch_news_data.clear()
            load_anchor_data.clear()
            st.rerun()

    st.markdown('<div style="height: 50px;"></div>', unsafe_allow_html=True)
