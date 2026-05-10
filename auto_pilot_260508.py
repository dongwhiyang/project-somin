import os
import re
import json
import time
import random
from datetime import datetime
from pathlib import Path
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
    generate_seo_metadata
)
from blogger_publisher import BloggerPublisher

# 환경변수 로드
load_dotenv(override=True)

STATUS_FILE = "automation_status.json"

def load_status():
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"enabled": False, "last_run": 0, "next_run": 0}

def save_status(status):
    # 1. 로컬 저장
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f, indent=2)
    # 2. 깃허브 동기화
    token = os.getenv("GITHUB_TOKEN", "")
    if token:
        try:
            import requests, base64
            repo = "dongwhiyang/project-somin"
            url = f"https://api.github.com/repos/{repo}/contents/{STATUS_FILE}"
            headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
            get_resp = requests.get(url, headers=headers)
            sha = get_resp.json().get("sha", "") if get_resp.status_code == 200 else ""
            content = json.dumps(status, indent=2).encode("utf-8")
            b64_content = base64.b64encode(content).decode("utf-8")
            requests.put(url, headers=headers, json={"message": "Auto Pilot Sync", "content": b64_content, "sha": sha})
        except:
            pass

def md_to_html(md_text):
    import re

    # 1. 마크다운 표를 HTML 표로 강제 변환 (초강력 버전)
    def parse_md_table(match):
        table_text = match.group(0).strip()
        rows = table_text.split('\n')
        if len(rows) < 2: return match.group(0)
        
        html = '<div style="overflow-x:auto; margin: 20px 0;"><table style="border-collapse: collapse; width: 100%; border: 1px solid #ddd; font-family: sans-serif;">'
        
        for i, row in enumerate(rows):
            if i == 1 and ('---' in row or '===' in row): continue
            
            cells = [c.strip() for c in row.split('|')]
            if cells and not cells[0]: cells.pop(0)
            if cells and not cells[-1]: cells.pop()
            
            if not cells: continue
            
            tag = 'th' if i == 0 else 'td'
            if i == 0:
                style = 'border: 1px solid #ddd; padding: 12px 15px; background-color: #667eea; color: white; text-align: center; font-weight: bold;'
            else:
                bg = 'background-color: #f8f9fa;' if i % 2 == 0 else 'background-color: #ffffff;'
                style = f'border: 1px solid #ddd; padding: 12px 15px; {bg}'
            
            html += '<tr>'
            for cell in cells:
                html += f'<{tag} style="{style}">{cell}</{tag}>'
            html += '</tr>'
            
        html += '</table></div>'
        return html

    # 표 패턴: | 로 시작해서 | 로 끝나는 행이 연속되는 모든 구간 (MULTILINE 필수)
    table_pattern = r'((?:^\s*\|.*\|[ \t]*$(?:\n|$))+)'
    html_output = re.sub(table_pattern, parse_md_table, md_text, flags=re.MULTILINE)

    # 2. 기타 마크다운 기본 변환
    html_output = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', html_output)
    html_output = re.sub(r'^### (.*?)$', r'<h3 style="border-left: 5px solid #667eea; padding-left:10px; color:#1a1a3e;">\1</h3>', html_output, flags=re.MULTILINE)
    html_output = re.sub(r'^## (.*?)$', r'<h2 style="background:#f8f9fa; padding:10px; border-radius:5px;">\1</h2>', html_output, flags=re.MULTILINE)
    html_output = re.sub(r'!\[(.*?)\]\((.*?)\)', r'<img src="\2" alt="\1" style="max-width:100%; height:auto;"><br>', html_output)
    
    html_output = html_output.replace('\n', '<br />')
    
    return html_output

def run_pipeline():
    print(f"\n[Automation Engine] Task Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. 뉴스 및 데이터 로드
    combined_text, _ = load_anchor_data()
    news_text, _, _ = fetch_news_data()
    
    # 2. 주제 선정
    print("[1/6] Analyzing and selecting topics...")
    topics = call_llama_for_topics(combined_text, news_text)
    all_topics = topics.get("exam", []) + topics.get("field", [])
    if not all_topics:
        print("ERROR: No topics selected.")
        return False
        
    selected_topic = random.choice(all_topics)
    topic_only = re.sub(r"^\(.*?\)\s*", "", selected_topic).strip()
    print(f"Selected Topic: {topic_only}")

    # 3. 초안 작성
    print("[2/6] Generating technical draft...")
    draft = generate_draft(topic_only, combined_text, "", "")
    
    # 4. 병렬 비판
    print("[3/6] Cross-critiquing (Parallel)...")
    crit_q = critique_with_qwen(draft, topic_only)
    crit_m = critique_with_mistral_small(draft, topic_only)
    combined_crit = f"【Qwen】\n{crit_q}\n\n【Mistral】\n{crit_m}"

    # 5. 이미지 생성
    print("[4/6] Generating AI illustrations...")
    image_prompts = re.findall(r'\[IMAGE_PROMPT:\s*(.*?)\]', combined_crit, re.DOTALL)
    image_paths = []
    for idx, p in enumerate(image_prompts[:2]):
        path = generate_image_from_nvidia(p, idx)
        if path:
            image_paths.append(path)

    # 6. 최종 수정 및 발행
    print("[5/6] Finalizing blog post...")
    final_text = revise_with_deepseek(draft, combined_crit, topic_only, image_paths=image_paths)
    seo_data = generate_seo_metadata(topic_only, final_text)
    
    print("[6/6] Publishing to Google Blogger...")
    html_content = md_to_html(final_text)
    seo_tags = seo_data.get("seo_tags", []) if seo_data else []
    
    pub = BloggerPublisher()
    result = pub.publish(title=topic_only, html_content=html_content, tags=seo_tags)
    
    if result["success"]:
        print(f"SUCCESS: Published! {result.get('url', '')}")
        return True
    else:
        print(f"FAILED: {result.get('message', 'Unknown error')}")
        return False

if __name__ == "__main__":
    status = load_status()
    
    if not status.get("enabled"):
        print("[Notice] Automation switch is OFF. Stopping task.")
        exit(0)
        
    now = time.time()
    if now < status.get("next_run", 0):
        remaining = int((status["next_run"] - now) / 60)
        print(f"[Wait] Approx. {remaining} minutes left until next run.")
        exit(0)

    # 실행!
    success = run_pipeline()
    
    if success:
        # 다음 실행 시간 설정 (4~5시간 사이 랜덤)
        interval = random.uniform(4 * 3600, 5 * 3600)
        status["last_run"] = time.time()
        status["next_run"] = time.time() + interval
        save_status(status)
        print(f"Next Run Scheduled: {datetime.fromtimestamp(status['next_run']).strftime('%Y-%m-%d %H:%M:%S')}")
