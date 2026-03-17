"""
이미지 핸들러 모듈
- 소제목 텍스트를 카드형 이미지로 렌더링 (PIL)
- 680x200 가로형 배너 크기 (네이버 블로그 최적화)
- NanumPen / NanumBrush / 맑은고딕 혼합 사용
- 그라데이션 배경 + 장식 요소로 시각적 복잡도 확보
"""

import os
import re
import logging
import random
import uuid
import requests
import urllib.request
import math

logger = logging.getLogger(__name__)

# ── 폰트 관련 설정 ─────────────────────────────────
FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")
FONTS = {
    "NanumPen": "https://github.com/google/fonts/raw/main/ofl/nanumpenscript/NanumPenScript-Regular.ttf",
    "NanumBrush": "https://github.com/google/fonts/raw/main/ofl/nanumbrushscript/NanumBrushScript-Regular.ttf",
    "Pretendard": "https://github.com/orioncactus/pretendard/raw/main/packages/pretendard/dist/public/static/Pretendard-SemiBold.otf",
    "PretendardBold": "https://github.com/orioncactus/pretendard/raw/main/packages/pretendard/dist/public/static/Pretendard-Bold.otf",
}

# 가로형 배너 이미지 크기 - 윤변리사 (손글씨 스타일)
IMG_WIDTH = 680
IMG_HEIGHT = 200

# 공식블로그 모던 이미지 크기 (2.5:1 비율, 세로 여유)
MODERN_WIDTH = 680
MODERN_HEIGHT = 270


def ensure_fonts():
    """폰트 자동 다운로드 (없으면)"""
    os.makedirs(FONT_DIR, exist_ok=True)
    available = {}
    for name, url in FONTS.items():
        # 확장자 자동 감지
        ext = "otf" if url.endswith(".otf") else "ttf"
        path = os.path.join(FONT_DIR, f"{name}.{ext}")
        if not os.path.exists(path):
            try:
                logger.info(f"폰트 다운로드: {name}...")
                urllib.request.urlretrieve(url, path)
                logger.info(f"폰트 다운로드 완료: {path}")
            except Exception as e:
                logger.warning(f"폰트 다운로드 실패 ({name}): {e}")
                continue
        available[name] = path
    return available


def _extract_subtitles(content):
    """본문에서 소제목(## heading) 추출"""
    return re.findall(r'^##\s+(.+)$', content, re.MULTILINE)


def _extract_key_sentences(content, topic, count=4):
    """소제목이 없을 때 본문에서 카드 이미지용 핵심 문장 추출

    짧고 임팩트 있는 문장을 다양하게 추출 (키워드 반복 방지)
    """
    sentences = []
    for line in content.split("\n"):
        s = line.strip()
        # 빈 줄, 마크다운 기호, URL, 너무 짧은 줄 제외
        if not s or s.startswith("#") or s.startswith("-") or s.startswith("*"):
            continue
        if s.startswith("http") or len(s) < 10 or len(s) > 60:
            continue
        # 마크다운 볼드/링크 제거
        clean = re.sub(r'\*\*(.+?)\*\*', r'\1', s)
        clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', clean)
        clean = clean.strip('""\u201c\u201d')
        if 10 <= len(clean) <= 50:
            sentences.append(clean)

    if not sentences:
        # 길이 제한 완화해서 재시도
        for line in content.split("\n"):
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("-"):
                continue
            clean = re.sub(r'\*\*(.+?)\*\*', r'\1', s)
            if 8 <= len(clean) <= 80:
                # 너무 길면 앞부분만
                sentences.append(clean[:45] + "..." if len(clean) > 45 else clean)

    # 중복 제거 + 균등 선택
    unique = list(dict.fromkeys(sentences))
    if len(unique) <= count:
        return unique if unique else [topic]

    step = len(unique) // count
    return [unique[i * step] for i in range(count)]


def _get_font(name, size):
    """PIL ImageFont 로드"""
    from PIL import ImageFont
    fonts = ensure_fonts()
    path = fonts.get(name)
    if path and os.path.exists(path):
        return ImageFont.truetype(path, size)
    # 시스템 폰트 폴백
    for fallback in ["malgunbd.ttf", "malgun.ttf"]:
        try:
            return ImageFont.truetype(fallback, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap_text(text, font, max_width, draw):
    """텍스트가 max_width를 넘으면 줄바꿈"""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]

    if text_width <= max_width:
        return [text]

    # 중간 지점에서 분할
    mid = len(text) // 2
    split_at = -1
    for sep in [' ', ', ', '. ', '! ', '? ']:
        idx = text.rfind(sep, 0, mid + 5)
        if idx > len(text) // 4:
            split_at = idx + len(sep)
            break
    if split_at < 0:
        split_at = mid

    line1 = text[:split_at].strip()
    line2 = text[split_at:].strip()
    return [line1, line2] if line2 else [line1]


