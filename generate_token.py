import os
import pickle
import base64
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/blogger']

def main():
    creds = None
    
    # 1. 기존 token.pickle 파일이 있다면 삭제 (새로 발급받기 위함)
    if os.path.exists('token.pickle'):
        os.remove('token.pickle')
        print("🗑️ 기존 token.pickle을 삭제했습니다. 새로 인증을 진행합니다.")

    # 2. credentials.json 파일 확인
    if not os.path.exists('credentials.json'):
        print("❌ credentials.json 파일이 없습니다. Google Cloud Console에서 다운로드 받아 폴더에 넣어주세요.")
        return

    # 3. 새로운 인증 진행 (refresh token을 강제로 받기 위해 prompt='consent' 사용)
    print("🌐 브라우저 창이 열리면 Google 로그인을 진행해 주세요...")
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    # prompt='consent'를 추가하여 만료되지 않는 refresh token을 확실하게 받아옵니다.
    creds = flow.run_local_server(port=8088, prompt='consent')

    # 4. 새로운 토큰 저장
    with open('token.pickle', 'wb') as token:
        pickle.dump(creds, token)
    
    # 5. 스트림릿 시크릿용 Base64 문자열 출력
    with open('token.pickle', 'rb') as token:
        token_data = token.read()
        base64_str = base64.b64encode(token_data).decode('utf-8')
    
    print("\n✅ [성공] 새로운 토큰이 발급되었습니다!")
    print("👇 아래의 문자열을 복사해서 Streamlit Cloud의 Secrets 항목 중 GOOGLE_TOKEN_PICKLE_BASE64 에 붙여넣기 하세요.\n")
    print("-" * 50)
    print(base64_str)
    print("-" * 50)

if __name__ == '__main__':
    main()
