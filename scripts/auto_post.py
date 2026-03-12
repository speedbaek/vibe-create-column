"""
자동 포스팅 스크립트
- 네이버 로그인 → 에디터 이동 → 이미지 CDN 업로드 → SE 데이터 빌드 → 발행
"""
import os
import sys
import json
import asyncio

sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv(override=True)

# 프로젝트 루트 기준 경로 계산
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)


def _out(filename):
    """outputs 폴더 내 파일 경로"""
    return os.path.join(PROJECT_ROOT, 'outputs', filename)


async def full_posting():
    from playwright.async_api import async_playwright

    naver_id = os.environ.get('NAVER_ID', '')
    naver_pw = os.environ.get('NAVER_PW', '')
    blog_id = naver_id

    # Load generated content
    with open(_out('_temp_post.json'), 'r', encoding='utf-8') as f:
        post_data = json.load(f)

    title = post_data['title']
    content = post_data['content']
    local_image_paths = post_data.get('local_image_paths', [])

    print(f'[INFO] Title: {title}')
    print(f'[INFO] Content length: {len(content)} chars')
    print(f'[INFO] Local images: {len(local_image_paths)}장')

    # Connect to Chrome CDP
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp('http://127.0.0.1:9222')
    context = browser.contexts[0]
    page = context.pages[0] if context.pages else await context.new_page()

    # Step 1: Navigate to Naver login
    print('[STEP 1] Navigating to Naver login...')
    await page.goto('https://nid.naver.com/nidlogin.login')
    await page.wait_for_load_state('networkidle')
    await asyncio.sleep(2)

    # Check if already logged in (redirected to main page)
    if 'naver.com' in page.url and 'nidlogin' not in page.url and 'login' not in page.url:
        print('[STEP 1] Already logged in!')
    else:
        # Step 2: Login using evaluate
        print('[STEP 2] Logging in...')
        login_result = await page.evaluate(
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

                return {ok: true, id_val: idEl.value.length, pw_val: pwEl.value.length};
            }""",
            {'id': naver_id, 'pw': naver_pw}
        )
        print(f'[STEP 2] Login fields set: {login_result}')

        if not login_result.get('ok'):
            print(f'[ERROR] Login field setup failed')
            await browser.close()
            await pw.stop()
            return

        # Click login button
        await asyncio.sleep(1)
        try:
            login_btn = page.locator('#log\\.login').first
            if await login_btn.is_visible(timeout=2000):
                await login_btn.click()
            else:
                login_btn = page.locator('button.btn_login, button[type="submit"]').first
                await login_btn.click()
        except Exception:
            await page.evaluate('document.querySelector("form").submit()')

        await asyncio.sleep(5)
        current_url = page.url
        print(f'[STEP 2] After login URL: {current_url}')

        # Handle device confirmation page
        if 'deviceConfirm' in current_url:
            print('[STEP 2.5] Device confirmation detected - clicking register...')
            try:
                register_btn = page.locator('button:has-text("등록")').first
                if await register_btn.is_visible(timeout=3000):
                    await register_btn.click()
                    await asyncio.sleep(3)
                    print(f'[STEP 2.5] After device confirm URL: {page.url}')
                else:
                    await page.evaluate("""() => {
                        const links = document.querySelectorAll('a, button');
                        for (const el of links) {
                            if (el.textContent.trim() === '등록') {
                                el.click();
                                return true;
                            }
                        }
                        return false;
                    }""")
                    await asyncio.sleep(3)
            except Exception as e:
                print(f'[WARNING] Device confirm click: {e}')

        # Final check
        current_url = page.url
        if 'nidlogin' in current_url or 'login' in current_url:
            print('[ERROR] Still on login page after all attempts')
            await page.screenshot(path=_out('login_final.png'))
            await browser.close()
            await pw.stop()
            return

    print('[LOGIN] Login successful!')

    # Step 3: Navigate to blog editor
    print('[STEP 3] Navigating to blog editor...')
    editor_url = f'https://blog.naver.com/{blog_id}/postwrite'
    await page.goto(editor_url)
    await page.wait_for_load_state('networkidle')
    await asyncio.sleep(3)

    if 'nidlogin' in page.url or 'login' in page.url:
        print('[ERROR] Redirected to login - session not valid')
        await browser.close()
        await pw.stop()
        return

    # Wait for SmartEditor
    print('[STEP 3] Waiting for SmartEditor...')
    try:
        await page.wait_for_function(
            "() => typeof SmartEditor !== 'undefined' && SmartEditor._editors && SmartEditor._editors.blogpc001",
            timeout=20000,
        )
    except Exception as e:
        print(f'[ERROR] SmartEditor not loaded: {e}')
        await page.screenshot(path=_out('editor_check.png'))
        await browser.close()
        await pw.stop()
        return

    await asyncio.sleep(3)
    print('[STEP 3] SmartEditor loaded!')

    # 팝업 제거는 uploader 내부에서 처리 (중복 제거 방지)

    # Step 4: 이미지 네이버 CDN 업로드
    native_image_components = []
    if local_image_paths:
        print(f'[STEP 4] 이미지 {len(local_image_paths)}장 네이버 CDN 업로드 중...')
        from src.naver_uploader import upload_images_to_naver
        upload_results = await upload_images_to_naver(page, blog_id, local_image_paths)

        for i, result in enumerate(upload_results):
            if result and result.get('src'):
                native_image_components.append(result)
                src = result.get('src', '')
                w, h = result.get('width', 0), result.get('height', 0)
                print(f'  [{i+1}] OK: {src[:80]}... ({w}x{h})')
            else:
                print(f'  [{i+1}] FAIL')

        print(f'[STEP 4] 업로드 결과: {len(native_image_components)}/{len(local_image_paths)}장 성공')

        # 이미지 업로드 전부 실패 시 중단 (불필요한 발행 방지)
        if local_image_paths and not native_image_components:
            print('[ERROR] 이미지 업로드 전부 실패 - 발행 중단')
            await page.screenshot(path=_out('upload_all_fail.png'))
            await browser.close()
            await pw.stop()
            return
    else:
        print('[STEP 4] 업로드할 이미지 없음 (건너뜀)')

    # Step 5: SE Document Data 빌드 (네이티브 이미지 컴포넌트 사용)
    print('[STEP 5] SE Document Data 빌드 (네이티브 이미지 컴포넌트 사용)...')
    from src.se_converter import build_document_data

    se_doc_data = build_document_data(
        title=title,
        text=content,
        image_urls=native_image_components if native_image_components else None,
    )

    comp_count = len(se_doc_data.get('document', {}).get('components', []))
    print(f'[STEP 5] 컴포넌트 수: {comp_count}')

    # 컴포넌트 타입 요약
    type_counts = {}
    for comp in se_doc_data.get('document', {}).get('components', []):
        ctype = comp.get('@ctype', 'unknown')
        type_counts[ctype] = type_counts.get(ctype, 0) + 1
    for ctype, count in type_counts.items():
        print(f'  {ctype}: {count}')

    # Step 6: setDocumentData로 제목+본문 설정
    print('[STEP 6] setDocumentData 설정...')
    content_result = await page.evaluate(
        """(docData) => {
            var ed = SmartEditor._editors.blogpc001;
            var ds = ed._documentService;
            try {
                ds.setDocumentData(docData);
                var ct = ds.getContentText();
                var title = ds.getDocumentTitle();
                return {
                    ok: ct.length > 10,
                    method: 'setDocumentData',
                    contentLen: ct.length,
                    title: title,
                    preview: ct.substring(0, 150),
                    isEmpty: ed.isEmptyDocumentContent(),
                };
            } catch(e) {
                return {ok: false, method: 'setDocumentData_failed', error: e.message};
            }
        }""",
        se_doc_data
    )
    print(f'[STEP 6] method={content_result.get("method")}, len={content_result.get("contentLen", 0)}')

    # setDocumentData 실패 시 plain text 폴백
    if not content_result.get('ok'):
        print('[STEP 6] setDocumentData 실패 → plain text 폴백...')
        await page.evaluate(
            """(title) => {
                var ed = SmartEditor._editors.blogpc001;
                ed.setDocumentTitle(title);
            }""",
            title
        )
        content_result = await page.evaluate(
            """(body) => {
                var ed = SmartEditor._editors.blogpc001;
                ed.focusFirstText();
                ed._editingService.write(body);
                return {
                    ok: true,
                    method: 'plain_fallback',
                    contentLen: ed.getContentText().length,
                    isEmpty: ed.isEmptyDocumentContent(),
                };
            }""",
            content
        )

    print(f'[STEP 6] isEmpty={content_result.get("isEmpty")}, method={content_result.get("method")}')

    if content_result.get('isEmpty'):
        print('[ERROR] Content is empty after write!')
        await page.screenshot(path=_out('content_empty.png'))
        await browser.close()
        await pw.stop()
        return

    # Step 7: Validate
    print('[STEP 7] Validating...')
    validation = await page.evaluate("""() => {
        var ed = SmartEditor._editors.blogpc001;
        var v = ed.validate();
        return {
            valid: v.valid,
            reason: v.reason || '',
            title: ed.getDocumentTitle(),
            isEmpty: ed.isEmptyDocumentContent(),
        };
    }""")
    print(f'[STEP 7] valid={validation.get("valid")}, reason={validation.get("reason")}')

    if not validation.get('valid'):
        print(f'[ERROR] Validation failed!')
        await page.screenshot(path=_out('validation_fail.png'))
        await browser.close()
        await pw.stop()
        return

    # Step 8: Publish
    print('[STEP 8] Publishing...')

    # 발행 전 도움말/복구 팝업만 선택적 제거 (에디터 자체 레이어 보존)
    await page.evaluate("""() => {
        var helpClose = document.querySelector('.se-help-close');
        if (helpClose) helpClose.click();
        document.querySelectorAll('[class*="se-help"]').forEach(function(el) { el.remove(); });
        document.querySelectorAll('.se-popup-alert, .se-popup-alert-confirm').forEach(function(popup) {
            var cancelBtn = popup.querySelector('.se-popup-button-cancel');
            if (cancelBtn) cancelBtn.click();
        });
    }""")
    await asyncio.sleep(1)

    # 발행 버튼 찾기
    try:
        publish_btn = page.locator("button[class*='publish_btn']").first
        if not await publish_btn.is_visible(timeout=2000):
            publish_btn = page.locator("button:has-text('발행')").first

        await publish_btn.click(force=True)
        print('[STEP 8] Publish button clicked')
        await asyncio.sleep(3)
    except Exception as e:
        print(f'[ERROR] Publish button: {e}')
        await page.screenshot(path=_out('publish_btn_fail.png'))
        await browser.close()
        await pw.stop()
        return

    # 발행 확인 팝업
    await page.screenshot(path=_out('before_confirm.png'))
    print('[STEP 8] Screenshot before confirm: outputs/before_confirm.png')

    try:
        confirm_btn = page.locator('button.se-popup-button-confirm').first
        if not await confirm_btn.is_visible(timeout=2000):
            confirm_btn = page.locator("button[class*='confirm']").first
        if not await confirm_btn.is_visible(timeout=2000):
            confirm_btn = page.locator("button:has-text('확인')").first

        if await confirm_btn.is_visible(timeout=3000):
            await confirm_btn.click()
            print('[STEP 8] Confirm button clicked')
            await asyncio.sleep(5)
        else:
            print('[WARNING] No confirm button found')
    except Exception as e:
        print(f'[WARNING] Confirm: {e}')

    # 결과 확인
    await asyncio.sleep(3)
    final_url = page.url
    print(f'[RESULT] Final URL: {final_url}')

    if 'PostView' in final_url or 'logNo' in final_url:
        print(f'[SUCCESS] Published! URL: {final_url}')
    else:
        await asyncio.sleep(5)
        final_url = page.url
        if 'PostView' in final_url or 'logNo' in final_url:
            print(f'[SUCCESS] Published! URL: {final_url}')
        else:
            print(f'[INFO] Final URL: {final_url}')
            await page.screenshot(path=_out('publish_result.png'))
            print('[INFO] Screenshot: outputs/publish_result.png')

    await browser.close()
    await pw.stop()


if __name__ == '__main__':
    asyncio.run(full_posting())
