"""
SmartEditor ONE Document Data 변환기
- 마크다운 텍스트 → SmartEditor JSON 컴포넌트 구조 변환
- setDocumentData()로 에디터에 삽입 가능한 포맷 생성

참고글 구조 기반:
- 문단 그룹핑 + ZWS(​)로 간격 생성
- 이미지는 소제목 앞에 배치 (이미지 텍스트 = 바로 아래 소제목)
- URL → oglink 링크 미리보기 (제목/설명 포함)
- 따옴표 문장 → quote 컴포넌트
- **bold** → 빨간색 볼드, 중요 문장 → 배경 하이라이트
"""

import re
import uuid


# Zero-Width Space (문단 간격용)
ZWS = "\u200B"

# ── 내부 링크 메타데이터 (oglink 제목/설명 표시용) ──────────
KNOWN_LINKS = {
    "222176762007": {
        "title": "포기도, 실패도 없다. 변리사 윤웅채 철학",
        "description": "마음껏 의심하십시오. 19년차 변리사의 업무 철학을 소개합니다.",
    },
    "222176805543": {
        "title": "특허법인 테헤란, 진짜 고객의 추천",
        "description": "실제 고객분들의 후기와 추천을 확인하실 수 있습니다.",
    },
    "222180460017": {
        "title": "컨설팅 접수 방법 (비용없는 1차상담 신청)",
        "description": "무료 1차 상담 신청 방법을 안내해 드립니다.",
    },
}


def _lookup_link_meta(url):
    """내부 링크 URL에서 제목/설명 조회"""
    for log_no, meta in KNOWN_LINKS.items():
        if log_no in url:
            return meta["title"], meta["description"]
    return "", ""


def _gen_id():
    return f"SE-{uuid.uuid4()}"


def _text_node(value, bold=False, font_color="#000000", font_size=None, link_url=None, background_color=None):
    style = {
        "fontColor": font_color,
        "fontFamily": "system",
        "@ctype": "nodeStyle",
    }
    if bold:
        style["bold"] = True
    if font_size:
        style["fontSize"] = font_size
    if background_color:
        style["fontBackgroundColor"] = background_color
    node = {
        "id": _gen_id(),
        "value": value,
        "style": style,
        "@ctype": "textNode",
    }
    if link_url:
        node["link"] = {"url": link_url, "@ctype": "urlLink"}
    return node


# ── 색상/하이라이트 설정 ─────────────────────────────
BOLD_COLOR = "#E53935"       # 빨간색 볼드
HIGHLIGHT_BG = "#FFF3CD"     # 노란색 배경 하이라이트
HIGHLIGHT_MAX = 6

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


def _paragraph(nodes, align="justify"):
    return {
        "id": _gen_id(),
        "nodes": nodes,
        "style": {"align": align, "@ctype": "paragraphStyle"},
        "@ctype": "paragraph",
    }


def _empty_para():
    """빈 문단 (ZWS) - 문단 사이 간격용"""
    return _paragraph([_text_node(ZWS)])


def _text_component(paragraphs):
    return {
        "id": _gen_id(),
        "layout": "default",
        "value": paragraphs,
        "@ctype": "text",
    }


def _image_component(image_source, alt="", width=600):
    """이미지 컴포넌트 - 네이티브 컴포넌트 dict 또는 URL 문자열 지원

    Args:
        image_source: SmartEditor 네이티브 이미지 컴포넌트 dict 또는 URL 문자열
    """
    # 네이티브 컴포넌트 dict → ID만 새로 부여하여 그대로 사용
    if isinstance(image_source, dict) and image_source.get("@ctype") == "image":
        comp = dict(image_source)
        comp["id"] = _gen_id()
        comp["represent"] = False  # 대표 이미지 설정은 별도
        return comp

    # URL 문자열 → 기본 컴포넌트 생성
    image_url = image_source
    is_naver_cdn = "pstatic.net" in image_url or "blogfiles" in image_url

    comp = {
        "id": _gen_id(),
        "layout": "default",
        "align": "justify",
        "src": image_url,
        "internalResource": is_naver_cdn,
        "represent": False,
        "imageLoaded": False,
        "width": width,
        "widthPercentage": 0,
        "height": 0,
        "caption": None,
        "format": "normal",
        "displayFormat": "normal",
        "contentMode": "fit",
        "ai": False,
        "@ctype": "image",
    }

    # CDN URL에서 path, domain 추출
    if is_naver_cdn and "://" in image_url:
        parts = image_url.split("://", 1)
        scheme = parts[0]
        rest = parts[1]
        domain_end = rest.index("/") if "/" in rest else len(rest)
        domain = f"{scheme}://{rest[:domain_end]}"
        path = rest[domain_end:]
        # ?type= 파라미터 제거
        if "?" in path:
            path = path[:path.index("?")]
        comp["domain"] = domain
        comp["path"] = path
        # 파일명 추출
        filename = path.rsplit("/", 1)[-1] if "/" in path else ""
        if filename:
            comp["fileName"] = filename
        comp["origin"] = {"srcFrom": "local", "@ctype": "imageOrigin"}

    return comp


