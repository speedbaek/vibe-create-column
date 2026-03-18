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
import random


# Zero-Width Space (문단 간격용)
ZWS = "\u200B"

# ── 내부 링크 메타데이터 (oglink 제목/설명/썸네일 표시용) ──────────
KNOWN_LINKS = {
    # ── 윤웅채 변리사 블로그 (jninsa) ──
    "222176762007": {
        "title": "포기도, 실패도 없다. 변리사 윤웅채 철학",
        "description": "마음껏 의심하십시오. 19년차 변리사의 업무 철학을 소개합니다.",
        "thumbnail": "https://blogthumb.pstatic.net/MjAyNDA1MDlfMjg5/MDAxNzE1MjM5NjMwNTUw.placeholder.jpg",
    },
    "222176805543": {
        "title": "특허법인 테헤란, 진짜 고객의 추천",
        "description": "실제 고객분들의 후기와 추천을 확인하실 수 있습니다.",
        "thumbnail": "https://blogthumb.pstatic.net/MjAyNDA1MDlfMjg5/MDAxNzE1MjM5NjMwNTUw.placeholder.jpg",
    },
    "222180460017": {
        "title": "컨설팅 접수 방법 (비용없는 1차상담 신청)",
        "description": "무료 1차 상담 신청 방법을 안내해 드립니다.",
        "thumbnail": "https://blogthumb.pstatic.net/MjAyNDA1MDlfMjg5/MDAxNzE1MjM5NjMwNTUw.placeholder.jpg",
    },
    # ── 특허법인 테헤란 공식 블로그 (gempy123) ──
    "223441103769": {
        "title": "[상담신청] 변리사 1:1 상담 신청 방법",
        "description": "365일 1:1 상담 신청 가능. 특허/상표/디자인 전문 변리사 상담.",
        "thumbnail": "https://blogthumb.pstatic.net/MjAyNTEwMTNfNjEg/MDAxNzYwMzQ0OTg2ODkw.c-7ZeJfKCqLeY4r7VeIdwJH29zbLpKU3qO73nWLASyog.ynaZmAFwCSxq0mLFx4-kMUdcRDD9jA-qgiG3cQacifMg.PNG/gem%BA%ED_%B0%F8%C1%F6%B1%DB3.png?type=w2",
    },
    "221743525874": {
        "title": "[테헤란 지식재산연구소] 변리사 상담 신청 방법 공개",
        "description": "365일 1:1 상담 신청 가능. 비용없는 상담 안내.",
        "thumbnail": "https://blogthumb.pstatic.net/MjAyNTEwMTNfMjI3/MDAxNzYwMzQ0ODgxNTY2.Xy5J3k9m62mhWUAAhZz9zRWmYj2RRLVchihtLyvaISgg.lhbtmu-h6-dql5BaxUv-Cq7hw3wLz8snn2NGt_Q7kDcg.PNG/gem%BA%ED_%B0%F8%C1%F6%B1%DB1.png?type=w2",
    },
    "223311360349": {
        "title": "[카톡상담] 모든 궁금증 쉽게 해결할 수 있습니다",
        "description": "카카오톡으로 편하게 변리사 상담을 받아보실 수 있습니다.",
        "thumbnail": "https://blogthumb.pstatic.net/MjAyNTEwMTNfMjIg/MDAxNzYwMzQ0OTIwMzk4.SMUadPxLurIN-1Ll-oXg9aXWMwwCErQCzzoKX1WV-aYg.Vd4NN1KFfOikin0sZVIWV-C5vXUXMMVSMeePtXI3akog.PNG/gem%BA%ED_%B0%F8%C1%F6%B1%DB2.png?type=w2",
    },
    "224013166948": {
        "title": "100% 등록을 보장하는 안심등록 프로모션",
        "description": "테헤란 첫 고객이라면 안심등록 프로모션을 신청하세요.",
        "thumbnail": "https://blogthumb.pstatic.net/MjAyNTA5MTlfOTUg/MDAxNzU4MjcyMzkxNzM3.SSHFp1sFOxAduJ1ICdUhK5o-uGyAT1kgesGCy2O_eqog.qDpVOjkY7RBP6jNqIInUDhMJSVSBixdhM1IRv6NfAmEg.PNG/Group_1000003767.png?type=w2",
    },
    "223657466660": {
        "title": "[변리사소개] 평균 경력 18년, 특허법인 테헤란",
        "description": "권리 선점을 위한 최고의 선택. 특허법인 테헤란 소개.",
        "thumbnail": "https://blogthumb.pstatic.net/MjAyNDExMTJfMTU4/MDAxNzMxMzkwMjkzNzA3.Panc1kKeUD9cgeLANnuBv-j9iGZmhuWKtNxeb5OJvj8g.lMmaYeNHwxP6og6-WybS58XKaXVSLZ0676Ga2PQAqSAg.JPEG/FIM_4760.jpg?type=w2",
    },
    "222881474758": {
        "title": "[고객사 인터뷰] 바딥슬립, 왜 테헤란과 함께 출원했을까?",
        "description": "테헤란 덕분에 지식재산권 등록 과정이 어렵지 않았습니다.",
        "thumbnail": "https://blogthumb.pstatic.net/MjAyMjA5MjJfMjQ0/MDAxNjYzODMxOTk5OTMz.HuBaoc7PGJqH9lRU07vJS_nFSVTXQXDpTnF0c0l4Vzkg.DTRKFFuQ-CP5IGuWRfvIOW78X5-hOUZr1z7_mA1juYgg.JPEG.gempy123/220922%2C-%B0%ED%B0%B4%BB%E7%C0%CE%C5%CD%BA%E4.jpg?type=w2",
    },
    "222638817949": {
        "title": "골프퍼터 특허등록에 성공한 실제 고객 후기",
        "description": "테헤란을 통해 특허등록에 성공한 고객 인터뷰.",
        "thumbnail": "https://blogthumb.pstatic.net/MjAyMjAyMDRfMjcw/MDAxNjQzOTU4MDk0ODAx.Ug48QxZUQEsJ5ICgiOb4w8BSKmLiiNB8JcPDDpNUPsIg.o3Ym-cYwFdgUG64bSSL74TJgUXZfdVIV2uqJfSZmze8g.PNG.gempy123/220204-%C1%AA%2C-%C6%AF%C7%E3%B5%EE%B7%CF.png?type=w2",
    },
    "222590924011": {
        "title": "스포츠언더웨어 특허등록에 성공한 실제 고객 후기",
        "description": "테헤란 고객 직접 인터뷰. 특허 출원 후기.",
        "thumbnail": "https://blogthumb.pstatic.net/MjAyMTEyMDlfOTUg/MDAxNjM5MDIzMDYwMDE1.Nm5pVWLvkF4ZmWpqIMCXlQdjGO5GLeiWdFrfif0FQ-Yg.f7RuVpyLP0rUp2ZtMivfo6u_f_22_hsfwezxN6ctfNkg.PNG.gempy123/211209-%C1%AA%2C-%B0%ED%B0%B4%BD%BA%C5%E4%B8%AE.png?type=w2",
    },
    "222177594095": {
        "title": "BM특허 등록 받은 테헤란 특허법인 고객 찐후기",
        "description": "테헤란 고객사 인터뷰. BM특허 등록 성공 사례.",
        "thumbnail": "https://blogthumb.pstatic.net/MjAyMDEyMThfMTg0/MDAxNjA4MjU2MTUyNTY5.zurH4unF-LVsUNzV_keESgFyTnPI4bKkEVc9mmx7ys8g.hWNq5qRNEcF1c1sLVafSEQr9caWq4GFBTaR8l2R5XzEg.JPEG.gempy123/1-1.jpg?type=w2",
    },
    "222128813704": {
        "title": "만화카페 놀숲 상표 등록, 테헤란 고객 사례",
        "description": "놀숲 상표등록 성공 사례. 테헤란 고객 인터뷰.",
        "thumbnail": "https://blogthumb.pstatic.net/MjAyMDEwMjhfNzgg/MDAxNjAzODQ2MjE4ODgy.yJfRATqmsYH9ll0Br_-fcX7f5o98fal4QRxblCQHqbsg.6j6fgO9NsuBaJyFBwKp5Zjrg0vb6jvxXmJA2ZeNHmSMg.JPEG.gempy123/%C5%D7%C7%EC%B6%F5_%C1%F6%BD%C4%C0%E7%BB%EA%BF%AC%B1%B8%BC%D2_%BD%E6%B3%D7%C0%CF1.jpg?type=w2",
    },
}