def _adjust_font_size(text, font_name, max_width, max_height, draw, size_range=None):
    """텍스트에 맞게 폰트 크기 자동 조정"""
    if size_range is None:
        size_range = [64, 58, 52, 48, 44, 40, 36]
    for size in size_range:
        font = _get_font(font_name, size)
        lines = _wrap_text(text, font, max_width, draw)
        total_h = 0
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            total_h += bbox[3] - bbox[1]
        total_h += (len(lines) - 1) * 12
        if total_h <= max_height:
            return font, lines, size
    font = _get_font(font_name, size_range[-1])
    lines = _wrap_text(text, font, max_width, draw)
    return font, lines, size_range[-1]


def _draw_gradient(draw, width, height, color_start, color_end, direction="vertical"):
    """그라데이션 배경 생성"""
    r1, g1, b1 = color_start
    r2, g2, b2 = color_end
    for i in range(height if direction == "vertical" else width):
        ratio = i / (height if direction == "vertical" else width)
        r = int(r1 + (r2 - r1) * ratio)
        g = int(g1 + (g2 - g1) * ratio)
        b = int(b1 + (b2 - b1) * ratio)
        if direction == "vertical":
            draw.line([(0, i), (width, i)], fill=(r, g, b))
        else:
            draw.line([(i, 0), (i, height)], fill=(r, g, b))


def _draw_decorative_circles(draw, width, height, base_color, count=8):
    """장식용 반투명 원 그리기"""
    from PIL import Image, ImageDraw as ID
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    od = ID.Draw(overlay)
    for _ in range(count):
        cx = random.randint(-50, width + 50)
        cy = random.randint(-50, height + 50)
        radius = random.randint(30, 120)
        alpha = random.randint(15, 40)
        r, g, b = base_color
        r = min(255, r + random.randint(-20, 20))
        g = min(255, g + random.randint(-20, 20))
        b = min(255, b + random.randint(-20, 20))
        od.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=(r, g, b, alpha)
        )
    return overlay


def _draw_geometric_shapes(draw, width, height, color, count=5):
    """기하학적 장식 (삼각형, 사각형, 선)"""
    for _ in range(count):
        shape = random.choice(['line', 'rect', 'diamond'])

        if shape == 'line':
            x1 = random.randint(0, width)
            y1 = random.randint(0, height)
            x2 = x1 + random.randint(-200, 200)
            y2 = y1 + random.randint(-200, 200)
            draw.line([(x1, y1), (x2, y2)], fill=color[:3], width=1)
        elif shape == 'rect':
            x = random.randint(0, width)
            y = random.randint(0, height)
            s = random.randint(10, 40)
            draw.rectangle([x, y, x + s, y + s], outline=color[:3], width=1)
        elif shape == 'diamond':
            cx = random.randint(0, width)
            cy = random.randint(0, height)
            s = random.randint(8, 25)
            draw.polygon([(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)],
                         outline=color[:3])


# ── 배경 테마 (그라데이션 색상 조합) ─────────────────
_BG_THEMES = [
    {"grad_start": (30, 60, 114), "grad_end": (42, 82, 152), "text": "#FFFFFF",
     "accent": (100, 180, 255), "name": "deep_blue"},
    {"grad_start": (44, 62, 80), "grad_end": (52, 73, 94), "text": "#FFFFFF",
     "accent": (149, 165, 166), "name": "dark_slate"},
    {"grad_start": (15, 32, 39), "grad_end": (32, 58, 67), "text": "#FFFFFF",
     "accent": (80, 200, 180), "name": "dark_teal"},
    {"grad_start": (72, 85, 99), "grad_end": (41, 50, 60), "text": "#FFFFFF",
     "accent": (200, 200, 200), "name": "charcoal"},
    {"grad_start": (200, 205, 215), "grad_end": (170, 180, 200), "text": "#1a1a2e",
     "accent": (80, 100, 160), "name": "steel_blue"},
    {"grad_start": (210, 200, 185), "grad_end": (185, 175, 155), "text": "#2c2c2c",
     "accent": (150, 120, 70), "name": "warm_sand"},
]


