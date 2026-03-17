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

# 가로형 배너 이미지 크기 (3.4:1 비율)
IMG_WIDTH = 680
IMG_HEIGHT = 200


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
    {"grad_start": (240, 240, 245), "grad_end": (220, 225, 235), "text": "#1a1a2e",
     "accent": (100, 120, 180), "name": "light_gray"},
    {"grad_start": (250, 248, 240), "grad_end": (235, 230, 220), "text": "#2c2c2c",
     "accent": (180, 150, 100), "name": "warm_ivory"},
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
        draw.text((x + 1, y + 1), line, fill='#00000044', font=font)
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
        box_color = theme["grad_start"]
        text_color = '#FFFFFF'

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


# ── 토스 스타일 테마 (모던/세련된 파스텔 컬러) ─────────────
_TOSS_THEMES = [
    {"bg": (248, 249, 253), "accent": (51, 102, 255), "text": "#191F28",
     "sub": "#8B95A1", "pill_bg": (232, 240, 254), "name": "toss_blue"},
    {"bg": (245, 248, 245), "accent": (60, 180, 110), "text": "#191F28",
     "sub": "#8B95A1", "pill_bg": (230, 245, 235), "name": "toss_green"},
    {"bg": (253, 247, 244), "accent": (255, 100, 50), "text": "#191F28",
     "sub": "#8B95A1", "pill_bg": (254, 237, 230), "name": "toss_coral"},
    {"bg": (247, 245, 253), "accent": (120, 80, 220), "text": "#191F28",
     "sub": "#8B95A1", "pill_bg": (237, 230, 254), "name": "toss_purple"},
    {"bg": (255, 255, 255), "accent": (51, 102, 255), "text": "#191F28",
     "sub": "#8B95A1", "pill_bg": (245, 246, 248), "name": "toss_white"},
    {"bg": (30, 33, 40), "accent": (51, 145, 255), "text": "#FFFFFF",
     "sub": "#8B95A1", "pill_bg": (45, 50, 60), "name": "toss_dark"},
]


