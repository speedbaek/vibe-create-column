"""
자동 포스팅 스크립트
- 네이버 로그인 → 기기등록 → 에디터 이동 → 제목/본문 설정 → 발행
"""
import os
import sys
import json
import asyncio

sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv(override=True)


async def full_posting():
    from playwright.async_api import async_playwright

    naver_id = os.environ.get('NAVER_ID', '')
    naver_pw = os.environ.get('NAVER_PW', '')
    blog_id = naver_id

    # Load generated content
    with open('outputs/_temp_post.json', 'r', encoding='utf-8') as f:
        post_data = json.load(f)

    title = post_data['title']
    content = post_data['content']
    print(f'[INFO] Title: {title}')
    print(f'[INFO] Content length: {len(content)} chars')

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
                # "등록" 버튼 클릭
                register_btn = page.locator('button:has-text("등록")').first
                if await register_btn.is_visible(timeout=3000):
                    await register_btn.click()
                    await asyncio.sleep(3)
                    print(f'[STEP 2.5] After device confirm URL: {page.url}')
                else:
                    # 링크로도 시도
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
            await page.screenshot(path='outputs/login_final.png')
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
        await page.screenshot(path='outputs/editor_check.png')
        print('[INFO] Screenshot: outputs/editor_check.png')
        await browser.close()
        await pw.stop()
        return

    await asyncio.sleep(2)
    print('[STEP 3] SmartEditor loaded!')

    # Remove overlays (including help dialog)
    await page.evaluate("""() => {
        // 도움말, 오버레이, 딤 레이어 모두 제거
        document.querySelectorAll('[class*="overlay"], [class*="dim"], [class*="help"], [class*="container__"]').forEach(el => {
            if (el.querySelector('.se-help-title') || el.classList.toString().includes('overlay') || el.classList.toString().includes('dim')) {
                el.remove();
            }
        });
        // 도움말 닫기 버튼이 있으면 클릭
        const closeBtn = document.querySelector('.se-help-close, button[class*="close"]');
        if (closeBtn) closeBtn.click();
    }""")
    await asyncio.sleep(1)

    # Step 4: Set title
    print(f'[STEP 4] Setting title...')
    title_result = await page.evaluate(
        """(title) => {
            var ed = SmartEditor._editors.blogpc001;
            ed.setDocumentTitle(title);
            return {
                ok: true,
                title: ed.getDocumentTitle(),
            };
        }""",
        title
    )
    print(f'[STEP 4] Title: {title_result.get("title", "")[:60]}')

    # Step 5: Set content
    print('[STEP 5] Setting content...')
    content_result = await page.evaluate(
        """(body) => {
            var ed = SmartEditor._editors.blogpc001;
            ed.focusFirstText();
            ed._editingService.write(body);
            return {
                ok: true,
                contentText: ed.getContentText().substring(0, 100),
                isEmpty: ed.isEmptyDocumentContent(),
            };
        }""",
        content
    )
    print(f'[STEP 5] isEmpty={content_result.get("isEmpty")}')

    if content_result.get('isEmpty'):
        print('[ERROR] Content is empty after write!')
        await page.screenshot(path='outputs/content_empty.png')
        await browser.close()
        await pw.stop()
        return

    # Step 6: Validate
    print('[STEP 6] Validating...')
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
    print(f'[STEP 6] valid={validation.get("valid")}, reason={validation.get("reason")}')

    if not validation.get('valid'):
        print(f'[ERROR] Validation failed!')
        await page.screenshot(path='outputs/validation_fail.png')
        await browser.close()
        await pw.stop()
        return

    # Step 7: Publish
    print('[STEP 7] Publishing...')

    # 발행 전 오버레이 재제거
    await page.evaluate("""() => {
        document.querySelectorAll('[class*="help"], [class*="overlay"], [class*="dim"], [class*="container__"]').forEach(el => {
            const text = el.textContent || '';
            if (text.includes('도움말') || el.classList.toString().includes('overlay') || el.classList.toString().includes('dim')) {
                el.remove();
            }
        });
    }""")
    await asyncio.sleep(1)

    # 발행 버튼 찾기
    try:
        publish_btn = page.locator("button[class*='publish_btn']").first
        if not await publish_btn.is_visible(timeout=2000):
            publish_btn = page.locator("button:has-text('발행')").first

        await publish_btn.click(force=True)
        print('[STEP 7] Publish button clicked')
        await asyncio.sleep(3)
    except Exception as e:
        print(f'[ERROR] Publish button: {e}')
        await page.screenshot(path='outputs/publish_btn_fail.png')
        await browser.close()
        await pw.stop()
        return

    # 발행 확인 팝업
    await page.screenshot(path='outputs/before_confirm.png')
    print('[STEP 7] Screenshot before confirm: outputs/before_confirm.png')

    try:
        # 확인 버튼
        confirm_btn = page.locator('button.se-popup-button-confirm').first
        if not await confirm_btn.is_visible(timeout=2000):
            confirm_btn = page.locator("button[class*='confirm']").first
        if not await confirm_btn.is_visible(timeout=2000):
            confirm_btn = page.locator("button:has-text('확인')").first

        if await confirm_btn.is_visible(timeout=3000):
            await confirm_btn.click()
            print('[STEP 7] Confirm button clicked')
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
            await page.screenshot(path='outputs/publish_result.png')
            print('[INFO] Screenshot: outputs/publish_result.png')

    await browser.close()
    await pw.stop()


if __name__ == '__main__':
    asyncio.run(full_posting())
