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

EDITOR_KEY = "blogpc001"
EDITOR_URL = "https://blog.naver.com/{blog_id}/postwrite"
# Playwright 전용 사용자 데이터 (로그인 세션 유지용)
PW_USER_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pw_browser_data")


def _log(msg):
    print(f"[NaverPoster] {msg}")


class NaverPoster:
    def __init__(self, progress_callback=None):
        self.context = None
        self.page = None
        self._pw = None
        self._progress_cb = progress_callback

    def _progress(self, step, total, msg):
        _log(msg)
        if self._progress_cb:
            self._progress_cb(step, total, msg)

    def connect(self):
        """Playwright 내장 Chromium으로 브라우저 실행 (sync API)"""
        from playwright.sync_api import sync_playwright

        os.makedirs(PW_USER_DATA, exist_ok=True)

        self._pw = sync_playwright().start()

        # channel='chrome' → 시스템 Chrome 사용 (Playwright 내장 Chromium은 spawn 실패)
        # persistent context → 로그인 쿠키/세션 pw_browser_data에 유지
        self.context = self._pw.chromium.launch_persistent_context(
            user_data_dir=PW_USER_DATA,
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
        naver_id = naver_id or os.environ.get("NAVER_ID", "")
        naver_pw = naver_pw or os.environ.get("NAVER_PW", "")

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
        blog_id = blog_id or os.environ.get("NAVER_ID", "")
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
    """
    poster = NaverPoster(progress_callback=kwargs.pop("progress_callback", None))
    try:
        return poster.one_click_post(topic=topic, **kwargs)
    finally:
        poster.close()