def _hex_to_rgb(hex_color):
    """HEX 색상 → RGB 튜플"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def _draw_rounded_rect(draw, xy, radius, fill=None, outline=None, width=1):
    """라운드 사각형 그리기"""
    x1, y1, x2, y2 = xy
    # PIL의 rounded_rectangle (Pillow 8.2+)
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)
    except AttributeError:
        # fallback: 일반 사각형
        draw.rectangle(xy, fill=fill, outline=outline, width=width)


def _style_toss_clean(text, output_path, theme_index=0):
    """토스 스타일 1: 클린 미니멀 카드 (배경색 + 중앙 텍스트 + 좌측 액센트 라인)"""
    from PIL import Image, ImageDraw

    theme = _TOSS_THEMES[theme_index % len(_TOSS_THEMES)]
    img = Image.new('RGB', (IMG_WIDTH, IMG_HEIGHT), theme["bg"])
    draw = ImageDraw.Draw(img)

    # 좌측 액센트 바 (4px, 라운드)
    bar_x = 40
    draw.rectangle([bar_x, 50, bar_x + 4, IMG_HEIGHT - 50], fill=theme["accent"])

    # 하단 미세 라인
    draw.line([(60, IMG_HEIGHT - 35), (IMG_WIDTH - 60, IMG_HEIGHT - 35)],
              fill=(*_hex_to_rgb(theme["sub"]), 40) if isinstance(theme["sub"], str) else theme["sub"],
              width=1)

    # 텍스트
    font_name = "Pretendard"
    font, lines, fsize = _adjust_font_size(
        text, font_name, IMG_WIDTH - 140, IMG_HEIGHT - 80, draw,
        size_range=[44, 40, 36, 32, 28, 24]
    )

    text_color = theme["text"]
    total_h = sum(draw.textbbox((0, 0), line, font=font)[3] - draw.textbbox((0, 0), line, font=font)[1] for line in lines)
    total_h += (len(lines) - 1) * 12

    y = (IMG_HEIGHT - total_h) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        x = 70  # 좌측 정렬 (토스 스타일)
        draw.text((x, y), line, fill=text_color, font=font)
        y += h + 12

    img.save(output_path, 'PNG', quality=95)
    return output_path


def _style_toss_pill(text, output_path, theme_index=0):
    """토스 스타일 2: 필 카드 (라운드 배경 + 아이콘 느낌의 장식)"""
    from PIL import Image, ImageDraw

    theme = _TOSS_THEMES[theme_index % len(_TOSS_THEMES)]
    img = Image.new('RGB', (IMG_WIDTH, IMG_HEIGHT), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 중앙에 라운드 배경 카드
    card_margin_x = 30
    card_margin_y = 20
    _draw_rounded_rect(draw,
        [card_margin_x, card_margin_y, IMG_WIDTH - card_margin_x, IMG_HEIGHT - card_margin_y],
        radius=20, fill=theme["bg"])

    # 상단 좌측에 작은 pill 배지 (액센트 색)
    pill_text = "KEY POINT"
    pill_font = _get_font("Pretendard", 14)
    pill_bbox = draw.textbbox((0, 0), pill_text, font=pill_font)
    pill_w = pill_bbox[2] - pill_bbox[0] + 20
    pill_h = pill_bbox[3] - pill_bbox[1] + 10
    pill_x = 55
    pill_y = 38
    _draw_rounded_rect(draw,
        [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
        radius=pill_h // 2, fill=theme["accent"])
    draw.text((pill_x + 10, pill_y + 3), pill_text, fill="#FFFFFF", font=pill_font)

    # 메인 텍스트 (pill 아래)
    font_name = "PretendardBold"
    font, lines, fsize = _adjust_font_size(
        text, font_name, IMG_WIDTH - 140, IMG_HEIGHT - 100, draw,
        size_range=[40, 36, 32, 28, 24, 20]
    )

    text_color = theme["text"]
    total_h = sum(draw.textbbox((0, 0), line, font=font)[3] - draw.textbbox((0, 0), line, font=font)[1] for line in lines)
    total_h += (len(lines) - 1) * 10

    y = pill_y + pill_h + 20
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        x = 55
        draw.text((x, y), line, fill=text_color, font=font)
        y += h + 10

    # 우측 하단에 작은 도트 장식
    dot_colors = [theme["accent"], (*theme["accent"][:2], min(255, theme["accent"][2] + 60))]
    for i, dc in enumerate(dot_colors):
        cx = IMG_WIDTH - 70 - i * 18
        cy = IMG_HEIGHT - 50
        draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=dc)

    img.save(output_path, 'PNG', quality=95)
    return output_path


def _style_toss_gradient_soft(text, output_path, theme_index=0):
    """토스 스타일 3: 소프트 그라데이션 + 중앙 정렬 텍스트"""
    from PIL import Image, ImageDraw

    theme = _TOSS_THEMES[theme_index % len(_TOSS_THEMES)]
    img = Image.new('RGB', (IMG_WIDTH, IMG_HEIGHT), theme["bg"])
    draw = ImageDraw.Draw(img)

    # 소프트 그라데이션 (액센트 색 → 배경색, 하단에서 상단으로)
    accent = theme["accent"]
    bg = theme["bg"]
    for y_pos in range(IMG_HEIGHT):
        ratio = y_pos / IMG_HEIGHT
        # 하단 20%에서만 액센트가 살짝 보이도록
        blend = max(0, (ratio - 0.7) / 0.3) * 0.08
        r = int(bg[0] * (1 - blend) + accent[0] * blend)
        g = int(bg[1] * (1 - blend) + accent[1] * blend)
        b = int(bg[2] * (1 - blend) + accent[2] * blend)
        draw.line([(0, y_pos), (IMG_WIDTH, y_pos)], fill=(r, g, b))

    # 상단 우측에 큰 반투명 원 (장식)
    overlay = Image.new('RGBA', (IMG_WIDTH, IMG_HEIGHT), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    circle_r = 120
    cx, cy = IMG_WIDTH - 80, -30
    od.ellipse([cx - circle_r, cy - circle_r, cx + circle_r, cy + circle_r],
               fill=(*accent, 15))
    circle_r2 = 60
    cx2, cy2 = 50, IMG_HEIGHT + 10
    od.ellipse([cx2 - circle_r2, cy2 - circle_r2, cx2 + circle_r2, cy2 + circle_r2],
               fill=(*accent, 12))
    img_rgba = img.convert('RGBA')
    img_rgba = Image.alpha_composite(img_rgba, overlay)
    img = img_rgba.convert('RGB')
    draw = ImageDraw.Draw(img)

    # 중앙 텍스트
    font_name = "PretendardBold"
    font, lines, fsize = _adjust_font_size(
        text, font_name, IMG_WIDTH - 120, IMG_HEIGHT - 60, draw,
        size_range=[44, 40, 36, 32, 28, 24]
    )

    text_color = theme["text"]
    total_h = sum(draw.textbbox((0, 0), line, font=font)[3] - draw.textbbox((0, 0), line, font=font)[1] for line in lines)
    total_h += (len(lines) - 1) * 12

    y = (IMG_HEIGHT - total_h) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (IMG_WIDTH - w) // 2
        draw.text((x, y), line, fill=text_color, font=font)
        y += h + 12

    # 하단 중앙 액센트 언더라인
    line_w = min(len(text) * 10, 200)
    draw.rectangle(
        [(IMG_WIDTH - line_w) // 2, IMG_HEIGHT - 25,
         (IMG_WIDTH + line_w) // 2, IMG_HEIGHT - 22],
        fill=theme["accent"]
    )

    img.save(output_path, 'PNG', quality=95)
    return output_path


# 토스 스타일 함수 목록 (테헤란 공식 블로그)
_TOSS_STYLES = [_style_toss_clean, _style_toss_pill, _style_toss_gradient_soft]


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
    소제목 텍스트를 토스 스타일 모던 카드 이미지로 생성 (680x200)
    """
    if style_index is None:
        style_idx = random.randint(0, len(_TOSS_STYLES) - 1)
    else:
        style_idx = style_index % len(_TOSS_STYLES)

    theme_idx = (style_index or 0) % len(_TOSS_THEMES)
    return _TOSS_STYLES[style_idx](text, output_path, theme_index=theme_idx)


def generate_blog_images(topic, content="", image_count=4, user_image_paths=None, persona_id=None):
    """
    블로그 본문 이미지 생성 (PIL 가로형 배너 이미지)

    소제목을 추출하여 가로형 배너 텍스트 이미지를 생성합니다.
    680x200 가로형 크기로 자연스러운 블로그 구분선 역할.
    """
    body_images = []

    if user_image_paths:
        for path in user_image_paths[:image_count]:
            body_images.append({
                "url": path,
                "alt": f"{topic} 관련 이미지",
                "source": "user_upload",
            })

    remaining = image_count - len(body_images)
    if remaining <= 0:
        return {"body_images": body_images, "total_count": len(body_images)}

    subtitles = _extract_subtitles(content)
    if not subtitles:
        # 소제목이 없으면 본문에서 핵심 문장 추출 (키워드 반복 방지)
        subtitles = _extract_key_sentences(content, topic, remaining)
    if not subtitles:
        subtitles = [topic]

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
