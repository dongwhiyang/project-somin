import os
import sys
import json
sys.stdout.reconfigure(encoding='utf-8')

from pipeline import generate_draft, critique_with_qwen, critique_with_mistral_small
from scraper import load_anchor_data

print("[3] Draft Generation Test...")
topic = "(실무가이드) 공기 연장 시 간접비 산정·지급 어떻게 하나? 서울시 가이드라인을 중심으로"
anchor, _ = load_anchor_data()

try:
    draft = generate_draft(topic, anchor, "", "")
    print(f"   - Draft size: {len(draft)} chars")
    print("\n[4] Parallel Critique Test...")
    crit_q = critique_with_qwen(draft, topic)
    crit_m = critique_with_mistral_small(draft, topic)
    print(f"   - Qwen critique size: {len(crit_q)} chars")
    print(f"   - Mistral critique size: {len(crit_m)} chars")
    print("\n[OK] Core content generation logic verified!")
except Exception as e:
    print(f"\n[Fail] Error during generation: {e}")
