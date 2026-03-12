"""
칼럼 포맷팅 모듈
- 마크다운 텍스트 → 블로그용 HTML 변환
- 네이버 블로그 SmartEditor ONE 호환
- 미리보기 HTML 생성
"""

import re
import html as html_mod


def _inline_format(text):
    """인라인 마크다운 변환 (bold, italic, 링크)

    html.escape를 먼저 적용하되, 마크다운 기호(*, **, [])는 보존
    """
    # **bold** → <b>bold</b>
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # *italic* → <i>italic</i>
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    # [text](url) → <a href="url">text</a>
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" target="_blank">\1</a>',
        text,
    )
    return text


def _md_to_html_lines(text):
    """마크다운 → HTML 변환 (네이버 블로그 최적화)"""
    lines = text.split("\n")
    html_lines = []
    in_ul = False
    in_ol = False

    for line in lines:
        stripped = line.strip()

        if not stripped:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            if in_ol:
                html_lines.append("</ol>")
                in_ol = False
            html_lines.append("<p>&nbsp;</p>")
            continue

        # 리스트 종료 체크 (리스트 아이템이 아닌 줄이 오면)
        if not (stripped.startswith("- ") or stripped.startswith("* ") or
                re.match(r"^\d+\.\s", stripped)):
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            if in_ol:
                html_lines.append("</ol>")
                in_ol = False

        # 헤딩 (네이버 블로그 스타일)
        if stripped.startswith("### "):
            content = _inline_format(stripped[4:])
            html_lines.append(
                f'<h3 style="font-size:16px;color:#333;margin:25px 0 10px 0;'
                f'font-weight:bold;">{content}</h3>'
            )
        elif stripped.startswith("## "):
            content = _inline_format(stripped[3:])
            html_lines.append(
                f'<h2 style="font-size:20px;color:#1a73e8;margin:30px 0 12px 0;'
                f'font-weight:bold;border-bottom:2px solid #1a73e8;padding-bottom:6px;">'
                f'{content}</h2>'
            )
        elif stripped.startswith("# "):
            content = _inline_format(stripped[2:])
            html_lines.append(
                f'<h1 style="font-size:24px;color:#222;margin:0 0 15px 0;'
                f'font-weight:bold;">{content}</h1>'
            )
        # 구분선
        elif stripped in ("---", "***", "___"):
            html_lines.append('<hr style="border:none;border-top:1px solid #ddd;margin:20px 0;">')

        # 인용 (blockquote)
        elif stripped.startswith("> "):
            content = _inline_format(stripped[2:])
            html_lines.append(
                f'<blockquote style="border-left:4px solid #1a73e8;margin:15px 0;'
                f'padding:10px 15px;background:#f8f9fa;color:#555;'
                f'font-style:italic;">{content}</blockquote>'
            )

        # 비순서 리스트
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_ul:
                html_lines.append('<ul style="padding-left:20px;margin:10px 0;">')
                in_ul = True
            content = _inline_format(stripped[2:])
            html_lines.append(
                f'<li style="margin:5px 0;line-height:1.8;">{content}</li>'
            )

        # 순서 리스트
        elif re.match(r"^\d+\.\s", stripped):
            if not in_ol:
                html_lines.append('<ol style="padding-left:20px;margin:10px 0;">')
                in_ol = True
            content = re.sub(r"^\d+\.\s", "", stripped)
            content = _inline_format(content)
            html_lines.append(
                f'<li style="margin:5px 0;line-height:1.8;">{content}</li>'
            )

        # 일반 단락
        else:
            content = _inline_format(stripped)
            html_lines.append(
                f'<p style="margin:8px 0;line-height:1.9;font-size:16px;'
                f'color:#333;">{content}</p>'
            )

    # 열린 리스트 닫기
    if in_ul:
        html_lines.append("</ul>")
    if in_ol:
        html_lines.append("</ol>")

    return "\n".join(html_lines)


def format_column_html(text, persona_id, include_images=False, image_data=None):
    """
    마크다운 텍스트를 블로그용 HTML로 변환

    Args:
        text: 칼럼 텍스트 (마크다운)
        persona_id: 페르소나 ID
        include_images: 이미지 포함 여부
        image_data: 이미지 데이터 dict

    Returns:
        str: HTML 문자열
    """
    body_html = _md_to_html_lines(text)

    # 이미지 삽입
    if include_images and image_data:
        body_images = image_data.get("body_images", [])
        if body_images:
            paragraphs = body_html.split("</p>")
            interval = max(1, len(paragraphs) // (len(body_images) + 1))
            for i, img in enumerate(body_images):
                insert_idx = (i + 1) * interval
                if insert_idx < len(paragraphs):
                    img_url = img.get("url", "")
                    alt = img.get("alt", "본문 이미지")
                    img_tag = (
                        f'</p><div style="text-align:center;margin:20px 0;">'
                        f'<img src="{html_mod.escape(img_url)}" alt="{html_mod.escape(alt)}" '
                        f'style="max-width:100%;border-radius:8px;"></div><p>'
                    )
                    paragraphs[insert_idx] = img_tag + paragraphs[insert_idx]
            body_html = "</p>".join(paragraphs)

    return body_html


def format_column_preview(text, persona_id, image_data=None):
    """
    미리보기용 HTML 생성 (스타일 포함)

    Args:
        text: 칼럼 텍스트
        persona_id: 페르소나 ID
        image_data: 이미지 데이터

    Returns:
        str: 완전한 HTML 문서
    """
    content_html = format_column_html(
        text, persona_id,
        include_images=bool(image_data),
        image_data=image_data,
    )

    # 제목 추출 (첫 번째 헤딩 또는 첫 줄)
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
                f'<img src="{html_mod.escape(thumb_url)}" style="max-width:100%;border-radius:8px;">'
                f'</div>'
            )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: 'Noto Sans KR', sans-serif; max-width: 700px; margin: 0 auto;
       padding: 20px; line-height: 1.8; color: #333; }}
h1 {{ font-size: 24px; margin-bottom: 15px; }}
h2 {{ font-size: 20px; color: #1a73e8; margin-top: 30px; border-bottom: 2px solid #1a73e8; padding-bottom: 6px; }}
h3 {{ font-size: 16px; margin-top: 25px; }}
p {{ margin: 8px 0; line-height: 1.9; font-size: 16px; }}
ul, ol {{ padding-left: 20px; }}
li {{ margin: 5px 0; }}
blockquote {{ border-left: 4px solid #1a73e8; margin: 15px 0; padding: 10px 15px;
             background: #f8f9fa; color: #555; font-style: italic; }}
</style></head><body>
{thumbnail_html}
<h1>{html_mod.escape(title)}</h1>
<hr>
{content_html}
</body></html>"""
