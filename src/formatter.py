"""
네이버 블로그 HTML 포맷터 v1
- 생성된 텍스트 칼럼을 네이버 블로그 Smart Editor HTML로 변환
- 모바일 최적화 (70%+ 모바일 사용자 대응)
- 폰트, 색상, 구분선, 이미지 영역, CTA 링크 처리
"""

import re
import os
import json

# ── 디자인 설정 ──────────────────────────────────────────

FONT_CONFIG = {
    "family": "'나눔고딕', 'Nanum Gothic', 'Malgun Gothic', '맑은 고딕', sans-serif",
    "body_size": "16px",        # 모바일 가독성 기본
    "heading_size": "20px",     # 소제목
    "small_size": "14px",       # 부가정보
    "line_height": "1.8",       # 넓은 줄간격
    "color": "#333333",         # 본문 색상
    "heading_color": "#222222", # 소제목 색상
    "accent_color": "#1a73e8",  # 강조 색상 (파란색)
    "cta_color": "#0068b7",     # CTA 링크 색상
}

# 네이버 블로그 Smart Editor 3.0 호환 클래스 접두사
SE_PREFIX = "se-"

PERSONAS_DIR = "config/personas"


def _load_cta_config(persona_id):
    """페르소나별 CTA 설정 로드"""
    json_path = os.path.join(PERSONAS_DIR, f"{persona_id}.json")
    if not os.path.exists(json_path):
        return {}
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("cta_config", {})
    except (json.JSONDecodeError, IOError):
        return {}


def _wrap_paragraph(text, bold=False, color=None, size=None, align="left"):
    """단일 문단을 HTML <p> 태그로 감싸기"""
    style_parts = [
        f"font-family: {FONT_CONFIG['family']}",
        f"font-size: {size or FONT_CONFIG['body_size']}",
        f"line-height: {FONT_CONFIG['line_height']}",
        f"color: {color or FONT_CONFIG['color']}",
        f"text-align: {align}",
        "margin: 0",
        "padding: 0",
        "word-break: keep-all",  # 한국어 단어 단위 줄바꿈
    ]
    style = "; ".join(style_parts)

    content = text
    if bold:
        content = f"<b>{content}</b>"

    return f'<p style="{style}">{content}</p>'


def _make_heading(text):
    """소제목 HTML 생성"""
    # **텍스트** 형태의 마크다운 볼드를 제거하고 순수 텍스트 추출
    clean_text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)

    style_parts = [
        f"font-family: {FONT_CONFIG['family']}",
        f"font-size: {FONT_CONFIG['heading_size']}",
        f"line-height: {FONT_CONFIG['line_height']}",
        f"color: {FONT_CONFIG['heading_color']}",
        "font-weight: bold",
        "margin: 0",
        "padding: 0",
    ]
    style = "; ".join(style_parts)
    return f'<p style="{style}"><b>{clean_text}</b></p>'


def _make_divider():
    """구분선 HTML (네이버 블로그 스타일)"""
    return (
        '<div style="width: 100%; margin: 20px 0; text-align: center;">'
        '<hr style="border: none; border-top: 1px solid #e0e0e0; margin: 0 auto; width: 80%;">'
        '</div>'
    )


def _make_spacer(height=20):
    """빈 줄 스페이서"""
    return f'<div style="height: {height}px;"></div>'


def _make_cta_link(text, url, style="normal"):
    """CTA 링크 HTML 생성"""
    if style == "button":
        btn_style = (
            f"display: inline-block; padding: 12px 24px; "
            f"background-color: {FONT_CONFIG['cta_color']}; color: #ffffff; "
            f"font-family: {FONT_CONFIG['family']}; font-size: 15px; "
            f"text-decoration: none; border-radius: 6px; font-weight: bold;"
        )
        return f'<p style="text-align: center; margin: 10px 0;"><a href="{url}" style="{btn_style}">{text}</a></p>'
    else:
        link_style = (
            f"color: {FONT_CONFIG['cta_color']}; text-decoration: underline; "
            f"font-weight: bold;"
        )
        return f'<a href="{url}" style="{link_style}">{text}</a>'


