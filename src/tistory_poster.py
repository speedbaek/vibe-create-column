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
    try:
        print(f"[TistoryPoster] {msg}")
    except UnicodeEncodeError:
        print(f"[TistoryPoster] {msg.encode('utf-8', errors='replace').decode('utf-8')}")


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
        """키워드 기반 카테고리 자동 선택 (티스토리 에디터 대응)"""
        categories = self._blog_config.get("categories", {})
        default_cat = self._blog_config.get("default_category", "")

        # 키워드로 카테고리 매칭
        matched_category = default_cat
        for cat_name, cat_keywords in categories.items():
            if any(kw in keyword for kw in cat_keywords):
                matched_category = cat_name
                break

        if not matched_category:
            _log("카테고리 매칭 실패: 키워드에 맞는 카테고리 없음")
            return

        _log(f"카테고리 매칭: '{keyword}' → '{matched_category}'")

        try:
            # ── 방법 1: #category-btn 버튼 (현재 티스토리 에디터) ──
            cat_btn = self.page.query_selector('#category-btn')
            if cat_btn:
                _log("카테고리 버튼 발견: #category-btn")
                cat_btn.click()
                time.sleep(2)

                # 드롭다운 열린 후 모든 li 요소 탐색
                dropdown_selectors = [
                    '.btn-category li',
                    '.btn-category ul li',
                    '#category-list li',
                    '[class*="category"] li',
                    '.layer_category li',
                    '.list_category li',
                ]
                for item_sel in dropdown_selectors:
                    cat_items = self.page.query_selector_all(item_sel)
                    if cat_items:
                        _log(f"드롭다운 아이템 ({item_sel}): {[i.inner_text().strip() for i in cat_items[:10]]}")
                        for item in cat_items:
                            item_text = item.inner_text().strip()
                            if matched_category in item_text or item_text in matched_category:
                                item.click()
                                time.sleep(0.5)
                                _log(f"✅ 카테고리 선택: {matched_category}")
                                return

                # 버튼/a 태그로도 시도
                link_selectors = [
                    '.btn-category a',
                    '.btn-category button',
                    '#category-list a',
                ]
                for link_sel in link_selectors:
                    links = self.page.query_selector_all(link_sel)
                    if links:
                        _log(f"링크 아이템 ({link_sel}): {[l.inner_text().strip() for l in links[:10]]}")
                        for link in links:
                            link_text = link.inner_text().strip()
                            if matched_category in link_text or link_text in matched_category:
                                link.click()
                                time.sleep(0.5)
                                _log(f"✅ 카테고리 선택 (링크): {matched_category}")
                                return

                # JS로 드롭다운 내 텍스트 매칭 클릭
                js_result = self.page.evaluate(f"""() => {{
                    const items = document.querySelectorAll('.btn-category *');
                    for (const el of items) {{
                        const text = el.textContent?.trim() || '';
                        if (text === '{matched_category}' || text.includes('{matched_category}')) {{
                            if (el.tagName === 'A' || el.tagName === 'BUTTON' || el.tagName === 'LI'
                                || el.tagName === 'SPAN' || el.onclick) {{
                                el.click();
                                return 'clicked:' + text;
                            }}
                        }}
                    }}
                    // 전체 DOM에서 텍스트 검색
                    const all = document.querySelectorAll('a, button, li, span');
                    for (const el of all) {{
                        if (el.textContent?.trim() === '{matched_category}') {{
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {{
                                el.click();
                                return 'clicked_global:' + el.tagName + ':' + el.textContent.trim();
                            }}
                        }}
                    }}
                    return 'not_found';
                }}""")

                if js_result and js_result.startswith("clicked"):
                    _log(f"✅ 카테고리 선택 (JS): {js_result}")
                    return

                # 닫기
                self.page.keyboard.press("Escape")
                time.sleep(0.5)
                _log(f"⚠️ 드롭다운에서 '{matched_category}' 못 찾음: {js_result}")
                return

            # ── 방법 2: select 엘리먼트 (구버전 에디터) ──
            for sel in ['select#category', 'select.tf_category', 'select[name="category"]']:
                cat_select = self.page.query_selector(sel)
                if cat_select:
                    options = cat_select.query_selector_all("option")
                    for opt in options:
                        text = opt.inner_text().strip()
                        if matched_category in text or text in matched_category:
                            value = opt.get_attribute("value")
                            cat_select.select_option(value=value)
                            _log(f"✅ 카테고리 선택 (select): {matched_category} (value={value})")
                            return

            _log(f"⚠️ 카테고리 UI 요소를 찾지 못함")
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

            # 임시저장/복구 팝업 제거 (있을 경우)
            try:
                # 티스토리: "이전에 작성하던 글이 있습니다" 같은 팝업
                dismissed = self.page.evaluate("""() => {
                    // 모든 팝업/모달에서 "취소", "새로", "아니오", "닫기" 버튼 찾아 클릭
                    const btns = document.querySelectorAll('button, a.btn, .btn');
                    for (const btn of btns) {
                        const txt = (btn.textContent || '').trim();
                        if (txt.includes('취소') || txt.includes('새로') || txt.includes('아니')
                            || txt.includes('닫기') || txt.includes('삭제')) {
                            // 모달/팝업 안의 버튼인 경우만
                            const parent = btn.closest('.layer, .modal, .popup, [class*="alert"], [class*="dialog"], [role="dialog"]');
                            if (parent) {
                                btn.click();
                                return 'dismissed: ' + txt;
                            }
                        }
                    }
                    // confirm 팝업도 있을 수 있으므로 dismiss
                    return null;
                }""")
                if dismissed:
                    _log(f"팝업 제거: {dismissed}")
                    time.sleep(1)

                # "이전 작성글 보기" 같은 알림도 제거
                self.page.evaluate("""() => {
                    const alerts = document.querySelectorAll('[class*="notification"], [class*="toast"], .mce-notification');
                    for (const a of alerts) { a.remove(); }
                }""")
            except Exception:
                pass

            # 기존 제목/본문 초기화 (임시저장 글이 남아있을 수 있음)
            self.page.evaluate("""() => {
                // 제목 초기화
                const titleInput = document.getElementById('post-title-inp');
                if (titleInput) { titleInput.value = ''; titleInput.innerHTML = ''; }
                // TinyMCE 본문 초기화
                if (typeof tinymce !== 'undefined' && tinymce.activeEditor) {
                    tinymce.activeEditor.setContent('');
                }
            }""")
            time.sleep(1)

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
                time.sleep(0.3)
                # 기존 내용 선택 후 삭제
                self.page.keyboard.press('Control+a')
                time.sleep(0.2)
                self.page.keyboard.press('Backspace')
                time.sleep(0.3)
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

            # CodeMirror → 숨겨진 textarea 강제 동기화 (HTML 모드에서 바로 발행)
            _log("CodeMirror 동기화 중...")
            self.page.evaluate("""() => {
                // 1. CodeMirror.save() - textarea에 동기화
                const cms = document.querySelectorAll('.CodeMirror');
                for (const cm of cms) {
                    if (cm.CodeMirror) {
                        cm.CodeMirror.save();
                    }
                }
                // 2. 모든 textarea에 CodeMirror 내용 복사
                const cmContent = cms[0]?.CodeMirror?.getValue() || '';
                const textareas = document.querySelectorAll('textarea');
                for (const ta of textareas) {
                    if (ta.style.display === 'none' || ta.offsetParent === null) {
                        ta.value = cmContent;
                    }
                }
                // 3. TinyMCE 내부 상태에도 반영
                if (typeof tinymce !== 'undefined') {
                    const editors = tinymce.editors || [];
                    for (const ed of editors) {
                        try { ed.setContent(cmContent); } catch(e) {}
                    }
                }
            }""")
            time.sleep(1)
            _log("CodeMirror 동기화 완료")

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

            # 발행 전 URL 기록 (발행 후 비교용)
            pre_publish_url = self.page.url
            _log(f"발행 전 URL: {pre_publish_url}")

            # 발행 레이어 열기 (publish-layer-btn = "완료" 버튼)
            # Playwright click + JS click 이중 시도
            try:
                btn = self.page.locator('#publish-layer-btn')
                if btn.count() > 0 and btn.is_visible():
                    btn.click()
                else:
                    self.page.evaluate('document.getElementById("publish-layer-btn")?.click()')
            except Exception:
                self.page.evaluate('document.getElementById("publish-layer-btn")?.click()')
            _log("발행 레이어 열기 시도")
            time.sleep(2 + random.uniform(0.5, 1.0))

            # 발행 레이어 열렸는지 확인
            layer_open = self.page.evaluate("""() => {
                const layer = document.getElementById('publish-layer');
                if (!layer) return false;
                const style = window.getComputedStyle(layer);
                return style.display !== 'none' && style.visibility !== 'hidden';
            }""")
            _log(f"발행 레이어 상태: {'열림' if layer_open else '안 열림'}")

            if not layer_open:
                # fallback: JS로 강제 표시
                self.page.evaluate("""() => {
                    const layer = document.getElementById('publish-layer');
                    if (layer) { layer.style.display = 'block'; layer.style.visibility = 'visible'; }
                }""")
                time.sleep(1)

            # 공개 설정: Playwright 실제 클릭 (JS DOM 조작은 React 상태에 반영 안됨)
            time.sleep(1)  # 레이어 렌더링 대기

            # 방법1: Playwright로 라디오 label 클릭 (가장 확실)
            visibility_set = "NOT_SET"
            try:
                # #open20 라디오의 label을 클릭 (for="open20")
                open_label = self.page.locator('label[for="open20"]')
                if open_label.count() > 0 and open_label.is_visible():
                    open_label.click()
                    visibility_set = "label_for_open20"
                    _log(f"공개 설정: label[for=open20] 클릭")
                else:
                    # #open20 라디오 직접 클릭
                    open_radio = self.page.locator('#open20')
                    if open_radio.count() > 0:
                        open_radio.click(force=True)
                        visibility_set = "radio_open20_force"
                        _log(f"공개 설정: #open20 강제 클릭")
            except Exception as e:
                _log(f"Playwright 공개 설정 시도1 오류: {e}")

            time.sleep(0.5)

            # 방법2: 여전히 체크 안됐으면 JS dispatchEvent + click 조합
            if visibility_set == "NOT_SET":
                visibility_set = self.page.evaluate("""() => {
                    let radio = document.getElementById('open20');
                    if (!radio) radio = document.querySelector('input[name="visibility"][value="20"]');
                    if (radio) {
                        radio.checked = true;
                        radio.click();
                        radio.dispatchEvent(new Event('change', { bubbles: true }));
                        radio.dispatchEvent(new Event('input', { bubbles: true }));
                        // label도 클릭
                        const label = document.querySelector('label[for="' + radio.id + '"]');
                        if (label) label.click();
                        return 'js_fallback';
                    }
                    return 'NOT_FOUND';
                }""")
            _log(f"공개 설정 결과: {visibility_set}")
            time.sleep(1)

            # 검증: 실제 체크 상태
            is_public = self.page.evaluate("""() => {
                const radio = document.getElementById('open20') ||
                              document.querySelector('input[name="visibility"][value="20"]');
                return radio ? radio.checked : null;
            }""")
            _log(f"공개 라디오 체크 상태: {is_public}")

            # 방법3: 스크린샷으로 디버깅 정보 수집
            if not is_public:
                _log("⚠️ 공개 설정 실패 - 발행 레이어 HTML 디버깅")
                layer_html = self.page.evaluate("""() => {
                    const layer = document.getElementById('publish-layer');
                    if (!layer) return 'NO_LAYER';
                    // 라디오 버튼 목록
                    const radios = layer.querySelectorAll('input[type="radio"]');
                    const info = [];
                    radios.forEach(r => {
                        info.push({id: r.id, name: r.name, value: r.value, checked: r.checked});
                    });
                    return JSON.stringify(info);
                }""")
                _log(f"발행 레이어 라디오 목록: {layer_html}")

            # 최종 발행 버튼 클릭 (#publish-btn)
            # 발행 버튼 텍스트가 "공개발행" 또는 "발행"인지 확인
            publish_btn_text = self.page.evaluate("""() => {
                const btn = document.getElementById('publish-btn');
                return btn ? btn.textContent.trim() : 'NOT_FOUND';
            }""")
            _log(f"발행 버튼 텍스트: {publish_btn_text}")

            # Playwright 실제 클릭 (JS click보다 확실)
            try:
                final_btn = self.page.locator('#publish-btn')
                if final_btn.count() > 0 and final_btn.is_visible():
                    final_btn.click()
                    _log("발행 버튼 Playwright 클릭!")
                else:
                    self.page.evaluate('document.getElementById("publish-btn")?.click()')
                    _log("발행 버튼 JS 클릭!")
            except Exception:
                self.page.evaluate('document.getElementById("publish-btn")?.click()')
                _log("발행 버튼 JS 폴백 클릭!")
            time.sleep(5 + random.uniform(1, 2))

            # 8. 발행 결과 확인
            self._progress(8, total_steps, "발행 결과 확인 중...")

            # 페이지 리다이렉트 대기 (최대 15초)
            blog_url = self._blog_config.get("blog_url", "")
            for _ in range(15):
                time.sleep(1)
                current_url = self.page.url
                # newpost가 아닌 글 페이지로 이동했으면 성공
                if "/manage/newpost" not in current_url and current_url != pre_publish_url:
                    break

            current_url = self.page.url
            _log(f"발행 후 URL: {current_url}")

            # 발행 후 글 페이지로 리다이렉트된 경우
            if blog_url.replace("https://", "") in current_url and "/manage/newpost" not in current_url and "/manage/posts" not in current_url:
                _log(f"발행 성공! URL: {current_url}")
                return {"success": True, "url": current_url, "error": ""}

            # 관리 페이지에 있으면 → 최신 글 확인
            self.page.goto(f"{blog_url}/manage/posts", wait_until="domcontentloaded", timeout=10000)
            time.sleep(2)

            # 최신 글 제목이 현재 발행한 제목과 일치하는지 확인
            post_url = ""
            try:
                first_title_el = self.page.query_selector('.tit_post, .list_post .tit_cont, .post-item .title')
                if first_title_el:
                    first_title = first_title_el.text_content().strip()
                    _log(f"최신 글 제목: {first_title}")

                first_link = self.page.query_selector('.list_post a[href*="/manage/post/"], .post-item a')
                if first_link:
                    href = first_link.get_attribute("href") or ""
                    # /manage/post/123 → /123
                    import re as _re
                    post_id_match = _re.search(r'/post/(\d+)', href)
                    if post_id_match:
                        post_url = f"{blog_url}/{post_id_match.group(1)}"
            except Exception as ex:
                _log(f"최신 글 확인 오류: {ex}")

            # 비공개 → 공개 전환 (관리 페이지에서)
            try:
                self._ensure_post_public(title)
            except Exception as e:
                _log(f"공개 전환 시도 오류: {e}")

            if post_url:
                _log(f"발행 성공! URL: {post_url}")
                return {"success": True, "url": post_url, "error": ""}

            _log(f"발행 완료 (URL 확인 불가): {current_url}")
            return {"success": True, "url": current_url, "error": ""}

        except Exception as e:
            err_msg = str(e).encode('ascii', errors='replace').decode('ascii')
            _log(f"발행 오류: {err_msg}")
            return {"success": False, "url": "", "error": err_msg}

    def _ensure_post_public(self, title=""):
        """관리 페이지에서 최신 글이 비공개이면 공개로 변경"""
        blog_url = self._blog_config.get("blog_url", "")

        # 현재 관리 페이지인지 확인, 아니면 이동
        if "/manage/posts" not in self.page.url:
            self.page.goto(f"{blog_url}/manage/posts", wait_until="domcontentloaded", timeout=10000)
            time.sleep(2)

        # 최신 글의 비공개 표시 확인
        is_private = self.page.evaluate("""() => {
            // 최신 글(첫 번째 행)에서 비공개/보호 표시 찾기
            const firstRow = document.querySelector('.list_post li, .post-item, tr.item');
            if (!firstRow) return null;
            const text = firstRow.textContent || '';
            if (text.includes('비공개') || text.includes('보호')) return true;
            // 공개 상태 아이콘 확인
            const badge = firstRow.querySelector('.ico_secret, .badge-private, .label_secret');
            return badge ? true : false;
        }""")
        _log(f"최신 글 비공개 여부: {is_private}")

        if not is_private:
            _log("이미 공개 상태 - 변경 불필요")
            return

        # 비공개 → 공개 변경: 최신 글의 설정 메뉴에서 "공개로 변경" 클릭
        _log("비공개 글 감지 → 공개로 변경 시도...")

        # 방법1: 글 목록의 더보기(...) 버튼 → "공개로 변경" 클릭
        try:
            # 첫 번째 글의 더보기 버튼 클릭
            more_btn = self.page.locator('.list_post li:first-child .btn_more, .post-item:first-child .btn-more, .item:first-child .btn_setting').first
            if more_btn.count() > 0:
                more_btn.click()
                time.sleep(1)

                # "공개로 변경" 메뉴 클릭
                public_menu = self.page.locator('text=공개로 변경').first
                if public_menu.count() > 0 and public_menu.is_visible():
                    public_menu.click()
                    time.sleep(1)

                    # 확인 다이얼로그 있으면 확인 클릭
                    try:
                        confirm_btn = self.page.locator('text=확인, .btn_ok, .confirm-btn').first
                        if confirm_btn.count() > 0 and confirm_btn.is_visible():
                            confirm_btn.click()
                    except Exception:
                        pass

                    _log("공개로 변경 완료!")
                    time.sleep(1)
                    return
        except Exception as e:
            _log(f"더보기 메뉴 공개 변경 실패: {e}")

        # 방법2: 글 수정 페이지로 진입해서 공개 설정 변경
        try:
            first_edit = self.page.locator('.list_post li:first-child a[href*="/manage/post/"], .post-item:first-child a').first
            if first_edit.count() > 0:
                first_edit.click()
                time.sleep(3)

                # 발행 레이어 열기
                self.page.evaluate('document.getElementById("publish-layer-btn")?.click()')
                time.sleep(2)

                # 공개 라디오 클릭
                open_label = self.page.locator('label[for="open20"]')
                if open_label.count() > 0 and open_label.is_visible():
                    open_label.click()
                    time.sleep(0.5)

                # 수정 발행
                self.page.evaluate('document.getElementById("publish-btn")?.click()')
                time.sleep(3)
                _log("수정 페이지에서 공개로 재발행 완료!")
                return
        except Exception as e:
            _log(f"수정 페이지 공개 변경 실패: {e}")

        _log("⚠️ 공개 전환 모든 방법 실패")

    def _upload_images(self, image_paths):
        """
        네트워크 응답 가로채기로 이미지를 업로드하고 CDN URL 획득

        Args:
            image_paths: 로컬 이미지 파일 경로 리스트

        Returns:
            list: 업로드된 이미지의 티스토리 CDN URL 리스트
        """
        uploaded_urls = []
        if not image_paths:
            return uploaded_urls

        for i, img_path in enumerate(image_paths):
            if not os.path.exists(img_path):
                _log(f"이미지 파일 없음: {img_path}")
                continue

            try:
                _log(f"이미지 업로드 중... ({i+1}/{len(image_paths)})")

                # 네트워크 응답 캡처 준비
                captured_urls = []
                def handle_response(response):
                    try:
                        url = response.url
                        # 티스토리 이미지 업로드 API 응답 캡처
                        if ('upload' in url or 'attach' in url or 'image' in url) and response.status == 200:
                            try:
                                body = response.text()
                                # JSON 응답에서 URL 추출
                                import json as _json
                                data = _json.loads(body)
                                # 다양한 응답 형식 처리
                                img_url = (data.get('url') or data.get('imageUrl')
                                          or data.get('src') or data.get('fileUrl', ''))
                                if not img_url and isinstance(data, dict):
                                    # 중첩 구조 탐색
                                    for v in data.values():
                                        if isinstance(v, str) and ('cdn' in v or 'daumcdn' in v or 'kakaocdn' in v):
                                            img_url = v
                                            break
                                        if isinstance(v, dict):
                                            img_url = v.get('url', v.get('src', ''))
                                            if img_url:
                                                break
                                if img_url:
                                    captured_urls.append(img_url)
                            except Exception:
                                pass
                    except Exception:
                        pass

                self.page.on("response", handle_response)

                # 1. "첨부" 버튼 클릭 (보이는 것만)
                attach_btns = self.page.locator('[aria-label="첨부"]')
                clicked = False
                for idx in range(attach_btns.count()):
                    if attach_btns.nth(idx).is_visible():
                        attach_btns.nth(idx).click()
                        clicked = True
                        break
                if not clicked:
                    # fallback: 다른 셀렉터 시도
                    alt_btn = self.page.locator('button:has-text("첨부"), .btn-attach, [data-name="attach"]').first
                    if alt_btn.count() > 0:
                        alt_btn.click()
                        clicked = True
                if not clicked:
                    _log("첨부 버튼을 찾을 수 없습니다")
                    self.page.remove_listener("response", handle_response)
                    continue
                time.sleep(1.5)

                # 2. 드롭다운에서 "사진" 클릭 + file_chooser 대기
                with self.page.expect_file_chooser(timeout=10000) as fc_info:
                    self.page.evaluate("""() => {
                        const all = document.querySelectorAll('*');
                        for (const el of all) {
                            if (el.textContent?.trim() === '사진'
                                && el.offsetParent !== null
                                && el.children.length === 0
                                && el.getBoundingClientRect().height > 10
                                && el.getBoundingClientRect().height < 50) {
                                el.click();
                                return;
                            }
                        }
                    }""")

                file_chooser = fc_info.value
                file_chooser.set_files(img_path)
                _log(f"이미지 파일 전달: {os.path.basename(img_path)}")

                # 3. 업로드 완료 + CDN URL 대기 (최대 15초)
                cdn_url = ""
                for wait_i in range(15):
                    time.sleep(1)

                    # 방법1: 네트워크 응답에서 캡처된 URL 확인
                    if captured_urls:
                        cdn_url = captured_urls[-1]
                        _log(f"네트워크 응답에서 CDN URL 캡처 ({wait_i+1}초): {cdn_url[:80]}...")
                        break

                    # 방법2: TinyMCE DOM에서 CDN URL 확인
                    new_url = self.page.evaluate("""(() => {
                        if (typeof tinymce !== 'undefined' && tinymce.activeEditor) {
                            const imgs = tinymce.activeEditor.dom.select('img');
                            for (let i = imgs.length - 1; i >= 0; i--) {
                                const src = imgs[i].src || '';
                                if (src.includes('daumcdn') || src.includes('kakaocdn')
                                    || src.includes('tistory') || (src.startsWith('http') && !src.startsWith('file:'))) {
                                    return src;
                                }
                            }
                        }
                        // iframe 내 확인
                        const iframes = document.querySelectorAll('.mce-edit-area iframe');
                        for (const iframe of iframes) {
                            try {
                                const imgs = iframe.contentDocument.querySelectorAll('img');
                                for (let i = imgs.length - 1; i >= 0; i--) {
                                    const src = imgs[i].src || '';
                                    if (src.includes('daumcdn') || src.includes('kakaocdn')
                                        || (src.startsWith('http') && !src.startsWith('file:'))) {
                                        return src;
                                    }
                                }
                            } catch(e) {}
                        }
                        return '';
                    })()""")

                    if new_url:
                        cdn_url = new_url
                        _log(f"DOM에서 CDN URL 발견 ({wait_i+1}초): {cdn_url[:80]}...")
                        break

                self.page.remove_listener("response", handle_response)

                if cdn_url:
                    uploaded_urls.append(cdn_url)
                    _log(f"이미지 업로드 완료: {cdn_url[:80]}...")
                else:
                    _log(f"이미지 CDN URL 추출 실패")

                time.sleep(1 + random.uniform(0.3, 0.8))

            except Exception as e:
                _log(f"이미지 업로드 오류: {e}")
                try:
                    self.page.remove_listener("response", handle_response)
                except Exception:
                    pass

        return uploaded_urls

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

        # 2. 로컬 이미지 경로 수집
        local_image_paths = []
        image_data = preview.get("image_data")
        if image_data:
            imgs_list = image_data.get("body_images") or image_data.get("images") or []
            for img in imgs_list:
                if img:
                    path = img.get("url", img.get("path", ""))
                    if path and os.path.exists(path):
                        local_image_paths.append(path)

        # 3. 브라우저 연결 + 로그인
        self._progress(2, total_steps, "티스토리 로그인 중...")
        self.connect()
        login_ok = self.login()
        if not login_ok:
            return {"success": False, "url": "", "error": "로그인 실패",
                    "title": title, "content": raw_content}

        # 4. 이미지 업로드 → CDN URL 획득
        cdn_image_urls = []
        if local_image_paths:
            self._progress(3, total_steps, f"이미지 업로드 중... ({len(local_image_paths)}장)")
            # 에디터 페이지로 이동 (이미지 업로드용)
            editor_url = self._blog_config.get(
                "editor_url",
                f"{self._blog_config.get('blog_url', '')}/manage/newpost"
            )
            self.page.goto(editor_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(6)
            # 팝업 제거
            try:
                self.page.evaluate("""() => {
                    const alerts = document.querySelectorAll('.mce-notification');
                    for (const a of alerts) { a.remove(); }
                }""")
            except Exception:
                pass
            time.sleep(1)
            cdn_image_urls = self._upload_images(local_image_paths)
            _log(f"CDN 이미지 {len(cdn_image_urls)}장 확보")

        # 5. HTML 변환 (CDN URL 사용)
        self._progress(4, total_steps, "HTML 변환 + 발행 중...")
        html_content = markdown_to_html(
            raw_content,
            image_urls=cdn_image_urls if cdn_image_urls else [],
            persona_id=persona_id,
        )

        # 6. 글 발행 (이미지 업로드한 같은 에디터 페이지에서 계속)
        tags = [topic] + topic.split() if topic else []
        # 이미지 업로드 후 에디터 초기화 필요 (이미지만 올린 상태)
        result = self.post_human_like(
            title=title,
            html_content=html_content,
            keyword=topic,
            tags=tags[:10],
        )

        result["title"] = title
        result["content"] = raw_content
        result["char_count"] = len(raw_content)
        result["image_count"] = len(cdn_image_urls)
        result["generation"] = {
            "title_candidates": preview.get("title_candidates", []),
        }
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