def _style_gradient_card(text, output_path, theme_index=0):
    """스타일 1: 그라데이션 배경 + 큰 텍스트 배너 (680x200)"""
    from PIL import Image, ImageDraw

    theme = _BG_THEMES[theme_index % len(_BG_THEMES)]
    img = Image.new('RGB', (IMG_WIDTH, IMG_HEIGHT), theme["grad_start"])
    draw = ImageDraw.Draw(img)

    _draw_gradient(draw, IMG_WIDTH, IMG_HEIGHT, theme["grad_start"], theme["grad_end"])
    _draw_geometric_shapes(draw, IMG_WIDTH, IMG_HEIGHT, theme["accent"], count=5)

    overlay = _draw_decorative_circles(draw, IMG_WIDTH, IMG_HEIGHT, theme["accent"], count=4)
    img_rgba = img.convert('RGBA')
    img_rgba = Image.alpha_composite(img_rgba, overlay)
    img = img_rgba.convert('RGB')
    draw = ImageDraw.Draw(img)

    # 좌우 장식 라인
    draw.line([(30, 30), (30, IMG_HEIGHT - 30)], fill=theme["accent"], width=2)
    draw.line([(IMG_WIDTH - 30, 30), (IMG_WIDTH - 30, IMG_HEIGHT - 30)], fill=theme["accent"], width=2)

    font_name = random.choice(["NanumBrush", "NanumPen"])
    font, lines, fsize = _adjust_font_size(
        text, font_name, IMG_WIDTH - 120, IMG_HEIGHT - 60, draw,
        size_range=[52, 48, 44, 40, 36, 32]
    )

    total_h = 0
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        total_h += h
    total_h += (len(lines) - 1) * 10

    y = (IMG_HEIGHT - total_h) // 2
    text_color = theme["text"]
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (IMG_WIDTH - w) // 2
        # 그림자 + 볼드 효과
        draw.text((x + 2, y + 2), line, fill='#00000044', font=font)
        draw.text((x + 1, y), line, fill=text_color, font=font)
        draw.text((x, y + 1), line, fill=text_color, font=font)
        draw.text((x, y), line, fill=text_color, font=font)
        y += line_heights[i] + 10

    img.save(output_path, 'PNG', quality=95)
    return output_path


def _style_split_card(text, output_path, theme_index=0):
    """스타일 2: 좌우 분할 배너 (색상 블록 + 텍스트, 680x200)"""
    from PIL import Image, ImageDraw

    theme = _BG_THEMES[theme_index % len(_BG_THEMES)]
    img = Image.new('RGB', (IMG_WIDTH, IMG_HEIGHT), '#FFFFFF')
    draw = ImageDraw.Draw(img)

    split_x = int(IMG_WIDTH * 0.25)
    _draw_gradient(draw, split_x, IMG_HEIGHT, theme["grad_start"], theme["grad_end"])
    _draw_geometric_shapes(draw, split_x, IMG_HEIGHT, theme["accent"], count=3)
    overlay = _draw_decorative_circles(draw, IMG_WIDTH, IMG_HEIGHT, theme["accent"], count=3)
    img_rgba = img.convert('RGBA')
    img_rgba = Image.alpha_composite(img_rgba, overlay)
    img = img_rgba.convert('RGB')
    draw = ImageDraw.Draw(img)

    # 좌측 따옴표 장식
    quote_font = _get_font("NanumBrush", 80)
    draw.text((20, 30), "\u201c", fill=theme["text"], font=quote_font)

    right_bg = (248, 248, 250)
    draw.rectangle([split_x, 0, IMG_WIDTH, IMG_HEIGHT], fill=right_bg)

    text_area_w = IMG_WIDTH - split_x - 60
    font_name = random.choice(["NanumPen", "NanumBrush"])
    font, lines, fsize = _adjust_font_size(
        text, font_name, text_area_w, IMG_HEIGHT - 50, draw,
        size_range=[48, 44, 40, 36, 32, 28]
    )

    total_h = 0
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        total_h += h
    total_h += (len(lines) - 1) * 8

    y = (IMG_HEIGHT - total_h) // 2
    for i, line in enumerate(lines):
        x = split_x + 30
        draw.text((x, y), line, fill='#1a1a2e', font=font)
        y += line_heights[i] + 8

    # 하단 라인
    draw.line([(split_x + 30, IMG_HEIGHT - 20),
               (split_x + 30 + min(len(text) * 8, text_area_w - 20), IMG_HEIGHT - 20)],
              fill=theme["grad_start"], width=2)

    img.save(output_path, 'PNG', quality=95)
    return output_path


