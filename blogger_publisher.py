import os
import pickle
import re
import base64
import json
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request

class BloggerPublisher:
    def __init__(self, headless=True):
        """
        공식 Google Blogger API v3를 사용하는 퍼블리셔입니다.
        """
        # 환경 변수에서 먼저 읽기
        self.blog_id = os.getenv("BLOGGER_BLOG_ID", "")
        
        # 스트림릿 환경인지 아주 조심스럽게 확인
        if not self.blog_id:
            try:
                # 깃허브 액션이나 로컬에서는 이 블록이 실행되지 않아야 함
                if "STREAMLIT_RUNTIME" in os.environ:
                    import streamlit as st
                    self.blog_id = str(st.secrets.get("BLOGGER_BLOG_ID", ""))
            except:
                pass
            
        # BLOGGER_BLOG_ID에서 숫자만 추출
        match = re.search(r"(\d+)", str(self.blog_id))
        if match:
            self.blog_id = match.group(1)
            
        self.service = None
        self.headless = headless

    def log(self, msg):
        print(f"[BloggerPublisher] {msg}")

    def _get_credentials(self):
        creds = None
        # google-auth와 google-api-python-client 라이브러리 필요
        from google.oauth2.credentials import Credentials

        # 1. 환경 변수에서 직접 체크 (최우선)
        token_b64 = os.getenv("GOOGLE_TOKEN_PICKLE_BASE64", "")
        if token_b64:
            try:
                token_data = base64.b64decode(token_b64)
                creds = pickle.loads(token_data)
                self.log("[성공] 환경 변수에서 인증 정보를 불러왔습니다.")
            except:
                pass

        # 2. 스트림릿 Secrets 체크 (조심스럽게)
        if not creds and "STREAMLIT_RUNTIME" in os.environ:
            try:
                import streamlit as st
                if "GOOGLE_TOKEN_PICKLE_BASE64" in st.secrets:
                    token_data = base64.b64decode(st.secrets["GOOGLE_TOKEN_PICKLE_BASE64"])
                    creds = pickle.loads(token_data)
                    self.log("[클라우드] 스트림릿 Secrets에서 인증 정보를 불러왔습니다.")
            except:
                pass

        # 3. 로컬 파일 체크
        if not creds and os.path.exists('token.pickle'):
            self.log("[로컬] 로컬 token.pickle에서 인증 정보를 불러옵니다.")
            with open('token.pickle', 'rb') as token:
                creds = pickle.loads(token.read())

        # 토큰 갱신
        if creds and creds.expired and creds.refresh_token:
            self.log("[갱신] 만료된 토큰을 갱신합니다...")
            creds.refresh(Request())
            # 갱신된 토큰 저장 (로컬일 경우만)
            if os.path.exists('token.pickle'):
                with open('token.pickle', 'wb') as token:
                    token.write(pickle.dumps(creds))

        if not creds:
            raise Exception("인증 정보(token.pickle 또는 Secrets)를 찾을 수 없습니다. generate_token.py를 먼저 실행하세요.")
            
        return creds

    def _get_service(self):
        if self.service:
            return self.service
        creds = self._get_credentials()
        self.service = build('blogger', 'v3', credentials=creds)
        return self.service

    def publish(self, title, html_content, tags=[]):
        if not self.blog_id:
            return {"success": False, "message": "BLOGGER_BLOG_ID가 설정되지 않았습니다."}

        try:
            self.log("[연결] 구글 Blogger API 연결 중...")
            service = self._get_service()
            
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
            self.log(f"[성공] 포스팅 완료! 주소: {post_url}")
            return {"success": True, "message": "구글 블로그에 성공적으로 발행되었습니다!", "url": post_url}

        except HttpError as e:
            err = json.loads(e.content).get('error', {})
            msg = err.get('message', str(e))
            self.log(f"[에러] API 오류: {msg}")
            return {"success": False, "message": f"Blogger API 오류: {msg}"}
        except Exception as e:
            self.log(f"[실패] 포스팅 실패: {e}")
            return {"success": False, "message": str(e)}