def _oglink_component(url, title="", description=""):
    """OG Link 컴포넌트 - 링크 미리보기 카드 (내부 링크 메타데이터 자동 조회)"""
    domain = ""
    if "://" in url:
        domain = url.split("://")[1].split("/")[0]

    # 내부 링크 메타데이터 자동 조회
    if not title:
        title, description = _lookup_link_meta(url)
    if not title:
        title = domain

    return {
        "id": _gen_id(),
        "layout": "default",
        "link": url,
        "title": title,
        "description": description,
        "domain": domain,
        "video": False,
        "@ctype": "oglink",
    }


def _quote_component(text):
    """인용구 컴포넌트 - 따옴표 문장 강조"""
    return {
        "id": _gen_id(),
        "layout": "default",
        "value": [_paragraph([_text_node(text)])],
        "@ctype": "quotation",
    }


def _heading_quote_component(text, font_size="20"):
    """소제목용 인용구 컴포넌트 - 좌측 막대바 + 큰 글씨 볼드 + 가운데 정렬"""
    return {
        "id": _gen_id(),
        "layout": "default",
        "value": [_paragraph([_text_node(text, bold=True, font_color="#333333", font_size=font_size)], align="center")],
        "@ctype": "quotation",
    }


def _parse_inline(text, background_color=None):
    """인라인 마크다운 파싱: **bold** → 빨간색 볼드, [text](url) → 파란색 링크"""
    nodes = []
    pattern = r'\*\*(.+?)\*\*|\[([^\]]+)\]\((https?://[^\)]+)\)'
    last_end = 0

    for match in re.finditer(pattern, text):
        before = text[last_end:match.start()]
        if before:
            nodes.append(_text_node(before, background_color=background_color))
        if match.group(1):
            # **bold** → 빨간색 볼드
            nodes.append(_text_node(match.group(1), bold=True, font_color=BOLD_COLOR, background_color=background_color))
        elif match.group(2) and match.group(3):
            nodes.append(_text_node(match.group(2), font_color="#1a73e8", link_url=match.group(3), background_color=background_color))
        last_end = match.end()

    remaining = text[last_end:]
    if remaining:
        nodes.append(_text_node(remaining, background_color=background_color))
    if not nodes:
        nodes.append(_text_node("", background_color=background_color))
    return nodes


