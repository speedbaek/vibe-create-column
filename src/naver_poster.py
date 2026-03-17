"""
네이버 블로그 자동 발행 모듈
- Playwright CDP 연결 (실행 중인 Chrome에 연결)
- SmartEditor ONE 내부 API 활용
- 핵심 패턴: setDocumentTitle() → focusFirstText() → _editingService.write()
"""

import os
import re
import asyncio
import subprocess
import time
import random

EDITOR_KEY = "blogpc001"
CDP_URL = "http://127.0.0.1:9222"
EDITOR_URL = "https://blog.naver.com/{blog_id}/postwrite"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


class NaverPoster:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None

    async def _ensure_chrome_running(self):
        """Chrome이 remote debugging 모드로 실행 중인지 확인"""
        try:
            from playwright.async_api import async_playwright
            pw = await async_playwright().start()
            browser = await pw.chromium.connect_over_cdp(CDP_URL)
            await browser.close()
            await pw.stop()
            return True
        except Exception:
            return False

    async def _launch_chrome_debug(self):
        """Chrome을 remote debugging 모드로 실행"""
        cmd = [
            CHROME_PATH,
            f"--remote-debugging-port=9222",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)

    async def connect(self):
        """CDP로 Chrome 연결"""
        from playwright.async_api import async_playwright

        if not await self._ensure_chrome_running():
            await self._launch_chrome_debug()
            await asyncio.sleep(3)

        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.connect_over_cdp(CDP_URL)
        self.context = self.browser.contexts[0]

    async def login(self, naver_id=None, naver_pw=None):
        """네이버 자동 로그인 (세션 유효하면 스킵)"""
        self._naver_id = naver_id or os.environ.get("NAVER_ID", "")
        self._naver_pw = naver_pw or os.environ.get("NAVER_PW", "")
        if not self._naver_id:
            raise ValueError("NAVER_ID가 설정되지 않았습니다.")

        # 기존 탭에서 페이지 획득
        pages = self.context.pages
        if pages:
            self.page = pages[0]
        else:
            self.page = await self.context.new_page()

        return True

    async def _do_login(self):
        """네이버 로그인 페이지에서 자동 로그인 수행"""
        if not self._naver_pw:
            raise RuntimeError(
                "NAVER_PW가 설정되지 않았습니다. .env 파일에 NAVER_PW를 추가해주세요."
            )

        await self.page.goto("https://nid.naver.com/nidlogin.login")
        await self.page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # 이미 로그인된 경우 (메인으로 리디렉트)
        if "nidlogin" not in self.page.url and "login" not in self.page.url:
            return True

        # evaluate로 ID/PW 설정 (Playwright type/fill은 contentEditable 이슈)
        login_result = await self.page.evaluate(
            """(credentials) => {
                const idEl = document.querySelector('#id');
                const pwEl = document.querySelector('#pw');
                if (!idEl || !pwEl) return {ok: false, error: 'login fields not found'};

                idEl.value = credentials.id;
                pwEl.value = credentials.pw;

                ['input', 'change'].forEach(evt => {
                    idEl.dispatchEvent(new Event(evt, {bubbles: true}));
                    pwEl.dispatchEvent(new Event(evt, {bubbles: true}));
                });

                return {ok: true};
            }""",
            {"id": self._naver_id, "pw": self._naver_pw}
        )

        if not login_result.get("ok"):
            raise RuntimeError(f"로그인 필드 설정 실패: {login_result}")

        # 로그인 버튼 클릭
        await asyncio.sleep(1)
        try:
            login_btn = self.page.locator("#log\\.login").first
            if await login_btn.is_visible(timeout=2000):
                await login_btn.click()
            else:
                login_btn = self.page.locator('button.btn_login, button[type="submit"]').first
                await login_btn.click()
        except Exception:
            await self.page.evaluate('document.querySelector("form").submit()')

        await asyncio.sleep(5)

        # 기기 등록 페이지 처리
        if "deviceConfirm" in self.page.url:
            try:
                register_btn = self.page.locator('button:has-text("등록")').first
                if await register_btn.is_visible(timeout=3000):
                    await register_btn.click()
                    await asyncio.sleep(3)
            except Exception:
                pass

        # 최종 확인
        if "nidlogin" in self.page.url or "login" in self.page.url:
            raise RuntimeError("자동 로그인 실패 - 캡차 또는 2차 인증이 필요할 수 있습니다.")

        return True

    async def _navigate_to_editor(self, blog_id):
        """에디터 페이지로 이동 (로그인 안 되면 자동 로그인 시도)"""
        url = EDITOR_URL.format(blog_id=blog_id)
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # 로그인 리디렉트 감지 → 자동 로그인 시도
        if "nidlogin" in self.page.url or "login" in self.page.url:
            await self._do_login()
            # 로그인 후 에디터로 재이동
            await self.page.goto(url)
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

        # 그래도 로그인 안 되면 에러
        if "nidlogin" in self.page.url or "login" in self.page.url:
            raise RuntimeError("로그인 실패 - 에디터 진입 불가")

        # 에디터 로드 대기
        await self.page.wait_for_function(
            f"() => typeof SmartEditor !== 'undefined' && SmartEditor._editors && SmartEditor._editors.{EDITOR_KEY}",
            timeout=15000,
        )
        await asyncio.sleep(1)

        # 오버레이 제거 (도움말 포함)
        await self.page.evaluate("""() => {
            document.querySelectorAll('[class*="overlay"], [class*="dim"], [class*="help"], [class*="container__"]').forEach(el => {
                if (el.querySelector('.se-help-title') || el.classList.toString().includes('overlay') || el.classList.toString().includes('dim')) {
                    el.remove();
                }
            });
            const closeBtn = document.querySelector('.se-help-close, button[class*="close"]');
            if (closeBtn) closeBtn.click();
        }""")
        await asyncio.sleep(1)

    async def _set_title(self, title):
        """제목 설정 (SmartEditor API)"""
        result = await self.page.evaluate(f"""(title) => {{
            var ed = SmartEditor._editors['{EDITOR_KEY}'];
            ed.setDocumentTitle(title);
            return {{
                ok: true,
                title: ed.getDocumentTitle(),
            }};
        }}""", title)
        return result

    async def _set_content(self, content, use_html=True):
        """
        본문 설정 (HTML 모드 → Plain Text 폴백)

        Args:
            content: 본문 내용 (HTML 또는 plain text)
            use_html: True면 HTML 삽입 시도 후 실패 시 plain text 폴백
        """
        if use_html:
            result = await self._set_content_html(content)
            if result and result.get("ok"):
                return result
            # HTML 실패 → plain text 폴백 (HTML 태그 제거)
            import re
            plain = re.sub(r'<[^>]+>', '', content)
            plain = plain.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
            return await self._set_content_plain(plain)

        return await self._set_content_plain(content)

    async def _set_content_plain(self, text_content):
        """Plain text 본문 설정 (기존 방식)"""
        result = await self.page.evaluate(f"""(body) => {{
            var ed = SmartEditor._editors['{EDITOR_KEY}'];
            ed.focusFirstText();
            ed._editingService.write(body);
            return {{
                ok: true,
                method: 'plain_text',
                contentText: ed.getContentText().substring(0, 200),
                isEmpty: ed.isEmptyDocumentContent(),
            }};
        }}""", text_content)
        return result

    async def _set_content_html(self, html_content):
        """
        HTML 본문 설정 시도 (3가지 방법 순차 시도)
        1. SmartEditor setContent/setDocumentContent API
        2. editing area의 execCommand('insertHTML')
        3. contenteditable 영역 직접 조작
        """
        result = await self.page.evaluate(f"""(html) => {{
            var ed = SmartEditor._editors['{EDITOR_KEY}'];

            // Method 1: SmartEditor 내장 API 시도
            try {{
                if (typeof ed.setDocumentContent === 'function') {{
                    ed.setDocumentContent(html);
                    var ct = ed.getContentText();
                    if (ct && ct.length > 10 && !ct.includes('<p>') && !ct.includes('<b>')) {{
                        return {{
                            ok: true,
                            method: 'setDocumentContent',
                            contentText: ct.substring(0, 200),
                            isEmpty: ed.isEmptyDocumentContent(),
                        }};
                    }}
                }}
            }} catch(e) {{}}

            // Method 2: editing area iframe의 execCommand
            try {{
                ed.focusFirstText();
                var iframe = document.querySelector('.se-editing-area iframe');
                var editDoc = null;
                if (iframe && iframe.contentDocument) {{
                    editDoc = iframe.contentDocument;
                }}
                if (!editDoc) {{
                    // contenteditable 영역 찾기
                    var editables = document.querySelectorAll('[contenteditable="true"]');
                    for (var el of editables) {{
                        if (el.closest('.se-editing-area') || el.classList.toString().includes('editing')) {{
                            editDoc = el.ownerDocument;
                            break;
                        }}
                    }}
                }}
                if (editDoc) {{
                    editDoc.execCommand('selectAll', false, null);
                    editDoc.execCommand('insertHTML', false, html);
                    var ct2 = ed.getContentText();
                    if (ct2 && ct2.length > 10 && !ct2.includes('<p>') && !ct2.includes('<b>')) {{
                        return {{
                            ok: true,
                            method: 'execCommand',
                            contentText: ct2.substring(0, 200),
                            isEmpty: ed.isEmptyDocumentContent(),
                        }};
                    }}
                }}
            }} catch(e) {{}}

            // Method 3: write()에 HTML 전달 (일부 에디터에서 HTML로 처리됨)
            try {{
                ed.focusFirstText();
                ed._editingService.write(html);
                var ct3 = ed.getContentText().substring(0, 200);
                if (ct3.includes('<p>') || ct3.includes('<b>') || ct3.includes('&lt;')) {{
                    // HTML 태그가 텍스트로 보임 → 실패
                    return {{ ok: false, method: 'write_failed', reason: 'HTML rendered as text' }};
                }}
                return {{
                    ok: true,
                    method: 'write_html',
                    contentText: ct3,
                    isEmpty: ed.isEmptyDocumentContent(),
                }};
            }} catch(e) {{}}

            return {{ ok: false, method: 'all_failed' }};
        }}""", html_content)
        return result

    async def _insert_images(self, image_paths):
        """
        SmartEditor에 이미지 파일 삽입

        SmartEditor의 이미지 업로드 input을 활용하여 이미지 삽입.
        Args:
            image_paths: 로컬 이미지 파일 경로 리스트
        """
        if not image_paths:
            return

        for img_path in image_paths:
            if not os.path.exists(img_path):
                continue
            try:
                # SmartEditor의 이미지 추가 버튼 클릭
                img_btn = self.page.locator("button.se-image-toolbar-button, button[data-name='image']").first
                if await img_btn.is_visible(timeout=3000):
                    await img_btn.click()
                    await asyncio.sleep(1)

                    # 파일 input에 이미지 설정
                    file_input = self.page.locator("input[type='file'][accept*='image']").first
                    if await file_input.count() > 0:
                        await file_input.set_input_files(img_path)
                        await asyncio.sleep(3)
            except Exception:
                pass

    async def discover_editor_api(self):
        """SmartEditor API 디스커버리 (디버깅용)"""
        result = await self.page.evaluate(f"""() => {{
            var ed = SmartEditor._editors['{EDITOR_KEY}'];
            var es = ed._editingService;

            var edMethods = Object.getOwnPropertyNames(Object.getPrototypeOf(ed))
                .filter(m => typeof ed[m] === 'function')
                .filter(m => /content|html|insert|write|set|component/i.test(m));

            var esMethods = Object.getOwnPropertyNames(Object.getPrototypeOf(es))
                .filter(m => typeof es[m] === 'function')
                .filter(m => /content|html|insert|write|set|component/i.test(m));

            // editing area 정보
            var iframe = document.querySelector('.se-editing-area iframe');
            var contentEditable = document.querySelector('[contenteditable="true"]');

            return {{
                editor_methods: edMethods,
                editing_service_methods: esMethods,
                has_iframe: !!iframe,
                has_contenteditable: !!contentEditable,
                contenteditable_tag: contentEditable ? contentEditable.tagName : null,
            }};
        }}""")
        return result

    async def _validate(self):
        """발행 전 유효성 검증"""
        result = await self.page.evaluate(f"""() => {{
            var ed = SmartEditor._editors['{EDITOR_KEY}'];
            var v = ed.validate();
            return {{
                valid: v.valid,
                reason: v.reason || '',
                title: ed.getDocumentTitle(),
                isEmpty: ed.isEmptyDocumentContent(),
            }};
        }}""")
        return result

    async def _set_category(self, category_no):
        """카테고리 설정"""
        if not category_no:
            return
        try:
            await self.page.evaluate(f"""(catNo) => {{
                var select = document.querySelector('select[name="categoryNo"]');
                if (select) {{
                    select.value = catNo;
                    select.dispatchEvent(new Event('change'));
                }}
            }}""", str(category_no))
        except Exception:
            pass

    async def _publish(self):
        """발행 버튼 클릭"""
        # 발행 전 오버레이 재제거
        await self.page.evaluate("""() => {
            document.querySelectorAll('[class*="help"], [class*="overlay"], [class*="dim"], [class*="container__"]').forEach(el => {
                const text = el.textContent || '';
                if (text.includes('도움말') || el.classList.toString().includes('overlay') || el.classList.toString().includes('dim')) {
                    el.remove();
                }
            });
        }""")
        await asyncio.sleep(1)

        # 발행 버튼 클릭
        publish_btn = self.page.locator("button[class*='publish_btn']").first
        if not await publish_btn.is_visible(timeout=3000):
            publish_btn = self.page.locator("button:has-text('발행')").first

        await publish_btn.click(force=True)
        await asyncio.sleep(3)

        # 확인 버튼 클릭
        confirm_btn = self.page.locator("button.se-popup-button-confirm, button[class*='confirm']").first
        if not await confirm_btn.is_visible(timeout=3000):
            confirm_btn = self.page.locator("button:has-text('확인')").first

        if await confirm_btn.is_visible(timeout=3000):
            await confirm_btn.click()
        await asyncio.sleep(5)

        # 발행 성공 확인 (URL 변경)
        final_url = self.page.url
        if "PostView" in final_url or "logNo" in final_url:
            return {"success": True, "url": final_url}

        # 추가 대기
        await asyncio.sleep(5)
        final_url = self.page.url
        if "PostView" in final_url or "logNo" in final_url:
            return {"success": True, "url": final_url}

        return {"success": False, "url": final_url, "error": "발행 후 URL 미변경"}

    async def post(self, title, content, blog_id=None, category_no=None,
                   use_html=True, image_urls=None):
        """
        블로그 글 발행 전체 흐름

        Args:
            title: 글 제목
            content: 본문 (HTML 또는 plain text)
            blog_id: 블로그 ID (없으면 NAVER_ID 사용)
            category_no: 카테고리 번호
            use_html: HTML 모드 사용 여부
            image_urls: 이미지 URL 리스트 (HTML에 이미 포함된 경우 None)

        Returns:
            dict: {'success': bool, 'url': str, ...}
        """
        blog_id = blog_id or os.environ.get("NAVER_ID", "")

        if not self.browser:
            await self.connect()

        await self.login()
        await self._navigate_to_editor(blog_id)

        # 제목 설정
        title_result = await self._set_title(title)
        if not title_result.get("ok"):
            return {"success": False, "error": "제목 설정 실패"}

        # 본문 설정
        content_result = await self._set_content(content, use_html=use_html)
        if content_result.get("isEmpty"):
            return {"success": False, "error": "본문 설정 실패 (isEmpty=true)"}

        # 카테고리 설정
        if category_no:
            await self._set_category(category_no)

        # 유효성 검증
        validation = await self._validate()
        if not validation.get("valid"):
            return {
                "success": False,
                "error": f"검증 실패: {validation.get('reason')}",
                "validation": validation,
            }

        # 발행
        result = await self._publish()
        return result

    # ── Human-like 발행 메서드 (수정 8) ──────────────────

    async def _set_title_human(self, title):
        """제목을 사람처럼 타이핑 (IME fallback 포함)"""
        title_area = self.page.locator('.se-documentTitle-editView .se-text-paragraph')
        try:
            await title_area.click()
        except Exception:
            # fallback: JS로 포커스
            await self.page.evaluate(f"""() => {{
                SmartEditor._editors['{EDITOR_KEY}'].focusTitle();
            }}""")
        await asyncio.sleep(random.uniform(0.3, 0.8))

        try:
            # 방법 1: 직접 타이핑 시도
            await self.page.keyboard.type(title, delay=random.randint(80, 150))
        except Exception:
            # 방법 2: insertText fallback
            try:
                await self.page.keyboard.insert_text(title)
            except Exception:
                pass

        await asyncio.sleep(random.uniform(1.0, 2.0))

        # 입력 검증
        actual = await self.page.evaluate(f"""() => {{
            var ed = SmartEditor._editors['{EDITOR_KEY}'];
            return ed.getDocumentTitle();
        }}""")

        # 제목이 비어있으면 JS API fallback
        if not actual or actual.strip() == '':
            await self.page.evaluate(f"""(t) => {{
                SmartEditor._editors['{EDITOR_KEY}'].setDocumentTitle(t);
            }}""", title)

        return {"ok": True, "title": actual or title}

    async def _set_content_human(self, html_content):
        """본문을 문단 단위로 나누어 시간차 삽입"""
        # HTML을 블록 단위로 분리
        chunks = re.split(r'(?<=</(?:p|div|h[1-6])>)', html_content)
        chunks = [c.strip() for c in chunks if c.strip()]

        # 첫 번째 텍스트에 포커스
        await self.page.evaluate(f"""() => {{
            SmartEditor._editors['{EDITOR_KEY}'].focusFirstText();
        }}""")
        await asyncio.sleep(random.uniform(0.5, 1.0))

        # chunk별 순차 삽입
        for i, chunk in enumerate(chunks):
            await self.page.evaluate(f"""(c) => {{
                SmartEditor._editors['{EDITOR_KEY}']._editingService.write(c);
            }}""", chunk)

            # 기본 딜레이: 1.5~3초
            delay = random.uniform(1.5, 3.0)

            # 30% 확률로 "생각하는 시간" 추가
            if random.random() < 0.3:
                delay = random.uniform(4.0, 6.0)

            # 마지막 chunk는 짧게
            if i == len(chunks) - 1:
                delay = random.uniform(0.5, 1.0)

            await asyncio.sleep(delay)

        return {"ok": True, "chunks": len(chunks)}

    async def _simulate_review(self):
        """사람이 글을 훑어보는 동작 시뮬레이션"""
        # 아래로 천천히 스크롤
        for _ in range(random.randint(3, 5)):
            await self.page.mouse.wheel(0, random.randint(200, 400))
            await asyncio.sleep(random.uniform(0.8, 1.5))

        await asyncio.sleep(random.uniform(1.0, 2.0))

        # 맨 위로 스크롤
        await self.page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        await asyncio.sleep(random.uniform(2.0, 3.0))

        # 다시 맨 아래로
        await self.page.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")
        await asyncio.sleep(random.uniform(1.0, 2.0))

    async def post_human_like(self, title, content, blog_id=None, category_no=None,
                               use_html=True):
        """
        사람처럼 자연스럽게 블로그 글 발행

        기존 post()와 동일한 인터페이스, 동일한 반환값.
        차이점: 각 단계 사이에 사람 행동 패턴의 딜레이 삽입.
        총 소요시간: 약 2~4분 (본문 길이에 따라 변동)
        """
        blog_id = blog_id or os.environ.get("NAVER_ID", "")

        if not self.browser:
            await self.connect()

        await self.login()

        # 1. 에디터 진입
        await self._navigate_to_editor(blog_id)
        await asyncio.sleep(random.uniform(2.0, 3.0))  # 화면 보는 시간

        # 2. 제목 타이핑
        title_result = await self._set_title_human(title)
        if not title_result.get("ok"):
            return {"success": False, "error": "제목 설정 실패"}

        # 3. 본문 chunk 단위 삽입
        await self._set_content_human(content)

        # 4. 글 훑어보기
        await self._simulate_review()

        # 5. 카테고리 선택
        if category_no:
            await asyncio.sleep(random.uniform(0.5, 1.0))
            await self._set_category(category_no)
            await asyncio.sleep(random.uniform(0.8, 1.5))

        # 6. 유효성 검증
        validation = await self._validate()
        if not validation.get("valid"):
            return {
                "success": False,
                "error": f"검증 실패: {validation.get('reason')}",
                "validation": validation,
            }

        # 7. 최종 검토
        await asyncio.sleep(random.uniform(2.0, 4.0))

        # 8. 발행
        result = await self._publish()
        return result

    async def post_with_se_data(self, title, content, blog_id=None,
                               category_no=None, local_image_paths=None,
                               image_data=None, progress_callback=None):
        """
        setDocumentData 방식으로 블로그 글 발행 (auto_post.py 검증 완료 패턴)

        Args:
            title: 글 제목
            content: 본문 (마크다운/plain text)
            blog_id: 블로그 ID (없으면 NAVER_ID 사용)
            category_no: 카테고리 번호
            local_image_paths: 로컬 이미지 파일 경로 리스트
            image_data: orchestrator에서 받은 이미지 데이터 (DALL-E URL 포함)
            progress_callback: 진행상황 콜백 함수 (msg: str) -> None

        Returns:
            dict: {'success': bool, 'url': str, ...}
        """
        blog_id = blog_id or os.environ.get("NAVER_ID", "")

        def _log(msg):
            if progress_callback:
                progress_callback(msg)

        if not self.browser:
            await self.connect()

        await self.login()

        # Step 1: 에디터 이동
        _log("에디터 페이지 이동 중...")
        await self._navigate_to_editor(blog_id)

        # Step 2: DALL-E 이미지 로컬 다운로드 (아직 안 된 경우)
        actual_local_paths = local_image_paths or []
        if not actual_local_paths and image_data:
            _log("DALL-E 이미지 다운로드 중...")
            from src.image_handler import download_dalle_images
            images_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "outputs", "images"
            )
            actual_local_paths = [
                p for p in download_dalle_images(image_data, output_dir=images_dir) if p
            ]
            _log(f"이미지 다운로드 완료: {len(actual_local_paths)}장")

        # Step 3: 이미지 네이버 CDN 업로드
        native_image_components = []
        if actual_local_paths:
            _log(f"이미지 {len(actual_local_paths)}장 CDN 업로드 중...")
            from src.naver_uploader import upload_images_to_naver
            upload_results = await upload_images_to_naver(
                self.page, blog_id, actual_local_paths
            )
            native_image_components = [r for r in upload_results if r and r.get('src')]
            _log(f"CDN 업로드 완료: {len(native_image_components)}/{len(actual_local_paths)}장")

            if actual_local_paths and not native_image_components:
                return {"success": False, "error": "이미지 CDN 업로드 전부 실패"}

        # Step 4: SE Document Data 빌드
        _log("SE Document Data 빌드 중...")
        from src.se_converter import build_document_data
        se_doc_data = build_document_data(
            title=title,
            text=content,
            image_urls=native_image_components if native_image_components else None,
        )

        # Step 5: setDocumentData로 제목+본문 설정
        _log("setDocumentData 설정 중...")
        content_result = await self.page.evaluate(
            """(docData) => {
                var ed = SmartEditor._editors.blogpc001;
                var ds = ed._documentService;
                try {
                    ds.setDocumentData(docData);
                    var ct = ds.getContentText();
                    return {
                        ok: ct.length > 10,
                        method: 'setDocumentData',
                        contentLen: ct.length,
                        isEmpty: ed.isEmptyDocumentContent(),
                    };
                } catch(e) {
                    return {ok: false, error: e.message};
                }
            }""",
            se_doc_data
        )

        # setDocumentData 실패 시 plain text 폴백
        if not content_result.get('ok'):
            _log("setDocumentData 실패 → plain text 폴백...")
            await self._set_title(title)
            content_result = await self._set_content_plain(content)

        if content_result.get('isEmpty'):
            return {"success": False, "error": "본문 설정 실패 (isEmpty=true)"}

        # Step 6: 카테고리 설정
        if category_no:
            await self._set_category(category_no)

        # Step 7: 유효성 검증
        _log("유효성 검증 중...")
        validation = await self._validate()
        if not validation.get("valid"):
            return {
                "success": False,
                "error": f"검증 실패: {validation.get('reason')}",
                "validation": validation,
            }

        # Step 8: 발행
        _log("발행 중...")
        result = await self._publish()
        if result.get("success"):
            _log(f"발행 성공! {result.get('url', '')}")
        return result

    async def close(self):
        """연결 종료"""
        if self.browser:
            await self.browser.close()
        if hasattr(self, "_pw") and self._pw:
            await self._pw.stop()


