"""
네이버 블로그 이미지 업로드 모듈 (Sync 버전)
- Playwright sync API 전용
- SmartEditor 이미지 버튼 + #hidden-file input 활용
- 1장씩 순차 업로드 → CDN URL 추출
"""

import os
import time


def _log(msg):
    print(f'[UPLOAD] {msg}')


def upload_images_to_naver(page, blog_id, local_image_paths):
    """
    로컬 이미지 파일들을 네이버 블로그 CDN에 업로드 (sync)

    Args:
        page: Playwright sync page
        blog_id: 네이버 블로그 ID (호환성 유지)
        local_image_paths: 로컬 이미지 파일 경로 리스트

    Returns:
        list[dict | None]: 네이티브 이미지 컴포넌트 dict 또는 None
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
            _log(f"  유효 파일 [{idx}]: {os.path.basename(p)} ({os.path.getsize(p)} bytes)")
        else:
            _log(f"  파일 없음: {p}")

    if not valid_paths:
        _log("업로드할 유효한 이미지 파일 없음")
        return [None] * len(local_image_paths)

    _log(f"이미지 {len(valid_paths)}장 업로드 시작 (1장씩 순차)...")

    cdn_data = []
    for file_idx, file_path in enumerate(valid_paths):
        _log(f"[{file_idx+1}/{len(valid_paths)}] 업로드: {os.path.basename(file_path)}")

        # 팝업 제거
        _clear_popups(page)
        time.sleep(1)

        # 현재 이미지 수 기록 (업로드 전)
        before_count = _count_images(page)
        _log(f"  업로드 전 이미지 수: {before_count}")

        # 이미지 버튼 클릭
        try:
            img_btn = page.locator('button[data-name="image"]').first
            try:
                img_btn.click(timeout=5000)
            except Exception:
                img_btn.click(force=True)
        except Exception as e:
            _log(f"  이미지 버튼 실패: {e}")
            cdn_data.append(None)
            continue

        time.sleep(3)

        # #hidden-file 확인
        hf = page.evaluate("() => !!document.querySelector('#hidden-file')")
        if not hf:
            _log("  #hidden-file 미발견 -> 재시도")
            page.keyboard.press('Escape')
            time.sleep(1)
            try:
                img_btn = page.locator('button[data-name="image"]').first
                img_btn.click(force=True)
                time.sleep(3)
                hf = page.evaluate("() => !!document.querySelector('#hidden-file')")
            except Exception:
                pass

            if not hf:
                _log("  #hidden-file 여전히 없음 -> 건너뜀")
                cdn_data.append(None)
                page.keyboard.press('Escape')
                time.sleep(1)
                continue

        # 단일 파일 설정
        file_input = page.locator('#hidden-file').first
        file_input.set_input_files(file_path)
        _log("  파일 설정 완료, CDN 업로드 대기...")

        # CDN URL 감지 대기 (최대 30초)
        found_new = None
        for sec in range(30):
            time.sleep(1)
            current_count = _count_images(page)

            if current_count > before_count:
                found_new = _get_last_image_component(page)
                if found_new:
                    _log(f"  CDN 감지! ({sec+1}초) src={found_new.get('src', '')[:80]}...")
                    break

            if sec % 5 == 0 and sec > 0:
                _log(f"  대기 중... ({sec}초, 이미지: {current_count})")

        if found_new:
            cdn_data.append(found_new)
        else:
            _log("  타임아웃 - 이 파일 업로드 실패")
            cdn_data.append(None)

        # 패널 닫기
        page.keyboard.press('Escape')
        time.sleep(1)

    # 결과 매핑 (원본 인덱스 기준)
    results = [None] * len(local_image_paths)
    for i, cdn_item in enumerate(cdn_data):
        if i < len(valid_indices):
            results[valid_indices[i]] = cdn_item

    success_count = sum(1 for r in results if r)
    _log(f"업로드 완료: {success_count}/{len(local_image_paths)}장 성공")

    return results


def _count_images(page):
    """현재 에디터에 있는 CDN 이미지 수"""
    return page.evaluate("""() => {
        try {
            var ed = SmartEditor._editors.blogpc001;
            var comps = ed._documentService.getDocumentData().document.components;
            var count = 0;
            for (var i = 0; i < comps.length; i++) {
                var c = comps[i];
                if (c['@ctype'] === 'image' && c.src &&
                    (c.src.includes('pstatic.net') || c.src.includes('blogfiles'))) {
                    count++;
                }
            }
            return count;
        } catch(e) { return 0; }
    }""")


def _get_last_image_component(page):
    """에디터의 마지막 이미지 컴포넌트 전체 dict 반환"""
    return page.evaluate("""() => {
        try {
            var ed = SmartEditor._editors.blogpc001;
            var comps = ed._documentService.getDocumentData().document.components;
            var lastImg = null;
            for (var i = 0; i < comps.length; i++) {
                var c = comps[i];
                if (c['@ctype'] === 'image' && c.src &&
                    (c.src.includes('pstatic.net') || c.src.includes('blogfiles'))) {
                    lastImg = c;
                }
            }
            return lastImg;
        } catch(e) { return null; }
    }""")


def _clear_popups(page):
    """팝업 제거 (sync)"""
    removed = page.evaluate("""() => {
        var removed = [];
        var helpClose = document.querySelector('.se-help-close');
        if (helpClose) { helpClose.click(); removed.push('help-close'); }
        document.querySelectorAll('[class*="se-help"]').forEach(function(el) {
            el.remove(); removed.push('help-el');
        });
        document.querySelectorAll('.se-popup-alert, .se-popup-alert-confirm').forEach(function(popup) {
            var cancelBtn = popup.querySelector('.se-popup-button-cancel');
            if (cancelBtn) { cancelBtn.click(); removed.push('popup-cancel'); }
        });
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