def _lookup_link_meta(url):
    """내부 링크 URL에서 제목/설명/썸네일 조회"""
    for log_no, meta in KNOWN_LINKS.items():
        if log_no in url:
            return meta["title"], meta["description"], meta.get("thumbnail", "")
    return "", "", ""


def _gen_id():
    return f"SE-{uuid.uuid4()}"


def _text_node(value, bold=False, font_color="#000000", font_size=None, link_url=None, bg_color=None):
    style = {
        "fontColor": font_color,
        "fontFamily": "system",
        "@ctype": "nodeStyle",
    }
    if bold:
        style["bold"] = True
    if font_size:
        style["fontSize"] = font_size
    if bg_color:
        style["backgroundColor"] = bg_color
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
BOLD_COLOR = "#E53935"       # **bold** 키워드 → 빨간색
HIGHLIGHT_BG = "#FFF9C4"     # 하이라이트 문장 → 노란색 배경 (backgroundColor)
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


def _paragraph(nodes, align="left"):
    """문단 생성 (기본 좌측정렬 - 모바일 가독성 최적화)

    justify는 한글에서 단어 간격이 불균일해져 모바일에서 어색함.
    left 정렬이 줄 끝이 자연스럽게 흘러가면서 가독성이 높음.
    """
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
        comp["align"] = "center"   # 소제목과 통일된 중앙정렬
        return comp

    # URL 문자열 → 기본 컴포넌트 생성
    image_url = image_source
    is_naver_cdn = "pstatic.net" in image_url or "blogfiles" in image_url

    comp = {
        "id": _gen_id(),
        "layout": "default",
        "align": "center",
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


def _oglink_component(url, title="", description="", thumbnail=""):
    """OG Link 컴포넌트 - 링크 미리보기 카드 (내부 링크 메타데이터 자동 조회)

    주의: setDocumentData()로 삽입 시 oglink가 렌더링되지 않는 경우가 있음.
    대안으로 _cta_link_component()를 사용 권장.
    """
    domain = ""
    if "://" in url:
        domain = url.split("://")[1].split("/")[0]

    if not title:
        title, description, thumbnail = _lookup_link_meta(url)
    if not title:
        title = domain

    comp = {
        "id": _gen_id(),
        "layout": "default",
        "align": "center",
        "link": url,
        "title": title,
        "description": description,
        "domain": domain,
        "video": False,
        "@ctype": "oglink",
    }

    if thumbnail:
        comp["thumbnail"] = thumbnail

    if "naver.com" in url or "blog.naver" in url:
        comp["source"] = "blog.naver.com"

    return comp


def _cta_link_component(url):
    """CTA 링크 텍스트 블록 - setDocumentData()에서 확실히 작동하는 링크 형태

    oglink 대신 사용. 텍스트 컴포넌트 + urlLink 조합으로 클릭 가능한 링크 생성.
    KNOWN_LINKS에 등록된 제목이 있으면 제목 표시, 없으면 URL 자체를 링크로.

    형태:
      ▷ [제목 텍스트] (파란색, 볼드, 클릭 가능)
    """
    title, description, _ = _lookup_link_meta(url)

    CTA_BLUE = "#1a73e8"

    if title:
        # 제목이 있는 경우: "▷ 제목" 형태로 표시
        nodes = [
            _text_node("▷ ", font_color="#666666"),
            _text_node(title, bold=True, font_color=CTA_BLUE, link_url=url),
        ]
    else:
        # 제목이 없는 경우: URL 자체를 링크로
        nodes = [
            _text_node(url, font_color=CTA_BLUE, link_url=url),
        ]

    return _text_component([
        _empty_para(),
        _paragraph(nodes, align="center"),
        _empty_para(),
    ])


def update_known_links(log_no, title, description, thumbnail=""):
    """KNOWN_LINKS에 새 링크 메타데이터 추가/업데이트 (런타임)

    Planner가 발행된 글의 OG 데이터를 수집하여 업데이트할 때 사용
    """
    KNOWN_LINKS[str(log_no)] = {
        "title": title,
        "description": description,
        "thumbnail": thumbnail,
    }


def _quote_component(text):
    """인용구 컴포넌트 - 따옴표 문장 강조 (가운데 정렬)"""
    return {
        "id": _gen_id(),
        "layout": "default",
        "value": [_paragraph([_text_node(text)], align="center")],
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


def _parse_inline(text):
    """인라인 마크다운 파싱: **bold** → 빨간색 볼드, [text](url) → 파란색 링크"""
    nodes = []
    pattern = r'\*\*(.+?)\*\*|\[([^\]]+)\]\((https?://[^\)]+)\)'
    last_end = 0

    for match in re.finditer(pattern, text):
        before = text[last_end:match.start()]
        if before:
            nodes.append(_text_node(before))
        if match.group(1):
            # **bold** → 빨간색 볼드
            nodes.append(_text_node(match.group(1), bold=True, font_color=BOLD_COLOR))
        elif match.group(2) and match.group(3):
            nodes.append(_text_node(match.group(2), font_color="#1a73e8", link_url=match.group(3)))
        last_end = match.end()

    remaining = text[last_end:]
    if remaining:
        nodes.append(_text_node(remaining))
    if not nodes:
        nodes.append(_text_node(""))
    return nodes


def _parse_inline_highlight(text):
    """하이라이트 문장 파싱: 전체 노란색 배경 + **bold** 부분은 빨간색"""
    nodes = []
    pattern = r'\*\*(.+?)\*\*|\[([^\]]+)\]\((https?://[^\)]+)\)'
    last_end = 0

    for match in re.finditer(pattern, text):
        before = text[last_end:match.start()]
        if before:
            nodes.append(_text_node(before, bg_color=HIGHLIGHT_BG))
        if match.group(1):
            # **bold** → 빨간색 볼드 + 노란색 배경
            nodes.append(_text_node(match.group(1), bold=True, font_color=BOLD_COLOR, bg_color=HIGHLIGHT_BG))
        elif match.group(2) and match.group(3):
            nodes.append(_text_node(match.group(2), font_color="#1a73e8", link_url=match.group(3), bg_color=HIGHLIGHT_BG))
        last_end = match.end()

    remaining = text[last_end:]
    if remaining:
        nodes.append(_text_node(remaining, bg_color=HIGHLIGHT_BG))
    if not nodes:
        nodes.append(_text_node("", bg_color=HIGHLIGHT_BG))
    return nodes


def _parse_inline_corporate_highlight(text):
    """법인 블로그용 하이라이트: 연한 파란 배경 + 볼드 처리 (이모지 없음)"""
    CORP_HIGHLIGHT_BG = "#E8F0FE"  # 연파랑 배경 (테헤란 블루 계열)
    nodes = []
    # **bold** 패턴 및 [text](url) 패턴 처리
    pattern = re.compile(r'(\*\*(.+?)\*\*|\[([^\]]+)\]\(([^)]+)\))')
    last_end = 0
    for match in pattern.finditer(text):
        before = text[last_end:match.start()]
        if before:
            nodes.append(_text_node(before, bg_color=CORP_HIGHLIGHT_BG))
        if match.group(2):  # **bold**
            nodes.append(_text_node(match.group(2), bold=True, font_color="#1A56DB", bg_color=CORP_HIGHLIGHT_BG))
        elif match.group(4):  # [text](url)
            nodes.append(_text_node(match.group(3), font_color="#1a73e8", link_url=match.group(4), bg_color=CORP_HIGHLIGHT_BG))
        last_end = match.end()
    remaining = text[last_end:]
    if remaining:
        nodes.append(_text_node(remaining, bg_color=CORP_HIGHLIGHT_BG))
    if not nodes:
        nodes.append(_text_node("", bg_color=CORP_HIGHLIGHT_BG))
    return nodes


def markdown_to_se_components(text, image_urls=None, persona_id=None):
    """
    마크다운 텍스트 → SmartEditor 컴포넌트 리스트 변환

    참고글 구조 반영:
    - 연속 문단을 하나의 텍스트 컴포넌트에 묶고, 빈줄은 ZWS 문단으로 간격 생성
    - 소제목(##) 앞에 이미지 배치
    - URL → oglink 컴포넌트 (링크 미리보기)
    - "따옴표 문장" → quote 컴포넌트

    Args:
        persona_id: 페르소나 ID (teheran_official이면 이미지가 있는 소제목의 quotation 생략)
    """
    lines = text.split("\n")
    components = []
    current_paragraphs = []
    # 이미지가 있어도 소제목 텍스트(quotation)는 항상 표시 (SEO 상위노출 위해 텍스트 필수)
    _skip_heading_quote = False
    # teheran_official: 하이라이트를 이모지+볼드 방식으로 (노란 배경 대신)
    _use_emoji_highlight = persona_id in ("teheran_official",)

    # ── 하이라이트 골고루 분산 배치 ──
    # 1단계: 하이라이트 가능한 일반 텍스트 줄의 인덱스 수집
    _highlight_candidate_indices = []
    for _i, _line in enumerate(lines):
        _s = _line.strip()
        # 소제목, 빈줄, 리스트, URL, 따옴표 등은 제외 — 일반 텍스트만
        if (not _s or _s.startswith("#") or _s.startswith("- ") or _s.startswith("* ")
            or _s.startswith("http://") or _s.startswith("https://")
            or _s.startswith("---")
            or (_s.startswith("<") and _s.endswith(">") and len(_s) < 50)
            or ((_s.startswith('"') and _s.endswith('"'))
                or (_s.startswith('\u201c') and _s.endswith('\u201d')))
            or re.match(r'^\d+\.\s', _s)):
            continue
        if _should_highlight(_s):
            _highlight_candidate_indices.append(_i)

    # 2단계: 후보 중에서 MAX개를 골고루 선택 (앞쪽 치우침 방지)
    _highlight_selected = set()
    if len(_highlight_candidate_indices) <= HIGHLIGHT_MAX:
        _highlight_selected = set(_highlight_candidate_indices)
    else:
        # 균등 간격으로 선택
        step = len(_highlight_candidate_indices) / HIGHLIGHT_MAX
        for _j in range(HIGHLIGHT_MAX):
            idx = int(_j * step)
            _highlight_selected.add(_highlight_candidate_indices[idx])

    # --- 이미지 배치 계산: 소제목(##) 앞에 1장씩 (순서 보장) ---
    heading_line_indices = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("## ") or s.startswith("### "):
            heading_line_indices.append(i)

    img_before_line = {}  # line_index → image_source (URL 문자열 또는 네이티브 dict)
    img_used_indices = set()  # 사용된 image_urls 인덱스
    if image_urls and heading_line_indices:
        # 이미지를 소제목에 순서대로 1:1 매칭 (랜덤 없음)
        # image[0] → heading[0] 앞, image[1] → heading[1] 앞, ...
        for i, img_source in enumerate(image_urls):
            if i < len(heading_line_indices):
                img_before_line[heading_line_indices[i]] = img_source
                img_used_indices.add(i)

    # 소제목이 부족해서 배치 안 된 이미지 → 본문 중간에 균등 배치
    if image_urls:
        unplaced = [i for i in range(len(image_urls)) if i not in img_used_indices]
        if unplaced and len(lines) > 0:
            # 빈 줄 위치를 찾아서 균등 배치 (문단 사이)
            empty_line_indices = [i for i, line in enumerate(lines) if not line.strip() and i > 5]
            if empty_line_indices and len(empty_line_indices) >= len(unplaced):
                step = len(empty_line_indices) // (len(unplaced) + 1)
                for j, img_idx in enumerate(unplaced):
                    target_pos = empty_line_indices[min((j + 1) * step, len(empty_line_indices) - 1)]
                    img_before_line[target_pos] = image_urls[img_idx]
                    img_used_indices.add(img_idx)
            elif not heading_line_indices:
                total_lines = len(lines)
                step = total_lines // (len(unplaced) + 1)
                for j, img_idx in enumerate(unplaced):
                    target_line = (j + 1) * step
                    img_before_line[target_line] = image_urls[img_idx]
                    img_used_indices.add(img_idx)

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
        # 이미지 유무와 관계없이 항상 텍스트 소제목 표시 (SEO 상위노출용)
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

        # URL 단독 줄 → CTA 링크 텍스트 블록 (클릭 가능한 링크)
        # URL 단독 줄 → oglink 컴포넌트 (링크 미리보기 카드)
        if stripped.startswith("http://") or stripped.startswith("https://"):
            _flush_text()
            url_clean = stripped.split()[0] if ' ' in stripped else stripped
            components.append(_oglink_component(url_clean))
            continue

        # <제목> 형태의 줄은 CTA 라벨 — 가운데 정렬로 표시
        if stripped.startswith("<") and stripped.endswith(">") and len(stripped) < 50:
            _flush_text()
            label = stripped[1:-1]  # < > 제거
            nodes = [_text_node(label, bold=True, font_color="#333333")]
            components.append(_text_component([
                _empty_para(),
                _paragraph(nodes, align="center"),
            ]))
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

        # 일반 텍스트 + 하이라이트 (골고루 분산 적용)
        if line_idx in _highlight_selected:
            if _use_emoji_highlight:
                nodes = _parse_inline_corporate_highlight(stripped)
            else:
                nodes = _parse_inline_highlight(stripped)
        else:
            nodes = _parse_inline(stripped)
        current_paragraphs.append(_paragraph(nodes))

    # 나머지 flush
    _flush_text()

    # 남은 이미지 → 마지막 텍스트 앞에 삽입 (끝에 몰리지 않도록)
    if image_urls:
        remaining_imgs = [image_urls[i] for i in range(len(image_urls)) if i not in img_used_indices]
        if remaining_imgs and len(components) > 2:
            # 끝에서 1/3 지점에 삽입
            insert_pos = max(len(components) * 2 // 3, 1)
            for img_source in remaining_imgs:
                components.insert(insert_pos, _image_component(img_source))
                insert_pos += 1
        elif remaining_imgs:
            for img_source in remaining_imgs:
                components.append(_image_component(img_source))

    # ── 문단 간격 균일화 후처리 ──
    # 이미지/quotation 전후에 ZWS 간격이 일정하도록 보장
    components = _normalize_spacing(components)

    return components


def _normalize_spacing(components):
    """컴포넌트 간 간격 균일화 후처리

    규칙:
    - image, oglink 앞뒤에 반드시 ZWS 간격 1줄
    - quotation 앞에 ZWS 2줄, 뒤에 1줄
    - text 컴포넌트 연속 시 사이에 ZWS 1줄
    - 연속 빈 줄(ZWS) 3줄 이상은 2줄로 축소
    """
    if not components:
        return components

    result = []

    def _is_spacing_comp(comp):
        """ZWS만 있는 간격 컴포넌트인지"""
        if comp.get("@ctype") != "text":
            return False
        paras = comp.get("value", [])
        if not paras:
            return False
        for p in paras:
            nodes = p.get("nodes", [])
            for n in nodes:
                val = n.get("value", "")
                if val and val.strip("\u200B").strip():
                    return False
        return True

    def _spacing_comp(count=1):
        """ZWS 간격 컴포넌트 생성 (count줄)"""
        paras = [_empty_para() for _ in range(count)]
        return _text_component(paras)

    for i, comp in enumerate(components):
        ctype = comp.get("@ctype", "")

        # 이미지/oglink 앞에 간격 보장
        if ctype in ("image", "oglink"):
            # 앞 컴포넌트가 간격이 아니면 추가
            if result and not _is_spacing_comp(result[-1]):
                result.append(_spacing_comp(1))
            result.append(comp)
            continue

        # quotation (소제목) 앞에 간격 보장
        if ctype == "quotation":
            if result and not _is_spacing_comp(result[-1]):
                result.append(_spacing_comp(2))
            result.append(comp)
            continue

        result.append(comp)

    # 연속 빈 줄 축소: ZWS-only text 컴포넌트가 연속 3개 이상이면 2개로
    cleaned = []
    spacing_streak = 0
    for comp in result:
        if _is_spacing_comp(comp):
            spacing_streak += 1
            if spacing_streak <= 2:
                cleaned.append(comp)
        else:
            spacing_streak = 0
            cleaned.append(comp)

    return cleaned


def build_document_data(title, text, image_urls=None, persona_id=None):
    """완전한 SmartEditor Document Data 생성"""
    title_comp = {
        "id": _gen_id(),
        "layout": "default",
        "title": [_paragraph([_text_node(title)], align="center")],
        "subTitle": None,
        "align": "center",
        "@ctype": "documentTitle",
    }

    body_components = markdown_to_se_components(text, image_urls=image_urls, persona_id=persona_id)

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
