"""
네이버 블로그 자동 포스팅 모듈 v2
- Selenium 기반 브라우저 자동화
- Smart Editor ONE (2024~) 대응
- HTML 본문 직접 삽입 (JS innerHTML + 클립보드 방식)
- 카테고리 선택, 태그 입력, 공개 설정
- 발행 및 예약 발행 지원
- 캡차/2FA 수동 대기 지원
"""

import os
import time
import json
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
)

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    ChromeDriverManager = None

logger = logging.getLogger(__name__)

# ── 상수 ──────────────────────────────────────────────

NAVER_LOGIN_URL = "https://nid.naver.com/nidlogin.login"
NAVER_BLOG_WRITE_URL = "https://blog.naver.com/{blog_id}/postwrite"
NAVER_BLOG_WRITE_URL_V2 = "https://blog.naver.com/PostWriteForm.naver?blogId={blog_id}"
NAVER_BLOG_HOME = "https://blog.naver.com/{blog_id}"

# 로그인 후 대기 시간 (2FA, 캡차 대응)
LOGIN_WAIT_SECONDS = 5
# 에디터 로딩 대기
EDITOR_LOAD_TIMEOUT = 30
# 발행 완료 대기
PUBLISH_TIMEOUT = 15

# 히스토리 파일
HISTORY_DIR = "outputs/history"


