import streamlit as st
import os
import json
import re
import concurrent.futures
from datetime import datetime
from dotenv import load_dotenv

# 내부 모듈
from scraper import fetch_news_data, load_anchor_data
from pipeline import (
    call_llama_for_topics,
    generate_draft,
    critique_with_qwen,
    critique_with_mistral_small,
    generate_image_from_nvidia,
    revise_with_deepseek,
    generate_seo_metadata,
    collect_gov_data
)
from blogger_publisher import BloggerPublisher

# 환경변수 로드
load_dotenv(override=True)

# ─────────────────────────────────────────────
# 🎨 페이지 설정 및 스타일
# ─────────────────────────────────────────────
st.set_page_config(page_title="Project Somin V2.2", page_icon="🏗️", layout="wide")

st.markdown("""
<style>
    .main { background-color: #0e1117; color: #ffffff; }
    .stButton>button { border-radius: 8px; font-weight: bold; height: 3em; transition: all 0.3s; }
    .stButton>button:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(102,126,234,0.4); }
    .stProgress > div > div > div > div { background-image: linear-gradient(to right, #667eea, #764ba2); }
    .status-card { background: rgba(255,255,255,0.05); padding: 20px; border-radius: 15px; border-left: 5px solid #667eea; }
    h1, h2, h3 { font-family: 'Inter', sans-serif; }
    .divider { height: 2px; background: linear-gradient(to right, transparent, #667eea, transparent); margin: 20px 0; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# ⚙️ 자동화 상태 관리 함수
# ─────────────────────────────────────────────
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
    # 1. 로컬 파일 저장
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f)
        
    # 2. 스트림릿 클라우드 환경이면 깃허브 저장소에도 직접 업데이트 (동기화)
    is_streamlit = os.getenv("STREAMLIT_RUNTIME", "") != "" or "STREAMLIT_SERVER_PORT" in os.environ
    if is_streamlit:
        try:
            import streamlit as st
            import requests
            import base64
            
            token = st.secrets.get("GITHUB_TOKEN", "")
            if token:
                repo = "dongwhiyang/project-somin"
                path = "automation_status.json"
                url = f"https://api.github.com/repos/{repo}/contents/{path}"
                headers = {
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github.v3+json"
                }
                
                # 기존 파일의 SHA 키 가져오기 (덮어쓰기 위해 필요)
                get_resp = requests.get(url, headers=headers)
                sha = ""
                if get_resp.status_code == 200:
                    sha = get_resp.json().get("sha", "")
                    
                # 새 상태값 업로드
                content = json.dumps(status, indent=2).encode('utf-8')
                b64_content = base64.b64encode(content).decode('utf-8')
                data = {
                    "message": "Update automation status from Streamlit UI",
                    "content": b64_content,
                    "sha": sha
                }
                requests.put(url, headers=headers, json=data)
        except Exception as e:
            print(f"GitHub Sync Error: {e}")

# ─────────────────────────────────────────────
# 세션 상태 초기화
# ─────────────────────────────────────────────
defaults = {
    'phase': 0,
    'topics_data': None,
    'selected_topic': None,
    'draft_text': None,
    'combined_critique': None,
    'image_paths': [],
    'tuned_text': None,
    'seo_data': None,
    'auto_mode': False
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

if 'auto_mode' not in st.session_state:
    st.session_state.auto_mode = load_automation_status()["enabled"]

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
    if "<li>" in html:
        html = html.replace("<li>", "<ul><li>", 1).replace("</li><br><ul>", "</li>")
    return html

# ═════════════════════════════════════════════
#  메인 UI
# ═════════════════════════════════════════════
st.markdown("""
<div style="text-align: center; padding: 20px;">
    <h1 style="background: linear-gradient(to right, #667eea, #f093fb); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 3em;">
        PROJECT SOMIN V2.2
    </h1>
    <p style="color: #a0aec0; font-size: 1.2em;">실무 융합형 원스톱 블로깅 파이프라인</p>
</div>
""", unsafe_allow_html=True)

# 상단 메뉴 버튼 및 자동화 토글
col_btn1, col_btn2, col_btn3, col_auto = st.columns([1, 1, 1, 1.5])
with col_btn1:
    st.link_button("🌐 블로그 바로가기", "https://project-somin.blogspot.com/", use_container_width=True)
with col_btn2:
    st.link_button("🛠 블로그 관리", "https://www.blogger.com/", use_container_width=True)
with col_btn3:
    st.link_button("🐙 깃허브 저장소", "https://github.com/dongwhiyang/project-somin", use_container_width=True)

with col_auto:
    auto_toggle = st.toggle(
        "🤖 **완전 자동화 가동**", 
        value=st.session_state.auto_mode,
        help="켜두면 4~5시간 간격으로 AI가 알아서 글을 씁니다. (수동 버튼 비활성화)"
    )
    if auto_toggle != st.session_state.auto_mode:
        st.session_state.auto_mode = auto_toggle
        status = load_automation_status()
        status["enabled"] = auto_toggle
        save_automation_status(status)
        st.rerun()

st.markdown("---")

if st.session_state.auto_mode:
    status = load_automation_status()
    st.info(f"🚀 **현재 완전 자동화 파이프라인이 가동 중입니다.** 수동 조작은 제한됩니다.")
    if status.get("last_run"):
        last_dt = datetime.fromtimestamp(status["last_run"]).strftime('%Y-%m-%d %H:%M:%S')
        st.caption(f"최근 실행 시각: {last_dt}")

# ─── 데이터 로드 ───
@st.cache_data(ttl=3600)
def load_anchor_data_cached():
    import scraper
    return scraper.load_anchor_data()

combined_text, file_count = load_anchor_data_cached()

# ═════════════════════════════════════════════
#  Phase 0: 주제 선정
# ═════════════════════════════════════════════
if st.session_state.phase == 0:
    btn_disabled = st.session_state.auto_mode

    st.subheader("📍 Phase 1. 스마트 주제 선정")
    
    if st.button("🔍 최신 건설 뉴스 분석 및 주제 제안", use_container_width=True, disabled=btn_disabled):
        with st.spinner("최신 뉴스 검색 및 기출문제 분석 중..."):
            news_text = fetch_news_data()
            topics_data = call_llama_for_topics(combined_text, news_text)
            st.session_state.topics_data = topics_data
            st.rerun()

    if st.session_state.topics_data:
        data = st.session_state.topics_data
        exam_topics = data.get("exam_topics", [])
        field_topics = data.get("field_topics", [])
        all_topics = exam_topics + field_topics

        selected_topic = st.radio("추천 주제를 선택하세요:", all_topics, disabled=btn_disabled)
        
        st.markdown("---")
        st.subheader("⚡ 원스톱 생성 및 바로 발행")
        if st.button("🚀 원스톱 생성 및 바로 발행 시작", use_container_width=True, type="primary", disabled=btn_disabled):
            st.session_state.selected_topic = selected_topic
            st.session_state.phase = 1
            st.rerun()
            
        if st.button("🔄 주제 새로 생성하기", use_container_width=True, disabled=btn_disabled):
            st.session_state.topics_data = None
            st.rerun()

# ─────────────────────────────────────────────
# Phase 1: 파이프라인 자동 실행
# ─────────────────────────────────────────────
elif st.session_state.phase == 1:
    topic_only = re.sub(r"^\(.*?\)\s*", "", st.session_state.selected_topic).strip()
    
    with st.status("⚙️ 파이프라인 실행 중...", expanded=True) as status:
        st.write("🏢 정부 공공 API 데이터 수집 중...")
        gov_data_text, _ = collect_gov_data(topic_only)

        st.write("📝 [1/4] 기술 초안 작성 중...")
        draft = generate_draft(topic_only, combined_text, gov_data_text, "")
        st.session_state.draft_text = draft

        st.write("🔍 [2/4] 교차 비판 중...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            fut_q = executor.submit(critique_with_qwen, draft, topic_only)
            fut_m = executor.submit(critique_with_mistral_small, draft, topic_only)
            critique_q = fut_q.result()
            critique_m = fut_m.result()
        combined_crit = f"【Qwen 비판】\n{critique_q}\n\n【Mistral 비판】\n{critique_m}"
        st.session_state.combined_critique = combined_crit

        st.write("🎨 [3/4] 이미지 생성 중...")
        image_prompts = re.findall(r'\[IMAGE_PROMPT:\s*(.*?)\]', combined_crit, re.DOTALL)
        image_paths = []
        for idx, p in enumerate(image_prompts[:3]):
            path = generate_image_from_nvidia(p, idx)
            if path: image_paths.append(path)
        st.session_state.image_paths = image_paths

        st.write("🤖 [4/4] 최종 포스팅 작성 및 SEO 메타데이터 생성 중...")
        final_report = revise_with_deepseek(draft, combined_crit, topic_only, image_paths=image_paths)
        st.session_state.tuned_text = final_report
        st.session_state.seo_data = generate_seo_metadata(topic_only, final_report)

        status.update(label="✅ 파이프라인 완료!", state="complete", expanded=False)

    # 발행 로직
    html_content = md_to_html(st.session_state.tuned_text)
    seo_tags = st.session_state.seo_data.get("seo_tags", []) if st.session_state.seo_data else []
    
    pub = BloggerPublisher(headless=True)
    pub_result = pub.publish(title=topic_only, html_content=html_content, tags=seo_tags)
    
    if pub_result["success"]:
        st.success(f"🎊 블로그 발행 성공! {pub_result['url']}")
    else:
        st.error(f"❌ 발행 실패: {pub_result['message']}")

    if st.button("홈으로 돌아가기"):
        st.session_state.phase = 0
        st.rerun()

# ─────────────────────────────────────────────
# Phase 2: 결과 대시보드 (수동 모드용)
# ─────────────────────────────────────────────
elif st.session_state.phase == 2:
    st.subheader("📄 생성된 포스팅 미리보기")
    st.markdown(st.session_state.tuned_text, unsafe_allow_html=True)
    if st.button("홈으로 돌아가기"):
        st.session_state.phase = 0
        st.rerun()
