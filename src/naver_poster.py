"""
네이버 블로그 자동 발행 모듈 (v4 - Playwright Sync API)
- Playwright sync API 사용 (asyncio 완전 제거 → Windows/Streamlit 호환)
- Playwright 내장 Chromium (시스템 Chrome과 독립)
- 자동 로그인 (evaluate 방식)
- 이미지 CDN 업로드 (SmartEditor file input)
- setDocumentData()로 포맷팅된 JSON 삽입
- 원클릭 발행 파이프라인
"""

import os
import time
import random

EDITOR_KEY = "blogpc001"
EDITOR_URL = "https://blog.naver.com/{blog_id}/postwrite"
# Playwright 전용 사용자 데이터 (로그인 세션 유지용)
PW_USER_DATA_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pw_browser_data")


def _get_blog_config(blog_key=None):
    """blogs.json에서 블로그 설정 로드"""
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "blogs.json")
    if os.path.exists(config_path):
        import json
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        blogs = data.get("blogs", {})
        if blog_key and blog_key in blogs:
            return blogs[blog_key]
    return None


def _get_pw_user_data(blog_key=None):
    """블로그별 별도 브라우저 프로필 경로 (계정 세션 분리)"""
    if blog_key and blog_key != "yun_ung_chae":
        path = f"{PW_USER_DATA_BASE}_{blog_key}"
    else:
        path = PW_USER_DATA_BASE
    os.makedirs(path, exist_ok=True)
    return path


def _log(msg):
    print(f"[NaverPoster] {msg}")