def _style_center_box(text, output_path, theme_index=0):
    """스타일 3: 패턴 배경 + 중앙 박스 배너 (680x200)"""
    from PIL import Image, ImageDraw

    theme = _BG_THEMES[theme_index % len(_BG_THEMES)]
    img = Image.new('RGB', (IMG_WIDTH, IMG_HEIGHT), theme["grad_end"])
    draw = ImageDraw.Draw(img)

    # 대각선 그라데이션 (간소화)
    for y in range(IMG_HEIGHT):
        for x in range(0, IMG_WIDTH, 4):
            ratio = (x / IMG_WIDTH * 0.5 + y / IMG_HEIGHT * 0.5)
            r = int(theme["grad_start"][0] + (theme["grad_end"][0] - theme["grad_start"][0]) * ratio)
            g = int(theme["grad_start"][1] + (theme["grad_end"][1] - theme["grad_start"][1]) * ratio)
            b = int(theme["grad_start"][2] + (theme["grad_end"][2] - theme["grad_start"][2]) * ratio)
            draw.line([(x, y), (x + 3, y)], fill=(r, g, b))

    # 도트 패턴 (간격 축소)
    for dx in range(0, IMG_WIDTH, 25):
        for dy in range(0, IMG_HEIGHT, 25):
            r, g, b = theme["accent"]
            draw.ellipse([dx - 1, dy - 1, dx + 1, dy + 1],
                         fill=(min(r, 255), min(g, 255), min(b, 255)))

    box_margin_x = 50
    box_margin_y = 25
    is_dark = sum(theme["grad_start"]) < 400
    if is_dark:
        box_color = (255, 255, 255)
        text_color = '#1a1a2e'
    else:
        box_color = (255, 255, 255)
        text_color = '#2c2c2c'

    draw.rectangle(
        [box_margin_x, box_margin_y, IMG_WIDTH - box_margin_x, IMG_HEIGHT - box_margin_y],
        fill=box_color, outline=None
    )

    text_area_w = IMG_WIDTH - box_margin_x * 2 - 40
    text_area_h = IMG_HEIGHT - box_margin_y * 2 - 20
    font_name = random.choice(["NanumPen", "NanumBrush"])
    font, lines, fsize = _adjust_font_size(
        text, font_name, text_area_w, text_area_h, draw,
        size_range=[48, 44, 40, 36, 32, 28]
    )

    total_h = 0
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        total_h += h
    total_h += (len(lines) - 1) * 8

    y = (IMG_HEIGHT - total_h) // 2
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (IMG_WIDTH - w) // 2
        # 볼드 효과: 1px 오프셋으로 겹쳐 그려서 글자 두께 보강
        draw.text((x + 1, y), line, fill=text_color, font=font)
        draw.text((x, y + 1), line, fill=text_color, font=font)
        draw.text((x, y), line, fill=text_color, font=font)
        y += line_heights[i] + 8

    # 상단 액센트 라인
    draw.rectangle(
        [box_margin_x, box_margin_y, IMG_WIDTH - box_margin_x, box_margin_y + 3],
        fill=theme["accent"]
    )

    img.save(output_path, 'PNG', quality=95)
    return output_path


# 스타일 함수 목록 (윤웅채 - 손글씨 스타일)
_STYLES = [_style_gradient_card, _style_split_card, _style_center_box]


# ── 테헤란 공식 블로그 스타일 (토스/뱅크샐러드 감성 블루 카드) ─────────────
# 참고: 굵은 타이포, 블루 단색/그라디언트 배경, 3D 기하학 장식, 미니멀 레이아웃
_MODERN_THEMES = [
    # 딥 블루 그라디언트 (진한 파랑→중간 파랑)
    {"grad_start": (25, 60, 200), "grad_end": (50, 100, 240),
     "text": "#FFFFFF", "deco": (80, 140, 255), "name": "deep_blue"},
    # 로열 블루 (균일 톤)
    {"grad_start": (40, 80, 220), "grad_end": (30, 70, 200),
     "text": "#FFFFFF", "deco": (100, 160, 255), "name": "royal_blue"},
    # 라이트 블루 (밝은 배경 + 진한 텍스트)
    {"grad_start": (225, 235, 250), "grad_end": (205, 220, 245),
     "text": "#1A3A6B", "deco": (80, 130, 220), "name": "light_blue"},
    # 다크 네이비
    {"grad_start": (15, 25, 55), "grad_end": (25, 40, 80),
     "text": "#FFFFFF", "deco": (50, 120, 255), "name": "dark_navy"},
    # 스카이 그라디언트 (위: 흰색 → 아래: 연파랑)
    {"grad_start": (240, 245, 255), "grad_end": (190, 210, 245),
     "text": "#1A3060", "deco": (70, 120, 210), "name": "sky_gradient"},
]