class NaverPoster:
    """네이버 블로그 자동 포스팅 클래스"""

    def __init__(self, blog_id="jninsa", headless=False, chrome_profile=None):
        """
        Args:
            blog_id: 네이버 블로그 ID (URL의 blog.naver.com/{blog_id})
            headless: 헤드리스 모드 여부
            chrome_profile: Chrome 프로필 경로 (쿠키 재활용 시)
        """
        self.blog_id = blog_id
        self.headless = headless
        self.chrome_profile = chrome_profile
        self.driver = None
        self.is_logged_in = False

    def _init_driver(self):
        """Chrome WebDriver 초기화"""
        options = Options()

        if self.headless:
            options.add_argument("--headless=new")

        # 기본 옵션
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # 자동화 감지 우회
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Chrome 프로필 사용 (로그인 세션 유지)
        if self.chrome_profile:
            options.add_argument(f"--user-data-dir={self.chrome_profile}")

        try:
            if ChromeDriverManager:
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=options)
            else:
                self.driver = webdriver.Chrome(options=options)
        except Exception as e:
            logger.error(f"Chrome 드라이버 초기화 실패: {e}")
            raise

        # 자동화 감지 우회 스크립트
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    window.navigator.chrome = {runtime: {}};
                """
            },
        )

        logger.info("Chrome 드라이버 초기화 완료")

    def login(self, naver_id=None, naver_pw=None):
        """
        네이버 로그인 (클립보드 붙여넣기 방식 - 봇 탐지 우회)

        Args:
            naver_id: 네이버 아이디 (None이면 환경변수에서 로드)
            naver_pw: 네이버 비밀번호 (None이면 환경변수에서 로드)

        Returns:
            bool: 로그인 성공 여부
        """
        if not self.driver:
            self._init_driver()

        naver_id = naver_id or os.environ.get("NAVER_ID", "")
        naver_pw = naver_pw or os.environ.get("NAVER_PW", "")

        if not naver_id or not naver_pw:
            logger.error("네이버 ID/PW가 설정되지 않았습니다. .env 파일을 확인하세요.")
            return False

        try:
            self.driver.get(NAVER_LOGIN_URL)
            time.sleep(2)

            # 방법 1: 클립보드 붙여넣기 방식 (가장 안전)
            try:
                import pyperclip

                # ID 입력
                id_input = self.driver.find_element(By.CSS_SELECTOR, "#id")
                id_input.click()
                time.sleep(0.3)
                pyperclip.copy(naver_id)
                id_input.send_keys(Keys.CONTROL, "v")
                time.sleep(0.5)

                # PW 입력
                pw_input = self.driver.find_element(By.CSS_SELECTOR, "#pw")
                pw_input.click()
                time.sleep(0.3)
                pyperclip.copy(naver_pw)
                pw_input.send_keys(Keys.CONTROL, "v")
                time.sleep(0.5)

                logger.info("클립보드 붙여넣기 방식으로 입력 완료")

            except (ImportError, Exception) as clip_err:
                # 방법 2: JavaScript 직접 대입 (pyperclip 없을 때)
                logger.info(f"클립보드 방식 불가 ({clip_err}), JS 방식으로 전환")
                self.driver.execute_script(
                    """
                    var id_input = document.querySelector("#id");
                    var pw_input = document.querySelector("#pw");
                    var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value').set;
                    nativeInputValueSetter.call(id_input, arguments[0]);
                    id_input.dispatchEvent(new Event('input', {bubbles: true}));
                    nativeInputValueSetter.call(pw_input, arguments[1]);
                    pw_input.dispatchEvent(new Event('input', {bubbles: true}));
                    """,
                    naver_id, naver_pw,
                )
                time.sleep(0.5)

            # 로그인 버튼 클릭
            try:
                login_btn = self.driver.find_element(
                    By.CSS_SELECTOR, "#log\\.login, .btn_login, button[type='submit']"
                )
                login_btn.click()
            except NoSuchElementException:
                # 폼 직접 제출
                self.driver.execute_script(
                    "document.querySelector('form').submit();"
                )

            time.sleep(LOGIN_WAIT_SECONDS)

            # 로그인 확인
            if "nidlogin" not in self.driver.current_url:
                self.is_logged_in = True
                logger.info(f"네이버 로그인 성공: {naver_id}")
                return True
            else:
                # 캡차나 2차인증이 필요한 경우
                logger.warning(
                    "⚠️ 추가 인증 필요 (캡차/2FA). 브라우저에서 직접 처리해주세요."
                )
                if not self.headless:
                    # 최대 60초 대기 (5초 간격 체크)
                    logger.info("60초 동안 수동 인증 대기 중... (브라우저에서 처리하세요)")
                    for i in range(12):
                        time.sleep(5)
                        if "nidlogin" not in self.driver.current_url:
                            self.is_logged_in = True
                            logger.info("✅ 수동 인증 후 로그인 성공!")
                            return True
                        logger.info(f"  대기 중... ({(i+1)*5}/60초)")
                return False

        except Exception as e:
            logger.error(f"로그인 중 오류: {e}")
            return False

    def _navigate_to_editor(self):
        """블로그 글쓰기 에디터로 이동"""
        # 우선 v1 URL 시도, 실패 시 v2 URL
        write_url = NAVER_BLOG_WRITE_URL.format(blog_id=self.blog_id)
        self.driver.get(write_url)
        time.sleep(3)

        # 에디터가 안 뜨면 v2 URL 시도
        if "postwrite" not in self.driver.current_url.lower() and \
           "PostWrite" not in self.driver.current_url:
            write_url_v2 = NAVER_BLOG_WRITE_URL_V2.format(blog_id=self.blog_id)
            logger.info(f"v1 URL 실패, v2 URL 시도: {write_url_v2}")
            self.driver.get(write_url_v2)
            time.sleep(3)

        try:
            # Smart Editor 로딩 대기 (여러 에디터 버전 대응)
            WebDriverWait(self.driver, EDITOR_LOAD_TIMEOUT).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR,
                     ".se-content, #mainFrame, .blog_editor, "
                     ".se-component, #post-editor, [contenteditable='true']")
                )
            )
            time.sleep(2)

            # iframe 전환 (Smart Editor가 iframe 내에 있는 경우)
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                iframe_id = iframe.get_attribute("id") or ""
                iframe_name = iframe.get_attribute("name") or ""
                iframe_src = iframe.get_attribute("src") or ""
                if any(kw in (iframe_id + iframe_name + iframe_src).lower()
                       for kw in ["mainframe", "editor", "postwrite"]):
                    self.driver.switch_to.frame(iframe)
                    logger.info(f"iframe 전환 완료: {iframe_id or iframe_name}")
                    time.sleep(1)
                    break

            logger.info("에디터 로딩 완료")
            return True

        except TimeoutException:
            logger.error("에디터 로딩 타임아웃")
            # 현재 페이지 상태 로깅
            logger.error(f"현재 URL: {self.driver.current_url}")
            return False

    def _set_title(self, title):
        """글 제목 입력"""
        try:
            # Smart Editor ONE 제목 영역
            title_selectors = [
                ".se-title-text .se-text-paragraph",  # SE ONE
                "#subject",  # 구형 에디터
                ".post_title input",
                "[placeholder*='제목']",
            ]

            for selector in title_selectors:
                try:
                    title_elem = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    title_elem.click()
                    time.sleep(0.3)
                    title_elem.send_keys(title)
                    logger.info(f"제목 입력 완료: {title}")
                    return True
                except (TimeoutException, NoSuchElementException):
                    continue

            # JavaScript 방식 시도
            self.driver.execute_script(
                """
                var titleElem = document.querySelector('.se-title-text .se-text-paragraph')
                    || document.querySelector('#subject')
                    || document.querySelector('[placeholder*="제목"]');
                if (titleElem) {
                    titleElem.textContent = arguments[0];
                    titleElem.dispatchEvent(new Event('input', {bubbles: true}));
                }
            """,
                title,
            )
            logger.info(f"제목 입력 완료 (JS): {title}")
            return True

        except Exception as e:
            logger.error(f"제목 입력 실패: {e}")
            return False

    def _set_content_html(self, html_content):
        """본문 HTML 삽입"""
        try:
            # 방법 1: Smart Editor ONE - HTML 모드 전환 후 삽입
            # HTML 버튼 클릭
            html_btn_selectors = [
                ".se-toolbar-button-html",
                "button[data-name='html']",
                ".se-popup-button-html",
            ]

            html_mode = False
            for selector in html_btn_selectors:
                try:
                    btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    btn.click()
                    time.sleep(1)
                    html_mode = True
                    break
                except NoSuchElementException:
                    continue

            if html_mode:
                # HTML 입력 영역에 내용 삽입
                html_input_selectors = [
                    ".se-popup-content textarea",
                    "#html_code",
                    "textarea.se-html-textarea",
                ]
                for selector in html_input_selectors:
                    try:
                        textarea = self.driver.find_element(By.CSS_SELECTOR, selector)
                        textarea.clear()
                        textarea.send_keys(html_content)

                        # 확인 버튼 클릭
                        confirm_btn = self.driver.find_element(
                            By.CSS_SELECTOR,
                            ".se-popup-button-confirm, .se-popup-footer button",
                        )
                        confirm_btn.click()
                        time.sleep(1)
                        logger.info("HTML 모드로 본문 삽입 완료")
                        return True
                    except NoSuchElementException:
                        continue

            # 방법 2: JavaScript로 에디터 본문 직접 교체
            self.driver.execute_script(
                """
                // Smart Editor ONE
                var contentArea = document.querySelector('.se-content .se-component-content')
                    || document.querySelector('.se-main-container')
                    || document.querySelector('#content');
                if (contentArea) {
                    contentArea.innerHTML = arguments[0];
                    contentArea.dispatchEvent(new Event('input', {bubbles: true}));
                    return true;
                }

                // 구형 에디터 (contentEditable)
                var editableArea = document.querySelector('[contenteditable="true"]');
                if (editableArea) {
                    editableArea.innerHTML = arguments[0];
                    editableArea.dispatchEvent(new Event('input', {bubbles: true}));
                    return true;
                }

                return false;
            """,
                html_content,
            )
            logger.info("JS로 본문 HTML 삽입 완료")
            return True

        except Exception as e:
            logger.error(f"본문 삽입 실패: {e}")
            return False

    def _set_category(self, category_name):
        """카테고리 선택"""
        if not category_name:
            return True

        try:
            # 카테고리 드롭다운 클릭
            cat_btn_selectors = [
                ".post_category button",
                ".se-category-button",
                "#category",
            ]

            for selector in cat_btn_selectors:
                try:
                    cat_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    cat_btn.click()
                    time.sleep(0.5)

                    # 카테고리 목록에서 선택
                    cat_items = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        ".post_category li, .se-category-item, option",
                    )
                    for item in cat_items:
                        if category_name in item.text:
                            item.click()
                            logger.info(f"카테고리 선택: {category_name}")
                            return True
                    break
                except NoSuchElementException:
                    continue

            logger.warning(f"카테고리 '{category_name}'를 찾을 수 없음")
            return False

        except Exception as e:
            logger.error(f"카테고리 설정 실패: {e}")
            return False

    def _set_tags(self, tags):
        """태그 입력"""
        if not tags:
            return True

        try:
            tag_input_selectors = [
                ".post_tag input",
                "#tag",
                ".se-tag-input input",
                "[placeholder*='태그']",
            ]

            for selector in tag_input_selectors:
                try:
                    tag_input = self.driver.find_element(By.CSS_SELECTOR, selector)
                    for tag in tags:
                        tag_input.send_keys(tag)
                        tag_input.send_keys(Keys.ENTER)
                        time.sleep(0.3)
                    logger.info(f"태그 입력 완료: {tags}")
                    return True
                except NoSuchElementException:
                    continue

            logger.warning("태그 입력 영역을 찾을 수 없음")
            return False

        except Exception as e:
            logger.error(f"태그 입력 실패: {e}")
            return False

    def _publish(self):
        """발행 버튼 클릭"""
        try:
            publish_selectors = [
                ".publish_btn",
                "#publish_btn",
                "button.se-publish-button",
                ".btn_publish",
                "button[data-action='publish']",
            ]

            for selector in publish_selectors:
                try:
                    btn = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    btn.click()
                    time.sleep(2)

                    # 발행 확인 팝업이 있는 경우
                    confirm_selectors = [
                        ".confirm_btn",
                        ".se-popup-button-confirm",
                        "button.btn_ok",
                    ]
                    for confirm_sel in confirm_selectors:
                        try:
                            confirm_btn = self.driver.find_element(
                                By.CSS_SELECTOR, confirm_sel
                            )
                            confirm_btn.click()
                            break
                        except NoSuchElementException:
                            continue

                    time.sleep(PUBLISH_TIMEOUT)
                    logger.info("발행 완료")
                    return True
                except (TimeoutException, NoSuchElementException):
                    continue

            logger.error("발행 버튼을 찾을 수 없음")
            return False

        except Exception as e:
            logger.error(f"발행 중 오류: {e}")
            return False

    def _get_published_url(self):
        """발행된 글 URL 추출"""
        try:
            current_url = self.driver.current_url
            if "/postwrite" not in current_url and self.blog_id in current_url:
                return current_url

            # URL에서 logNo 추출 시도
            time.sleep(2)
            current_url = self.driver.current_url
            return current_url
        except Exception:
            return None

    def _save_history(self, result):
        """발행 히스토리 저장"""
        os.makedirs(HISTORY_DIR, exist_ok=True)
        history_file = os.path.join(HISTORY_DIR, "post_history.json")

        history = []
        if os.path.exists(history_file):
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except (json.JSONDecodeError, IOError):
                history = []

        history.append(result)

        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    def post(
        self,
        title,
        html_content,
        category=None,
        tags=None,
        publish_immediately=True,
    ):
        """
        블로그에 글 발행

        Args:
            title: 글 제목
            html_content: HTML 본문
            category: 카테고리 이름 (선택)
            tags: 태그 리스트 (선택)
            publish_immediately: 즉시 발행 여부

        Returns:
            dict: {
                'success': bool,
                'url': str or None,
                'title': str,
                'published_at': str,
                'error': str or None
            }
        """
        result = {
            "success": False,
            "url": None,
            "title": title,
            "published_at": None,
            "error": None,
        }

        try:
            if not self.is_logged_in:
                if not self.login():
                    result["error"] = "로그인 실패"
                    return result

            # 1. 에디터 이동
            if not self._navigate_to_editor():
                result["error"] = "에디터 로딩 실패"
                return result

            # 2. 제목 입력
            if not self._set_title(title):
                result["error"] = "제목 입력 실패"
                return result

            # 3. 본문 삽입
            if not self._set_content_html(html_content):
                result["error"] = "본문 삽입 실패"
                return result

            # 4. 카테고리 선택
            self._set_category(category)

            # 5. 태그 입력
            self._set_tags(tags)

            # 6. 발행
            if publish_immediately:
                if self._publish():
                    result["success"] = True
                    result["url"] = self._get_published_url()
                    result["published_at"] = datetime.now().isoformat()
                else:
                    result["error"] = "발행 실패"
            else:
                # 임시저장 (발행 대신)
                result["success"] = True
                result["published_at"] = None
                result["error"] = "임시저장 모드 (예약 발행은 scheduler.py에서 처리)"

            # 히스토리 저장
            self._save_history(result)

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"포스팅 중 오류: {e}")

        return result

    def close(self):
        """브라우저 종료"""
        if self.driver:
            self.driver.quit()
            self.driver = None
            self.is_logged_in = False
            logger.info("브라우저 종료")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ── 편의 함수 ──────────────────────────────────────────


def quick_post(title, html_content, category=None, tags=None, blog_id="jninsa"):
    """
    간편 포스팅 함수

    Usage:
        from src.naver_poster import quick_post
        result = quick_post("제목", "<p>내용</p>", tags=["상표", "특허"])
    """
    with NaverPoster(blog_id=blog_id) as poster:
        return poster.post(title, html_content, category, tags)


def generate_and_post(
    topic,
    persona_id="yun_ung_chae",
    persona_name="윤웅채",
    category=None,
    tags=None,
    blog_id="jninsa",
    auto_title=True,
):
    """
    키워드 → 생성 → 포맷팅 → 포스팅 원스톱 함수

    Args:
        topic: 키워드/주제
        persona_id: 페르소나 ID
        persona_name: 페르소나 이름
        category: 블로그 카테고리
        tags: 태그 리스트
        blog_id: 블로그 ID
        auto_title: 자동 제목 생성 여부

    Returns:
        dict: 포스팅 결과
    """
    from src.engine import generate_column_with_validation
    from src.formatter import format_column_html

    # 1. 컨텐츠 생성 + 유사도 검증
    gen_result = generate_column_with_validation(persona_id, persona_name, topic)

    if not gen_result["success"]:
        return {
            "success": False,
            "error": f"컨텐츠 생성 실패 (유사도 미통과, 최대 유사도: {gen_result['similarity_check']['max_doc_similarity']})",
            "content": gen_result["content"],
        }

    content = gen_result["content"]

    # 2. 제목 추출 또는 생성
    if auto_title:
        title = _extract_or_generate_title(topic, content)
    else:
        title = topic

    # 3. HTML 포맷팅
    html = format_column_html(content, persona_id, include_images=False)

    # 4. 포스팅
    post_result = quick_post(title, html, category, tags, blog_id)
    post_result["raw_content"] = content
    post_result["generation_attempts"] = gen_result["attempts"]

    return post_result


def _extract_or_generate_title(topic, content):
    """본문 첫 소제목이나 주제에서 제목 생성"""
    import re

    # 본문에서 첫 **소제목** 추출 시도
    match = re.search(r"\*\*(.+?)\*\*", content)
    if match:
        title = match.group(1).strip()
        if len(title) > 10:
            return title

    # 기본: 주제를 그대로 제목으로 사용
    return topic


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(override=True)

    logging.basicConfig(level=logging.INFO)

    # 테스트: 드라이버만 초기화 (실제 발행 X)
    print("=== NaverPoster 테스트 ===")
    print(f"NAVER_ID 설정: {'✅' if os.environ.get('NAVER_ID') else '❌'}")
    print(f"NAVER_PW 설정: {'✅' if os.environ.get('NAVER_PW') else '❌'}")
    print("포스터 모듈 로드 완료")
