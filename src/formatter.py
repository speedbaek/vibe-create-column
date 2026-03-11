"""
칼럼 포맷팅 모듈
- 마크다운 텍스트 → 블로그용 HTML 변환
- 미리보기 HTML 생성
"""

import re
import html


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
            # **bold**
            safe = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)
            # *italic*
            safe = re.sub(r"\*(.+?)\*", r"<em>\1</em>", safe)
            html_lines.append(f"<p>{safe}</p>")

    if in_list:
        html_lines.append("</ul>")

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
                        f'<img src="{html.escape(img_url)}" alt="{html.escape(alt)}" '
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
                f'<img src="{html.escape(thumb_url)}" style="max-width:100%;border-radius:8px;">'
                f'</div>'
            )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: 'Noto Sans KR', sans-serif; max-width: 700px; margin: 0 auto;
       padding: 20px; line-height: 1.8; color: #333; }}
h1 {{ font-size: 22px; margin-bottom: 10px; }}
h2 {{ font-size: 18px; color: #1a73e8; margin-top: 30px; }}
h3 {{ font-size: 16px; margin-top: 25px; }}
p {{ margin: 8px 0; }}
ul {{ padding-left: 20px; }}
li {{ margin: 4px 0; }}
</style></head><body>
{thumbnail_html}
<h1>{html.escape(title)}</h1>
<hr>
{content_html}
</body></html>"""
