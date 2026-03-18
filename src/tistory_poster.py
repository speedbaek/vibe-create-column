"""
티스토리 블로그 자동 발행 모듈
- Playwright sync API (네이버와 동일한 구조)
- 카카오 로그인
- TinyMCE HTML 모드로 콘텐츠 삽입
- 카테고리 자동 선택
- 휴먼 시뮬레이션 발행
"""

import os
import time
import random
import json

PW_USER_DATA_BASE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "pw_browser_data"
)


def _get_blog_config(blog_key):
    """blogs.json에서 블로그 설정 로드"""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "blogs.json"
    )
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("blogs", {}).get(blog_key)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _log(msg):
    print(f"[TistoryPoster] {msg}")


class TistoryPoster:
    def __init__(self, progress_callback=None, blog_key="tistory_yun"):
        self.context = None
        self.page = None
        self._pw = None
        self._progress_cb = progress_callback
        self._blog_key = blog_key
        self._blog_config = _get_blog_config(blog_key) or {}

    def _progress(self, step, total, msg):
        _log(msg)
        if self._progress_cb:
            self._progress_cb(step, total, msg)

    def connect(self):
        """Playwright Chrome 실행 (persistent context)"""
        from playwright.sync_api import sync_playwright

        user_data = f"{PW_USER_DATA_BASE}_tistory_{self._blog_key}"
        os.makedirs(user_data, exist_ok=True)

        self._pw = sync_playwright().start()
        self.context = self._pw.chromium.launch_persistent_context(
            user_data_dir=user_data,
            headless=False,
            channel="chrome",
            args=[
                "--no-first-run",
                "--disable-blink-features=AutomationControlled",
            ],
            viewport={"width": 1280, "height": 900},
            locale="ko-KR",
        )
        # confirm 다이얼로그 자동 승인 (HTML 모드 전환용)
        self.context.add_init_script('window.confirm = function() { return true; };')
        pages = self.context.pages
        self.page = pages[0] if pages else self.context.new_page()
        _log("Chrome 실행 완료 (티스토리용 프로필)")

    def login(self, kakao_id=None, kakao_pw=None):
        """카카오 로그인으로 티스토리 접속"""
        id_key = self._blog_config.get("env_id_key", "KAKAO_ID")
        pw_key = self._blog_config.get("env_pw_key", "KAKAO_PW")
        kakao_id = kakao_id or os.environ.get(id_key, "")
        kakao_pw = kakao_pw or os.environ.get(pw_key, "")

        if not kakao_id or not kakao_pw:
            raise ValueError(f"{id_key}/{pw_key}가 .env에 설정되지 않았습니다.")

        blog_url = self._blog_config.get("blog_url", "https://www.tistory.com")

        # 이미 로그인 상태인지 확인
        self.page.goto(blog_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # 로그인 상태 체크: 관리 페이지 접근 가능 여부
        manage_url = self._blog_config.get("manage_url", f"{blog_url}/manage")
        self.page.goto(manage_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        current_url = self.page.url
        if "manage" in current_url and "login" not in current_url:
            _log("이미 로그인 상태입니다.")
            return True

        # 1단계: 티스토리 로그인 -> "카카오계정으로 로그인" 버튼
        _log("로그인 필요 - 카카오 로그인 시도")
        self.page.goto("https://www.tistory.com/auth/login", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # "카카오계정으로 로그인" 노란 버튼 - Playwright .click()으로 실제 이벤트 발생
        kakao_btn = self.page.locator('a.link_kakao_id')
        if kakao_btn.count() > 0:
            kakao_btn.click()
            _log("카카오 로그인 버튼 클릭 (link_kakao_id)")
        else:
            # fallback: 텍스트로 찾기
            self.page.locator('text=카카오계정으로 로그인').click()
            _log("카카오 로그인 버튼 클릭 (text)")
        time.sleep(5)
        # 페이지 전환 대기
        self.page.wait_for_load_state("domcontentloaded", timeout=15000)

        # 2단계: 카카오 계정 선택 화면 - a.wrap_profile 클릭
        current = self.page.url
        if "accounts.kakao.com" in current:
            try:
                # 첫 번째 계정 프로필 클릭 (a.wrap_profile)
                account_link = self.page.locator('a.wrap_profile').first
                if account_link.count() > 0:
                    account_link.click()
                    _log("카카오 계정 선택 (wrap_profile 클릭)")
                else:
                    # fallback
                    self.page.locator('ul.list_easy li:first-child a').click()
                    _log("카카오 계정 선택 (list_easy 클릭)")
                time.sleep(5)
            except Exception as e:
                _log(f"카카오 계정 선택 실패: {e}")

        # 3단계: ID/PW 입력 필요한 경우 (간편로그인 없을 때)
        current = self.page.url
        if "accounts.kakao.com" in current:
            try:
                email_input = self.page.query_selector(
                    'input[name="loginId"], input[name="email"], input#loginId--1'
                )
                if email_input:
                    email_input.fill(kakao_id)
                    time.sleep(0.5)
                    pw_input = self.page.query_selector('input[type="password"]')
                    if pw_input:
                        pw_input.fill(kakao_pw)
                        time.sleep(0.5)
                    submit = self.page.query_selector('button[type="submit"]')
                    if submit:
                        submit.click()
                        time.sleep(5)
                    _log("카카오 ID/PW 로그인 완료")
            except Exception as e:
                _log(f"카카오 로그인 실패: {e}")
                _log("수동으로 로그인해주세요. 30초 대기...")
                time.sleep(30)

        # 카카오 -> 티스토리 리다이렉트 완료 대기
        _log("티스토리 리다이렉트 대기...")
        for _ in range(15):
            time.sleep(2)
            current = self.page.url
            _log(f"  URL: {current[:80]}")
            if "tistory.com" in current and "accounts.kakao.com" not in current and "auth/login" not in current:
                _log("로그인 성공! 티스토리 세션 확보")
                return True

        # manage 접근 재시도
        try:
            self.page.goto(manage_url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(3)
            if "auth/login" not in self.page.url:
                _log("로그인 성공!")
                return True
        except Exception:
            pass

        _log("로그인 확인 실패. 수동 로그인 후 재시도하세요.")
        return False

    def _select_category(self, keyword):
        """키워드 기반 카테고리 자동 선택"""
        categories = self._blog_config.get("categories", {})
        default_cat = self._blog_config.get("default_category", "")

        # 키워드로 카테고리 매칭
        matched_category = default_cat
        for cat_name, keywords in categories.items():
            if any(kw in keyword for kw in keywords):
                matched_category = cat_name
                break

        if not matched_category:
            return

        try:
            # 카테고리 드롭다운 클릭
            cat_selector = self.page.query_selector(
                'select.tf_category, #category, select[name="category"], .btn_category'
            )
            if cat_selector:
                tag_name = cat_selector.evaluate("el => el.tagName.toLowerCase()")
                if tag_name == "select":
                    # select 엘리먼트 → option에서 매칭
                    options = cat_selector.query_selector_all("option")
                    for opt in options:
                        text = opt.inner_text().strip()
                        if matched_category in text:
                            value = opt.get_attribute("value")
                            cat_selector.select_option(value=value)
                            _log(f"카테고리 선택: {matched_category}")
                            return
                else:
                    # 버튼 형태 → 클릭 후 목록에서 선택
                    cat_selector.click()
                    time.sleep(1)
                    cat_items = self.page.query_selector_all('.layer_category li, .list_category li')
                    for item in cat_items:
                        if matched_category in item.inner_text():
                            item.click()
                            _log(f"카테고리 선택: {matched_category}")
                            return

            _log(f"카테고리 '{matched_category}' 선택 실패 -기본 카테고리 유지")
        except Exception as e:
            _log(f"카테고리 선택 오류: {e}")

    def post_human_like(self, title, html_content, keyword="", tags=None):
        """
        휴먼 시뮬레이션 발행

        Args:
            title: 글 제목
            html_content: HTML 형식 본문
            keyword: 키워드 (카테고리 매칭용)
            tags: 태그 리스트

        Returns:
            dict: {"success": bool, "url": str, "error": str}
        """
        total_steps = 8
        try:
            editor_url = self._blog_config.get(
                "editor_url",
                f"{self._blog_config.get('blog_url', '')}/manage/newpost"
            )

            # 1. 에디터 페이지 이동
            self._progress(1, total_steps, "에디터 페이지 이동 중...")
            self.page.goto(editor_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3 + random.uniform(0.5, 1.5))

            # 2. 카테고리 선택
            self._progress(2, total_steps, f"카테고리 선택 중... ({keyword})")
            self._select_category(keyword)
            time.sleep(1 + random.uniform(0.3, 0.8))

            # 3. 제목 입력
            self._progress(3, total_steps, f"제목 입력 중... ({title[:30]})")
            title_input = self.page.wait_for_selector(
                '#post-title-inp',
                timeout=10000
            )
            if title_input:
                title_input.click()
                time.sleep(0.5)
                # 한 글자씩 타이핑 (휴먼 시뮬레이션)
                for char in title:
                    title_input.type(char, delay=random.randint(30, 80))
                time.sleep(1 + random.uniform(0.3, 0.8))

            # 4~5. HTML 모드 전환 + 콘텐츠 삽입
            self._progress(4, total_steps, "HTML 모드 전환 + 콘텐츠 삽입 중...")

            # HTML 모드 전환 (confirm 자동 승인)
            self.page.evaluate('window.confirm = function() { return true; };')
            self.page.locator('#editor-mode-layer-btn-open').click()
            time.sleep(1)
            self.page.locator('#editor-mode-html').click()
            time.sleep(3)
            _log("HTML 모드 전환 완료")

            # 클립보드 붙여넣기로 CodeMirror에 HTML 삽입
            self.page.evaluate(f'navigator.clipboard.writeText({json.dumps(html_content)})')
            time.sleep(1)
            cm = self.page.locator('.CodeMirror.cm-s-tistory-html')
            cm.click()
            time.sleep(0.5)
            self.page.keyboard.press('Control+a')
            time.sleep(0.3)
            self.page.keyboard.press('Control+v')
            time.sleep(2)

            # 삽입 확인
            inserted = self.page.evaluate("""(() => {
                const cms = document.querySelectorAll('.CodeMirror');
                for (const cm of cms) {
                    if (cm.CodeMirror && cm.offsetParent !== null) {
                        const len = cm.CodeMirror.getValue().length;
                        return len > 0 ? 'clipboard_paste: ' + len : null;
                    }
                }
                return null;
            })()""")
            _log(f"HTML 삽입 결과: {inserted}")

            if not inserted:
                return {"success": False, "url": "", "error": "HTML content insertion failed"}

            time.sleep(2 + random.uniform(0.5, 1.5))

            # 6. 태그 입력
            if tags:
                self._progress(6, total_steps, f"태그 입력 중... ({', '.join(tags[:3])})")
                tag_input = self.page.query_selector('#tagText')
                if tag_input:
                    for tag in tags[:10]:  # 최대 10개
                        tag_input.fill(tag)
                        time.sleep(0.3)
                        tag_input.press("Enter")
                        time.sleep(0.5 + random.uniform(0.1, 0.3))
            else:
                self._progress(6, total_steps, "태그 생략")

            # 7. 발행 버튼 클릭
            self._progress(7, total_steps, "발행 버튼 클릭 중...")
            time.sleep(1 + random.uniform(0.5, 1.0))

            # "완료" 버튼 = 발행 레이어 열기 (publish-layer-btn)
            publish_layer_btn = self.page.locator('#publish-layer-btn')
            if publish_layer_btn.count() > 0:
                publish_layer_btn.click()
                _log("발행 레이어 열림")
                time.sleep(2 + random.uniform(0.3, 0.8))

                # 공개 설정: #open20 (공개) 라디오 선택 (기본이 비공개임)
                open_radio = self.page.locator('#open20')
                if open_radio.count() > 0:
                    open_radio.click()
                    _log("공개 설정 완료")
                    time.sleep(0.5)

                # 최종 "공개로 발행" 버튼 클릭 (#publish-btn)
                final_btn = self.page.locator('#publish-btn')
                if final_btn.count() > 0:
                    final_btn.click()
                    _log("공개로 발행 클릭!")
                    time.sleep(5 + random.uniform(1, 2))
                else:
                    _log("publish-btn not found, trying fallback")
                    self.page.evaluate("""() => {
                        const btns = document.querySelectorAll('button');
                        for (const b of btns) {
                            if (b.offsetParent && b.textContent.includes('발행')) {
                                b.click(); return;
                            }
                        }
                    }""")
                    time.sleep(5 + random.uniform(1, 2))
            else:
                _log("완료 버튼 없음!")
                return {"success": False, "url": "", "error": "publish button not found"}

            # 8. 발행 결과 확인
            self._progress(8, total_steps, "발행 결과 확인 중...")
            time.sleep(3)

            current_url = self.page.url
            blog_url = self._blog_config.get("blog_url", "")

            # 발행 후 리다이렉트된 URL 확인
            if blog_url.replace("https://", "") in current_url and "/manage/newpost" not in current_url:
                _log(f"발행 성공! URL: {current_url}")
                return {"success": True, "url": current_url, "error": ""}

            # 관리 페이지로 돌아간 경우 → 최신 글 URL 추출
            if "/manage" in current_url:
                try:
                    self.page.goto(f"{blog_url}/manage/posts", wait_until="domcontentloaded", timeout=10000)
                    time.sleep(2)
                    first_post = self.page.query_selector('.list_post li:first-child a, .post_list a:first-child')
                    if first_post:
                        post_url = first_post.get_attribute("href")
                        if post_url and not post_url.startswith("http"):
                            post_url = f"{blog_url}{post_url}"
                        _log(f"발행 성공! URL: {post_url}")
                        return {"success": True, "url": post_url or current_url, "error": ""}
                except Exception:
                    pass

            _log(f"발행 완료 (URL 확인 불가): {current_url}")
            return {"success": True, "url": current_url, "error": ""}

        except Exception as e:
            _log(f"발행 오류: {e}")
            return {"success": False, "url": "", "error": str(e)}

    def close(self):
        """브라우저 종료"""
        try:
            if self.context:
                self.context.close()
            if self._pw:
                self._pw.stop()
            _log("브라우저 종료 완료")
        except Exception as e:
            _log(f"브라우저 종료 오류: {e}")


    def post_full_pipeline(
        self,
        topic,
        persona_id="yun_ung_chae",
        persona_name="윤웅채",
        model_id="claude-sonnet-4-6",
        temperature=0.7,
        include_images=True,
        image_count=None,
        title_count=3,
        blog_id=None,
        category_no=None,
        override_title=None,
    ):
        """
        올인원 발행: 글 생성 → HTML 변환 → 티스토리 발행
        (네이버 post_human_like과 동일한 시그니처)
        """
        from src.orchestrator import generate_preview
        from src.html_converter import markdown_to_html
        from src.engine import replace_link_markers

        total_steps = 5

        # 1. 칼럼 생성
        self._progress(1, total_steps, f"칼럼 생성 중... ({topic})")
        preview = generate_preview(
            topic=topic,
            persona_id=persona_id,
            persona_name=persona_name,
            model_id=model_id,
            temperature=temperature,
            include_images=include_images,
            image_count=image_count,
            auto_title=True,
            title_count=title_count,
            platform="tistory",  # 유사도 회피용 플랫폼 구분
        )

        if not preview.get("success"):
            return {"success": False, "url": "", "error": "칼럼 생성 실패",
                    "title": topic, "content": ""}

        title = override_title or preview.get("title", topic)
        raw_content = preview.get("raw_content", "")

        # 2. 이미지 URL 수집
        image_urls = []
        image_data = preview.get("image_data")
        if image_data and image_data.get("images"):
            image_urls = [img.get("path", img.get("url", ""))
                         for img in image_data["images"] if img]

        # 3. HTML 변환
        self._progress(2, total_steps, "HTML 변환 중...")
        html_content = markdown_to_html(
            raw_content,
            image_urls=image_urls,
            persona_id=persona_id,
        )

        # 4. 로그인 + 발행
        self._progress(3, total_steps, "티스토리 로그인 중...")
        login_ok = self.login()
        if not login_ok:
            return {"success": False, "url": "", "error": "로그인 실패",
                    "title": title, "content": raw_content}

        # 5. 글 발행
        self._progress(4, total_steps, "티스토리 발행 중...")
        tags = [topic] + topic.split() if topic else []
        result = self.post_human_like(
            title=title,
            html_content=html_content,
            keyword=topic,
            tags=tags[:10],
        )

        result["title"] = title
        result["content"] = raw_content
        self._progress(5, total_steps, "완료!")
        return result


def post_to_tistory(title, html_content, keyword="", tags=None,
                     blog_key="tistory_yun", progress_callback=None):
    """
    티스토리 원스텝 발행 함수

    Args:
        title: 글 제목
        html_content: HTML 본문
        keyword: 키워드 (카테고리 매칭용)
        tags: 태그 리스트
        blog_key: blogs.json의 블로그 키
        progress_callback: 진행 콜백

    Returns:
        dict: {"success": bool, "url": str, "error": str}
    """
    poster = TistoryPoster(progress_callback=progress_callback, blog_key=blog_key)
    try:
        poster.connect()
        login_ok = poster.login()
        if not login_ok:
            return {"success": False, "url": "", "error": "로그인 실패"}

        result = poster.post_human_like(
            title=title,
            html_content=html_content,
            keyword=keyword,
            tags=tags,
        )
        return result
    except Exception as e:
        return {"success": False, "url": "", "error": str(e)}
    finally:
        poster.close()
