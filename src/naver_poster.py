"""
네이버 블로그 자동 발행 모듈
- Playwright CDP 연결 (실행 중인 Chrome에 연결)
- SmartEditor ONE 내부 API 활용
- 핵심 패턴: setDocumentTitle() → focusFirstText() → _editingService.write()
"""

import os
import asyncio
import subprocess
import time

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
        """네이버 로그인 상태 확인 (이미 로그인된 Chrome 사용)"""
        naver_id = naver_id or os.environ.get("NAVER_ID", "")
        if not naver_id:
            raise ValueError("NAVER_ID가 설정되지 않았습니다.")

        # 기존 탭에서 페이지 획득
        pages = self.context.pages
        if pages:
            self.page = pages[0]
        else:
            self.page = await self.context.new_page()

        # 에디터 페이지로 직접 이동하여 로그인 확인
        # (로그인 안 되면 에디터가 로드되지 않음)
        return True

    async def _navigate_to_editor(self, blog_id):
        """에디터 페이지로 이동"""
        url = EDITOR_URL.format(blog_id=blog_id)
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # 로그인 리디렉트 감지
        if "nidlogin" in self.page.url or "login" in self.page.url:
            raise RuntimeError(
                "네이버 로그인이 필요합니다. Chrome에서 먼저 로그인해주세요."
            )

        # 에디터 로드 대기
        await self.page.wait_for_function(
            f"() => typeof SmartEditor !== 'undefined' && SmartEditor._editors && SmartEditor._editors.{EDITOR_KEY}",
            timeout=15000,
        )
        await asyncio.sleep(1)

        # 오버레이 제거
        await self.page.evaluate("""() => {
            document.querySelectorAll('[class*="overlay"], [class*="dim"]').forEach(el => {
                if (el.style.display !== 'none') el.remove();
            });
        }""")

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

    async def _set_content(self, text_content):
        """본문 설정 (SmartEditor API: focusFirstText + write)"""
        result = await self.page.evaluate(f"""(body) => {{
            var ed = SmartEditor._editors['{EDITOR_KEY}'];
            ed.focusFirstText();
            ed._editingService.write(body);
            return {{
                ok: true,
                contentText: ed.getContentText().substring(0, 200),
                isEmpty: ed.isEmptyDocumentContent(),
            }};
        }}""", text_content)
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
        # 발행 버튼 클릭
        publish_btn = self.page.locator("button[class*='publish_btn']").first
        if not await publish_btn.is_visible():
            publish_btn = self.page.locator("button:has-text('발행')").first

        await publish_btn.click()
        await asyncio.sleep(2)

        # 확인 버튼 클릭
        confirm_btn = self.page.locator("button[class*='confirm_btn']").first
        if not await confirm_btn.is_visible():
            confirm_btn = self.page.locator("button:has-text('확인')").first

        await confirm_btn.click()
        await asyncio.sleep(3)

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

    async def post(self, title, content, blog_id=None, category_no=None):
        """
        블로그 글 발행 전체 흐름

        Args:
            title: 글 제목
            content: 본문 텍스트
            blog_id: 블로그 ID (없으면 NAVER_ID 사용)
            category_no: 카테고리 번호

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
        content_result = await self._set_content(content)
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

    async def close(self):
        """연결 종료"""
        if self.browser:
            await self.browser.close()
        if hasattr(self, "_pw") and self._pw:
            await self._pw.stop()


async def quick_post(title, content, blog_id=None, category_no=None):
    """
    간편 발행 함수

    Usage:
        import asyncio
        from src.naver_poster import quick_post
        result = asyncio.run(quick_post("제목", "본문"))
    """
    poster = NaverPoster()
    try:
        result = await poster.post(title, content, blog_id, category_no)
        return result
    finally:
        await poster.close()


async def generate_and_post(topic, persona_id="yun_ung_chae",
                            persona_name="윤웅채",
                            model_id="claude-sonnet-4-6",
                            blog_id=None, category_no=None):
    """
    키워드 → 칼럼 생성 → 네이버 발행 통합 함수

    Usage:
        import asyncio
        from src.naver_poster import generate_and_post
        result = asyncio.run(generate_and_post("상표등록 필수인 이유"))
    """
    from src.engine import generate_column_with_validation

    # 1. 칼럼 생성
    gen_result = generate_column_with_validation(
        persona_id=persona_id,
        persona_name=persona_name,
        topic=topic,
        model_id=model_id,
    )

    content = gen_result["content"]

    # 제목 추출
    title = topic
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped.lstrip("#").strip()
            break

    # 2. 발행
    poster = NaverPoster()
    try:
        post_result = await poster.post(title, content, blog_id, category_no)
        post_result["generation"] = {
            "attempts": gen_result["attempts"],
            "similarity": gen_result["similarity_check"],
            "char_count": len(content),
        }
        return post_result
    finally:
        await poster.close()
