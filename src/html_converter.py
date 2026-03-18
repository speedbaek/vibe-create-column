"""
마크다운 → HTML 변환기 (티스토리용)

네이버 SmartEditor JSON 대신 표준 HTML로 변환합니다.
기존 se_converter.py의 스타일(빨간 볼드, 하이라이트, 인용구 등)을
HTML/CSS로 재현합니다.
"""

import re

# ── 색상 설정 ─────────────────────────────────
BOLD_COLOR = "#E53935"          # **bold** → 빨간색
HIGHLIGHT_BG = "#FFF9C4"        # 하이라이트 배경
HEADING_COLOR = "#222222"       # 소제목 색상
HEADING_BORDER = "#333333"      # 소제목 좌측 바
CTA_BLUE = "#1A73E8"            # CTA 링크 색상
HIGHLIGHT_MAX = 6               # 최대 하이라이트 수

_HIGHLIGHT_ENDINGS = re.compile(
    r'(하십시오|해야\s*합니다|하시기\s*바랍니다|하셔야|해주세요|하세요|해야만|필수입니다)[.!]?\s*$'
)
_HIGHLIGHT_KEYWORDS = re.compile(
    r'(중요|핵심|반드시|절대|꼭|필수|주의|경고|명심)'
)


def _should_highlight(text):
    """하이라이트 대상 여부 판별"""
    if _HIGHLIGHT_ENDINGS.search(text):
        return True
    if _HIGHLIGHT_KEYWORDS.search(text):
        return True
    if '**' in text:
        return True
    return False


def _parse_inline(text):
    """인라인 마크다운 → HTML: **bold** → 빨간 볼드, [text](url) → 링크"""
    # **bold** → 빨간 볼드
    text = re.sub(
        r'\*\*(.+?)\*\*',
        rf'<strong style="color:{BOLD_COLOR}">\1</strong>',
        text
    )
    # [text](url) → 링크
    text = re.sub(
        r'\[(.+?)\]\((.+?)\)',
        rf'<a href="\2" style="color:{CTA_BLUE}; text-decoration:underline;" target="_blank">\1</a>',
        text
    )
    return text


def _parse_inline_highlight(text):
    """하이라이트 문장 → 노란 배경 + 빨간 볼드"""
    inner = _parse_inline(text)
    return f'<span style="background-color:{HIGHLIGHT_BG}; padding:2px 4px;">{inner}</span>'