def _make_real_image(image_path, alt="", max_width=None):
    """실제 이미지를 base64 인라인 HTML로 삽입"""
    try:
        from src.image_handler import image_to_base64
        import json as _json

        data_uri = image_to_base64(image_path)
        if not data_uri:
            return ""

        # 이미지 스타일 설정 로드
        try:
            with open("config/image_styles.json", "r", encoding="utf-8") as f:
                config = _json.load(f)
            size_cfg = config.get("body_images", {}).get("size", {})
            display_width = max_width or size_cfg.get("display_width", "60%")
            display_max_w = size_cfg.get("display_max_width", "360px")
        except Exception:
            display_width = max_width or "60%"
            display_max_w = "360px"

        if max_width == "100%":
            # 썸네일용 풀폭
            style = (
                "display: block; margin: 0 auto; "
                "width: 100%; max-width: 680px; height: auto;"
            )
        else:
            # 본문 이미지 (소형)
            style = (
                f"display: block; margin: 8px auto; "
                f"width: {display_width}; max-width: {display_max_w}; "
                f"height: auto; border-radius: 4px;"
            )

        return f'<div style="text-align: center; margin: 8px 0;"><img src="{data_uri}" alt="{alt}" style="{style}"></div>'

    except Exception as e:
        return f'<!-- 이미지 로드 실패: {e} -->'


def _make_image_placeholder(alt_text="", caption=""):
    """이미지 삽입 위치 마커 (나중에 실제 이미지로 교체)"""
    placeholder_style = (
        "width: 100%; max-width: 600px; margin: 15px auto; "
        "padding: 40px 20px; background-color: #f5f5f5; "
        "border: 2px dashed #cccccc; text-align: center; "
        f"font-family: {FONT_CONFIG['family']}; color: #999999; "
        "font-size: 14px; box-sizing: border-box;"
    )
    html = f'<div style="{placeholder_style}">[이미지 삽입 위치: {alt_text}]</div>'
    if caption:
        caption_style = (
            f"text-align: center; font-family: {FONT_CONFIG['family']}; "
            f"font-size: {FONT_CONFIG['small_size']}; color: #888888; "
            "margin: 5px 0 15px 0;"
        )
        html += f'<p style="{caption_style}">{caption}</p>'
    return html


def _process_inline_formatting(text):
    """인라인 마크다운 → HTML 변환"""
    # **볼드** → <b>볼드</b>
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    # *이탤릭* → <i>이탤릭</i>
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    # [텍스트](URL) → <a>링크</a>
    def replace_link(m):
        link_text = m.group(1)
        url = m.group(2)
        link_style = f"color: {FONT_CONFIG['cta_color']}; text-decoration: underline;"
        return f'<a href="{url}" style="{link_style}">{link_text}</a>'
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', replace_link, text)
    return text


def _detect_cta_markers(text, cta_config):
    """텍스트에서 CTA 마커를 감지하고 링크로 변환"""
    notice_url = cta_config.get("notice_post_url", "")
    philosophy_url = cta_config.get("philosophy_post_url", "")

    # [공지글 제목] 패턴이나 **→ [제목]** 패턴을 CTA 링크로 변환
    # 공지 접수 관련
    if notice_url:
        patterns = [
            r'\*?\*?→?\s*\[컨설팅 접수 방법[^\]]*\]\*?\*?',
            r'\*?\*?\[?컨설팅 접수 방법[^\]]*\]?\*?\*?',
            r'상담\s*신청\s*방법.*?안내',
        ]
        for pattern in patterns:
            if re.search(pattern, text):
                link_html = _make_cta_link(
                    "▶ 컨설팅 접수 방법 (비용없는 1차상담 신청)",
                    notice_url,
                    style="normal"
                )
                text = re.sub(pattern, link_html, text, count=1)
                break

    # 철학글 관련
    if philosophy_url:
        patterns = [
            r'\*?\*?→?\s*\[포기도,?\s*실패도 없다[^\]]*\]\*?\*?',
            r'\*?\*?\[?포기도,?\s*실패도 없다[^\]]*\]?\*?\*?',
            r'변리사\s*윤웅채\s*철학',
        ]
        for pattern in patterns:
            if re.search(pattern, text):
                link_html = _make_cta_link(
                    "▶ 포기도, 실패도 없다. 변리사 윤웅채 철학",
                    philosophy_url,
                    style="normal"
                )
                text = re.sub(pattern, link_html, text, count=1)
                break

    return text


