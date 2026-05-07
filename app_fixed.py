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

# ?????????????????????????????????????????????
# ?섍꼍蹂??濡쒕뱶
# ?????????????????????????????????????????????
load_dotenv(override=True)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

LOCAL_LLM_BASE_URL  = "http://localhost:1234/v1"
LOCAL_LLM_MODEL_NAME = "google/gemma-4-e4b"

# ?????????????????????????????????????????????
# ?섏씠吏 ?ㅼ젙
# ?????????????????????????????????????????????
st.set_page_config(
    page_title="?꾨줈?앺듃 ?뚮? V2.2 | ?ㅻТ ?듯빀???먯뒪???뚯씠?꾨씪??,
    page_icon="?뱷",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ?????????????????????????????????????????????
# CSS ?ㅽ???# ?????????????????????????????????????????????
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


# ?????????????????????????????????????????????
# ?곗씠??濡쒕뵫 ?⑥닔??# ?????????????????????????????????????????????
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
                all_texts.append(f"[?뚯씪: {f.name}]\n{content[:2000]}")
        except Exception:
            pass
    return "\n\n---\n\n".join(all_texts), len(txt_files)


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_news_data():
    """?ㅻТ ?ㅼ썙????먯꽌 ?쒕뜡 3媛쒕줈 援ш? ?댁뒪 RSS ?섏쭛"""
    news_dict = scrape_all_keywords(n_random=3)
    formatted = format_news_for_prompt(news_dict)
    total = sum(len(v) for v in news_dict.values())
    return formatted, total, list(news_dict.keys())


def md_to_html(md_text):
    import re
    html = md_text
    
    # 1. 援듦쾶 **text** -> <b>text</b>
    html = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', html)
    
    # 2. ?대?吏 留덊겕?ㅼ슫 ![alt](url) -> <img src="url" alt="alt">
    html = re.sub(r'!\[(.*?)\]\((.*?)\)', r'<img src="\2" alt="\1" style="max-width:100%; height:auto;"><br>', html)
    
    # 3. ?쒕ぉ 泥섎━ (### -> <h3>, ## -> <h2>)
    html = re.sub(r'^### (.*?)$', r'<h3 style="color: #2c3e50; border-left: 5px solid #667eea; padding-left: 10px; margin-top: 25px;">\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.*?)$', r'<h2 style="color: #1a1a3e; background: #f8f9fa; padding: 10px; border-radius: 5px; margin-top: 30px;">\1</h2>', html, flags=re.MULTILINE)
    
    # 4. 由ъ뒪??泥섎━ (- item -> <li>item</li>)
    html = re.sub(r'^\- (.*?)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    
    # 5. 以꾨컮轅?泥섎━
    html = html.replace("\n", "<br>")
    
    # 由ъ뒪???쒓렇 媛먯떥湲?(媛꾨떒??泥섎━)
    if "<li>" in html:
        html = html.replace("<li>", "<ul><li>", 1).replace("</li><br><ul>", "</li>")
        
    return html

# ?????????????????????????????????????????????
# 二쇱젣 ?앹꽦: NVIDIA Llama 3 70B ?ъ슜
# ?????????????????????????????????????????????
def call_llama_for_topics(anchor_text: str, news_text: str) -> dict:
    """
    NVIDIA Llama 3 70B 紐⑤뜽濡??섑뿕 4媛?+ ?ㅻТ 2媛? 珥?6媛?二쇱젣 ?앹꽦.
    諛섑솚: {"exam": ["二쇱젣1",...], "field": ["二쇱젣5","二쇱젣6"]}
    """
    from litellm import completion

    system_prompt = """Role: ?덈뒗 10??李??뚯썙釉붾줈嫄곗씠?? 嫄댁꽕??怨듬Т 異쒖떊?쇰줈 ?꾩옱 ?좊ぉ嫄댁꽕 怨꾩빟 諛?媛먮룆 ?낅Т瑜?珥앷큵?섎뒗 ?꾩쭅 怨듬Т?먯씠??
Goal: ?쒓났??湲곗텧臾몄젣 ?곗씠?곗? ???ㅽ겕?섑븨 ?댁뒪瑜?議고빀?댁꽌, ?섑뿕?앷낵 ?ㅻТ??紐⑤몢???대ぉ???????덈뒗 ?꾩＜ ?λ?濡?퀬 ?ㅼ슜?곸씤 釉붾줈洹?二쇱젣 6媛쒕? ?쒖븞??以?

洹쒖튃:
1. "exam" ?? 湲곗텧臾몄젣 湲곕컲 ?섑뿕 ?뺣낫 二쇱젣 4媛?(?좊ぉ湲곗궗/?좊ぉ?쒓났湲곗닠???좎쭏諛뤾린珥덇린?좎궗 以??섎굹瑜??욎뿉 ?쒓렇)
2. "field" ?? 理쒖떊 ?ㅻТ ?댁뒪 湲곕컲 ?꾩옣 媛?대뱶 二쇱젣 2媛?(?ㅻТ ?쒓렇 遺숈엫)
3. 媛?二쇱젣??釉붾줈洹??쒕ぉ?쇰줈 ?????덉쓣 ?뺣룄濡?援ъ껜?곸씠怨?留ㅻ젰?곸씠?댁빞 ??4. 諛섎뱶???꾨옒 JSON ?뺤떇?쇰줈留??묐떟 (?ㅻⅨ ?띿뒪??湲덉?):

{
  "exam": [
    "(?좊ぉ湲곗궗) 二쇱젣1",
    "(?좊ぉ?쒓났湲곗닠?? 二쇱젣2",
    "(?좎쭏諛뤾린珥덇린?좎궗) 二쇱젣3",
    "(?좊ぉ湲곗궗) 二쇱젣4"
  ],
  "field": [
    "(?ㅻТ媛?대뱶) 二쇱젣5",
    "(?ㅻТ媛?대뱶) 二쇱젣6"
  ]
}"""

    user_prompt = f"""?먭린異쒕Ц???곗씠?겹?n{anchor_text[:6000]}\n\n?먯턀???ㅻТ ?댁뒪 ?ㅻ뱶?쇱씤??n{news_text[:2000]}\n\n???곗씠?곕? 醫낇빀?댁꽌 ?섑뿕 二쇱젣 4媛?+ ?ㅻТ 二쇱젣 2媛쒕? JSON?쇰줈 ?묐떟?섏꽭??"""

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
    
    # JSON 異붿텧 (肄붾뱶釉붾줉 ?쒓굅)
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        raw = match.group(1)
    else:
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1:
            raw = raw[start:end + 1]

    parsed = json.loads(raw.strip())
    # 理쒖냼 蹂댁옣
    if "exam" not in parsed:
        parsed["exam"] = []
    if "field" not in parsed:
        parsed["field"] = []
    return parsed


# ?????????????????????????????????????????????
# ?몄뀡 ?곹깭 珥덇린??# ?????????????????????????????????????????????
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


# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧??#  ?ㅻ뜑
# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧??st.markdown("""
<div class="hero-header">
    <h1>?뱷 ?꾨줈?앺듃 ?뚮? V2.2</h1>
    <p>?ㅻТ ?듯빀???먯뒪??AI 釉붾줈洹??뚯씠?꾨씪??| ?섑뿕 ?뺣낫 + ?꾩옣 ?ㅻТ瑜???踰덉뿉</p>
</div>
""", unsafe_allow_html=True)

# ??? ?곗씠??濡쒕뱶 ???
combined_text, file_count = load_anchor_data()

if file_count == 0:
    st.error("?좑툘 `anchor_data` ?대뜑???띿뒪???뚯씪???놁뒿?덈떎. 癒쇱? `extract_pdfs.py`瑜??ㅽ뻾??二쇱꽭??")
    st.stop()

with st.spinner("?뱻 理쒖떊 ?ㅻТ ?댁뒪瑜??섏쭛?섍퀬 ?덉뒿?덈떎..."):
    news_text, news_count, selected_kws = fetch_news_data()

# ?듦퀎 諛?st.markdown(f"""
<div class="stat-bar">
    <div class="stat-item">
        <div class="stat-number">{file_count}</div>
        <div class="stat-label">湲곗텧臾몄젣 ?뚯씪</div>
    </div>
    <div class="stat-item">
        <div class="stat-number">{len(combined_text):,}</div>
        <div class="stat-label">?띿뒪??湲?먯닔</div>
    </div>
    <div class="stat-item">
        <div class="stat-number">{news_count}</div>
        <div class="stat-label">?ㅻТ ?댁뒪 ?섏쭛</div>
    </div>
    <div class="stat-item">
        <div class="stat-number">6</div>
        <div class="stat-label">二쇱젣 ?꾨낫</div>
    </div>
</div>
<hr class="divider">
""", unsafe_allow_html=True)

# ?? [?좉퇋] ?곷떒 諛붾줈媛湲?留곹겕 ?뱀뀡 ??
link_col1, link_col2, link_col3 = st.columns(3)
with link_col1:
    st.markdown(f'<a href="https://project-somin.blogspot.com/" target="_blank" style="text-decoration: none;"><div style="background: rgba(102,126,234,0.1); padding: 10px; border-radius: 10px; text-align: center; color: #667eea; border: 1px solid #667eea; font-weight: bold;">?뱷 釉붾줈洹?諛붾줈媛湲?/div></a>', unsafe_allow_html=True)
with link_col2:
    st.markdown(f'<a href="https://www.blogger.com/blog/posts/8783571704512221638?hl=ko&tab=jj" target="_blank" style="text-decoration: none;"><div style="background: rgba(240,147,251,0.1); padding: 10px; border-radius: 10px; text-align: center; color: #f093fb; border: 1px solid #f093fb; font-weight: bold;">?숋툘 釉붾줈洹?愿由??몄쭛</div></a>', unsafe_allow_html=True)
with link_col3:
    st.markdown(f'<a href="https://github.com/dongwhiyang/project-somin" target="_blank" style="text-decoration: none;"><div style="background: rgba(255,255,255,0.05); padding: 10px; border-radius: 10px; text-align: center; color: #ffffff; border: 1px solid #ffffff; font-weight: bold;">?릻 源껎뿀釉???μ냼</div></a>', unsafe_allow_html=True)

st.markdown('<div style="height: 20px;"></div>', unsafe_allow_html=True)

if selected_kws:
    st.caption(f"?뱻 ?ㅻ뒛???ㅻТ ?ㅼ썙?? {' | '.join(selected_kws)}")

# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧??#  Phase 0: 二쇱젣 ?좎젙
# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧??if st.session_state.phase == 0:

    # 二쇱젣 ?앹꽦 踰꾪듉
    if st.session_state.topics_data is None:
        col_l, col_c1, col_c2, col_r = st.columns([0.5, 2, 2, 0.5])
        with col_c1:
            if st.button("?쭬 AI 二쇱젣 遺꾩꽍 ?쒖옉", use_container_width=True):
                with st.spinner(f"NVIDIA Llama 3 70B媛 湲곗텧臾몄젣 + ?ㅻТ ?댁뒪瑜?遺꾩꽍 以?.."):
                    try:
                        data = call_llama_for_topics(combined_text, news_text)
                        st.session_state.topics_data = data
                        st.session_state.auto_mode = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"?ㅻ쪟 諛쒖깮: {e}")
        
        with col_c2:
            if st.button("?? ?먮룞 二쇱젣 ?좎젙 諛?利됱떆 諛쒗뻾", use_container_width=True):
                with st.spinner(f"AI媛 理쒖쟻??二쇱젣瑜??좎젙?섍퀬 諛쒗뻾源뚯? ?먮룞?쇰줈 吏꾪뻾?⑸땲??.."):
                    try:
                        # 1. 二쇱젣 ?앹꽦
                        data = call_llama_for_topics(combined_text, news_text)
                        st.session_state.topics_data = data
                        
                        # 2. 理쒖쟻 二쇱젣 ?좎젙
                        picked_topic = auto_pick_topic(data)
                        st.session_state.selected_topic = picked_topic
                        st.session_state.auto_mode = True
                        
                        # 3. ?섏씠吏 由щ줈?쒗븯??利됱떆 ?뚯씠?꾨씪??吏꾩엯 ?좊룄 (Phase 1?쇰줈 蹂寃?
                        st.session_state.phase = 1
                        st.rerun()
                    except Exception as e:
                        st.error(f"?먮룞 吏꾪뻾 以??ㅻ쪟 諛쒖깮: {e}")
        
        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        st.markdown("### ?랃툘 而ㅼ뒪? 二쇱젣/?꾨＼?꾪듃 吏곸젒 ?낅젰")
        user_prompt = st.text_area(
            "AI 遺꾩꽍 ???吏곸젒 ?먰븯??二쇱젣???곸꽭 ?붿껌 ?ы빆???낅젰?????덉뒿?덈떎.",
            placeholder="?? ?쒖슱??怨좎슜媛쒖꽑吏?먮퉬 媛쒖젙 吏移⑥쓣 ?쒖슜?섏뿬 ?ㅻТ?먯슜 ?먭?怨꾩궛 ?덉떆瑜??ы븿??湲???⑥쨾.",
            height=120,
            key="user_custom_prompt"
        )
        col_la, col_ca, col_ra = st.columns([1, 2, 1])
        with col_ca:
            if st.button("?? 而ㅼ뒪? 二쇱젣濡?利됱떆 諛쒗뻾", use_container_width=True):
                if user_prompt.strip():
                    st.session_state.selected_topic = user_prompt.strip()
                    st.session_state.auto_mode = True
                    st.session_state.phase = 1
                    st.rerun()
                else:
                    st.warning("?댁슜???낅젰??二쇱꽭??")
        st.stop()

    # ??? 二쇱젣 紐⑸줉 ?쒖떆 ???
    data = st.session_state.topics_data
    exam_topics = data.get("exam", [])
    field_topics = data.get("field", [])
    all_topics = exam_topics + field_topics

    if not all_topics:
        st.warning("二쇱젣 ?앹꽦???ㅽ뙣?덉뒿?덈떎. ?ㅼ떆 ?쒕룄??二쇱꽭??")
        if st.button("?봽 ?ㅼ떆 ?쒕룄"):
            st.session_state.topics_data = None
            st.rerun()
        st.stop()

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    col_left, col_right = st.columns(2, gap="large")

    with col_left:
        st.markdown('<div class="section-title section-exam">?뱲 ?섑뿕 ?뺣낫 二쇱젣 (湲곗텧臾몄젣 遺꾩꽍)</div>', unsafe_allow_html=True)
        exam_choice = st.radio(
            "?섑뿕 ?뺣낫",
            options=exam_topics if exam_topics else ["(?섑뿕 二쇱젣 ?놁쓬)"],
            label_visibility="collapsed",
            key="radio_exam",
        )

    with col_right:
        st.markdown('<div class="section-title section-field">?뫕 ?ㅻТ 媛?대뱶 二쇱젣 (理쒖떊 ?댁뒪 湲곕컲)</div>', unsafe_allow_html=True)
        field_choice = st.radio(
            "?ㅻТ 媛?대뱶",
            options=field_topics if field_topics else ["(?ㅻТ 二쇱젣 ?놁쓬)"],
            label_visibility="collapsed",
            key="radio_field",
        )

    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown("### ?렞 理쒖쥌 二쇱젣 ?좏깮")

    # ?듯빀 ?쇰뵒?? ??洹몃９ ?⑹퀜??理쒖쥌 1媛??좏깮
    selected_recommendation = st.radio(
        "?꾩뿉??愿??媛??二쇱젣瑜??좏깮?섏꽭??(?섑뿕 4媛?+ ?ㅻТ 2媛?:",
        options=all_topics,
        index=0,
        key="radio_final",
    )

    # ?먮룞 ?좏깮 紐⑤뱶??寃쎌슦 利됱떆 ?ㅽ뻾 濡쒖쭅 ?곸슜
    auto_trigger = False
    if st.session_state.auto_mode and st.session_state.selected_topic:
        auto_trigger = True
        final_choice = st.session_state.selected_topic
        st.success(f"?쨼 ?좎젙??二쇱젣/?꾨＼?꾪듃: **{final_choice}**")
    else:
        # AI 遺꾩꽍 ???좏깮 紐⑤뱶??寃쎌슦 ?쇰뵒??踰꾪듉 媛??ъ슜
        final_choice = selected_recommendation

    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.info("?랃툘 4?④퀎 ?뚯씠?꾨씪?? ?섏쭛 ??珥덉븞 ??蹂묐젹 鍮꾪뙋 ???대?吏 ?앹꽦 諛?理쒖쥌 ?섏젙")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("?? ?먯뒪??釉붾줈洹??먮룞 ?앹꽦", use_container_width=True):
            st.session_state.selected_topic = final_choice
            st.session_state.phase = 1
            st.rerun()

    # 二쇱젣 ?ъ깮??踰꾪듉
# ?????????????????????????????????????????????
# Phase 1: ?뚯씠?꾨씪???먮룞 ?ㅽ뻾
# ?????????????????????????????????????????????
if st.session_state.phase == 1:
    final_choice = st.session_state.selected_topic
    if not final_choice:
        st.error("?좏깮??二쇱젣媛 ?놁뒿?덈떎.")
        st.session_state.phase = 0
        st.rerun()

    topic_only = re.sub(r"^\(.*?\)\s*", "", final_choice).strip()

    st.info(f"?렞 **?좏깮??二쇱젣:** {final_choice}")

    # ?? 1?④퀎: 怨듦났 API ?곗씠???섏쭛 ??
    with st.status("?숋툘 ?먯뒪???뚯씠?꾨씪???ㅽ뻾 以?..", expanded=True) as status:
        st.write("?룫 ?뺣? 怨듦났 API ?곗씠???섏쭛 以?..")
        gov_data_text, gov_count = collect_gov_data(topic_only)

        # ?? 1.5?④퀎: 寃쎌웳 釉붾줈洹?踰ㅼ튂留덊궧 ??
        st.write("?빑截??곸쐞 ?몄텧 寃쎌웳 釉붾줈洹?踰ㅼ튂留덊궧 遺꾩꽍 以?..")
        try:
            comp_texts = scrape_competitor_blogs(topic_only)
            comp_analysis = analyze_competitors_with_deepseek(topic_only, comp_texts) if comp_texts else ""
        except Exception as e:
            comp_analysis = ""
            st.warning(f"寃쎌웳 釉붾줈洹?遺꾩꽍 ?ㅽ뙣 (吏꾪뻾? 怨꾩냽?⑸땲??: {e}")

        # ?? 2?④퀎: DeepSeek V4 珥덉븞 ??
        st.write("?뱷 [1/5] DeepSeek V4 湲곗닠 珥덉븞 ?묒꽦 以?..")
        try:
            draft = generate_draft(topic_only, combined_text, gov_data_text, comp_analysis)
            st.session_state.draft_text = draft
        except Exception as e:
            status.update(label="??珥덉븞 ?묒꽦 ?ㅽ뙣", state="error")
            st.error(f"珥덉븞 ?묒꽦 ?ㅻ쪟: {e}")
            st.stop()

        # ?? 3?④퀎: Qwen + Mistral Small 蹂묐젹 鍮꾪뙋 ??
        st.write("?뵇 [2/5] Qwen & Mistral Small 援먯감 鍮꾪뙋 以?(蹂묐젹)...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            fut_q = executor.submit(critique_with_qwen, draft, topic_only)
            fut_m = executor.submit(critique_with_mistral_small, draft, topic_only)
            try:
                critique_q = fut_q.result()
            except Exception as e:
                critique_q = f"[Qwen 鍮꾪뙋 ?ㅽ뙣] {e}"
            try:
                critique_m = fut_m.result()
            except Exception as e:
                critique_m = f"[Mistral Small 鍮꾪뙋 ?ㅽ뙣] {e}"

        combined_crit = (
            f"?먰뙥???쇰━ 鍮꾪뙋 (Qwen 2.5 72B)??n{critique_q}"
            f"\n\n---\n\n?먭뎄議?媛?낆꽦 鍮꾪뙋 (Mistral Small)??n{critique_m}"
        )
        st.session_state.combined_critique = combined_crit

        # ?? 4?④퀎: ?대?吏 ?먮룞 ?앹꽦 ??
        st.write("?렓 [3/5] AI媛 釉붾줈洹몄슜 ?쏀솕瑜??앹꽦?섎뒗 以?(NVIDIA SDXL)...")
        image_prompts = re.findall(r'\[IMAGE_PROMPT:\s*(.*?)\]', combined_crit, re.DOTALL)
        image_paths = []
        for idx, prompt in enumerate(image_prompts[:3]):
            with st.spinner(f"?대?吏 {idx+1} ?앹꽦 以?.."):
                path = generate_image_from_nvidia(prompt, idx)
                if path:
                    image_paths.append(path)
        st.session_state.image_paths = image_paths

        # ?? 5?④퀎: DeepSeek 理쒖쥌 ?섏젙 諛??대?吏 ?쎌엯 ??
        st.write("?쨼 [4/4] DeepSeek V4 理쒖쥌 釉붾줈洹??ъ뒪???묒꽦 以?..")
        try:
            final_report = revise_with_deepseek(draft, combined_crit, topic_only, image_paths=image_paths)
            st.session_state.final_report = final_report
            st.session_state.tuned_text = final_report
        except Exception as e:
            status.update(label="??理쒖쥌 蹂닿퀬???묒꽦 ?ㅽ뙣", state="error")
            st.error(f"理쒖쥌 蹂닿퀬???ㅻ쪟: {e}")
            st.stop()

        # ?? SEO ??
        st.write("?뵇 SEO 硫뷀??곗씠???앹꽦 以?..")
        try:
            st.session_state.seo_data = generate_seo_metadata(topic_only, st.session_state.tuned_text)
        except Exception:
            st.session_state.seo_data = None

        status.update(label="???먯뒪???뚯씠?꾨씪???꾨즺!", state="complete", expanded=False)

        # ?? [?좉퇋] ?먮룞 諛쒗뻾 紐⑤뱶??寃쎌슦 利됱떆 釉붾줈洹?諛쒗뻾 ?ㅽ뻾 ??
        if st.session_state.get("auto_mode"):
            st.write("?? [?먮룞 紐⑤뱶] 援ш? 釉붾줈洹몄뿉 利됱떆 諛쒗뻾 以?..")
            try:
                html_content = md_to_html(st.session_state.tuned_text)
                seo_tags = st.session_state.seo_data.get("seo_tags", []) if st.session_state.seo_data else []
                
                # Streamlit Secrets ?먮뒗 ?섍꼍 蹂?섏뿉??BLOGGER_BLOG_ID 媛?몄삤湲?                blog_id = os.getenv("BLOGGER_BLOG_ID", "")
                if not blog_id and "BLOGGER_BLOG_ID" in st.secrets:
                    blog_id = st.secrets["BLOGGER_BLOG_ID"]

                if blog_id:
                    pub = BloggerPublisher(headless=True)
                    pub_result = pub.publish(title=topic_only, html_content=html_content, tags=seo_tags)
                    if pub_result["success"]:
                        st.success(f"?럧 釉붾줈洹??먮룞 諛쒗뻾 ?깃났! {pub_result['message']}")
                    else:
                        st.error(f"???먮룞 諛쒗뻾 ?ㅽ뙣: {pub_result['message']}")
                else:
                    st.warning("?좑툘 ?먮룞 諛쒗뻾 ?ㅽ뙣: BLOGGER_BLOG_ID媛 ?ㅼ젙?섏? ?딆븯?듬땲??")
            except Exception as e:
                st.error(f"?먮룞 諛쒗뻾 以??ㅻ쪟: {e}")

    st.session_state.phase = 2
    st.rerun()


# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧??#  Phase 2: 寃곌낵 ??쒕낫??# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧??if st.session_state.phase == 2:
    topic_full = st.session_state.selected_topic or ""
    topic_short = re.sub(r"^\(.*?\)\s*", "", topic_full).strip()
    tuned_text  = st.session_state.tuned_text or ""
    seo         = st.session_state.seo_data

    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown(f"### ???먯뒪???뚯씠?꾨씪???꾨즺 ??**{topic_short}**")

    # ?? 理쒖쥌 寃곌낵臾???
    st.markdown("#### ?랃툘 ?꾩꽦??釉붾줈洹??ъ뒪??)
    st.markdown(tuned_text)

    # ?? ?④퀎蹂?以묎컙 寃곌낵 (?묎린) ??
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    with st.expander("?뱷 1?④퀎 ??DeepSeek 珥덉븞 (?먮낯)", expanded=False):
        st.markdown(st.session_state.draft_text or "_珥덉븞 ?놁쓬_")

    with st.expander("?뵇 2?④퀎 ??Qwen + Mistral Small 援먯감 鍮꾪뙋", expanded=False):
        st.markdown(st.session_state.combined_critique or "_鍮꾪뙋 ?곗씠???놁쓬_")

    with st.expander("?쨼 3?④퀎 ??DeepSeek 理쒖쥌 ?섏젙蹂?, expanded=False):
        st.markdown(st.session_state.final_report or "_理쒖쥌 蹂닿퀬???놁쓬_")

    with st.expander("?렓 4?④퀎 ??AI ?앹꽦 ?대?吏 紐⑸줉", expanded=False):
        imgs = st.session_state.image_paths
        if imgs:
            cols = st.columns(len(imgs))
            for i, p in enumerate(imgs):
                cols[i].image(p, caption=f"?앹꽦???대?吏 {i+1}")
        else:
            st.info("?앹꽦???대?吏媛 ?놁뒿?덈떎. API ?곹깭瑜??뺤씤??二쇱꽭??")

    # ?? SEO ??
    with st.expander("?뵇 SEO 硫뷀??곗씠??, expanded=False):
        if seo:
            tag_html = " ".join([
                f'<span class="model-badge" style="background:#667eea;">#{t}</span>'
                for t in seo.get("seo_tags", [])
            ])
            st.markdown(tag_html, unsafe_allow_html=True)
            st.markdown(f"**硫뷀? ?ㅻ챸:** {seo.get('meta_description', '')}")
            for i, alt in enumerate(seo.get("image_alt_texts", []), 1):
                st.markdown(f"{i}. {alt}")
        else:
            st.caption("SEO ?곗씠???앹꽦 ?ㅽ뙣")

    # ?? ?대낫?닿린 踰꾪듉 ??
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    col_d1, col_d2, col_d3 = st.columns(3)

    with col_d1:
        # ?뚮뱶 ?ㅼ슫濡쒕뱶 ?댁뒋濡??명빐 留덊겕?ㅼ슫(.md) ?뚯씪濡???ν븯?꾨줉 蹂寃?        md_content = f"# {topic_short}\n\n{tuned_text}"
        if seo:
            md_content += f"\n\n## SEO 硫뷀??곗씠??n- ?쒓렇: {', '.join(seo.get('seo_tags', []))}\n- ?ㅻ챸: {seo.get('meta_description', '')}"
            
        # ?뚯씪紐낆뿉???뱀닔臾몄옄 ?쒓굅 (?덉쟾???뚯씪紐??앹꽦)
        safe_filename = re.sub(r'[\\/*?:"<>|]', "", topic_short)[:30]
        if not safe_filename: safe_filename = "釉붾줈洹??ъ뒪??
        
        st.download_button(
            label="?뱿 留덊겕?ㅼ슫(.md) ?ㅼ슫濡쒕뱶",
            data=md_content.encode('utf-8'),
            file_name=f"{safe_filename}.md",
            mime="text/markdown",
            use_container_width=True,
        )

    with col_d2:
        seo_tags = seo.get("seo_tags", []) if seo else []
        
        html_content = md_to_html(tuned_text)
        
        # Streamlit Secrets ?먮뒗 ?섍꼍 蹂?섏뿉??BLOGGER_BLOG_ID 媛?몄삤湲?        blog_id = os.getenv("BLOGGER_BLOG_ID", "")
        if not blog_id and "BLOGGER_BLOG_ID" in st.secrets:
            blog_id = st.secrets["BLOGGER_BLOG_ID"]
            
        can_publish = bool(blog_id)

        if not can_publish:
            st.warning("?좑툘 ?섍꼍 蹂???먮뒗 Streamlit Secrets??BLOGGER_BLOG_ID瑜??ㅼ젙?섏꽭??)

        if st.button("?? 援ш? 釉붾줈洹??먮룞 諛쒗뻾", use_container_width=True, disabled=not can_publish):
            status_ph = st.empty()
            pb = st.progress(0)
            steps = ["釉뚮씪?곗? 以鍮?, "Blogger ?묒냽", "??湲 ?묒꽦", "?쒕ぉ ?낅젰", "HTML ?꾪솚", "蹂몃Ц ?낅젰", "諛쒗뻾 ?꾨즺"]
            idx = [0]

            def upd(msg):
                status_ph.info(msg)
                if idx[0] < len(steps):
                    pb.progress((idx[0] + 1) / len(steps))
                    idx[0] += 1

            pub = BloggerPublisher(headless=False, status_callback=upd)
            result = pub.publish(title=topic_short, html_content=html_content, tags=seo_tags)
            pb.progress(1.0)
            if result["success"]:
                st.success(result["message"])
            else:
                st.error(result["message"])

    with col_d3:
        with st.expander("?뮲 HTML 肄붾뱶 蹂듭궗", expanded=False):
            preview = f"<h2>{topic_short}</h2>\n\n{tuned_text}"
            if seo:
                preview += f"\n\n<p><b>?쒓렇:</b> {', '.join(seo.get('seo_tags', []))}</p>"
            st.code(preview, language="html")

    # ?? ?덈줈 ?쒖옉 踰꾪듉 ??
    st.markdown("")
    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_b:
        if st.button("?봽 ?덈줈??二쇱젣 遺꾩꽍?섍린", use_container_width=True):
            for k in defaults:
                st.session_state[k] = defaults[k]
            fetch_news_data.clear()
            load_anchor_data.clear()
            st.rerun()

    st.markdown('<div style="height: 50px;"></div>', unsafe_allow_html=True)