def markdown_to_html(text, image_urls=None, persona_id=None):
    """
    마크다운 텍스트를 티스토리용 HTML로 변환

    Args:
        text: 마크다운 형식 칼럼 텍스트
        image_urls: 이미지 URL 리스트 (CDN 업로드된 URL)
        persona_id: 페르소나 ID

    Returns:
        str: HTML 문자열
    """
    lines = text.split("\n")
    html_parts = []

    # ── 이미지 배치 계산: 소제목(##) 앞에 1장씩 ──
    heading_line_indices = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("## ") or s.startswith("### "):
            heading_line_indices.append(i)

    img_before_line = {}
    if image_urls and heading_line_indices:
        for i, img_url in enumerate(image_urls):
            if i < len(heading_line_indices):
                img_before_line[heading_line_indices[i]] = img_url

    # ── 하이라이트 골고루 분산 ──
    highlight_candidates = []
    for i, line in enumerate(lines):
        s = line.strip()
        if (not s or s.startswith("#") or s.startswith("- ") or s.startswith("* ")
            or s.startswith("http://") or s.startswith("https://")
            or s.startswith("---")
            or (s.startswith("<") and s.endswith(">") and len(s) < 50)
            or ((s.startswith('"') and s.endswith('"'))
                or (s.startswith('\u201c') and s.endswith('\u201d')))
            or re.match(r'^\d+\.\s', s)):
            continue
        if _should_highlight(s):
            highlight_candidates.append(i)

    highlight_selected = set()
    if len(highlight_candidates) <= HIGHLIGHT_MAX:
        highlight_selected = set(highlight_candidates)
    else:
        step = len(highlight_candidates) / HIGHLIGHT_MAX
        for j in range(HIGHLIGHT_MAX):
            idx = int(j * step)
            highlight_selected.add(highlight_candidates[idx])

    # ── 라인별 변환 ──
    in_list = False

    for line_idx, line in enumerate(lines):
        stripped = line.strip()

        # 소제목 앞 이미지
        if line_idx in img_before_line:
            img_url = img_before_line[line_idx]
            if isinstance(img_url, str):
                html_parts.append(
                    f'<figure style="text-align:center; margin:30px 0;">'
                    f'<img src="{img_url}" style="max-width:100%; border-radius:8px;" />'
                    f'</figure>'
                )

        # 빈 줄
        if not stripped:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append('<br />')
            continue

        # 구분선
        if stripped == "---":
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append('<hr style="border:none; border-top:1px solid #ddd; margin:30px 0;" />')
            continue

        # ## 소제목 → 좌측 바 스타일
        if stripped.startswith("## "):
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            heading = stripped[3:]
            html_parts.append(
                f'<h3 style="border-left:4px solid {HEADING_BORDER}; padding-left:12px; '
                f'font-size:20px; font-weight:bold; color:{HEADING_COLOR}; margin:35px 0 15px 0;">'
                f'{heading}</h3>'
            )
            continue

        # ### 소소제목
        if stripped.startswith("### "):
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            heading = stripped[4:]
            html_parts.append(
                f'<h4 style="border-left:3px solid #999; padding-left:10px; '
                f'font-size:17px; font-weight:bold; color:#333; margin:25px 0 10px 0;">'
                f'{heading}</h4>'
            )
            continue

        # # 대제목
        if stripped.startswith("# "):
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            heading = stripped[2:]
            html_parts.append(
                f'<h2 style="font-size:22px; font-weight:bold; color:{HEADING_COLOR}; margin:30px 0 15px 0;">'
                f'{heading}</h2>'
            )
            continue

        # URL 단독 줄 → 링크 카드
        if stripped.startswith("http://") or stripped.startswith("https://"):
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            url_clean = stripped.split()[0] if ' ' in stripped else stripped
            html_parts.append(
                f'<div style="margin:20px 0; text-align:center;">'
                f'<a href="{url_clean}" target="_blank" '
                f'style="display:inline-block; padding:12px 24px; background:#f8f9fa; '
                f'border:1px solid #ddd; border-radius:8px; color:{CTA_BLUE}; '
                f'text-decoration:none; font-weight:bold;">'
                f'{url_clean}</a></div>'
            )
            continue

        # <제목> → CTA 라벨
        if stripped.startswith("<") and stripped.endswith(">") and len(stripped) < 50:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            label = stripped[1:-1]
            html_parts.append(
                f'<p style="text-align:center; font-weight:bold; color:#333; margin:15px 0;">'
                f'{label}</p>'
            )
            continue

        # "따옴표" → 인용구
        if ((stripped.startswith('"') and stripped.endswith('"'))
            or (stripped.startswith('\u201c') and stripped.endswith('\u201d'))):
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            inner = stripped.strip('"\u201c\u201d')
            html_parts.append(
                f'<blockquote style="border-left:4px solid #ccc; padding:12px 20px; '
                f'margin:20px 0; background:#f9f9f9; font-style:italic; color:#555;">'
                f'{inner}</blockquote>'
            )
            continue

        # 리스트 (- 또는 *)
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_parts.append('<ul style="margin:10px 0; padding-left:25px;">')
                in_list = True
            item_text = stripped[2:]
            html_parts.append(f'<li style="margin:5px 0;">{_parse_inline(item_text)}</li>')
            continue

        # 숫자 리스트
        num_match = re.match(r'^(\d+)\.\s(.+)', stripped)
        if num_match:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            num = num_match.group(1)
            item_text = num_match.group(2)
            html_parts.append(
                f'<p style="margin:5px 0; padding-left:10px;">'
                f'<strong>{num}.</strong> {_parse_inline(item_text)}</p>'
            )
            continue

        # 일반 텍스트 + 하이라이트
        if in_list:
            html_parts.append('</ul>')
            in_list = False

        if line_idx in highlight_selected:
            html_parts.append(f'<p style="margin:8px 0; line-height:1.8;">{_parse_inline_highlight(stripped)}</p>')
        else:
            html_parts.append(f'<p style="margin:8px 0; line-height:1.8;">{_parse_inline(stripped)}</p>')

    # 리스트 닫기
    if in_list:
        html_parts.append('</ul>')

    return "\n".join(html_parts)