def format_column_html(raw_text, persona_id="yun_ung_chae", include_images=False,
                       image_data=None):
    """
    생성된 텍스트 칼럼을 네이버 블로그 HTML로 변환

    Args:
        raw_text: 엔진에서 생성된 텍스트
        persona_id: 페르소나 ID (CTA 설정 로드용)
        include_images: 이미지 삽입 여부
        image_data: generate_blog_images() 반환값 (dict)
            - thumbnail: str (썸네일 경로)
            - body_images: list (본문 이미지 경로 리스트)
            - image_positions: list (삽입 위치)

    Returns:
        str: 네이버 블로그에 붙여넣을 수 있는 HTML
    """
    cta_config = _load_cta_config(persona_id)
    html_parts = []

    # 이미지 데이터 준비
    body_images = []
    image_positions = []
    thumbnail_path = None

    if image_data and include_images:
        body_images = image_data.get("body_images", [])
        image_positions = image_data.get("image_positions", [])
        thumbnail_path = image_data.get("thumbnail")

    # 전체 컨테이너 시작
    container_style = (
        "max-width: 100%; margin: 0 auto; padding: 0; "
        f"font-family: {FONT_CONFIG['family']}; "
        f"font-size: {FONT_CONFIG['body_size']}; "
        f"color: {FONT_CONFIG['color']}; "
        f"line-height: {FONT_CONFIG['line_height']};"
    )
    html_parts.append(f'<div style="{container_style}">')

    # 썸네일 삽입 (맨 위)
    if thumbnail_path and include_images:
        thumb_html = _make_real_image(thumbnail_path, alt="썸네일", max_width="100%")
        if thumb_html:
            html_parts.append(thumb_html)
            html_parts.append(_make_spacer(20))

    # 텍스트를 줄 단위로 분리
    lines = raw_text.strip().split('\n')

    # 문단 카운터 & 이미지 배치 추적
    paragraph_count = 0
    image_idx = 0  # 다음 삽입할 이미지 인덱스

    for line in lines:
        stripped = line.strip()

        # 빈 줄 → 스페이서
        if not stripped:
            html_parts.append(_make_spacer(15))
            continue

        # 구분선 (---)
        if stripped == '---':
            html_parts.append(_make_divider())
            continue

        # CTA 마커 감지 및 변환
        stripped = _detect_cta_markers(stripped, cta_config)

        # 소제목 감지 (**굵은 텍스트**로 시작하는 줄)
        if re.match(r'^\*\*(.+)\*\*$', stripped):
            html_parts.append(_make_spacer(10))
            html_parts.append(_make_heading(stripped))
            html_parts.append(_make_spacer(8))
            continue

        # 일반 문단
        processed = _process_inline_formatting(stripped)
        html_parts.append(_wrap_paragraph(processed))
        paragraph_count += 1

        # 이미지 삽입 체크 (위치 기반)
        if include_images and image_idx < len(body_images):
            should_insert = False
            if image_positions and image_idx < len(image_positions):
                if paragraph_count >= image_positions[image_idx]:
                    should_insert = True
            elif not image_positions:
                # 위치 정보 없으면 균등 배치
                total_paras = sum(1 for l in lines if l.strip() and l.strip() != '---')
                interval = max(3, total_paras // (len(body_images) + 1))
                if paragraph_count % interval == 0 and paragraph_count >= 3:
                    should_insert = True

            if should_insert:
                img_path = body_images[image_idx]
                img_html = _make_real_image(img_path, alt=f"본문 이미지 {image_idx+1}")
                if img_html:
                    html_parts.append(_make_spacer(8))
                    html_parts.append(img_html)
                    html_parts.append(_make_spacer(8))
                image_idx += 1

    # 전체 컨테이너 닫기
    html_parts.append('</div>')

    return '\n'.join(html_parts)


def format_column_preview(raw_text, persona_id="yun_ung_chae", image_data=None):
    """
    미리보기용 전체 HTML 페이지 생성 (브라우저에서 직접 열 수 있음)

    Args:
        raw_text: 생성된 텍스트
        persona_id: 페르소나 ID
        image_data: generate_blog_images() 반환값 (선택)

    Returns:
        str: 완전한 HTML 문서
    """
    include_images = image_data is not None
    blog_html = format_column_html(raw_text, persona_id,
                                    include_images=include_images,
                                    image_data=image_data)

    preview_html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>블로그 미리보기</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            max-width: 680px;
            margin: 0 auto;
            padding: 20px 16px;
            background-color: #ffffff;
            -webkit-text-size-adjust: 100%;
        }}
        /* 모바일 미리보기 프레임 */
        .mobile-frame {{
            max-width: 400px;
            margin: 20px auto;
            border: 2px solid #e0e0e0;
            border-radius: 20px;
            padding: 40px 16px 20px;
            background: #fff;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            position: relative;
        }}
        .mobile-frame::before {{
            content: "모바일 미리보기";
            position: absolute;
            top: 12px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 11px;
            color: #999;
            font-family: 'Nanum Gothic', sans-serif;
        }}
        /* PC 미리보기 */
        .pc-frame {{
            max-width: 680px;
            margin: 20px auto;
            padding: 30px 24px;
            background: #fff;
            border: 1px solid #e0e0e0;
        }}
        .tab-container {{
            text-align: center;
            margin: 10px 0 20px;
        }}
        .tab-btn {{
            display: inline-block;
            padding: 8px 20px;
            margin: 0 4px;
            border: 1px solid #ddd;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            font-family: 'Nanum Gothic', sans-serif;
            background: #f9f9f9;
        }}
        .tab-btn.active {{
            background: #0068b7;
            color: #fff;
            border-color: #0068b7;
        }}
    </style>