async def quick_post(title, content, blog_id=None, category_no=None, human_like=True):
    """
    간편 발행 함수

    Usage:
        import asyncio
        from src.naver_poster import quick_post
        result = asyncio.run(quick_post("제목", "본문"))
    """
    poster = NaverPoster()
    try:
        if human_like:
            result = await poster.post_human_like(title, content, blog_id, category_no)
        else:
            result = await poster.post(title, content, blog_id, category_no)
        return result
    finally:
        await poster.close()


async def generate_and_post(topic, persona_id="yun_ung_chae",
                            persona_name="윤웅채",
                            model_id="claude-sonnet-4-6",
                            blog_id=None, category_no=None,
                            human_like=True):
    """
    키워드 → 칼럼 생성 → HTML 포맷팅 → 네이버 발행 통합 함수

    Usage:
        import asyncio
        from src.naver_poster import generate_and_post
        result = asyncio.run(generate_and_post("상표등록 필수인 이유"))
    """
    from src.engine import generate_column_with_validation, replace_link_markers, normalize_content_spacing
    from src.formatter import format_for_smarteditor

    # 1. 칼럼 생성
    gen_result = generate_column_with_validation(
        persona_id=persona_id,
        persona_name=persona_name,
        topic=topic,
        model_id=model_id,
    )

    content = gen_result["content"]

    # 2. 후처리: 간격 정규화 + 링크 마커 치환
    content = normalize_content_spacing(content)
    content = replace_link_markers(content, persona_id)

    # 3. HTML 포맷팅
    html_content = format_for_smarteditor(content)

    # 제목 추출
    title = topic
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped.lstrip("#").strip()
            break

    # 4. 발행
    poster = NaverPoster()
    try:
        if human_like:
            post_result = await poster.post_human_like(title, html_content, blog_id, category_no)
        else:
            post_result = await poster.post(title, html_content, blog_id, category_no, use_html=True)
        post_result["generation"] = {
            "attempts": gen_result["attempts"],
            "similarity": gen_result["similarity_check"],
            "char_count": len(content),
        }
        return post_result
    finally:
        await poster.close()
