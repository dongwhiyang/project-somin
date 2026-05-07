"""
프로젝트 소민 — 티스토리 Selenium 자동 발행 모듈
크롬 유저 프로필을 활용하여 로그인 세션을 유지하고,
글쓰기 → HTML 모드 → 본문 입력 → 태그 → 발행까지 자동화합니다.
"""
import os
import time
import logging
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv(override=True)

logger = logging.getLogger(__name__)

BLOG_NAME = os.getenv("TISTORY_BLOG_NAME", "")
CHROME_USER_DATA = os.getenv("CHROME_USER_DATA_DIR", "")
CHROME_PROFILE = os.getenv("CHROME_PROFILE_DIR", "Default")


class TistoryPublisher:
    """Selenium 기반 티스토리 자동 발행기"""

    def __init__(self, headless: bool = False, status_callback=None):
        """
        Args:
            headless: True면 브라우저 숨김 모드
            status_callback: 상태 메시지 콜백 함수 (Streamlit 표시용)
        """
        self.driver = None
        self.headless = headless
        self._status = status_callback or (lambda msg: logger.info(msg))

    def _log(self, msg: str):
        self._status(msg)
        logger.info(msg)

    def _init_driver(self):
        """크롬 드라이버 초기화 (유저 프로필 로드)"""
        self._log("🌐 크롬 브라우저를 준비하고 있습니다...")
        opts = Options()

        # 크롬 유저 프로필 연결 (로그인 세션 유지)
        if CHROME_USER_DATA:
            opts.add_argument(f"user-data-dir={CHROME_USER_DATA}")
            opts.add_argument(f"profile-directory={CHROME_PROFILE}")
            self._log(f"   프로필: {CHROME_PROFILE}")

        if self.headless:
            opts.add_argument("--headless=new")

        # 봇 탐지 방지
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        opts.add_argument("--window-size=1280,900")

        # ─ Chrome 안정성 옵션 (DevToolsActivePort 에러 방지) ─
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--remote-debugging-port=0")   # 랜덤 포트 → 충돌 방지
        opts.add_argument("--disable-extensions")
        opts.add_argument("--disable-software-rasterizer")

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=opts)


        # navigator.webdriver 속성 숨기기
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self._log("✅ 크롬 브라우저 준비 완료")

    def _safe_delay(self, sec: float = 2.0):
        """사람처럼 행동하기 위한 안전 딜레이"""
        time.sleep(sec)

    def _wait_and_find(self, by, value, timeout=15):
        """요소가 나타날 때까지 대기 후 반환"""
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )

    def _wait_and_click(self, by, value, timeout=15):
        """클릭 가능한 요소가 나타날 때까지 대기 후 클릭"""
        el = WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable((by, value))
        )
        el.click()
        return el

    # ─────────────────────────────────────────
    # 메인 발행 흐름
    # ─────────────────────────────────────────
    def publish(self, title: str, html_content: str, tags: list[str] = None) -> dict:
        """
        티스토리에 글을 자동 발행합니다.
        Returns: {"success": bool, "message": str, "url": str}
        """
        if not BLOG_NAME:
            return {"success": False, "message": "TISTORY_BLOG_NAME이 .env에 설정되지 않았습니다.", "url": ""}

        try:
            self._init_driver()
            self._safe_delay(2)

            # 1) 글쓰기 페이지 이동
            self._navigate_to_write()
            self._safe_delay(3)

            # 2) 임시저장 팝업 처리
            self._dismiss_popup()
            self._safe_delay(1)

            # 3) 제목 입력
            self._input_title(title)
            self._safe_delay(2)

            # 4) HTML 모드 전환 & 본문 입력
            self._switch_to_html_and_input(html_content)
            self._safe_delay(2)

            # 5) 태그 입력
            if tags:
                self._input_tags(tags)
                self._safe_delay(2)

            # 6) 발행 버튼 클릭
            result_url = self._click_publish()
            self._safe_delay(3)

            return {
                "success": True,
                "message": "🎉 티스토리 발행이 완료되었습니다!",
                "url": result_url,
            }

        except Exception as e:
            logger.exception("발행 실패")
            return {
                "success": False,
                "message": f"❌ 발행 중 오류 발생: {str(e)}",
                "url": "",
            }
        finally:
            if self.driver:
                self._safe_delay(2)
                self.driver.quit()
                self._log("🔒 브라우저를 닫았습니다.")

    # ─────────────────────────────────────────
    # 단계별 메서드
    # ─────────────────────────────────────────
    def _navigate_to_write(self):
        """글쓰기 페이지로 이동"""
        write_url = f"https://{BLOG_NAME}.tistory.com/manage/newpost"
        self._log(f"📝 글쓰기 페이지로 이동: {write_url}")
        self.driver.get(write_url)
        self._safe_delay(3)

        # 로그인 필요 여부 확인
        current = self.driver.current_url
        if "login" in current or "accounts" in current:
            self._log("⚠️ 로그인이 필요합니다. 크롬 프로필에 로그인 세션이 없습니다.")
            self._log("   → 크롬에서 티스토리에 먼저 로그인한 후 다시 시도하세요.")
            raise Exception(
                "로그인 세션이 없습니다. 크롬 브라우저에서 티스토리에 먼저 로그인해 주세요. "
                "(.env의 CHROME_USER_DATA_DIR 경로도 확인하세요)"
            )

    def _dismiss_popup(self):
        """'임시저장된 글이 있습니다' 등의 팝업 닫기"""
        try:
            # Alert 형태
            alert = self.driver.switch_to.alert
            alert.dismiss()
            self._log("   팝업(Alert) 닫기 완료")
        except Exception:
            pass

        # 버튼 형태의 팝업
        try:
            close_btns = self.driver.find_elements(
                By.CSS_SELECTOR, "button.btn-default, button.cancel, .mce-close, .btn_cancel"
            )
            for btn in close_btns:
                if btn.is_displayed():
                    btn.click()
                    self._log("   팝업 버튼 닫기 완료")
                    break
        except Exception:
            pass

    def _input_title(self, title: str):
        """제목 입력"""
        self._log(f"📌 제목 입력: {title[:40]}...")
        try:
            # 티스토리 에디터 제목 입력란
            title_el = self._wait_and_find(By.ID, "post-title-inp")
            title_el.clear()
            title_el.send_keys(title)
        except Exception:
            # 대체 셀렉터
            try:
                title_el = self._wait_and_find(
                    By.CSS_SELECTOR, "input.txt_tit, #title, textarea.title"
                )
                title_el.clear()
                title_el.send_keys(title)
            except Exception:
                self._log("   ⚠️ 제목 입력란을 찾을 수 없습니다. JS로 시도합니다.")
                self.driver.execute_script(
                    'document.querySelector("#post-title-inp, .txt_tit, #title").value = arguments[0];',
                    title,
                )

    def _switch_to_html_and_input(self, html_content: str):
        """HTML 모드로 전환하고 본문을 입력합니다."""
        self._log("🔄 HTML 모드로 전환 중...")

        # 방법 1: 더보기(···) → HTML 모드
        try:
            more_btn = self.driver.find_element(
                By.CSS_SELECTOR, "button.btn_more, .btn-more, button[data-name='more']"
            )
            more_btn.click()
            self._safe_delay(1)

            html_btn = self.driver.find_element(
                By.XPATH, "//*[contains(text(), 'HTML')]"
            )
            html_btn.click()
            self._safe_delay(1)
            self._log("   ✅ HTML 모드 전환 완료 (메뉴)")
        except Exception:
            pass

        # 방법 2: 직접 HTML 버튼 찾기
        try:
            html_tabs = self.driver.find_elements(
                By.CSS_SELECTOR, "button.html, .btn_html, [data-mode='html']"
            )
            for tab in html_tabs:
                if tab.is_displayed():
                    tab.click()
                    self._safe_delay(1)
                    self._log("   ✅ HTML 모드 전환 완료 (탭)")
                    break
        except Exception:
            pass

        self._safe_delay(1)

        # 본문 입력
        self._log("📄 HTML 본문을 입력하고 있습니다...")
        input_done = False

        # CodeMirror(HTML 에디터) 시도
        try:
            cm_el = self.driver.find_element(By.CSS_SELECTOR, ".CodeMirror")
            self.driver.execute_script(
                "arguments[0].CodeMirror.setValue(arguments[1]);",
                cm_el,
                html_content,
            )
            input_done = True
            self._log("   ✅ CodeMirror로 입력 완료")
        except Exception:
            pass

        # textarea 시도
        if not input_done:
            try:
                ta = self.driver.find_element(
                    By.CSS_SELECTOR, "textarea.html_source, #html_source, textarea#content"
                )
                ta.clear()
                self.driver.execute_script(
                    "arguments[0].value = arguments[1];", ta, html_content
                )
                input_done = True
                self._log("   ✅ textarea로 입력 완료")
            except Exception:
                pass

        # contenteditable iframe 시도
        if not input_done:
            try:
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    try:
                        self.driver.switch_to.frame(iframe)
                        body = self.driver.find_element(By.TAG_NAME, "body")
                        self.driver.execute_script(
                            "arguments[0].innerHTML = arguments[1];",
                            body,
                            html_content,
                        )
                        self.driver.switch_to.default_content()
                        input_done = True
                        self._log("   ✅ iframe으로 입력 완료")
                        break
                    except Exception:
                        self.driver.switch_to.default_content()
            except Exception:
                pass

        if not input_done:
            raise Exception("HTML 본문 입력 실패: 에디터를 찾을 수 없습니다.")

    def _input_tags(self, tags: list[str]):
        """태그 입력"""
        self._log(f"🏷️ 태그 입력: {', '.join(tags[:5])}")
        try:
            tag_input = self.driver.find_element(
                By.CSS_SELECTOR, "input.tf_tag, input[placeholder*='태그'], #tagText"
            )
            for tag in tags[:10]:
                tag_input.clear()
                tag_input.send_keys(tag)
                tag_input.send_keys(Keys.ENTER)
                self._safe_delay(0.5)
            self._log("   ✅ 태그 입력 완료")
        except Exception:
            self._log("   ⚠️ 태그 입력란을 찾을 수 없습니다. 태그 없이 진행합니다.")

    def _click_publish(self) -> str:
        """발행 버튼 클릭"""
        self._log("🚀 발행 버튼을 클릭합니다...")

        # 1) "완료" 또는 "발행" 버튼 클릭 (설정 패널 열기)
        try:
            publish_open = self.driver.find_element(
                By.CSS_SELECTOR,
                "button.btn_publish, button.btn-publish, "
                "button.publish_btn, #publish-layer-btn, "
                "button[data-name='publish']"
            )
            publish_open.click()
            self._safe_delay(2)
        except Exception:
            # XPath로 시도
            try:
                btns = self.driver.find_elements(
                    By.XPATH, "//button[contains(text(), '완료') or contains(text(), '발행')]"
                )
                for btn in btns:
                    if btn.is_displayed():
                        btn.click()
                        self._safe_delay(2)
                        break
            except Exception:
                pass

        # 2) 최종 발행 확인 버튼
        try:
            confirm_btn = self.driver.find_element(
                By.CSS_SELECTOR,
                "button.btn_ok, button.confirm, "
                "button.btn-primary, #publish-btn"
            )
            confirm_btn.click()
            self._safe_delay(3)
            self._log("   ✅ 발행 완료!")
        except Exception:
            try:
                btns = self.driver.find_elements(
                    By.XPATH, "//button[contains(text(), '발행') or contains(text(), '공개')]"
                )
                for btn in btns:
                    if btn.is_displayed():
                        btn.click()
                        self._safe_delay(3)
                        break
            except Exception:
                self._log("   ⚠️ 발행 확인 버튼을 찾지 못했습니다.")

        # 발행된 URL 반환
        result_url = self.driver.current_url
        self._log(f"   📎 결과 URL: {result_url}")
        return result_url
