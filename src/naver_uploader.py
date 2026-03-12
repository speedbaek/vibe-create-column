"""
네이버 블로그 이미지 업로드 모듈
- SmartEditor의 이미지 버튼 + #hidden-file input 활용
- SmartEditor 내부 업로드 흐름 사용 (인증 자동 처리)
- SmartEditor documentData에서 CDN URL 추출

업로드 흐름:
1. 팝업/오버레이 제거
2. 이미지 버튼 클릭 → #hidden-file input 생성
3. set_input_files() → SmartEditor 자동 업로드 (session-key + simpleUpload)
4. SmartEditor getDocumentData()에서 이미지 컴포넌트 CDN URL 추출
5. CDN URL: https://blogfiles.pstatic.net/...
"""

import os
import asyncio


def _log(msg):
    """print 기반 로깅 (Windows 콘솔 인코딩 호환)"""
    print(f'[UPLOAD] {msg}')


async def upload_images_to_naver(page, blog_id, local_image_paths):
    """
    로컬 이미지 파일들을 네이버 블로그 CDN에 업로드

    Args:
        page: Playwright page (에디터 페이지에서 실행해야 함)
        blog_id: 네이버 블로그 ID (호환성 유지, 미사용)
        local_image_paths: 로컬 이미지 파일 경로 리스트

    Returns:
        list[dict | None]: 업로드 결과 리스트
            성공: {'cdn_url': str, 'width': int, 'height': int}
            실패: None
    """
    if not local_image_paths:
        return []

    # 유효한 파일만 필터
    valid_paths = []
    valid_indices = []
    for idx, p in enumerate(local_image_paths):
        if p and os.path.exists(p):
            valid_paths.append(os.path.abspath(p))
            valid_indices.append(idx)
        else:
            _log(f"  파일 없음: {p}")

    if not valid_paths:
        _log("업로드할 유효한 이미지 파일 없음")
        return [None] * len(local_image_paths)

    _log(f"이미지 {len(valid_paths)}장 업로드 시작 (1장씩 순차 업로드)...")

    # 네트워크 모니터링
    upload_responses = []

    async def _on_response(response):
        url = response.url
        if 'upphoto' in url or 'session-key' in url or 'simpleUpload' in url:
            try:
                body = await response.text()
                upload_responses.append({
                    'url': url[:150], 'status': response.status,
                    'body': body[:300],
                })
            except Exception:
                upload_responses.append({'url': url[:150], 'status': response.status})

    page.on('response', _on_response)

    cdn_data = []
    for file_idx, file_path in enumerate(valid_paths):
        _log(f"[{file_idx+1}/{len(valid_paths)}] 업로드: {os.path.basename(file_path)}")

        # 팝업 제거
        await _clear_popups(page)
        await asyncio.sleep(1)

        # 이미지 버튼 클릭
        try:
            img_btn = page.locator('button[data-name="image"]').first
            try:
                await img_btn.click(timeout=5000)
            except Exception:
                await img_btn.click(force=True)
        except Exception as e:
            _log(f"  이미지 버튼 실패: {e}")
            cdn_data.append(None)
            continue

        await asyncio.sleep(3)

        # #hidden-file 확인
        hf = await page.evaluate("() => !!document.querySelector('#hidden-file')")
        if not hf:
            _log("  #hidden-file 미발견")
            cdn_data.append(None)
            await page.keyboard.press('Escape')
            await asyncio.sleep(1)
            continue

        # 단일 파일 설정
        file_input = page.locator('#hidden-file').first
        await file_input.set_input_files(file_path)
        _log("  파일 설정 완료, CDN 대기...")

        # CDN URL 대기 (기존 이미지 제외)
        existing_count = len(cdn_data)  # 이미 업로드된 수
        found_new = None
        for sec in range(30):
            await asyncio.sleep(1)
            img_comps = await page.evaluate("""() => {
                try {
                    var ed = SmartEditor._editors.blogpc001;
                    var comps = ed._documentService.getDocumentData().document.components;
                    var images = [];
                    for (var i = 0; i < comps.length; i++) {
                        var c = comps[i];
                        if (c['@ctype'] === 'image' && c.src &&
                            (c.src.includes('pstatic.net') || c.src.includes('blogfiles'))) {
                            images.push(c);
                        }
                    }
                    return images;
                } catch(e) { return []; }
            }""")

            # 새로 추가된 이미지가 있으면 성공
            if len(img_comps) > existing_count:
                found_new = img_comps[-1]  # 마지막 추가된 네이티브 컴포넌트
                _log(f"  CDN 감지! ({sec+1}초) {found_new.get('src', '')[:80]}...")
                break

            if sec % 5 == 0:
                _log(f"  대기 중... ({sec}초, 이미지: {len(img_comps)})")

        if found_new:
            cdn_data.append(found_new)
        else:
            _log("  타임아웃 - 이 파일 업로드 실패")
            cdn_data.append(None)

        # 패널 닫기
        await page.keyboard.press('Escape')
        await asyncio.sleep(1)

    # 네트워크 응답 로그
    page.remove_listener('response', _on_response)
    if upload_responses:
        _log(f"업로드 네트워크 응답: {len(upload_responses)}개")
        for r in upload_responses:
            _log(f"  [{r['status']}] {r['url']}")
    else:
        _log("업로드 네트워크 응답: 없음")

    # 결과 매핑 (원본 인덱스 기준)
    results = [None] * len(local_image_paths)
    for i, cdn_item in enumerate(cdn_data):
        if i < len(valid_indices):
            results[valid_indices[i]] = cdn_item

    success_count = sum(1 for r in results if r)
    _log(f"업로드 완료: {success_count}/{len(local_image_paths)}장 성공")

    # 패널 닫기
    try:
        await page.keyboard.press('Escape')
        await asyncio.sleep(0.5)
    except Exception:
        pass

    return results


