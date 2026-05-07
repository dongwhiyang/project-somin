import os
import re
import json
import time
import random
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# internal modules
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

# load env
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
        # 1. local save
        with open(STATUS_FILE, "w") as f:
                    json.dump(status, f, indent=2)
                # 2. github sync
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

    # 1. Table conversion
    table_pattern = r'((?:\|.*\|(?:\n|$))+)'
    html = re.sub(table_pattern, lambda m: parse_md_table(m.group(1)), md_text)

    # 2. Other elements
    html = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', html)
    html = re.sub(r'!\[(.*?)\]\((.*?)\)', r'<img src="\2" alt="\1" style="max-width:100%; height:auto;"><br>', html)
    html = re.sub(r'^### (.*?)$', r'<h3 style="color: #2c3e50; border-left: 5px solid #667eea; padding-left: 10px; margin-top: 25px;">\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.*?)$', r'<h2 style="color: #1a1a3e; background: #f8f9fa; padding: 10px; border-radius: 5px; margin-top: 30px;">\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^\- (.*?)$', r'<li>\1</li>', html, flags=re.MULTILINE)

    # 3. Newlines
    parts = re.split(r'(<table.*?</table>)', html, flags=re.DOTALL)
    for i in range(len(parts)):
                if not parts[i].startswith('<table'):
                                parts[i] = parts[i].replace("\n", "<br>")

    html = "".join(parts)
    if "<li>" in html:
                html = html.replace("<li>", "<ul><li>", 1).replace("</li><br><ul>", "</li>")
    return html

def run_pipeline():
        print(f"\n[Automation Engine] Task Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. load data
    combined_text, _ = load_anchor_data()
    news_text, _, _ = fetch_news_data()

    # 2. topic selection
    print("[1/6] Analyzing and selecting topics...")
    topics = call_llama_for_topics(combined_text, news_text)
    all_topics = topics.get("exam", []) + topics.get("field", [])
    if not all_topics:
                print("ERROR: No topics selected.")
        return False

    selected_topic = random.choice(all_topics)
    topic_only = re.sub(r"^\(.*?\)\s*", "", selected_topic).strip()
    print(f"Selected Topic: {topic_only}")

    # 3. draft
    print("[2/6] Generating technical draft...")
    draft = generate_draft(topic_only, combined_text, "", "")

    # 4. critique
    print("[3/6] Cross-critiquing (Parallel)...")
    crit_q = critique_with_qwen(draft, topic_only)
    crit_m = critique_with_mistral_small(draft, topic_only)
    combined_crit = f"Cross critique results: \n{crit_q}\n\n{crit_m}"

    # 5. image
    print("[4/6] Generating AI illustrations...")
    image_prompts = re.findall(r'\[IMAGE_PROMPT:\s*(.*?)\]', combined_crit, re.DOTALL)
    image_paths = []
    for idx, p in enumerate(image_prompts[:2]):
                path = generate_image_from_nvidia(p, idx)
        if path:
                        image_paths.append(path)

    # 6. final revision
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

    # run
    success = run_pipeline()

    if success:
                # next run
                interval = random.uniform(4 * 3600, 5 * 3600)
        status["last_run"] = time.time()
        status["next_run"] = time.time() + interval
        save_status(status)
        print(f"Next Run Scheduled: {datetime.fromtimestamp(status['next_run']).strftime('%Y-%m-%d %H:%M:%S')}")