def markdown_to_se_components(text, image_urls=None):
    """
    마크다운 텍스트 → SmartEditor 컴포넌트 리스트 변환

    참고글 구조 반영:
    - 연속 문단을 하나의 텍스트 컴포넌트에 묶고, 빈줄은 ZWS 문단으로 간격 생성
    - 소제목(##) 앞에 이미지 배치
    - URL → oglink 컴포넌트 (링크 미리보기)
    - "따옴표 문장" → quote 컴포넌트
    """
    lines = text.split("\n")
    components = []
    current_paragraphs = []
    highlight_count = 0  # 하이라이트 카운터

    # --- 이미지 배치 계산: 소제목(##) 앞에 1장씩 ---
    heading_line_indices = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("## ") or s.startswith("### "):
            heading_line_indices.append(i)

    img_before_line = {}  # line_index → image_source (URL 문자열 또는 네이티브 dict)
    img_used_indices = set()  # 사용된 image_urls 인덱스
    if image_urls and heading_line_indices:
        # 이미지와 소제목 1:1 매핑 (이미지 텍스트 = 바로 아래 소제목)
        targets = heading_line_indices
        for i, img_source in enumerate(image_urls):
            if i < len(targets):
                img_before_line[targets[i]] = img_source
                img_used_indices.add(i)

    def _flush_text():
        nonlocal current_paragraphs
        if current_paragraphs:
            components.append(_text_component(current_paragraphs))
            current_paragraphs = []

    for line_idx, line in enumerate(lines):
        stripped = line.strip()

        # 소제목 앞 이미지 삽입
        if line_idx in img_before_line:
            _flush_text()
            components.append(_image_component(img_before_line[line_idx]))

        # 빈 줄 → 같은 텍스트 컴포넌트 안에 ZWS 문단 추가 (간격)
        if not stripped:
            current_paragraphs.append(_empty_para())
            continue

        # 구분선 (---) → flush + 간격
        if stripped == "---":
            _flush_text()
            components.append(_text_component([_empty_para(), _empty_para()]))
            continue

        # ## 소제목 → quotation 컴포넌트 (좌측 막대바 + 큰 글씨 볼드)
        if stripped.startswith("## "):
            _flush_text()
            heading = stripped[3:]
            components.append(_text_component([_empty_para(), _empty_para()]))
            components.append(_heading_quote_component(heading))
            components.append(_text_component([_empty_para()]))
            continue

        # ### 소소제목 → quotation 컴포넌트 (약간 작게)
        if stripped.startswith("### "):
            _flush_text()
            heading = stripped[4:]
            components.append(_text_component([_empty_para()]))
            components.append(_heading_quote_component(heading, font_size="17"))
            components.append(_text_component([_empty_para()]))
            continue

        # # 대제목
        if stripped.startswith("# "):
            _flush_text()
            heading = stripped[2:]
            nodes = [_text_node(heading, bold=True, font_color="#222222", font_size="20")]
            components.append(_text_component([
                _paragraph(nodes),
                _empty_para(),
            ]))
            continue

        # URL 단독 줄 → oglink 컴포넌트 (링크 미리보기)
        if stripped.startswith("http://") or stripped.startswith("https://"):
            _flush_text()
            components.append(_oglink_component(stripped))
            continue

        # "따옴표 문장" → quote 컴포넌트
        if (stripped.startswith('"') and stripped.endswith('"')) or \
           (stripped.startswith('\u201c') and stripped.endswith('\u201d')):
            _flush_text()
            # 따옴표 제거
            inner = stripped.strip('""\u201c\u201d')
            components.append(_quote_component(inner))
            continue

        # 리스트 (- 또는 *)
        if stripped.startswith("- ") or stripped.startswith("* "):
            item_text = stripped[2:]
            nodes = [_text_node("  \u2022 ")] + _parse_inline(item_text)
            current_paragraphs.append(_paragraph(nodes))
            continue

        # 숫자 리스트
        num_match = re.match(r'^(\d+)\.\s(.+)', stripped)
        if num_match:
            num = num_match.group(1)
            item_text = num_match.group(2)
            nodes = [_text_node(f"  {num}. ")] + _parse_inline(item_text)
            current_paragraphs.append(_paragraph(nodes))
            continue

        # 일반 텍스트 + 하이라이트 (수정 3)
        if highlight_count < HIGHLIGHT_MAX and _should_highlight(stripped):
            nodes = _parse_inline(stripped, background_color=HIGHLIGHT_BG)
            highlight_count += 1
        else:
            nodes = _parse_inline(stripped)
        current_paragraphs.append(_paragraph(nodes))

    # 나머지 flush
    _flush_text()

    # 남은 이미지 (소제목이 부족해서 배치 안 된 것) → 맨 끝에 추가
    if image_urls:
        for i, img_source in enumerate(image_urls):
            if i not in img_used_indices:
                components.append(_image_component(img_source))

    return components


def build_document_data(title, text, image_urls=None):
    """완전한 SmartEditor Document Data 생성"""
    title_comp = {
        "id": _gen_id(),
        "layout": "default",
        "title": [_paragraph([_text_node(title)], align="center")],
        "subTitle": None,
        "align": "center",
        "@ctype": "documentTitle",
    }

    body_components = markdown_to_se_components(text, image_urls=image_urls)

    return {
        "document": {
            "version": "2.9.0",
            "theme": "default",
            "language": "ko-KR",
            "id": _gen_id(),
            "components": [title_comp] + body_components,
        },
        "documentId": "",
    }