async def _clear_popups(page):
    """SmartEditor 도움말/복구 팝업만 선택적 제거 (에디터 자체 레이어 보존)"""
    removed = await page.evaluate("""() => {
        var removed = [];

        // 1. 도움말 닫기
        var helpClose = document.querySelector('.se-help-close');
        if (helpClose) { helpClose.click(); removed.push('help-close'); }

        // 2. 도움말 요소만 제거
        document.querySelectorAll('[class*="se-help"]').forEach(function(el) {
            el.remove();
            removed.push('help-el');
        });

        // 3. 복구 팝업 → 취소
        document.querySelectorAll('.se-popup-alert, .se-popup-alert-confirm').forEach(function(popup) {
            var cancelBtn = popup.querySelector('.se-popup-button-cancel');
            if (cancelBtn) { cancelBtn.click(); removed.push('popup-cancel'); }
        });

        // 4. 모든 visible 팝업 레이어에서 취소/닫기 버튼 클릭
        document.querySelectorAll('[data-group="popupLayer"]').forEach(function(popup) {
            if (popup.offsetHeight > 0) {
                var cancelBtn = popup.querySelector('.se-popup-button-cancel, button[class*="cancel"]');
                if (cancelBtn) { cancelBtn.click(); removed.push('popupLayer-cancel'); }
            }
        });

        return removed;
    }""")
    if removed:
        _log(f"  팝업 제거: {removed}")


async def _wait_for_uploaded_images(page, expected_count, max_wait=60):
    """SmartEditor documentData에서 업로드된 이미지 컴포넌트를 감지"""
    for elapsed in range(max_wait):
        await asyncio.sleep(1)

        img_data = await page.evaluate("""() => {
            try {
                var ed = SmartEditor._editors.blogpc001;
                var docData = ed._documentService.getDocumentData();
                var comps = docData.document.components;
                var images = [];
                for (var i = 0; i < comps.length; i++) {
                    var c = comps[i];
                    if (c['@ctype'] === 'image' && c.src) {
                        var src = c.src;
                        if (src.includes('pstatic.net') || src.includes('blogfiles')) {
                            images.push({
                                cdn_url: src,
                                width: c.width || 0,
                                height: c.height || 0,
                            });
                        }
                    }
                }
                return images;
            } catch(e) {
                return [];
            }
        }""")

        current_count = len(img_data)

        if elapsed % 5 == 0:
            _log(f"  {current_count}/{expected_count} ({elapsed}s)")

        if current_count >= expected_count:
            _log(f"  CDN 이미지 {current_count}개 감지 완료 ({elapsed+1}s)")
            return img_data

    _log(f"  타임아웃!")
    return await page.evaluate("""() => {
        try {
            var ed = SmartEditor._editors.blogpc001;
            var comps = ed._documentService.getDocumentData().document.components;
            return comps.filter(function(c) {
                return c['@ctype'] === 'image' && c.src && c.src.includes('pstatic.net');
            }).map(function(c) {
                return {cdn_url: c.src, width: c.width || 0, height: c.height || 0};
            });
        } catch(e) { return []; }
    }""")