class NaverPoster:
    def __init__(self, progress_callback=None, blog_key=None):
        self.context = None
        self.page = None
        self._pw = None
        self._progress_cb = progress_callback
        self._blog_key = blog_key
        self._blog_config = _get_blog_config(blog_key)

    def _progress(self, step, total, msg):
        _log(msg)
        if self._progress_cb:
            self._progress_cb(step, total, msg)

    def connect(self):
        """Playwright 내장 Chromium으로 브라우저 실행 (sync API)"""
        from playwright.sync_api import sync_playwright

        user_data = _get_pw_user_data(self._blog_key)

        self._pw = sync_playwright().start()

        # channel='chrome' → 시스템 Chrome 사용 (Playwright 내장 Chromium은 spawn 실패)
        # persistent context → 로그인 쿠키/세션 유지 (블로그별 분리)
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
        pages = self.context.pages
        self.page = pages[0] if pages else self.context.new_page()
        _log("Chrome 실행 완료 (Playwright 제어, 별도 프로필)")

    def login(self, naver_id=None, naver_pw=None):
        """자동 로그인 (evaluate로 값 설정 + 폼 제출)"""
        # 블로그 설정에서 계정 환경변수 키 조회
        if self._blog_config:
            id_key = self._blog_config.get("env_id_key", "NAVER_ID")
            pw_key = self._blog_config.get("env_pw_key", "NAVER_PW")
        else:
            id_key = "NAVER_ID"
            pw_key = "NAVER_PW"
        naver_id = naver_id or os.environ.get(id_key, "")
        naver_pw = naver_pw or os.environ.get(pw_key, "")

        if not naver_id or not naver_pw:
            raise ValueError("NAVER_ID/NAVER_PW가 설정되지 않았습니다. (.env 확인)")

        # 로그인 페이지로 이동
        self.page.goto("https://nid.naver.com/nidlogin.login")
        self.page.wait_for_load_state("networkidle")
        time.sleep(2)

        # 이미 로그인 상태 체크
        url = self.page.url
        if "naver.com" in url and "nidlogin" not in url and "login" not in url:
            _log("이미 로그인 상태!")
            return True

        _log(f"로그인 페이지 URL: {self.page.url}")

        # 로그인 필드 설정 (evaluate + nativeInputValueSetter 방식)
        login_result = self.page.evaluate(
            """(credentials) => {
                const idEl = document.querySelector('#id');
                const pwEl = document.querySelector('#pw');
                if (!idEl || !pwEl) return {ok: false, error: 'login fields not found'};

                // React/네이버가 감지할 수 있도록 nativeInputValueSetter 사용
                var nativeIdSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                var nativePwSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;

                nativeIdSetter.call(idEl, credentials.id);
                nativePwSetter.call(pwEl, credentials.pw);

                // 다양한 이벤트 발생
                ['input', 'change', 'keyup', 'keydown'].forEach(evt => {
                    idEl.dispatchEvent(new Event(evt, {bubbles: true}));
                    pwEl.dispatchEvent(new Event(evt, {bubbles: true}));
                });

                return {ok: true, id_len: idEl.value.length, pw_len: pwEl.value.length};
            }""",
            {"id": naver_id, "pw": naver_pw},
        )

        _log(f"로그인 필드 설정 결과: {login_result}")

        if not login_result.get("ok"):
            raise RuntimeError(f"로그인 필드 설정 실패: {login_result.get('error')}")

        # 로그인 버튼 클릭
        time.sleep(1)
        try:
            login_btn = self.page.locator("#log\\.login").first
            if login_btn.is_visible(timeout=2000):
                login_btn.click()
            else:
                login_btn = self.page.locator('button.btn_login, button[type="submit"]').first
                login_btn.click()
        except Exception:
            self.page.evaluate('document.querySelector("form").submit()')

        # 로그인 후 대기 (리디렉트 시간)
        time.sleep(8)
        _log(f"로그인 버튼 클릭 후 URL: {self.page.url}")

        # 캡챠/보안문자 감지
        page_text = self.page.evaluate("() => document.body ? document.body.innerText.substring(0, 500) : ''")

        # 기기 등록 페이지 처리
        if "deviceConfirm" in self.page.url or "new_device" in self.page.url:
            _log("기기 등록 페이지 감지 → 등록 안함/나중에 클릭")
            try:
                # "등록 안함" 또는 "나중에" 버튼 우선 시도
                skip_btn = self.page.locator('a:has-text("등록안함"), a:has-text("나중에"), button:has-text("등록안함")').first
                if skip_btn.is_visible(timeout=3000):
                    skip_btn.click()
                    time.sleep(3)
                else:
                    # "등록" 버튼
                    register_btn = self.page.locator('button:has-text("등록")').first
                    if register_btn.is_visible(timeout=3000):
                        register_btn.click()
                        time.sleep(3)
            except Exception as e:
                _log(f"기기 등록 처리 실패: {e}")
            _log(f"기기 등록 후 URL: {self.page.url}")

        # 2차 인증/보안 페이지 처리
        if "protect" in self.page.url or "security" in self.page.url:
            _log(f"보안 인증 페이지 감지: {self.page.url}")
            # 계속/건너뛰기 버튼 시도
            try:
                skip = self.page.locator('a:has-text("나중에"), button:has-text("건너뛰기"), a:has-text("skip")').first
                if skip.is_visible(timeout=3000):
                    skip.click()
                    time.sleep(3)
            except Exception:
                pass

        # 최종 로그인 결과 확인
        final_url = self.page.url
        _log(f"최종 URL: {final_url}")

        if "nidlogin" in final_url:
            # 로그인 실패 원인 분석
            error_msg = self.page.evaluate("""() => {
                var err = document.querySelector('.error_message, #err_common, .state_error');
                return err ? err.innerText : '';
            }""")
            raise RuntimeError(
                f"로그인 실패 - URL: {final_url}\n"
                f"에러 메시지: {error_msg or '없음'}\n"
                f"페이지 내용: {page_text[:200]}"
            )

        # login 관련 URL이지만 nidlogin은 아닌 경우 (인증 중간 페이지 등)
        if "login" in final_url and "naver.com" not in final_url.split("login")[0]:
            _log(f"경고: 로그인 관련 페이지지만 통과 시도 - {final_url}")

        _log("로그인 성공!")
        return True

    def _navigate_to_editor(self, blog_id):
        """에디터 페이지로 이동 + SmartEditor 로드 대기"""
        url = EDITOR_URL.format(blog_id=blog_id)
        self.page.goto(url)
        self.page.wait_for_load_state("networkidle")
        time.sleep(3)

        # 로그인 리디렉트 감지
        if "nidlogin" in self.page.url or "login" in self.page.url:
            raise RuntimeError("에디터 접근 실패 - 로그인 필요")

        # SmartEditor 로드 대기
        self.page.wait_for_function(
            f"() => typeof SmartEditor !== 'undefined' && SmartEditor._editors && SmartEditor._editors.{EDITOR_KEY}",
            timeout=20000,
        )
        time.sleep(3)

        # 팝업 제거
        self._clear_popups()

    def _clear_popups(self):
        """도움말/복구 팝업만 선택적 제거"""
        self.page.evaluate("""() => {
            var helpClose = document.querySelector('.se-help-close');
            if (helpClose) helpClose.click();
            document.querySelectorAll('[class*="se-help"]').forEach(el => el.remove());
            document.querySelectorAll('.se-popup-alert, .se-popup-alert-confirm').forEach(popup => {
                var cancelBtn = popup.querySelector('.se-popup-button-cancel');
                if (cancelBtn) cancelBtn.click();
            });
        }""")
        time.sleep(1)

    def _upload_images(self, blog_id, local_image_paths):
        """이미지 CDN 업로드 → 네이티브 컴포넌트 리스트 반환 (sync)"""
        if not local_image_paths:
            return []

        from src.naver_uploader_sync import upload_images_to_naver

        upload_results = upload_images_to_naver(
            self.page, blog_id, local_image_paths
        )

        native_components = []
        for i, result in enumerate(upload_results):
            if result and result.get("src"):
                native_components.append(result)
                _log(f"  이미지 [{i+1}] CDN OK: {result.get('src', '')[:80]}...")
            else:
                _log(f"  이미지 [{i+1}] 실패")

        _log(f"CDN 업로드 결과: {len(native_components)}/{len(local_image_paths)}장 성공")
        return native_components

    def _set_document_data(self, se_doc_data):
        """setDocumentData로 제목+본문 설정"""
        result = self.page.evaluate(
            """(docData) => {
                var ed = SmartEditor._editors.blogpc001;
                var ds = ed._documentService;
                try {
                    ds.setDocumentData(docData);
                    var ct = ds.getContentText();
                    return {
                        ok: ct.length > 10,
                        contentLen: ct.length,
                        title: ds.getDocumentTitle(),
                        isEmpty: ed.isEmptyDocumentContent(),
                    };
                } catch(e) {
                    return {ok: false, error: e.message};
                }
            }""",
            se_doc_data,
        )
        return result

    def _set_category(self, category_no):
        """카테고리 설정"""
        if not category_no:
            return
        try:
            self.page.evaluate(
                """(catNo) => {
                    var select = document.querySelector('select[name="categoryNo"]');
                    if (select) {
                        select.value = catNo;
                        select.dispatchEvent(new Event('change'));
                    }
                }""",
                str(category_no),
            )
        except Exception:
            pass

    def _validate(self):
        """발행 전 유효성 검증"""
        return self.page.evaluate(f"""() => {{
            var ed = SmartEditor._editors['{EDITOR_KEY}'];
            var v = ed.validate();
            return {{
                valid: v.valid,
                reason: v.reason || '',
                title: ed.getDocumentTitle(),
                isEmpty: ed.isEmptyDocumentContent(),
            }};
        }}""")

    def _publish(self):
        """발행 버튼 클릭 + 확인"""
        # 팝업 재제거
        self._clear_popups()

        # 발행 버튼 클릭
        publish_btn = self.page.locator("button[class*='publish_btn']").first
        if not publish_btn.is_visible(timeout=2000):
            publish_btn = self.page.locator("button:has-text('발행')").first

        publish_btn.click(force=True)
        time.sleep(3)

        # 확인 버튼 클릭
        try:
            confirm_btn = self.page.locator("button.se-popup-button-confirm").first
            if not confirm_btn.is_visible(timeout=2000):
                confirm_btn = self.page.locator("button[class*='confirm']").first
            if not confirm_btn.is_visible(timeout=2000):
                confirm_btn = self.page.locator("button:has-text('확인')").first

            if confirm_btn.is_visible(timeout=3000):
                confirm_btn.click()
                time.sleep(5)
        except Exception:
            pass

        # 발행 결과 확인 (URL 변경 감지)
        # 네이버 블로그 URL 패턴:
        #   - blog.naver.com/ID/숫자 (신형)
        #   - blog.naver.com/PostView.naver?blogId=...&logNo=... (구형)
        #   - postwrite가 아닌 URL이면 발행 성공
        import re
        for _ in range(5):
            time.sleep(3)
            final_url = self.page.url
            _log(f"발행 후 URL 확인: {final_url}")

            if "PostView" in final_url or "logNo" in final_url:
                return {"success": True, "url": final_url}

            # blog.naver.com/아이디/숫자 패턴
            if re.search(r'blog\.naver\.com/\w+/\d+', final_url):
                return {"success": True, "url": final_url}

            # 에디터(postwrite)가 아닌 블로그 URL이면 성공
            if "blog.naver.com" in final_url and "postwrite" not in final_url:
                return {"success": True, "url": final_url}

        return {"success": False, "url": self.page.url, "error": "발행 후 URL 미변경"}

    def one_click_post(
        self,
        topic,
        persona_id="yun_ung_chae",
        persona_name="윤웅채",
        model_id="claude-sonnet-4-6",
        temperature=0.7,
        include_images=True,
        image_count=4,
        title_count=3,
        blog_id=None,
        category_no=None,
        override_title=None,
    ):
        """원클릭 자동 발행: 키워드 → 칼럼 생성 → 이미지 → CDN 업로드 → 발행"""
        blog_id = blog_id or (self._blog_config.get("blog_id") if self._blog_config else "") or os.environ.get("NAVER_ID", "")
        total_steps = 8

        try:
            # Step 1: 브라우저 실행
            self._progress(1, total_steps, "Playwright Chromium 실행 중...")
            self.connect()

            # Step 2: 자동 로그인
            self._progress(2, total_steps, "네이버 자동 로그인 중...")
            self.login()

            # Step 3: 칼럼 생성
            self._progress(3, total_steps, f"'{topic}' 칼럼 생성 중... (리서치 + 작성)")
            from src.orchestrator import generate_preview

            gen_result = generate_preview(
                topic=topic,
                persona_id=persona_id,
                persona_name=persona_name,
                model_id=model_id,
                temperature=temperature,
                include_images=include_images,
                image_count=image_count,
                auto_title=True,
                title_count=title_count,
            )

            if not gen_result.get("success"):
                return {"success": False, "error": "칼럼 생성 실패"}

            title = override_title or gen_result["title"]
            content = gen_result["raw_content"]
            image_data = gen_result.get("image_data")

            self._progress(3, total_steps, f"칼럼 생성 완료! ({gen_result['char_count']}자)")

            # Step 4: 이미지 다운로드
            local_image_paths = []
            _log(f"이미지 설정: include_images={include_images}, image_data={type(image_data).__name__}")
            if image_data:
                _log(f"  image_data keys: {list(image_data.keys()) if isinstance(image_data, dict) else 'not dict'}")
                if isinstance(image_data, dict):
                    body_imgs = image_data.get("body_images", [])
                    _log(f"  body_images 수: {len(body_imgs)}")
                    for i, img in enumerate(body_imgs):
                        _log(f"    [{i}] source={img.get('source','?')}, url={str(img.get('url',''))[:80]}")

            if include_images and image_data:
                self._progress(4, total_steps, "이미지 로컬 다운로드 중...")
                try:
                    from src.image_handler import download_dalle_images
                    images_dir = os.path.join("outputs", "images")
                    local_paths = download_dalle_images(image_data, output_dir=images_dir)
                    local_image_paths = [p for p in local_paths if p and os.path.exists(p)]
                    _log(f"다운로드 결과: {len(local_image_paths)}장 유효 / {len(local_paths)}장 전체")
                    for p in local_image_paths:
                        _log(f"  파일: {p} ({os.path.getsize(p)} bytes)")
                    self._progress(4, total_steps, f"이미지 {len(local_image_paths)}장 다운로드 완료")
                except Exception as e:
                    _log(f"이미지 다운로드 실패 (이미지 없이 계속): {type(e).__name__}: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                self._progress(4, total_steps, f"이미지 없이 진행 (include={include_images}, data={'있음' if image_data else '없음'})")

            # Step 5: 에디터 이동
            self._progress(5, total_steps, "블로그 에디터 이동 중...")
            self._navigate_to_editor(blog_id)

            # Step 6: 이미지 CDN 업로드
            native_image_components = []
            if local_image_paths:
                self._progress(6, total_steps, f"이미지 {len(local_image_paths)}장 CDN 업로드 중...")
                native_image_components = self._upload_images(blog_id, local_image_paths)

                success_imgs = [c for c in native_image_components if c]
                _log(f"CDN 업로드 결과: {len(success_imgs)}/{len(local_image_paths)}장 성공")
                if not success_imgs:
                    _log("⚠️ 이미지 전부 실패 - 이미지 없이 계속 진행")
                    native_image_components = []
            else:
                self._progress(6, total_steps, f"CDN 업로드 건너뜀 (로컬 이미지 {len(local_image_paths)}장)")

            # Step 7: SE Document Data 빌드 + 설정
            self._progress(7, total_steps, "에디터에 콘텐츠 설정 중...")
            from src.se_converter import build_document_data

            se_doc_data = build_document_data(
                title=title,
                text=content,
                image_urls=native_image_components if native_image_components else None,
            )

            set_result = self._set_document_data(se_doc_data)
            if not set_result.get("ok"):
                return {"success": False, "error": f"setDocumentData 실패: {set_result.get('error')}"}

            # 카테고리 설정
            if category_no:
                self._set_category(category_no)

            # 유효성 검증
            validation = self._validate()
            if not validation.get("valid"):
                return {"success": False, "error": f"검증 실패: {validation.get('reason')}"}

            # Step 8: 발행
            self._progress(8, total_steps, "발행 중...")
            publish_result = self._publish()

            if publish_result.get("success"):
                self._progress(8, total_steps, f"발행 완료! {publish_result['url']}")

            publish_result["title"] = title
            publish_result["char_count"] = gen_result["char_count"]
            publish_result["image_count"] = len(native_image_components)
            publish_result["generation"] = {
                "attempts": gen_result.get("attempts", 0),
                "similarity": gen_result.get("similarity", {}),
                "title_candidates": gen_result.get("title_candidates", []),
            }

            return publish_result

        except Exception as e:
            return {"success": False, "error": f"{type(e).__name__}: {e}"}

    # ── 휴먼 시뮬레이션 메서드들 ──────────────────────────

    def _human_delay(self, min_sec=0.5, max_sec=2.0):
        """사람처럼 불규칙한 딜레이"""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)

    def _human_scroll(self, direction="down", amount=None):
        """사람처럼 스크롤 (불규칙한 양)"""
        if amount is None:
            amount = random.randint(100, 400)
        if direction == "up":
            amount = -amount
        self.page.mouse.wheel(0, amount)
        self._human_delay(0.3, 0.8)

    def _human_mouse_move(self):
        """사람처럼 마우스를 무작위 위치로 이동"""
        x = random.randint(100, 1100)
        y = random.randint(100, 700)
        self.page.mouse.move(x, y)
        self._human_delay(0.1, 0.3)

    def _type_like_human(self, text, delay_per_char=None):
        """사람처럼 한 글자씩 타이핑 (불규칙 속도)"""
        for char in text:
            self.page.keyboard.type(char)
            if delay_per_char:
                time.sleep(delay_per_char)
            else:
                # 한글은 좀 느리게, 영문/숫자는 빠르게
                if ord(char) > 127:
                    time.sleep(random.uniform(0.05, 0.15))
                else:
                    time.sleep(random.uniform(0.02, 0.08))

    def _simulate_writing_behavior(self):
        """글 작성 중 사람 행동 시뮬레이션 (스크롤, 마우스 이동, 잠시 멈춤)"""
        actions = [
            lambda: self._human_scroll("down"),
            lambda: self._human_scroll("up", random.randint(50, 150)),
            lambda: self._human_mouse_move(),
            lambda: self._human_delay(1.0, 3.0),  # 잠시 생각하는 듯 멈춤
        ]
        action = random.choice(actions)
        action()

    def _human_like_set_title(self, title):
        """제목을 사람처럼 입력 (타이핑 시뮬레이션)"""
        _log("제목 입력 시작 (타이핑 시뮬레이션)...")

        # 제목 영역 클릭
        title_area = self.page.locator('.se-documentTitle-editView .se-text-paragraph')
        try:
            title_area.click(timeout=5000)
        except Exception:
            self.page.evaluate("""() => {
                var titleEl = document.querySelector('.se-documentTitle-editView .se-text-paragraph');
                if (titleEl) titleEl.click();
            }""")

        self._human_delay(0.5, 1.0)

        # 한 글자씩 타이핑
        self._type_like_human(title)
        self._human_delay(1.0, 2.0)
        _log(f"제목 입력 완료: {title[:30]}...")

    def _human_like_set_content(self, se_doc_data, title):
        """본문을 하이브리드 방식으로 설정
        - 제목: 타이핑 시뮬레이션
        - 본문: setDocumentData() (타이핑으로는 SmartEditor 컴포넌트 생성 불가)
        - 전후로 사람 행동 시뮬레이션 추가
        """
        _log("하이브리드 콘텐츠 입력 시작...")

        # 1. 에디터 영역 클릭 + 스크롤
        self._human_delay(1.0, 2.0)
        self._human_scroll("down", 100)
        self._human_mouse_move()

        # 2. 본문 영역 클릭
        try:
            body_area = self.page.locator('.se-component-content .se-text-paragraph').first
            body_area.click(timeout=3000)
        except Exception:
            pass

        self._human_delay(0.5, 1.5)

        # 3. 사람처럼 잠시 생각하는 듯 멈춤
        _log("  본문 구성 중... (사람 행동 시뮬레이션)")
        self._simulate_writing_behavior()
        self._human_delay(2.0, 4.0)

        # 4. setDocumentData()로 본문 설정 (타이핑 불가능한 컴포넌트들)
        _log("  setDocumentData 실행...")
        result = self._set_document_data(se_doc_data)

        # 5. 설정 후 사람 행동 (스크롤하며 확인하는 듯)
        self._human_delay(1.0, 2.0)
        for _ in range(random.randint(2, 4)):
            self._human_scroll("down", random.randint(200, 500))
            self._human_delay(0.5, 1.5)

        # 6. 맨 위로 올라가서 확인
        self._human_scroll("up", 2000)
        self._human_delay(1.0, 2.0)

        return result

    def post_human_like(
        self,
        topic,
        persona_id="yun_ung_chae",
        persona_name="윤웅채",
        model_id="claude-sonnet-4-6",
        temperature=0.7,
        include_images=True,
        image_count=4,
        title_count=3,
        blog_id=None,
        category_no=None,
        override_title=None,
    ):
        """
        휴먼 시뮬레이션 발행: 사람이 직접 작성하는 것처럼 행동
        - 불규칙한 딜레이, 스크롤, 마우스 이동
        - 제목 타이핑 시뮬레이션
        - 본문은 setDocumentData (SmartEditor 제약)
        - 발행 전 미리보기 확인 행동
        """
        blog_id = blog_id or (self._blog_config.get("blog_id") if self._blog_config else "") or os.environ.get("NAVER_ID", "")
        total_steps = 8

        try:
            # Step 1: 브라우저 실행
            self._progress(1, total_steps, "Playwright Chromium 실행 중...")
            self.connect()
            self._human_delay(1.0, 2.0)

            # Step 2: 자동 로그인
            self._progress(2, total_steps, "네이버 자동 로그인 중...")
            self.login()
            self._human_delay(2.0, 4.0)

            # 로그인 후 메인 페이지 둘러보기
            self._human_mouse_move()
            self._human_scroll("down", 200)
            self._human_delay(1.0, 3.0)

            # Step 3: 칼럼 생성
            self._progress(3, total_steps, f"'{topic}' 칼럼 생성 중...")
            from src.orchestrator import generate_preview

            gen_result = generate_preview(
                topic=topic,
                persona_id=persona_id,
                persona_name=persona_name,
                model_id=model_id,
                temperature=temperature,
                include_images=include_images,
                image_count=image_count,
                auto_title=True,
                title_count=title_count,
            )

            if not gen_result.get("success"):
                return {"success": False, "error": "칼럼 생성 실패"}

            title = override_title or gen_result["title"]
            content = gen_result["raw_content"]
            image_data = gen_result.get("image_data")

            self._progress(3, total_steps, f"칼럼 생성 완료! ({gen_result['char_count']}자)")

            # Step 4: 이미지 다운로드
            local_image_paths = []
            if include_images and image_data:
                self._progress(4, total_steps, "이미지 로컬 다운로드 중...")
                try:
                    from src.image_handler import download_dalle_images
                    images_dir = os.path.join("outputs", "images")
                    local_paths = download_dalle_images(image_data, output_dir=images_dir)
                    local_image_paths = [p for p in local_paths if p and os.path.exists(p)]
                    self._progress(4, total_steps, f"이미지 {len(local_image_paths)}장 다운로드 완료")
                except Exception as e:
                    _log(f"이미지 다운로드 실패: {e}")

            # Step 5: 에디터 이동 (사람처럼)
            self._progress(5, total_steps, "블로그 에디터 이동 중...")
            self._human_delay(1.0, 2.0)
            self._navigate_to_editor(blog_id)
            self._human_delay(2.0, 4.0)

            # 에디터 로드 후 둘러보기
            self._human_scroll("down", 150)
            self._human_delay(0.5, 1.0)
            self._human_scroll("up", 150)

            # Step 6: 이미지 CDN 업로드 (사이사이 휴먼 딜레이)
            native_image_components = []
            if local_image_paths:
                self._progress(6, total_steps, f"이미지 {len(local_image_paths)}장 CDN 업로드 중...")
                native_image_components = self._upload_images(blog_id, local_image_paths)
                # 업로드 사이사이 사람 행동
                self._human_delay(1.0, 3.0)
                self._human_mouse_move()

            # Step 7: 콘텐츠 설정 (하이브리드 방식)
            self._progress(7, total_steps, "에디터에 콘텐츠 작성 중 (휴먼 시뮬레이션)...")
            from src.se_converter import build_document_data

            se_doc_data = build_document_data(
                title=title,
                text=content,
                image_urls=native_image_components if native_image_components else None,
            )

            set_result = self._human_like_set_content(se_doc_data, title)
            if not set_result.get("ok"):
                return {"success": False, "error": f"setDocumentData 실패: {set_result.get('error')}"}

            # 카테고리 설정
            if category_no:
                self._human_delay(0.5, 1.0)
                self._set_category(category_no)

            # 유효성 검증
            validation = self._validate()
            if not validation.get("valid"):
                return {"success": False, "error": f"검증 실패: {validation.get('reason')}"}

            # 발행 전 최종 확인 행동
            _log("발행 전 최종 확인 (스크롤)...")
            self._human_scroll("up", 2000)
            self._human_delay(1.0, 2.0)
            for _ in range(random.randint(1, 3)):
                self._human_scroll("down", random.randint(300, 600))
                self._human_delay(0.5, 1.5)
            self._human_scroll("up", 2000)
            self._human_delay(1.0, 2.0)

            # Step 8: 발행
            self._progress(8, total_steps, "발행 중...")
            self._human_delay(1.0, 2.0)
            publish_result = self._publish()

            if publish_result.get("success"):
                self._progress(8, total_steps, f"발행 완료! {publish_result['url']}")

            publish_result["title"] = title
            publish_result["char_count"] = gen_result["char_count"]
            publish_result["image_count"] = len(native_image_components)
            publish_result["posting_mode"] = "human_like"
            publish_result["generation"] = {
                "attempts": gen_result.get("attempts", 0),
                "similarity": gen_result.get("similarity", {}),
                "title_candidates": gen_result.get("title_candidates", []),
            }

            return publish_result

        except Exception as e:
            return {"success": False, "error": f"{type(e).__name__}: {e}"}

    def close(self):
        """연결 종료"""
        if self.context:
            try:
                self.context.close()
            except Exception:
                pass
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass


def one_click_post(topic, **kwargs):
    """
    간편 원클릭 발행 함수 (sync)

    Usage:
        from src.naver_poster import one_click_post
        result = one_click_post("상표등록 필수인 이유")
        result = one_click_post("상표등록", blog_key="teheran_official")
    """
    blog_key = kwargs.pop("blog_key", None)
    poster = NaverPoster(progress_callback=kwargs.pop("progress_callback", None), blog_key=blog_key)
    try:
        return poster.one_click_post(topic=topic, **kwargs)
    finally:
        poster.close()


def human_like_post(topic, **kwargs):
    """
    휴먼 시뮬레이션 발행 함수 (sync)

    Usage:
        from src.naver_poster import human_like_post
        result = human_like_post("상표등록 필수인 이유")
        result = human_like_post("상표등록", blog_key="teheran_official")
    """
    blog_key = kwargs.pop("blog_key", None)
    poster = NaverPoster(progress_callback=kwargs.pop("progress_callback", None), blog_key=blog_key)
    try:
        return poster.post_human_like(topic=topic, **kwargs)
    finally:
        poster.close()
