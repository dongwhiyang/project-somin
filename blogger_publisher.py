     1|import os
     2|import pickle
     3|import re
     4|import base64
     5|import json
     6|import datetime
     7|from dotenv import load_dotenv
     8|from googleapiclient.discovery import build
     9|from googleapiclient.errors import HttpError
    10|from google.auth.transport.requests import Request
    11|
    12|class BloggerPublisher:
    13|    def __init__(self):
    14|        """
    15|        공식 Google Blogger API v3를 사용하는 퍼블리셔입니다.
    16|        """
    17|        load_dotenv(override=True)
    18|        # 환경 변수에서 먼저 읽기
    19|        self.blog_id = os.getenv("BLOGGER_BLOG_ID", "")
    20|        
    21|        # 스트림릿 환경인지 아주 조심스럽게 확인
    22|        if not self.blog_id:
    23|            try:
    24|                # 깃허브 액션이나 로컬에서는 이 블록이 실행되지 않아야 함
    25|                if "STREAMLIT_RUNTIME" in os.environ:
    26|                    import streamlit as st
    27|                    self.blog_id = str(st.secrets.get("BLOGGER_BLOG_ID", ""))
    28|            except:
    29|                pass
    30|            
    31|        # BLOGGER_BLOG_ID에서 숫자만 추출
    32|        match = re.search(r"(\d+)", str(self.blog_id))
    33|        if match:
    34|            self.blog_id = match.group(1)
    35|            
    36|        self.service = None
    37|
    38|    def log(self, msg):
    39|        print(f"[BloggerPublisher] {msg}")
    40|
    41|    def _get_credentials(self):
    42|        creds = None
    43|        # google-auth와 google-api-python-client 라이브러리 필요
    44|        from google.oauth2.credentials import Credentials
    45|
    46|        # 1. 환경 변수에서 직접 체크 (최우선)
    47|        token_b64 = os.getenv("GOOGLE_TOKEN_PICKLE_BASE64", "")
    48|        if token_b64:
    49|            try:
    50|                token_data = base64.b64decode(token_b64)
    51|                creds = pickle.loads(token_data)
    52|                self.log("[성공] 환경 변수에서 인증 정보를 불러왔습니다.")
    53|            except:
    54|                pass
    55|
    56|        # 2. 스트림릿 Secrets 체크 (조심스럽게)
    57|        if not creds and "STREAMLIT_RUNTIME" in os.environ:
    58|            try:
    59|                import streamlit as st
    60|                if "GOOGLE_TOKEN_PICKLE_BASE64" in st.secrets:
    61|                    token_data = base64.b64decode(st.secrets["GOOGLE_TOKEN_PICKLE_BASE64"])
    62|                    creds = pickle.loads(token_data)
    63|                    self.log("[클라우드] 스트림릿 Secrets에서 인증 정보를 불러왔습니다.")
    64|            except:
    65|                pass
    66|
    67|        # 3. 로컬 파일 체크
    68|        if not creds and os.path.exists('token.pickle'):
    69|            self.log("[로컬] 로컬 token.pickle에서 인증 정보를 불러옵니다.")
    70|            with open('token.pickle', 'rb') as token:
    71|                creds = pickle.loads(token.read())
    72|
    73|        # 토큰 갱신
    74|        if creds and creds.expired and creds.refresh_token:
    75|            self.log("[갱신] 만료된 토큰을 갱신합니다...")
    76|            creds.refresh(Request())
    77|            # 갱신된 토큰 저장 (로컬일 경우만)
    78|            if os.path.exists('token.pickle'):
    79|                with open('token.pickle', 'wb') as token:
    80|                    token.write(pickle.dumps(creds))
    81|
    82|        if not creds:
    83|            raise Exception("인증 정보(token.pickle 또는 Secrets)를 찾을 수 없습니다. generate_token.py를 먼저 실행하세요.")
    84|            
    85|        return creds
    86|
    87|    def _get_service(self):
    88|        if self.service:
    89|            return self.service
    90|        creds = self._get_credentials()
    91|        self.service = build('blogger', 'v3', credentials=creds)
    92|        return self.service
    93|
    94|    def publish(self, title, html_content, tags=[]):
        """Blogger 발행 + SEO 최적화 (JSON-LD 자동 삽입)"""
        if not self.blog_id:
            return {"success": False, "message": "BLOGGER_BLOG_ID가 설정되지 않았습니다."}

        try:
            self.log("[연결] 구글 Blogger API 연결 중...")
            service = self._get_service()
            
            # SEO: JSON-LD 구조화 데이터 삽입
            jsonld = self._build_jsonld(title, html_content, tags)
            html_content = jsonld + html_content
            self.log(f"[SEO] JSON-LD 구조화 데이터 삽입 완료")
            
            # 본문에서 이미지 URL 추출 (썸네일 인식용 보조 필드)
            img_urls = re.findall(r'<img [^>]*src="([^"]+)"', html_content)
            
            body = {
                'kind': 'blogger#post',
                'title': title,
                'content': html_content,
                'labels': tags
            }
            
            # 이미지가 있다면 Blogger가 인식하도록 힌트 제공
            if img_urls:
                body['images'] = [{'url': url} for url in img_urls]

            self.log(f"[발행] 포스팅 발행 중: {title}")
            posts = service.posts()
            request = posts.insert(blogId=self.blog_id, body=body)
            result = request.execute()

            post_url = result.get('url', '')
            post_id = result.get('id', '')
            self.log(f"[완료] ID={post_id} → {post_url}")
            return {"success": True, "message": "구글 블로그에 성공적으로 발행되었습니다!", "url": post_url, "post_id": post_id}

        except HttpError as e:
            err = json.loads(e.content).get('error', {})
            msg = err.get('message', str(e))
            self.log(f"[에러] API 오류: {msg}")
            return {"success": False, "message": f"Blogger API 오류: {msg}"}
        except Exception as e:
            self.log(f"[실패] 포스팅 실패: {e}")
            return {"success": False, "message": str(e)}

    def _build_jsonld(self, title, html_content, tags):
        """JSON-LD BlogPosting 스키마 생성"""
        plain_text = re.sub(r'<[^>]+>', '', html_content)
        meta_desc = plain_text[:160].strip()
        img_match = re.search(r'<img [^>]*src="([^"]+)"', html_content)
        image_url = img_match.group(1) if img_match else ""
        
        article = {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": title,
            "description": meta_desc,
            "keywords": ", ".join(tags[:5]) if tags else "",
            "datePublished": datetime.datetime.utcnow().isoformat() + "Z",
            "dateModified": datetime.datetime.utcnow().isoformat() + "Z",
            "author": {"@type": "Person", "name": "프로젝트 소민"},
            "publisher": {"@type": "Organization", "name": "프로젝트 소민"}
        }
        if image_url:
            article["image"] = image_url
        
        return '<script type="application/ld+json">\n' + json.dumps(article, ensure_ascii=False, indent=2) + '\n</script>\n'

