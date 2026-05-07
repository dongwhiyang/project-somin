import json
import os
import sys

# 인코딩 강제 설정 (한글 깨짐 방지)
sys.stdout.reconfigure(encoding='utf-8')

from pipeline import call_llama_for_topics
from scraper import load_anchor_data, fetch_news_data

print("[1] Data Loading Test...")
anchor, a_count = load_anchor_data()
news, n_count, _ = fetch_news_data()
print(f"   - Anchor Data: {a_count} files loaded")
print(f"   - News Data: {n_count} items collected")

print("\n[2] Topic Generation Test (Llama 3)...")
try:
    topics = call_llama_for_topics(anchor, news)
    print("\n=== [Success] Topics Generated ===")
    print(json.dumps(topics, indent=2, ensure_ascii=False))
except Exception as e:
    print(f"\n[Fail] Error: {e}")

if topics and (topics.get("exam") or topics.get("field")):
    print("\n[OK] Phase 1 (Topic Selection) is working perfectly!")
else:
    print("\n[NG] Phase 1 logic failed or produced empty results.")
