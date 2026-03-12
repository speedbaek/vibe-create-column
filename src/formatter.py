"""
칼럼 포맷팅 모듈
- 마크다운 텍스트 → 블로그용 HTML 변환
- 미리보기 HTML 생성
- 소제목 가운데 정렬, 문단 간격 통일, 하이라이트, 이미지 소제목 위 배치
"""

import re
import html

# ── 간격 설정 (수정 2: 문단 간격 통일) ─────────────────
SPACER_NORMAL = 18      # 일반 문단 사이
SPACER_HEADING_ABOVE = 36   # 소제목 위
SPACER_HEADING_BELOW = 14   # 소제목 아래
SPACER_HR = 24          # 구분선 위아래
SPACER_IMAGE = 20       # 이미지 위아래

# ── 하이라이트 설정 (수정 3) ─────────────────────────
HIGHLIGHT_BG = "#FFF3CD"
HIGHLIGHT_MAX = 6  # 글 전체 최대 하이라이트 수

# 하이라이트 대상 패턴
_HIGHLIGHT_ENDINGS = re.compile(
    r'(하십시오|해야\s*합니다|하시기\s*바랍니다|하셔야|해주세요|하세요|해야만|필수입니다)[.!]?\s*$'
)
_HIGHLIGHT_KEYWORDS = re.compile(
    r'(중요|핵심|반드시|절대|꼭|필수|주의|경고|명심)'
)


def _spacer(height):
    """간격 div 생성"""
    return f'<div style="height: {height}px;"></div>'


def _should_highlight(line_text):
    """이 문장이 하이라이트 대상인지 판별"""
    plain = re.sub(r'<[^>]+>', '', line_text)
    if _HIGHLIGHT_ENDINGS.search(plain):
        return True
    if _HIGHLIGHT_KEYWORDS.search(plain):
        return True
    # 볼드 텍스트 포함 여부 (**text** 또는 <b>text</b>)
    if '**' in line_text or '<b>' in line_text or '<strong>' in line_text:
        return True
    return False


def _apply_highlight(html_text):
    """문장에 하이라이트 스팬 적용"""
    return (
        f'<span style="background-color: {HIGHLIGHT_BG}; '
        f'padding: 2px 4px; border-radius: 2px;">{html_text}</span>'
    )


def _inline_format(text):
    """인라인 마크다운 포맷팅 (bold → 빨간색, italic)"""
    safe = html.escape(text)
    # **bold** → 빨간색 볼드
    safe = re.sub(
        r"\*\*(.+?)\*\*",
        r'<b style="color: #E53935;">\1</b>',
        safe,
    )
    # *italic*
    safe = re.sub(r"\*(.+?)\*", r"<em>\1</em>", safe)
    return safe