</head>
<body>
    <div class="tab-container">
        <span class="tab-btn active" onclick="showMobile()">📱 모바일</span>
        <span class="tab-btn" onclick="showPC()">🖥️ PC</span>
    </div>

    <div id="mobile-view" class="mobile-frame">
        {blog_html}
    </div>

    <div id="pc-view" class="pc-frame" style="display: none;">
        {blog_html}
    </div>

    <script>
        function showMobile() {{
            document.getElementById('mobile-view').style.display = 'block';
            document.getElementById('pc-view').style.display = 'none';
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-btn')[0].classList.add('active');
        }}
        function showPC() {{
            document.getElementById('mobile-view').style.display = 'none';
            document.getElementById('pc-view').style.display = 'block';
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-btn')[1].classList.add('active');
        }}
    </script>
</body>
</html>"""

    return preview_html


if __name__ == "__main__":
    # 테스트
    sample = """안녕하세요
특허법인 테헤란 대표 변리사 윤웅채입니다.

오늘은 스타트업 대표님들에게 꼭 드리고 싶은 이야기가 있습니다.

---

**상표등록, 왜 미루면 안 되나요?**

솔직히 말씀드리면, 초기 창업자분들 입장에서는 당장 급한 일이 많으시죠.

그런데 19년간 이 일을 하면서 제가 가장 많이 본 안타까운 케이스가 바로 이겁니다.

"나중에 해야지" 하다가, 나중이 너무 늦어버린 경우.

---

**→ [포기도, 실패도 없다. 변리사 윤웅채 철학]**

읽어보시고 공감이 가시면 연락 주세요.

**→ [컨설팅 접수 방법 (비용없는 1차상담 신청)]**

여러분의 고민 해결, 노력해 보겠습니다.
"""

    html = format_column_html(sample)
    print("=== HTML 출력 ===")
    print(html[:500])
    print("...")
    print(f"\n총 HTML 길이: {len(html)}자")

    # 미리보기 저장
    preview = format_column_preview(sample)
    with open("outputs/preview_test.html", "w", encoding="utf-8") as f:
        f.write(preview)
    print("\n미리보기 파일 저장: outputs/preview_test.html")
