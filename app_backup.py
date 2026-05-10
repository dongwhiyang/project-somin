import os
import json
import re
import random
import streamlit as st
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv
from scraper import scrape_all_keywords, format_news_for_prompt, scrape_competitor_blogs
from pipeline import (
    TUNING_MODELS, check_api_key, collect_gov_data,
    analyze_competitors_with_deepseek, generate_draft, critique_with_qwen,
    generate_image_from_nvidia,
    revise_with_deepseek, tune_with_mistral, generate_seo_metadata, create_docx,
    auto_pick_topic, call_llama_for_topics
)
from tistory_publisher import TistoryPublisher
from blogger_publisher import BloggerPublisher
import base64

# Automation state management
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
        with open(STATUS_FILE, "w") as f:
                    json.dump(status, f, indent=2)
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

        load_dotenv(override=True)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

st.set_page_config(
        page_title="Project Somin V2.2",
        page_icon="memo",
        layout="wide",
        initial_sidebar_state="collapsed",
)

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

from scraper import load_anchor_data, fetch_news_data

@st.cache_data(show_spinner=False, ttl=300)
def get_cached_anchor():
        return load_anchor_data()

@st.cache_data(show_spinner=False, ttl=3600)
def get_cached_news():
        return fetch_news_data()

def md_to_html(md_text):
        import re
    def parse_md_table(md_content):
                lines = [l.strip() for l in md_content.strip().split('\n') if l.strip()]
        if len(lines) < 2: return md_content
                    if not any('|' in l and '-' in l for l in lines[1:2]): return md_content
                                html = '<table border="1" style="border-collapse: collapse; width: 100%; border: 1px solid #ccc; margin: 15px 0;">'
        for i, line in enumerate(lines):
                        if i == 1 and '-' in line and '|' in line: continue
                                        cells = [c.strip() for c in line.split('|')]
            if line.startswith('|'): cells = cells[1:]
                            if line.endswith('|'): cells = cells[:-1]
                                            tag = 'th' if i == 0 else 'td'
            bg_color = '#f8f9fa' if i == 0 else '#ffffff'
            html += f'<tr style="background-color: {bg_color};">'
            for cell in cells:
                                html += f'<{tag} style="padding: 10px; border: 1px solid #ccc;">{cell}</{tag}>'
                            html += '</tr>'
        html += '</table>'
        return html
    table_pattern = r'((?:\|.*\|(?:\n|$))+)'
    html = re.sub(table_pattern, lambda m: parse_md_table(m.group(1)), md_text)
    html = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', html)
    html = re.sub(r'!\[(.*?)\]\((.*?)\)', r'<img src="\2" alt="\1" style="max-width:100%; height:auto;"><br>', html)
    html = re.sub(r'^### (.*?)$', r'<h3 style="color: #2c3e50; border-left: 5px solid #667eea; padding-left: 10px; margin-top: 25px;">\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.*?)$', r'<h2 style="color: #1a1a3e; background: #f8f9fa; padding: 10px; border-radius: 5px; margin-top: 30px;">\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^\- (.*?)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    parts = re.split(r'(<table.*?</table>)', html, flags=re.DOTALL)
    for i in range(len(parts)):
                if not parts[i].startswith('<table'):
                                parts[i] = parts[i].replace("\n", "<br>")
                        html = "".join(parts)
    if "<li>" in html:
                html = html.replace("<li>", "<ul><li>", 1).replace("</li><br><ul>", "</li>")
    return html

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

st.markdown("""
<div class="hero-header">
    <h1>Project Somin V2.2</h1>
        <p>One-stop AI Blog Pipeline</p>
        </div>
        """, unsafe_allow_html=True)

combined_text, file_count = get_cached_anchor()

if file_count == 0:
        st.error("No anchor data found.")
    st.stop()

with st.spinner("Collecting news..."):
        news_text, news_count, selected_kws = get_cached_news()

st.markdown(f"""
<div class="stat-bar">
    <div class="stat-item">
            <div class="stat-number">{file_count}</div>
                    <div class="stat-label">Files</div>
                        </div>
                            <div class="stat-item">
                                    <div class="stat-number">{len(combined_text):,}</div>
                                            <div class="stat-label">Characters</div>
                                                </div>
                                                </div>
                                                <hr class="divider">
                                                """, unsafe_allow_html=True)

with st.container():
        c1, c2 = st.columns([1.2, 1])
    with c1:
                st.markdown('<div class="section-title section-exam">[Step 1] Topic Selection</div>', unsafe_allow_html=True)
        if st.button("Generate Topics (Llama-3.3-70B)"):
                        with st.spinner("Generating..."):
                                            st.session_state.topics_data = call_llama_for_topics(combined_text, news_text)
                                            st.session_state.phase = 1

        if st.session_state.topics_data:
                        st.write("---")
            topics = st.session_state.topics_data.get("topics", [])
            choice = st.radio("Choose a topic:", [t['title'] for t in topics], key="topic_choice", help="Select the best topic for your blog")
            if st.button("Confirm Topic"):
                                st.session_state.selected_topic = next(t for t in topics if t['title'] == choice)
                                st.session_state.phase = 2
                                st.success(f"Selected: {choice}")

    with c2:
                st.markdown('<div class="section-title section-field">[Config] Automation (Auto-Pilot)</div>', unsafe_allow_html=True)
        ap_enabled = st.toggle("Enable Auto-Pilot", value=st.session_state.auto_pilot)
        if ap_enabled != st.session_state.auto_pilot:
                        st.session_state.auto_pilot = ap_enabled
            save_automation_status({"enabled": ap_enabled, "last_run": 0, "next_run": 0})
            st.info(f"Auto-Pilot {'enabled' if ap_enabled else 'disabled'}.")

        st.markdown("---")
        st.markdown('<div class="section-title">[Status] Pipeline Progress</div>', unsafe_allow_html=True)
        st.progress(min(st.session_state.phase / 6.0, 1.0))
        steps = ["Topic Selection", "Competitor Analysis", "Drafting", "Critique & Revision", "SEO & Image", "Publishing"]
        for i, s in enumerate(steps):
                        color = "#4CAF50" if st.session_state.phase > i else "#888"
            icon = "[V]" if st.session_state.phase > i else "[.]"
            st.markdown(f"<span style='color: {color};'>{icon} {s}</span>", unsafe_allow_html=True)

if st.session_state.selected_topic:
        st.write("---")
    st.subheader(f"Selected Topic: {st.session_state.selected_topic['title']}")

    if st.button("Execute Full Pipeline"):
                st.session_state.phase = 3
        topic = st.session_state.selected_topic

        with st.status("Running pipeline...") as status:
                        status.update(label="Analyzing competitors...")
            comp_blogs = scrape_competitor_blogs(topic['keywords'])
            comp_analysis = analyze_competitors_with_deepseek(comp_blogs, topic['title'])

            status.update(label="Generating draft...")
            draft = generate_draft(topic['title'], topic['keywords'], combined_text, news_text, comp_analysis)
            st.session_state.draft_text = draft

            status.update(label="Critiquing...")
            combined_crit = critique_with_qwen(draft, topic["title"])
            st.session_state.combined_critique = combined_crit

            status.update(label="Revising...")
            final = revise_with_deepseek(draft, combined_crit, topic['title'])
            st.session_state.final_report = final

            status.update(label="Tuning...")
            tuned = tune_with_mistral(final)
            st.session_state.tuned_text = tuned

            status.update(label="Generating SEO & Images...")
            seo = generate_seo_metadata(tuned)
            st.session_state.seo_data = seo

            img_prompt = f"{topic['title']} related high quality blog header image, 3d render style"
            img_path = generate_image_from_nvidia(img_prompt)
            if img_path: st.session_state.image_paths = [img_path]

            st.session_state.phase = 6
            status.update(label="Pipeline Complete!", state="complete")

if st.session_state.phase >= 6:
        st.write("---")
    st.markdown('<div class="section-title section-field">[Step 2] Final Report & Publishing</div>', unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["Final Report", "SEO Metadata", "Images"])

    with tab1:
                st.markdown(md_to_html(st.session_state.tuned_text), unsafe_allow_html=True)
        doc_path = create_docx(st.session_state.tuned_text, st.session_state.selected_topic['title'])
        with open(doc_path, "rb") as f:
                        st.download_button("Download DOCX", f, file_name=f"{st.session_state.selected_topic['title']}.docx")

    with tab2:
                st.json(st.session_state.seo_data)

    with tab3:
                for img in st.session_state.image_paths:
                                st.image(img)

    st.write("---")
    st.subheader("Publishing")

    col_t, col_b = st.columns(2)
    with col_t:
                if st.button("Publish to Tistory"):
                                publisher = TistoryPublisher()
                                post_id = publisher.publish(
                                    title=st.session_state.selected_topic['title'],
                                    content=md_to_html(st.session_state.tuned_text),
                                    tags=st.session_state.selected_topic['keywords']
                                )
                                if post_id: st.success(f"Published to Tistory! ID: {post_id}")

                        with col_b:
                                    if st.button("Publish to Blogger"):
                                                    publisher = BloggerPublisher()
                                                    post_id = publisher.publish(
                                                        title=st.session_state.selected_topic['title'],
                                                        content=md_to_html(st.session_state.tuned_text),
                                                        tags=st.session_state.selected_topic['keywords']
                                                    )
                                                    if post_id: st.success(f"Published to Blogger! ID: {post_id}")
                                                        
