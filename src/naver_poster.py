"""
네이버 블로그 자동 발행 모듈
- Playwright CDP 연결 (실행 중인 Chrome에 연결)
- SmartEditor ONE 내부 API 활용
- 핵심 패턴: setDocumentTitle() -> focusFirstText() -> _editingService.write()
- 재시도 로직, 연결 복구, 에러 핸들링 포함
"""

import os
import sys
import asyncio
import subprocess
import time
import logging

from src.formatter import format_column_html

# UTF-8 출력 보장 (cp949 이모지 에러 방지)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logger = logging.getLogger(__name__)

EDITOR_KEY = "blogpc001"
CDP_URL = "http://127.0.0.1:9222"
EDITOR_URL = "https://blog.naver.com/{blog_id}/postwrite"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

MAX_RETRIES = 2
RETRY_DELAY = 3


class NaverPoster:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self._pw = None
        self._connected = False

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
        if not os.path.exists(CHROME_PATH):
            raise FileNotFoundError(
                f"Chrome을 찾을 수 없습니다: {CHROME_PATH}\n"
                "Chrome을 설치하거나 CHROME_PATH를 수정해주세요."
            )
        cmd = [
            CHROME_PATH,
            "--remote-debugging-port=9222",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await asyncio.sleep(3)

    async def connect(self):
        """CDP로 Chrome 연결 (재시도 포함)"""
        from playwright.async_api import async_playwright

        for attempt in range(MAX_RETRIES + 1):
            try:
                if not await self._ensure_chrome_running():
                    logger.info("Chrome이 실행되지 않음. 자동 시작...")
                    await self._launch_chrome_debug()

                self._pw = await async_playwright().start()
                self.browser = await self._pw.chromium.connect_over_cdp(CDP_URL)
                self.context = self.browser.contexts[0]
                self._connected = True
                logger.info("Chrome CDP 연결 성공")
                return
            except Exception as e:
                logger.warning(f"CDP 연결 시도 {attempt+1}/{MAX_RETRIES+1} 실패: {e}")
                if self._pw:
                    try:
                        await self._pw.stop()
                    except Exception:
                        pass
                    self._pw = None
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    raise ConnectionError(
                        f"Chrome CDP 연결 실패 ({MAX_RETRIES+1}회 시도).\n"
                        "Chrome을 --remote-debugging-port=9222 옵션으로 실행해주세요."
                    )

    async def _reconnect_if_needed(self):
        """연결 끊김 감지 시 재연결"""
        try:
            # 간단한 연결 상태 확인
            if self.page and not self.page.is_closed():
                await self.page.evaluate("1+1")
                return True
        except Exception:
            pass

        logger.info("연결 끊김 감지. 재연결 시도...")
        await self.close()
        await self.connect()
        await self.login()
        return True

    async def login(self, naver_id=None, naver_pw=None):
        """네이버 로그인 상태 확인 (이미 로그인된 Chrome 사용)"""
        naver_id = naver_id or os.environ.get("NAVER_ID", "")
        if not naver_id:
            raise ValueError("NAVER_ID가 설정되지 않았습니다. .env에 추가해주세요.")

        # 기존 탭에서 페이지 획득
        pages = self.context.pages
        if pages:
            self.page = pages[0]
        else:
            self.page = await self.context.new_page()

        return True

    async def _navigate_to_editor(self, blog_id):
        """에디터 페이지로 이동 (재시도 포함)"""
        url = EDITOR_URL.format(blog_id=blog_id)

        for attempt in range(MAX_RETRIES + 1):
            try:
                await self.page.goto(url, timeout=30000)
                await self.page.wait_for_load_state("networkidle", timeout=20000)
                await asyncio.sleep(2)

                # 로그인 리디렉트 감지
                current_url = self.page.url
                if "nidlogin" in current_url or "/login" in current_url:
                    raise RuntimeError(
                        "네이버 로그인이 필요합니다. Chrome에서 먼저 로그인해주세요."
                    )

                # 에디터 로드 대기
                await self.page.wait_for_function(
                    f"() => typeof SmartEditor !== 'undefined' "
                    f"&& SmartEditor._editors "
                    f"&& SmartEditor._editors.{EDITOR_KEY}",
                    timeout=15000,
                )
                await asyncio.sleep(1)

                # 오버레이/팝업 제거
                await self.page.evaluate("""() => {
                    document.querySelectorAll(
                        '[class*="overlay"], [class*="dim"], [class*="popup"]'
                    ).forEach(el => {
                        if (el.style.display !== 'none') el.remove();
                    });
                }""")

                logger.info(f"에디터 로드 완료: {blog_id}")
                return

            except RuntimeError:
                raise  # 로그인 필요 에러는 재시도하지 않음
            except Exception as e:
                logger.warning(f"에디터 로드 시도 {attempt+1} 실패: {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    raise RuntimeError(f"에디터 로드 실패 ({MAX_RETRIES+1}회 시도): {e}")

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

    async def _set_content(self, text_content, is_html=False):
        """본문 설정 (SmartEditor API: focusFirstText + write)

        Args:
            text_content: 본문 내용 (마크다운 텍스트 또는 HTML)
            is_html: True면 이미 HTML이므로 그대로 전달
        """
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
            await self.page.evaluate("""(catNo) => {
                var select = document.querySelector('select[name="categoryNo"]');
                if (select) {
                    select.value = catNo;
                    select.dispatchEvent(new Event('change'));
                }
            }""", str(category_no))
        except Exception as e:
            logger.warning(f"카테고리 설정 실패 (무시): {e}")

    async def _publish(self):
        """발행 버튼 클릭 + 성공 확인"""
        try:
            # 발행 버튼 클릭
            publish_btn = self.page.locator("button[class*='publish_btn']").first
            if not await publish_btn.is_visible(timeout=3000):
                publish_btn = self.page.locator("button:has-text('발행')").first

            await publish_btn.click()
            await asyncio.sleep(2)

            # 확인 버튼 클릭
            confirm_btn = self.page.locator("button[class*='confirm_btn']").first
            if not await confirm_btn.is_visible(timeout=3000):
                confirm_btn = self.page.locator("button:has-text('확인')").first

            await confirm_btn.click()

        except Exception as e:
            return {"success": False, "error": f"발행 버튼 클릭 실패: {e}"}

        # 발행 성공 대기 (최대 15초)
        for wait_sec in [3, 5, 7]:
            await asyncio.sleep(wait_sec)
            final_url = self.page.url
            if "PostView" in final_url or "logNo" in final_url:
                logger.info(f"발행 성공: {final_url}")
                return {"success": True, "url": final_url}

        final_url = self.page.url
        return {"success": False, "url": final_url, "error": "발행 후 URL 미변경 (타임아웃)"}

    async def post(self, title, content, blog_id=None, category_no=None,
                   format_html=True, persona_id="yun_ung_chae"):
        """
        블로그 글 발행 전체 흐름

        Args:
            title: 글 제목
            content: 본문 텍스트 (마크다운)
            blog_id: 블로그 ID (없으면 NAVER_ID 사용)
            category_no: 카테고리 번호
            format_html: True면 마크다운 -> HTML 변환 후 발행
            persona_id: 페르소나 ID (HTML 포맷팅 시 사용)

        Returns:
            dict: {'success': bool, 'url': str, ...}
        """
        blog_id = blog_id or os.environ.get("NAVER_ID", "")
        if not blog_id:
            return {"success": False, "error": "blog_id 또는 NAVER_ID가 필요합니다."}

        # 연결 확인/복구
        if not self._connected or not self.browser:
            await self.connect()
            await self.login()

        await self._reconnect_if_needed()
        await self._navigate_to_editor(blog_id)

        # 제목 설정
        title_result = await self._set_title(title)
        if not title_result.get("ok"):
            return {"success": False, "error": "제목 설정 실패"}

        # 본문: 마크다운 -> HTML 변환
        if format_html:
            html_content = format_column_html(content, persona_id)
            content_result = await self._set_content(html_content, is_html=True)
        else:
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
        """연결 종료 (안전)"""
        self._connected = False
        try:
            if self.browser:
                await self.browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
        self.browser = None
        self.context = None
        self.page = None
        self._pw = None


# -- 편의 함수 --

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
        await poster.connect()
        await poster.login()
        result = await poster.post(title, content, blog_id, category_no)
        return result
    finally:
        await poster.close()


async def generate_and_post(topic, persona_id="yun_ung_chae",
                            persona_name="윤웅채",
                            model_id="claude-sonnet-4-6",
                            blog_id=None, category_no=None):
    """
    키워드 -> 칼럼 생성 -> 네이버 발행 통합 함수

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

    # 2. 발행 (HTML 포맷팅 포함)
    poster = NaverPoster()
    try:
        await poster.connect()
        await poster.login()
        post_result = await poster.post(
            title, content, blog_id, category_no,
            format_html=True, persona_id=persona_id,
        )
        post_result["generation"] = {
            "attempts": gen_result["attempts"],
            "similarity": gen_result["similarity_check"],
            "char_count": len(content),
        }
        return post_result
    finally:
        await poster.close()
