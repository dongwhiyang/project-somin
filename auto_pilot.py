import os
import re
import json
import time
import concurrent.futures
from pathlib import Path
from dotenv import load_dotenv

# 기존 프로젝트 모듈 임포트
from scraper import scrape_all_keywords, format_news_for_prompt, scrape_competitor_blogs
from pipeline import (
    check_api_key, collect_gov_data,
    analyze_competitors_with_deepseek, generate_draft, critique_with_qwen, critique_with_mistral_small,
    generate_image_from_nvidia,
    revise_with_deepseek, generate_seo_metadata,
    auto_pick_topic
)
from blogger_publisher import BloggerPublisher

# 환경변수 로드
load_dotenv(override=True)

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
    
    # 리스트 태그 감싸기
    if "<li>" in html:
        html = html.replace("<li>", "<ul><li>", 1)
        
    return html

def load_anchor_data():
    anchor_dir = Path("anchor_data")
    if not anchor_dir.exists():
        return ""
    txt_files = sorted(anchor_dir.glob("*.txt"))
    all_texts = []
    for f in txt_files:
        try:
            content = f.read_text(encoding="utf-8")
            if len(content.strip()) > 60:
                all_texts.append(f"[파일: {f.name}]\n{content[:2000]}")
        except Exception:
            pass
    return "\n\n---\n\n".join(all_texts)

def call_llama_for_topics(anchor_text: str, news_text: str) -> dict:
    from litellm import completion
    system_prompt = """Role: 너는 10년 차 파워블로거이자 건설사 공무 출신 현직 공무원이야.
제공된 기출문제와 뉴스 데이터를 분석해 수험생과 실무자용 블로그 주제 6개를 JSON으로 제안해줘.
형식: {"exam": ["(태그) 주제1",...], "field": ["(실무) 주제5",...]}"""
    
    user_prompt = f"【기출문제】\n{anchor_text[:6000]}\n\n【뉴스】\n{news_text[:2000]}\n\n주제 6개를 JSON으로 응답하세요."
    
    response = completion(
        model="openai/meta/llama-3.1-70b-instruct",
        api_base="https://integrate.api.nvidia.com/v1",
        api_key=os.getenv("NVIDIA_API_KEY", ""),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.8,
        max_tokens=1000,
    )
    raw = response.choices[0].message.content.strip()
    match = re.search(r"(\{.*?\})", raw, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    return json.loads(raw)

def run_single_pipeline(topic_full: str, anchor_text: str):
    """주제 하나에 대해 전체 파이프라인을 실행하고 블로그에 발행합니다."""
    print(f"\n[시작] 작업 시작 - 주제: {topic_full}")
    topic_only = re.sub(r"^\(.*?\)\s*", "", topic_full).strip()
    
    # 1. 데이터 수집
    print("[1/6] 정부 API 데이터 수집 중...")
    gov_data_text, _ = collect_gov_data(topic_only)
    
    # 1.5 경쟁사 분석
    print("[1.5/6] 경쟁사 블로그 분석 중...")
    try:
        comp_texts = scrape_competitor_blogs(topic_only)
        comp_analysis = analyze_competitors_with_deepseek(topic_only, comp_texts) if comp_texts else ""
    except Exception:
        comp_analysis = ""

    # 2. 초안 생성
    print("[2/6] DeepSeek V4 기술 초안 작성 중...")
    draft = generate_draft(topic_only, anchor_text, gov_data_text, comp_analysis)
    
    # 3. 병렬 비판
    print("[3/6] Qwen & Mistral Small 교차 비판 중...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        fut_q = executor.submit(critique_with_qwen, draft, topic_only)
        fut_m = executor.submit(critique_with_mistral_small, draft, topic_only)
        critique_q = fut_q.result()
        critique_m = fut_m.result()
    
    combined_crit = f"【비판1】\n{critique_q}\n\n【비판2】\n{critique_m}"
    
    # 4. 이미지 생성
    print("[4/6] AI 삽화 생성 중...")
    image_prompts = re.findall(r'\[IMAGE_PROMPT:\s*(.*?)\]', combined_crit, re.DOTALL)
    image_paths = []
    for idx, prompt in enumerate(image_prompts[:3]):
        path = generate_image_from_nvidia(prompt, idx)
        if path:
            image_paths.append(path)
            
    # 5. 최종 수정
    print("[5/6] 최종 블로그 포스팅 완성 중...")
    final_text = revise_with_deepseek(draft, combined_crit, topic_only, image_paths=image_paths)
    
    # 6. SEO 및 발행
    print("[6/6] SEO 및 블로그 발행 중...")
    seo_data = generate_seo_metadata(topic_only, final_text)
    seo_tags = seo_data.get("seo_tags", []) if seo_data else []
    
    html_content = md_to_html(final_text)
    pub = BloggerPublisher(headless=True)
    result = pub.publish(title=topic_only, html_content=html_content, tags=seo_tags)
    
    if result["success"]:
        print(f"[성공] 발행 완료! {result['message']}")
    else:
        print(f"[실패] 발행 실패: {result['message']}")
    
    return result

def main(count=1):
    print(f"[알림] 프로젝트 소민 [오토파일럿 모드]를 시작합니다. (발행 예정: {count}개)")
    
    # 데이터 로드
    anchor_text = load_anchor_data()
    if not anchor_text:
        print("[오류] anchor_data가 없습니다. 작업을 종료합니다.")
        return

    for i in range(count):
        print(f"\n--- [{i+1}/{count} 번째 포스팅 작업 시작] ---")
        
        # 뉴스 수집
        news_dict = scrape_all_keywords(n_random=3)
        news_text = format_news_for_prompt(news_dict)
        
        # 주제 선정
        print("[진행] AI가 오늘의 주제를 선정하고 있습니다...")
        topics_data = call_llama_for_topics(anchor_text, news_text)
        picked_topic = auto_pick_topic(topics_data)
        
        # 파이프라인 실행
        try:
            run_single_pipeline(picked_topic, anchor_text)
        except Exception as e:
            print(f"[주의] 작업 중 오류 발생: {e}")
            
        if i < count - 1:
            print("\n[대기] 다음 작업을 위해 대기 중 (10초)...")
            time.sleep(10)

    print("\n[완료] 모든 자동 발행 작업이 완료되었습니다!")

if __name__ == "__main__":
    import sys
    # 실행 인자로 개수 설정 가능 (예: python auto_pilot.py 3)
    num_posts = 1
    if len(sys.argv) > 1:
        try:
            num_posts = int(sys.argv[1])
        except ValueError:
            pass
            
    main(num_posts)
