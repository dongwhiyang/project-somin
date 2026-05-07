import sys
sys.stdout.reconfigure(encoding='utf-8')

from blogger_publisher import BloggerPublisher

print("[Final] Blogger API Publishing Test...")
pub = BloggerPublisher()

test_title = "🚀 시스템 자동화 최종 연결 테스트 (Antigravity)"
test_content = """
<h2>시스템 자동화 점검 포스팅</h2>
<p>이 포스팅은 <b>프로젝트 소민 V2.2</b>의 24시간 자동화 파이프라인이 정상적으로 구축되었는지 확인하기 위한 테스트 글입니다.</p>
<ul>
  <li>1단계: 주제 선정 로직 개선 완료</li>
  <li>2단계: 깃허브 서버 권한 획득 완료</li>
  <li>3단계: Blogger API 연동 성공 여부 확인 중</li>
</ul>
<p>발행 시각: """ + str(__import__('datetime').datetime.now()) + """</p>
"""

try:
    result = pub.publish(title=test_title, html_content=test_content, tags=["테스트", "자동화"])
    if result["success"]:
        print(f"✅ [Success] Post URL: {result['url']}")
    else:
        print(f"❌ [Fail] Message: {result['message']}")
except Exception as e:
    print(f"❌ [Error] System Failure: {e}")