def _hex_to_rgb(hex_color):
    """HEX 색상 → RGB 튜플"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def _draw_3d_half_circle(draw, cx, cy, radius, color, alpha_draw=None):
    """3D 느낌의 반원/원형 장식 (그라디언트 효과)"""
    # 메인 원
    r, g, b = color
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=(r, g, b)
    )
    # 하이라이트 (밝은 부분 - 3D 느낌)
    highlight_r = int(radius * 0.7)
    hr = min(255, r + 50)
    hg = min(255, g + 50)
    hb = min(255, b + 50)
    draw.ellipse(
        [cx - highlight_r, cy - highlight_r - int(radius * 0.15),
         cx + int(highlight_r * 0.6), cy + int(highlight_r * 0.6)],
        fill=(hr, hg, hb)
    )


def _draw_diagonal_stripe(draw, width, height, color, stripe_width=60, gap=80):
    """대각선 스트라이프 장식 (레퍼런스 이미지 3번 스타일)"""
    r, g, b = color
    for offset in range(-height, width + height, gap):
        points = [
            (offset, 0),
            (offset + stripe_width, 0),
            (offset + stripe_width - height, height),
            (offset - height, height),
        ]
        draw.polygon(points, fill=(r, g, b))


def _draw_folded_shape(draw, x, y, size, color):
    """접힌 종이 느낌의 기하학 장식 (레퍼런스 이미지 1번 스타일)"""
    r, g, b = color
    # 왼쪽 반 (어두운)
    draw.polygon([
        (x, y - size),
        (x, y + size),
        (x - int(size * 0.8), y)
    ], fill=(max(0, r - 30), max(0, g - 30), max(0, b - 30)))
    # 오른쪽 반 (밝은)
    draw.polygon([
        (x, y - size),
        (x, y + size),
        (x + int(size * 0.8), y)
    ], fill=(min(255, r + 20), min(255, g + 20), min(255, b + 20)))


def _style_bold_blue(text, output_path, theme_index=0):
    """모던 스타일 1: 볼드 블루 그라디언트 + 대형 백색 타이포 + 대각선 스트라이프"""
    from PIL import Image, ImageDraw
    W, H = MODERN_WIDTH, MODERN_HEIGHT
    BRAND_H = 30  # 하단 브랜딩 영역 높이

    theme = _MODERN_THEMES[theme_index % len(_MODERN_THEMES)]
    img = Image.new('RGB', (W, H), theme["grad_start"])
    draw = ImageDraw.Draw(img)

    _draw_gradient(draw, W, H, theme["grad_start"], theme["grad_end"])

    # 우측에 대각선 스트라이프 장식
    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    dr, dg, db = theme["deco"]
    stripe_start = int(W * 0.55)
    for offset in range(-H, W, 50):
        points = [
            (stripe_start + offset, 0),
            (stripe_start + offset + 30, 0),
            (stripe_start + offset + 30 - H, H),
            (stripe_start + offset - H, H),
        ]
        od.polygon(points, fill=(dr, dg, db, 25))

    img_rgba = img.convert('RGBA')
    img_rgba = Image.alpha_composite(img_rgba, overlay)
    img = img_rgba.convert('RGB')
    draw = ImageDraw.Draw(img)

    # 볼드 텍스트 (크게, 좌측 정렬)
    font, lines, fsize = _adjust_font_size(
        text, "PretendardBold", W - 100, H - BRAND_H - 40, draw,
        size_range=[56, 52, 48, 44, 40, 36, 32]
    )

    text_color = theme["text"]
    total_h = 0
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        total_h += h
    total_h += (len(lines) - 1) * 8

    # 브랜딩 영역 제외하고 정중앙 배치
    y = (H - BRAND_H - total_h) // 2
    for i, line in enumerate(lines):
        x = 50
        draw.text((x, y), line, fill=text_color, font=font)
        y += line_heights[i] + 8

    # 좌하단 브랜딩
    brand_font = _get_font("Pretendard", 12)
    draw.text((50, H - 22), "특허법인 테헤란", fill=text_color, font=brand_font)

    img.save(output_path, 'PNG', quality=95)
    return output_path


def _style_dark_3d(text, output_path, theme_index=0):
    """모던 스타일 2: 다크 배경 + 3D 기하학 장식 + 굵은 백색 텍스트"""
    from PIL import Image, ImageDraw
    W, H = MODERN_WIDTH, MODERN_HEIGHT
    BRAND_H = 30

    dark_themes = [t for t in _MODERN_THEMES if "dark" in t["name"] or "deep" in t["name"]]
    theme = dark_themes[theme_index % len(dark_themes)] if dark_themes else _MODERN_THEMES[0]

    img = Image.new('RGB', (W, H), theme["grad_start"])
    draw = ImageDraw.Draw(img)
    _draw_gradient(draw, W, H, theme["grad_start"], theme["grad_end"])

    # 3D 접힌 도형 장식 (상단 영역)
    deco_color = theme["deco"]
    cx = W // 2
    cy = int(H * 0.3)
    shape_size = random.randint(50, 70)

    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    r1 = shape_size
    od.pieslice(
        [cx - r1, cy - r1, cx + r1, cy + r1],
        start=180, end=360,
        fill=(*deco_color, 180)
    )
    r2 = int(shape_size * 0.6)
    lighter = tuple(min(255, c + 40) for c in deco_color)
    od.pieslice(
        [cx - r2 + 15, cy - r2, cx + r2 + 15, cy + r2],
        start=0, end=180,
        fill=(*lighter, 200)
    )

    img_rgba = img.convert('RGBA')
    img_rgba = Image.alpha_composite(img_rgba, overlay)
    img = img_rgba.convert('RGB')
    draw = ImageDraw.Draw(img)

    # 텍스트 (정중앙, 브랜딩 영역 제외)
    font, lines, fsize = _adjust_font_size(
        text, "PretendardBold", W - 120, H - BRAND_H - 40, draw,
        size_range=[52, 48, 44, 40, 36, 32, 28]
    )

    total_h = 0
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        total_h += h
    total_h += (len(lines) - 1) * 8

    y = (H - BRAND_H - total_h) // 2
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (W - w) // 2
        draw.text((x, y), line, fill="#FFFFFF", font=font)
        y += line_heights[i] + 8

    brand_font = _get_font("Pretendard", 12)
    draw.text((45, H - 22), "특허법인 테헤란", fill="#FFFFFF", font=brand_font)

    img.save(output_path, 'PNG', quality=95)
    return output_path


def _style_corporate_light(text, output_path, theme_index=0):
    """모던 스타일 3: 라이트 블루 배경 + 진한 블루 텍스트 + 원형 글로우"""
    from PIL import Image, ImageDraw
    W, H = MODERN_WIDTH, MODERN_HEIGHT
    BRAND_H = 30

    light_themes = [t for t in _MODERN_THEMES if "light" in t["name"] or "sky" in t["name"]]
    theme = light_themes[theme_index % len(light_themes)] if light_themes else _MODERN_THEMES[2]

    img = Image.new('RGB', (W, H), theme["grad_start"])
    draw = ImageDraw.Draw(img)
    _draw_gradient(draw, W, H, theme["grad_start"], theme["grad_end"])

    # 배경에 큰 원형 글로우
    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    glow_r = 200
    glow_cx = W // 2
    glow_cy = -50
    for i in range(glow_r, 0, -3):
        alpha = max(2, int(15 * (i / glow_r)))
        dr, dg, db = theme["deco"]
        od.ellipse(
            [glow_cx - i, glow_cy - i, glow_cx + i, glow_cy + i],
            fill=(dr, dg, db, alpha)
        )

    img_rgba = img.convert('RGBA')
    img_rgba = Image.alpha_composite(img_rgba, overlay)
    img = img_rgba.convert('RGB')
    draw = ImageDraw.Draw(img)

    # 텍스트 (정중앙, 브랜딩 영역 제외)
    font, lines, fsize = _adjust_font_size(
        text, "PretendardBold", W - 100, H - BRAND_H - 40, draw,
        size_range=[52, 48, 44, 40, 36, 32, 28]
    )

    text_color = theme["text"]
    total_h = 0
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        total_h += h
    total_h += (len(lines) - 1) * 10

    y = (H - BRAND_H - total_h) // 2
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (W - w) // 2
        draw.text((x, y), line, fill=text_color, font=font)
        y += line_heights[i] + 10

    brand_font = _get_font("Pretendard", 12)
    brand_color = theme["text"] if isinstance(theme["text"], str) else "#333333"
    draw.text((45, H - 22), "특허법인 테헤란", fill=brand_color, font=brand_font)

    img.save(output_path, 'PNG', quality=95)
    return output_path


def _style_gradient_bar(text, output_path, theme_index=0):
    """모던 스타일 4: 블루 그라디언트 + 좌측 굵은 텍스트 + 우측 반원 장식"""
    from PIL import Image, ImageDraw
    W, H = MODERN_WIDTH, MODERN_HEIGHT
    BRAND_H = 30

    theme = _MODERN_THEMES[theme_index % len(_MODERN_THEMES)]
    img = Image.new('RGB', (W, H), theme["grad_start"])
    draw = ImageDraw.Draw(img)
    _draw_gradient(draw, W, H, theme["grad_start"], theme["grad_end"], direction="horizontal")

    # 우측에 큰 반원 장식
    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    circle_r = H
    cx = W + int(circle_r * 0.3)
    cy = H // 2
    dr, dg, db = theme["deco"]
    od.ellipse(
        [cx - circle_r, cy - circle_r, cx + circle_r, cy + circle_r],
        fill=(dr, dg, db, 40)
    )
    r2 = int(circle_r * 0.4)
    od.ellipse(
        [cx - circle_r - r2, cy - r2 + 20, cx - circle_r + r2, cy + r2 + 20],
        fill=(dr, dg, db, 60)
    )

    img_rgba = img.convert('RGBA')
    img_rgba = Image.alpha_composite(img_rgba, overlay)
    img = img_rgba.convert('RGB')
    draw = ImageDraw.Draw(img)

    # 좌측 굵은 텍스트 (정중앙, 브랜딩 영역 제외)
    font, lines, fsize = _adjust_font_size(
        text, "PretendardBold", int(W * 0.65), H - BRAND_H - 40, draw,
        size_range=[52, 48, 44, 40, 36, 32]
    )

    text_color = theme["text"]
    total_h = 0
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        total_h += h
    total_h += (len(lines) - 1) * 8

    y = (H - BRAND_H - total_h) // 2
    for i, line in enumerate(lines):
        x = 45
        draw.text((x, y), line, fill=text_color, font=font)
        y += line_heights[i] + 8

    brand_font = _get_font("Pretendard", 12)
    draw.text((45, H - 22), "특허법인 테헤란", fill=text_color, font=brand_font)

    img.save(output_path, 'PNG', quality=95)
    return output_path


# 모던 스타일 함수 목록 (테헤란 공식 블로그)
_MODERN_STYLES = [_style_bold_blue, _style_dark_3d, _style_corporate_light, _style_gradient_bar]


def generate_handwriting_image(text, output_path, style_index=None):
    """
    소제목 텍스트를 가로형 배너 이미지로 생성 (680x200)
    """
    if style_index is None:
        style_idx = random.randint(0, len(_STYLES) - 1)
    else:
        style_idx = style_index % len(_STYLES)

    theme_idx = (style_index or 0) % len(_BG_THEMES)
    return _STYLES[style_idx](text, output_path, theme_index=theme_idx)


def generate_modern_image(text, output_path, style_index=None):
    """
    소제목 텍스트를 모던 블루 카드 이미지로 생성 (680x270)
    토스/뱅크샐러드 감성: 굵은 타이포 + 블루 계열 + 3D 기하학 장식
    """
    if style_index is None:
        style_idx = random.randint(0, len(_MODERN_STYLES) - 1)
    else:
        style_idx = style_index % len(_MODERN_STYLES)

    theme_idx = (style_index or 0) % len(_MODERN_THEMES)
    return _MODERN_STYLES[style_idx](text, output_path, theme_index=theme_idx)


def generate_blog_images(topic, content="", image_count=None, user_image_paths=None, persona_id=None):
    """
    블로그 본문 이미지 생성 (PIL 가로형 배너 이미지)

    소제목을 추출하여 가로형 배너 텍스트 이미지를 생성합니다.
    image_count=None이면 소제목 개수에 맞춰 자동 결정.
    """
    body_images = []

    # 먼저 소제목 추출 → 이미지 개수 자동 결정
    subtitles = _extract_subtitles(content)

    # image_count가 None이면 소제목 수에 맞춤, 지정 시 해당 값 사용
    actual_count = len(subtitles) if (image_count is None and subtitles) else (image_count or 4)

    if user_image_paths:
        for path in user_image_paths[:actual_count]:
            body_images.append({
                "url": path,
                "alt": f"{topic} 관련 이미지",
                "source": "user_upload",
            })

    remaining = actual_count - len(body_images)
    if remaining <= 0:
        return {"body_images": body_images, "total_count": len(body_images)}

    if not subtitles:
        subtitles = _extract_key_sentences(content, topic, remaining)
    if not subtitles:
        subtitles = [topic]

    logger.info(f"이미지 생성: 소제목 {len(subtitles)}개 → 이미지 {actual_count}장")

    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "outputs", "images"
    )
    os.makedirs(output_dir, exist_ok=True)

    ensure_fonts()

    # persona에 따라 이미지 스타일 결정
    use_modern = persona_id and persona_id in ("teheran_official",)
    gen_func = generate_modern_image if use_modern else generate_handwriting_image
    style_label = "modern" if use_modern else "handwriting"

    for i in range(remaining):
        subtitle_text = subtitles[i] if i < len(subtitles) else subtitles[i % len(subtitles)]
        filename = f"{style_label}_{i+1}_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join(output_dir, filename)

        try:
            gen_func(subtitle_text, filepath, style_index=i)
            body_images.append({
                "url": os.path.abspath(filepath),
                "alt": subtitle_text,
                "source": f"pil_{style_label}",
            })
            logger.info(f"카드 이미지 생성 ({style_label}): {filepath}")
        except Exception as e:
            logger.error(f"카드 이미지 생성 실패 [{i}]: {e}")
            body_images.append({
                "url": _get_placeholder_url(text=f"Image+{i+1}"),
                "alt": f"본문 이미지 {i+1}",
                "source": "placeholder",
            })

    return {
        "body_images": body_images,
        "total_count": len(body_images),
    }


def download_dalle_images(image_data, output_dir="outputs/images"):
    """
    이미지를 로컬 파일로 다운로드 (PIL 이미지는 이미 로컬이므로 경로만 반환)

    Args:
        image_data: generate_blog_images() 반환값
        output_dir: 저장 디렉토리

    Returns:
        list[str]: 로컬 파일 경로 리스트
    """
    os.makedirs(output_dir, exist_ok=True)
    local_paths = []

    body_images = image_data.get("body_images", [])
    for i, img in enumerate(body_images):
        url = img.get("url", "")
        source = img.get("source", "")

        if not url or source == "placeholder":
            local_paths.append(None)
            continue

        # PIL 이미지 → 이미 로컬 파일
        if source in ("pil_handwriting", "pil_modern"):
            if os.path.exists(url):
                local_paths.append(url)
                logger.info(f"PIL 이미지 사용: {url}")
            else:
                local_paths.append(None)
            continue

        # 사용자 업로드 → 이미 로컬 파일
        if source == "user_upload":
            if os.path.exists(url):
                local_paths.append(os.path.abspath(url))
            else:
                local_paths.append(None)
            continue

        # DALL-E 또는 외부 URL → 다운로드
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()

            ext = "png"
            ct = resp.headers.get("content-type", "")
            if "jpeg" in ct or "jpg" in ct:
                ext = "jpg"
            elif "webp" in ct:
                ext = "webp"

            filename = f"blog_img_{i+1}_{uuid.uuid4().hex[:8]}.{ext}"
            filepath = os.path.join(output_dir, filename)

            with open(filepath, "wb") as f:
                f.write(resp.content)

            local_paths.append(os.path.abspath(filepath))
            logger.info(f"이미지 다운로드 완료: {filepath} ({len(resp.content)} bytes)")

        except Exception as e:
            logger.error(f"이미지 다운로드 실패 [{i}]: {e}")
            local_paths.append(None)

    return local_paths


def _get_placeholder_url(width=800, height=400, text="Blog Image"):
    """플레이스홀더 이미지 URL 생성"""
    safe_text = text.replace(" ", "+")[:30]
    return f"https://placehold.co/{width}x{height}/e8e8e8/333?text={safe_text}"


def generate_thumbnail(topic, subtitle="", preset="dark_minimal"):
    """썸네일 이미지 생성 (PIL 카드형 스타일)"""
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "outputs", "images"
    )
    os.makedirs(output_dir, exist_ok=True)

    filepath = os.path.join(output_dir, f"thumb_{uuid.uuid4().hex[:8]}.png")

    try:
        generate_handwriting_image(topic[:30], filepath, style_index=0)
        return {
            "url": os.path.abspath(filepath),
            "alt": topic,
            "preset": preset,
            "source": "pil_handwriting",
        }
    except Exception:
        return {
            "url": _get_placeholder_url(1200, 630, topic[:15]),
            "alt": topic,
            "preset": preset,
            "source": "placeholder",
        }
