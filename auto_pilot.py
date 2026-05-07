import os
import re
import json
import time
import random
from datetime import datetime
from dotenv import load_dotenv

# Internal modules
from scraper import fetch_news_data, load_anchor_data
from app import call_llama_for_topics
from pipeline import (
    generate_draft,
    critique_with_qwen,
    critique_with_mistral_small,
    generate_image_from_nvidia,
    revise_with_deepseek,
    generate_seo_metadata
)
from blogger_publisher import BloggerPublisher

# Load env
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
        # 1. Local save
        with open(STATUS_FILE, "w") as f:
                    json.dump(status, f, indent=2)
                # 2. Github sync
                token = os.getenv("GITHUB_TOKEN", "")
    if token:
                try:
                                import requests, base64
                                repo = "dongwhiyang/project-somin"
                                url = f"https://api.github.com/repos/{repo}/contents/{STATUS_FILE}"
                                headers = {
                                    "Authorization": f"token {token}",
                                    "Accept": "application/vnd.github.v3+json"
                                }
                                get_resp = requests.get(url, headers=headers)
                                sha = get_resp.json().get("sha", "") if get_resp.status_code == 200 else ""

            content_json = json.dumps(status, indent=2)
            content_b64 = base64.b64encode(content_json.encode()).decode()

            data = {
                                "message": "Update status via auto_pilot",
                                "content": content_b64,
                                "branch": "main"
            }
            if sha:
                                data["sha"] = sha

            requests.put(url, headers=headers, json=data)
except Exception as e:
            print(f"Github Sync Error: {e}")

def run_automation():
        status = load_status()
    if not status.get("enabled"):
                print("Automation is disabled.")
                return

    now = time.time()
    if now < status.get("next_run", 0):
                remaining = int(status["next_run"] - now)
                print(f"Next run in {remaining} seconds.")
                return

    print(f"Automation started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
                # 1. Fetch news
                print("Fetching news...")
                news_data = fetch_news_data()
                news_text = "\n".join([f"Title: {n['title']}\nContent: {n['content']}" for n in news_data])

        # 2. Load anchor data
                print("Loading anchor data...")
                anchor_data = load_anchor_data()
                combined_text = "\n".join([f"Title: {a['title']}\nContent: {a['content']}" for a in anchor_data])

        # 3. Topic selection
                print("Selecting topic...")
                topics = call_llama_for_topics(combined_text, news_text)

        selected_topic = None
        if topics.get("exam"):
                        selected_topic = random.choice(topics["exam"])
elif topics.get("field"):
            selected_topic = random.choice(topics["field"])

        if not selected_topic:
                        print("No topic selected.")
                        return

        print(f"Selected topic: {selected_topic}")

        # 4. Generate draft
        print("Generating draft...")
        draft = generate_draft(selected_topic, combined_text)

        # 5. Qwen critique
        print("Qwen critique...")
        qwen_critique = critique_with_qwen(draft)

        # 6. Mistral critique
        print("Mistral critique...")
        mistral_critique = critique_with_mistral_small(draft)

        # 7. DeepSeek revision
        print("DeepSeek revision...")
        final_content = revise_with_deepseek(draft, qwen_critique, mistral_critique)

        # 8. SEO metadata
        print("Generating SEO metadata...")
        seo = generate_seo_metadata(final_content)

        # 9. Image generation
        print("Generating image...")
        image_url = generate_image_from_nvidia(selected_topic)

        # 10. Blogger publish
        print("Publishing to Blogger...")
        publisher = BloggerPublisher()
        post_url = publisher.publish_post(
                        title=selected_topic,
                        content=final_content,
                        tags=seo.get("keywords", []),
                        image_url=image_url
        )

        if post_url:
                        print(f"Published: {post_url}")
else:
            print("Publish failed.")

except Exception as e:
        print(f"Error during execution: {e}")
finally:
        # Update status
            status["last_run"] = time.time()
        # Random interval between 6 and 12 hours
        interval = random.randint(6*3600, 12*3600)
        status["next_run"] = status["last_run"] + interval
        save_status(status)
        print(f"Next run scheduled at: {datetime.fromtimestamp(status['next_run']).strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
        run_automation()
