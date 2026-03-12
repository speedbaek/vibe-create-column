"""
이미지 업로드만 테스트 (발행 안 함!)
- 로그인 → 에디터 → 이미지 버튼 클릭 → file input 확인 → 업로드 → CDN URL 확인
- auto_post.py 흐름과 동일하게 로그인 과정 포함
- 발행 단계 완전 제거
"""
import os
import sys
import asyncio

sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv(override=True)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)


def _out(filename):
    d = os.path.join(PROJECT_ROOT, 'outputs')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, filename)


async def test_image_only():
    from playwright.async_api import async_playwright

    naver_id = os.environ.get('NAVER_ID', '')
    naver_pw = os.environ.get('NAVER_PW', '')

    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp('http://127.0.0.1:9222')
    context = browser.contexts[0]
    page = context.pages[0] if context.pages else await context.new_page()

    # ── 1. 로그인 (auto_post.py 동일 흐름) ──
    print('[1] 로그인 페이지 이동...')
    await page.goto('https://nid.naver.com/nidlogin.login')
    await page.wait_for_load_state('networkidle')
    await asyncio.sleep(2)

    current = page.url
    if 'nidlogin' in current or 'login' in current:
        print('[1] 로그인 수행...')
        await page.evaluate(
            """(cred) => {
                var id = document.querySelector('#id');
                var pw = document.querySelector('#pw');
                if (!id || !pw) return false;
                id.value = cred.id; pw.value = cred.pw;
                ['input','change'].forEach(e => {
                    id.dispatchEvent(new Event(e, {bubbles:true}));
                    pw.dispatchEvent(new Event(e, {bubbles:true}));
                });
                return true;
            }""",
            {'id': naver_id, 'pw': naver_pw}
        )
        await asyncio.sleep(1)
        try:
            btn = page.locator('#log\\.login').first
            if await btn.is_visible(timeout=2000):
                await btn.click()
            else:
                await page.locator('button.btn_login, button[type="submit"]').first.click()
        except Exception:
            await page.evaluate('document.querySelector("form").submit()')

        await asyncio.sleep(5)
        if 'deviceConfirm' in page.url:
            print('[1] 기기 등록 팝업...')
            try:
                await page.locator('button:has-text("등록")').first.click(timeout=3000)
                await asyncio.sleep(3)
            except Exception:
                pass

        if 'nidlogin' in page.url or 'login' in page.url:
            print('[ERROR] 로그인 실패')
            await browser.close(); await pw.stop()
            return
    else:
        print('[1] 이미 로그인됨')

    print(f'[1] 로그인 완료 - URL: {page.url}')

    # ── 2. 에디터 이동 ──
    print('[2] 에디터 이동...')
    await page.goto(f'https://blog.naver.com/{naver_id}/postwrite')
    await page.wait_for_load_state('networkidle')
    await asyncio.sleep(3)

    print('[2] SmartEditor 대기...')
    try:
        await page.wait_for_function(
            "typeof SmartEditor !== 'undefined' && SmartEditor._editors && SmartEditor._editors.blogpc001",
            timeout=20000,
        )
    except Exception as e:
        print(f'[ERROR] SmartEditor 미로드: {e}')
        await page.screenshot(path=_out('img_test_no_editor.png'))
        await browser.close(); await pw.stop()
        return

    await asyncio.sleep(2)
    print('[2] SmartEditor 로드됨!')

    # ── 3. 팝업 제거 (도움말/복구만, 선택적) ──
    print('[3] 팝업 제거...')
    removed = await page.evaluate("""() => {
        var removed = [];

        // 도움말 닫기
        var helpClose = document.querySelector('.se-help-close');
        if (helpClose) { helpClose.click(); removed.push('help-close'); }

        // 도움말 요소만 제거
        document.querySelectorAll('[class*="se-help"]').forEach(function(el) {
            el.remove();
            removed.push('help-el');
        });

        // 복구 팝업 → 취소
        document.querySelectorAll('.se-popup-alert, .se-popup-alert-confirm').forEach(function(popup) {
            var cancelBtn = popup.querySelector('.se-popup-button-cancel');
            if (cancelBtn) { cancelBtn.click(); removed.push('popup-cancel'); }
        });

        return removed;
    }""")
    if removed:
        print(f'  제거됨: {removed}')
    await asyncio.sleep(2)

    # ── 4. 에디터 상태 진단 ──
    print('[4] 에디터 상태 진단...')
    diag = await page.evaluate("""() => {
        var info = {};

        // 이미지 버튼
        var btn = document.querySelector('button[data-name="image"]');
        if (btn) {
            var r = btn.getBoundingClientRect();
            info.imgBtn = {
                found: true, visible: r.width > 0 && r.height > 0,
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                disabled: btn.disabled,
            };
        } else {
            info.imgBtn = {found: false};
        }

        // file input 개수
        info.fileInputsBefore = document.querySelectorAll('input[type="file"]').length;

        // 팝업/오버레이 존재 여부
        var popups = document.querySelectorAll('.se-popup, [data-group="popupLayer"]');
        info.popupCount = popups.length;
        info.popupNames = [];
        popups.forEach(function(p) {
            info.popupNames.push(p.getAttribute('data-name') || p.className.substring(0, 60));
        });

        // 에디터 편집 영역
        var editArea = document.querySelector('.se-content');
        info.editAreaExists = !!editArea;

        // SmartEditor 상태
        try {
            var ed = SmartEditor._editors.blogpc001;
            info.editorReady = true;
            info.isEmpty = ed.isEmptyDocumentContent();
        } catch(e) {
            info.editorReady = false;
            info.editorError = e.message;
        }

        return info;
    }""")
    print(f'  이미지 버튼: {diag.get("imgBtn")}')
    print(f'  파일 input: {diag.get("fileInputsBefore")}개')
    print(f'  팝업: {diag.get("popupCount")}개 - {diag.get("popupNames")}')
    print(f'  에디터 준비: {diag.get("editorReady")}, 빈 상태: {diag.get("isEmpty")}')

    await page.screenshot(path=_out('img_test_before_click.png'))

    # ── 5. 이미지 버튼 클릭 ──
    print('[5] 이미지 버튼 클릭...')

    # 클릭 전에 혹시 남은 팝업이 있는지 한번 더 확인 & 제거
    await page.evaluate("""() => {
        document.querySelectorAll('.se-popup-alert, .se-popup-alert-confirm, [data-name*="alert"]').forEach(function(popup) {
            var cancelBtn = popup.querySelector('.se-popup-button-cancel, button:last-child');
            if (cancelBtn) cancelBtn.click();
        });
    }""")
    await asyncio.sleep(1)

    try:
        img_btn = page.locator('button[data-name="image"]').first
        await img_btn.click(timeout=5000)
        print('  클릭 성공')
    except Exception as click_err:
        print(f'  일반 클릭 실패: {click_err}')
        try:
            await page.locator('button[data-name="image"]').first.click(force=True)
            print('  force 클릭 완료')
        except Exception as e2:
            print(f'  force 클릭도 실패: {e2}')
            await page.screenshot(path=_out('img_test_click_fail.png'))
            await browser.close(); await pw.stop()
            return

    # 3초 대기 후 상태 확인
    await asyncio.sleep(3)

    after = await page.evaluate("""() => {
        var info = {};

        // file input 확인
        var inputs = document.querySelectorAll('input[type="file"]');
        info.fileInputCount = inputs.length;
        info.fileInputs = [];
        for (var i = 0; i < inputs.length; i++) {
            var inp = inputs[i];
            info.fileInputs.push({
                id: inp.id, name: inp.name,
                accept: inp.accept, multiple: inp.multiple,
            });
        }

        // #hidden-file 직접 확인
        var hf = document.querySelector('#hidden-file');
        info.hiddenFileFound = !!hf;

        // 새로 열린 팝업/패널 확인
        var popups = document.querySelectorAll('.se-popup:not([style*="display: none"]), .se-layer:not([style*="display: none"])');
        info.visiblePopups = popups.length;
        info.popupInfo = [];
        popups.forEach(function(p) {
            info.popupInfo.push({
                name: p.getAttribute('data-name') || '',
                cls: p.className.substring(0, 80),
                visible: p.offsetHeight > 0,
            });
        });

        // 이미지 패널 관련 요소
        var imagePanel = document.querySelector('[data-name="image-panel"], .se-image-selection');
        info.imagePanelFound = !!imagePanel;

        return info;
    }""")

    print(f'  클릭 후 file input: {after.get("fileInputCount")}개')
    for fi in after.get('fileInputs', []):
        print(f'    id={fi["id"]}, accept={fi["accept"]}, multiple={fi["multiple"]}')
    print(f'  #hidden-file 발견: {after.get("hiddenFileFound")}')
    print(f'  이미지 패널: {after.get("imagePanelFound")}')
    print(f'  열린 팝업: {after.get("visiblePopups")}개')
    for pi in after.get('popupInfo', []):
        print(f'    name={pi["name"]}, visible={pi["visible"]}, cls={pi["cls"][:60]}')

    await page.screenshot(path=_out('img_test_after_click.png'))

    # ── 6. #hidden-file 없으면 추가 진단 ──
    if not after.get('hiddenFileFound'):
        print('\n[6] #hidden-file 미발견 → 추가 진단...')

        # 이미지 버튼 다시 클릭 시도 (force)
        print('  이미지 버튼 force 재클릭...')
        await page.locator('button[data-name="image"]').first.click(force=True)
        await asyncio.sleep(3)

        hf2 = await page.evaluate("() => !!document.querySelector('#hidden-file')")
        print(f'  재클릭 후 #hidden-file: {hf2}')

        if not hf2:
            # 전체 DOM에서 file input 검색
            all_inputs = await page.evaluate("""() => {
                var all = document.querySelectorAll('input[type="file"], input[accept*="image"]');
                var results = [];
                for (var i = 0; i < all.length; i++) {
                    var el = all[i];
                    results.push({
                        id: el.id, name: el.name, accept: el.accept,
                        parent: el.parentElement ? el.parentElement.className.substring(0, 60) : 'none',
                    });
                }
                return results;
            }""")
            print(f'  전체 file input: {len(all_inputs)}개')
            for inp in all_inputs:
                print(f'    id={inp["id"]}, parent={inp["parent"]}')

            # JavaScript로 직접 이미지 버튼 이벤트 발생
            print('  JS dispatch click 시도...')
            await page.evaluate("""() => {
                var btn = document.querySelector('button[data-name="image"]');
                if (btn) {
                    btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                }
            }""")
            await asyncio.sleep(3)

            hf3 = await page.evaluate("() => !!document.querySelector('#hidden-file')")
            print(f'  JS click 후 #hidden-file: {hf3}')

            await page.screenshot(path=_out('img_test_no_hidden_file.png'))
            print('\n결론: #hidden-file 생성 안 됨. 스크린샷 확인 필요.')
            await browser.close(); await pw.stop()
            return

    # ── 7. 이미지 업로드 테스트 ──
    print('\n[7] 이미지 파일 업로드 테스트...')
    images_dir = os.path.join(PROJECT_ROOT, 'outputs', 'images')
    if not os.path.exists(images_dir):
        print(f'  이미지 폴더 없음: {images_dir}')
        await browser.close(); await pw.stop()
        return

    img_files = sorted([
        os.path.join(images_dir, f)
        for f in os.listdir(images_dir)
        if f.lower().endswith(('.png', '.jpg', '.jpeg'))
    ])[:1]  # 1장만

    if not img_files:
        print('  테스트 이미지 없음!')
        await browser.close(); await pw.stop()
        return

    img_path = img_files[0]
    img_size = os.path.getsize(img_path) / 1024
    print(f'  파일: {os.path.basename(img_path)} ({img_size:.0f}KB)')

    file_input = page.locator('#hidden-file').first
    await file_input.set_input_files(img_path)
    print('  파일 설정 완료, 업로드 대기...')

    # ── 8. CDN URL 감지 대기 ──
    print('[8] CDN URL 감지 대기...')
    for sec in range(30):
        await asyncio.sleep(1)

        img_data = await page.evaluate("""() => {
            try {
                var ed = SmartEditor._editors.blogpc001;
                var comps = ed._documentService.getDocumentData().document.components;
                var images = [];
                for (var i = 0; i < comps.length; i++) {
                    var c = comps[i];
                    if (c['@ctype'] === 'image' && c.src) {
                        if (c.src.includes('pstatic.net') || c.src.includes('blogfiles')) {
                            images.push({
                                cdn_url: c.src,
                                width: c.width || 0,
                                height: c.height || 0,
                            });
                        }
                    }
                }
                return images;
            } catch(e) { return []; }
        }""")

        if sec % 5 == 0:
            print(f'  {sec}초: CDN 이미지 {len(img_data)}개')

        if len(img_data) > 0:
            print(f'\n  ✅ 업로드 성공! ({sec+1}초)')
            for img in img_data:
                print(f'    CDN: {img["cdn_url"][:100]}...')
                print(f'    크기: {img["width"]}x{img["height"]}')
            break
    else:
        print('  ❌ 30초 타임아웃 - 업로드 실패')

    await page.screenshot(path=_out('img_test_result.png'))
    print(f'\n스크린샷: outputs/img_test_result.png')

    # ── 발행 안 함! Escape로 패널 닫기 ──
    await page.keyboard.press('Escape')
    print('\n✅ 테스트 완료 (발행 안 함)')

    await browser.close()
    await pw.stop()


if __name__ == '__main__':
    asyncio.run(test_image_only())