def _md_to_html_lines(text):
    """간단한 마크다운 → HTML 변환"""
    lines = text.split("\n")
    html_lines = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        if not stripped:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<br>")
            continue

        # 헤딩
        if stripped.startswith("### "):
            html_lines.append(f"<h3>{html.escape(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            html_lines.append(f"<h2>{html.escape(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            html_lines.append(f"<h1>{html.escape(stripped[2:])}</h1>")
        # 리스트
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{html.escape(stripped[2:])}</li>")
        elif re.match(r"^\d+\.\s", stripped):
            content = re.sub(r"^\d+\.\s", "", stripped)
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{html.escape(content)}</li>")
        # 굵게/기울임
        else:
            safe = html.escape(stripped)
            safe = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)
            safe = re.sub(r"\*(.+?)\*", r"<em>\1</em>", safe)
            html_lines.append(f"<p>{safe}</p>")

    if in_list:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


def format_for_smarteditor(text, image_urls=None):
    """
    마크다운 텍스트를 SmartEditor ONE용 HTML로 변환

    수정 반영:
    - 수정 1: 소제목 가운데 정렬
    - 수정 2: 간격 통일
    - 수정 3: 하이라이트
    - 수정 7: 이미지를 소제목 위에 배치
    """
    lines = text.split("\n")
    html_parts = []
    in_list = False
    highlight_count = 0

    # ── 수정 7: 이미지 삽입 위치 계산 (소제목 위에 배치) ──
    heading_indices = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("## ") or s.startswith("### "):
            heading_indices.append(i)

    # 이미지 → 소제목 앞에 매핑 (1:1 매핑: 이미지 텍스트 = 바로 아래 소제목)
    img_before_line = {}
    if image_urls and heading_indices:
        targets = heading_indices
        for idx, img_url in enumerate(image_urls):
            if idx < len(targets):
                img_before_line[targets[idx]] = img_url

    for line_no, line in enumerate(lines):
        stripped = line.strip()

        # 소제목 앞에 이미지 삽입
        if line_no in img_before_line:
            img_url = img_before_line[line_no]
            html_parts.append(_spacer(SPACER_IMAGE))
            html_parts.append(
                f'<div style="text-align:center;margin:0 auto;width:80%;max-width:550px;">'
                f'<img src="{html.escape(str(img_url))}" '
                f'style="width:100%;border-radius:4px;display:block;">'
                f'</div>'
            )
            html_parts.append(_spacer(SPACER_IMAGE))

        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(_spacer(SPACER_NORMAL))
            continue

        # 구분선
        if stripped == "---":
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(_spacer(SPACER_HR))
            html_parts.append('<hr style="border:none;border-top:1px solid #e0e0e0;">')
            html_parts.append(_spacer(SPACER_HR))
            continue

        # ## 소제목 → 가운데 정렬 (수정 1)
        if stripped.startswith("## "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            heading = stripped[3:]
            html_parts.append(_spacer(SPACER_HEADING_ABOVE))
            html_parts.append(
                f'<p style="font-family: \'나눔고딕\', \'Nanum Gothic\', sans-serif; '
                f'font-size: 20px; line-height: 1.8; color: #222222; font-weight: bold; '
                f'margin: 0; padding: 0; text-align: center">'
                f'<b>{html.escape(heading)}</b></p>'
            )
            html_parts.append(_spacer(SPACER_HEADING_BELOW))
            continue

        # ### 소소제목 → 가운데 정렬
        if stripped.startswith("### "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            heading = stripped[4:]
            html_parts.append(_spacer(SPACER_HEADING_ABOVE))
            html_parts.append(
                f'<p style="font-family: \'나눔고딕\', \'Nanum Gothic\', sans-serif; '
                f'font-size: 17px; line-height: 1.8; color: #333333; font-weight: bold; '
                f'margin: 0; padding: 0; text-align: center">'
                f'<b>{html.escape(heading)}</b></p>'
            )
            html_parts.append(_spacer(SPACER_HEADING_BELOW))
            continue

        # # 대제목
        if stripped.startswith("# "):
            heading = stripped[2:]
            html_parts.append(
                f'<p style="font-size: 22px; font-weight: bold; color: #222222; '
                f'margin: 0; padding: 0; text-align: center">'
                f'<b>{html.escape(heading)}</b></p>'
            )
            html_parts.append(_spacer(SPACER_HEADING_BELOW))
            continue

        # 리스트
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_parts.append("<ul style='padding-left:20px;'>")
                in_list = True
            item_text = _inline_format(stripped[2:])
            html_parts.append(f"<li>{item_text}</li>")
            continue

        if re.match(r"^\d+\.\s", stripped):
            content_text = re.sub(r"^\d+\.\s", "", stripped)
            if not in_list:
                html_parts.append("<ul style='padding-left:20px;'>")
                in_list = True
            html_parts.append(f"<li>{_inline_format(content_text)}</li>")
            continue

        # URL 단독 줄 → 링크 카드 (수정 6-2)
        if stripped.startswith("http://") or stripped.startswith("https://"):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            domain = ""
            if "://" in stripped:
                domain = stripped.split("://")[1].split("/")[0]
            html_parts.append(_spacer(SPACER_NORMAL))
            html_parts.append(
                f'<div style="margin: 0; padding: 16px; border: 1px solid #e0e0e0; '
                f'border-radius: 8px; background: #f9f9f9;">'
                f'<a href="{html.escape(stripped)}" target="_blank" '
                f'style="color: #0068b7; text-decoration: none; font-weight: bold; font-size: 15px;">'
                f'{html.escape(stripped[:60])}</a>'
                f'<p style="color: #666; font-size: 13px; margin-top: 4px; margin-bottom: 0;">{html.escape(domain)}</p>'
                f'</div>'
            )
            html_parts.append(_spacer(SPACER_NORMAL))
            continue

        # 일반 텍스트 → 하이라이트 판별 (수정 3)
        if in_list:
            html_parts.append("</ul>")
            in_list = False

        formatted = _inline_format(stripped)

        if highlight_count < HIGHLIGHT_MAX and _should_highlight(stripped):
            formatted = _apply_highlight(formatted)
            highlight_count += 1

        html_parts.append(
            f'<p style="font-family: \'나눔고딕\', \'Nanum Gothic\', sans-serif; '
            f'font-size: 16px; line-height: 1.8; color: #333333; margin: 0; padding: 0">'
            f'{formatted}</p>'
        )

    if in_list:
        html_parts.append("</ul>")

    # 남은 이미지 맨 끝에 삽입
    if image_urls:
        used_count = len(img_before_line)
        for extra_idx in range(used_count, len(image_urls)):
            img_url = image_urls[extra_idx]
            html_parts.append(_spacer(SPACER_IMAGE))
            html_parts.append(
                f'<div style="text-align:center;margin:0 auto;width:80%;max-width:550px;">'
                f'<img src="{html.escape(str(img_url))}" '
                f'style="width:100%;border-radius:4px;display:block;">'
                f'</div>'
            )

    return "\n".join(html_parts)


def format_column_html(text, persona_id, include_images=False, image_data=None):
    """
    마크다운 텍스트를 블로그용 HTML로 변환
    """
    image_urls = None
    if include_images and image_data:
        body_images = image_data.get("body_images", [])
        image_urls = [img.get("url", "") for img in body_images if img.get("url")]

    return format_for_smarteditor(text, image_urls=image_urls)


def format_column_preview(text, persona_id, image_data=None):
    """
    미리보기용 HTML 생성 (스타일 포함)
    """
    content_html = format_column_html(
        text, persona_id,
        include_images=bool(image_data),
        image_data=image_data,
    )

    # 제목 추출
    title = ""
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped.lstrip("#").strip()
            break
        elif stripped:
            title = stripped[:50]
            break

    thumbnail_html = ""
    if image_data and image_data.get("thumbnail"):
        thumb = image_data["thumbnail"]
        thumb_url = thumb.get("url", "")
        if thumb_url:
            thumbnail_html = (
                f'<div style="text-align:center;margin-bottom:20px;">'
                f'<img src="{html.escape(thumb_url)}" style="max-width:100%;border-radius:8px;">'
                f'</div>'
            )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: 'Noto Sans KR', sans-serif; max-width: 700px; margin: 0 auto;
       padding: 20px; line-height: 1.8; color: #333; }}
h1 {{ font-size: 22px; margin-bottom: 10px; text-align: center; }}
h2 {{ font-size: 20px; color: #222; margin-top: 30px; text-align: center; }}
h3 {{ font-size: 17px; margin-top: 25px; text-align: center; }}
p {{ margin: 8px 0; }}
ul {{ padding-left: 20px; }}
li {{ margin: 4px 0; }}
</style></head><body>
{thumbnail_html}
<h1>{html.escape(title)}</h1>
<hr>
{content_html}
</body></html>"""
