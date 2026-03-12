"""
이미지 핸들러 모듈
- 소제목 텍스트를 카드형 이미지로 렌더링 (PIL)
- 960x540 표준 블로그 이미지 크기 (네이버 이미지 인식 대응)
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
}

# 표준 블로그 이미지 크기 (16:9)
IMG_WIDTH = 960
IMG_HEIGHT = 540


def ensure_fonts():
    """폰트 자동 다운로드 (없으면)"""
    os.makedirs(FONT_DIR, exist_ok=True)
    available = {}
    for name, url in FONTS.items():
        path = os.path.join(FONT_DIR, f"{name}.ttf")
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


def _get_font(name, size):
    """PIL ImageFont 로드"""
    from PIL import ImageFont
    fonts = ensure_fonts()
    path = fonts.get(name)
    if path and os.path.exists(path):
        return ImageFont.truetype(path, size)
    try:
        return ImageFont.truetype("malgun.ttf", size)
    except OSError:
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
        alpha_color = (*color, random.randint(20, 50))

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
    """스타일 1: 그라데이션 배경 + 큰 텍스트 카드"""
    from PIL import Image, ImageDraw

    theme = _BG_THEMES[theme_index % len(_BG_THEMES)]
    img = Image.new('RGB', (IMG_WIDTH, IMG_HEIGHT), theme["grad_start"])
    draw = ImageDraw.Draw(img)

    # 그라데이션 배경
    _draw_gradient(draw, IMG_WIDTH, IMG_HEIGHT, theme["grad_start"], theme["grad_end"])

    # 장식 기하학 요소
    _draw_geometric_shapes(draw, IMG_WIDTH, IMG_HEIGHT, theme["accent"], count=8)

    # 장식 원 오버레이
    overlay = _draw_decorative_circles(draw, IMG_WIDTH, IMG_HEIGHT, theme["accent"], count=6)
    img_rgba = img.convert('RGBA')
    img_rgba = Image.alpha_composite(img_rgba, overlay)
    img = img_rgba.convert('RGB')
    draw = ImageDraw.Draw(img)

    # 중앙 반투명 카드 영역
    card_margin = 80
    card_y1 = 100
    card_y2 = IMG_HEIGHT - 100
    for y in range(card_y1, card_y2):
        alpha = 30
        r, g, b = theme["grad_start"]
        draw.line([(card_margin, y), (IMG_WIDTH - card_margin, y)],
                  fill=(min(r + 30, 255), min(g + 30, 255), min(b + 30, 255)))

    # 텍스트
    font_name = random.choice(["NanumBrush", "NanumPen"])
    font, lines, fsize = _adjust_font_size(
        text, font_name, IMG_WIDTH - 200, 240, draw,
        size_range=[72, 64, 58, 52, 48, 44]
    )

    # 텍스트 중앙 배치
    total_h = 0
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        total_h += h
    total_h += (len(lines) - 1) * 16

    y = (IMG_HEIGHT - total_h) // 2
    text_color = theme["text"]
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (IMG_WIDTH - w) // 2
        # 그림자
        draw.text((x + 2, y + 2), line, fill='#00000044', font=font)
        draw.text((x, y), line, fill=text_color, font=font)
        y += line_heights[i] + 16

    # 하단 가는 선 장식
    line_w = min(len(text) * 14, IMG_WIDTH - 200)
    x_start = (IMG_WIDTH - line_w) // 2
    draw.line([(x_start, IMG_HEIGHT - 80), (x_start + line_w, IMG_HEIGHT - 80)],
              fill=theme["text"], width=2)

    img.save(output_path, 'PNG', quality=95)
    return output_path


def _style_split_card(text, output_path, theme_index=0):
    """스타일 2: 좌우 분할 카드 (색상 블록 + 텍스트)"""
    from PIL import Image, ImageDraw

    theme = _BG_THEMES[theme_index % len(_BG_THEMES)]
    img = Image.new('RGB', (IMG_WIDTH, IMG_HEIGHT), '#FFFFFF')
    draw = ImageDraw.Draw(img)

    # 왼쪽 40% 색상 블록
    split_x = int(IMG_WIDTH * 0.38)
    _draw_gradient(draw, split_x, IMG_HEIGHT, theme["grad_start"], theme["grad_end"])

    # 왼쪽 블록에 장식
    _draw_geometric_shapes(draw, split_x, IMG_HEIGHT, theme["accent"], count=6)
    overlay = _draw_decorative_circles(draw, IMG_WIDTH, IMG_HEIGHT, theme["accent"], count=4)
    img_rgba = img.convert('RGBA')
    img_rgba = Image.alpha_composite(img_rgba, overlay)
    img = img_rgba.convert('RGB')
    draw = ImageDraw.Draw(img)

    # 왼쪽 블록에 큰 따옴표 장식
    quote_font = _get_font("NanumBrush", 140)
    draw.text((40, 60), "\u201c", fill=theme["text"], font=quote_font)

    # 오른쪽 영역: 연한 배경
    right_bg = (248, 248, 250)
    draw.rectangle([split_x, 0, IMG_WIDTH, IMG_HEIGHT], fill=right_bg)

    # 오른쪽에 미세 패턴
    for _ in range(300):
        rx = random.randint(split_x, IMG_WIDTH - 1)
        ry = random.randint(0, IMG_HEIGHT - 1)
        gray = random.randint(235, 248)
        draw.point((rx, ry), fill=(gray, gray, gray))

    # 텍스트 (오른쪽 영역)
    text_area_w = IMG_WIDTH - split_x - 100
    font_name = random.choice(["NanumPen", "NanumBrush"])
    font, lines, fsize = _adjust_font_size(
        text, font_name, text_area_w, 300, draw,
        size_range=[64, 58, 52, 48, 44, 40]
    )

    total_h = 0
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        total_h += h
    total_h += (len(lines) - 1) * 14

    y = (IMG_HEIGHT - total_h) // 2
    for i, line in enumerate(lines):
        x = split_x + 50
        draw.text((x, y), line, fill='#1a1a2e', font=font)
        y += line_heights[i] + 14

    # 오른쪽 하단에 장식 라인
    draw.line([(split_x + 50, IMG_HEIGHT - 70),
               (split_x + 50 + min(len(text) * 10, text_area_w - 20), IMG_HEIGHT - 70)],
              fill=theme["grad_start"], width=3)

    img.save(output_path, 'PNG', quality=95)
    return output_path


def _style_center_box(text, output_path, theme_index=0):
    """스타일 3: 패턴 배경 + 중앙 박스 카드"""
    from PIL import Image, ImageDraw

    theme = _BG_THEMES[theme_index % len(_BG_THEMES)]
    img = Image.new('RGB', (IMG_WIDTH, IMG_HEIGHT), theme["grad_end"])
    draw = ImageDraw.Draw(img)

    # 대각선 그라데이션 시뮬레이션
    for y in range(IMG_HEIGHT):
        for x in range(0, IMG_WIDTH, 4):
            ratio = (x / IMG_WIDTH * 0.5 + y / IMG_HEIGHT * 0.5)
            r = int(theme["grad_start"][0] + (theme["grad_end"][0] - theme["grad_start"][0]) * ratio)
            g = int(theme["grad_start"][1] + (theme["grad_end"][1] - theme["grad_start"][1]) * ratio)
            b = int(theme["grad_start"][2] + (theme["grad_end"][2] - theme["grad_start"][2]) * ratio)
            draw.line([(x, y), (x + 3, y)], fill=(r, g, b))

    # 도트 패턴
    for dx in range(0, IMG_WIDTH, 30):
        for dy in range(0, IMG_HEIGHT, 30):
            alpha = random.randint(5, 20)
            r, g, b = theme["accent"]
            draw.ellipse([dx - 2, dy - 2, dx + 2, dy + 2],
                         fill=(min(r, 255), min(g, 255), min(b, 255)))

    # 중앙 흰색/반투명 박스
    box_margin_x = 100
    box_margin_y = 80
    # 박스 배경 (연한색)
    is_dark = sum(theme["grad_start"]) < 400
    if is_dark:
        box_color = (255, 255, 255)
        text_color = '#1a1a2e'
    else:
        box_color = theme["grad_start"]
        text_color = '#FFFFFF'

    # 라운드 사각형 대신 일반 사각형 + 테두리
    draw.rectangle(
        [box_margin_x, box_margin_y, IMG_WIDTH - box_margin_x, IMG_HEIGHT - box_margin_y],
        fill=box_color, outline=None
    )

    # 박스 안 텍스트
    text_area_w = IMG_WIDTH - box_margin_x * 2 - 80
    text_area_h = IMG_HEIGHT - box_margin_y * 2 - 60
    font_name = random.choice(["NanumPen", "NanumBrush"])
    font, lines, fsize = _adjust_font_size(
        text, font_name, text_area_w, text_area_h, draw,
        size_range=[68, 62, 56, 50, 46, 42]
    )

    total_h = 0
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        total_h += h
    total_h += (len(lines) - 1) * 14

    y = (IMG_HEIGHT - total_h) // 2
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (IMG_WIDTH - w) // 2
        draw.text((x, y), line, fill=text_color, font=font)
        y += line_heights[i] + 14

    # 박스 상단 악센트 라인
    draw.rectangle(
        [box_margin_x, box_margin_y, IMG_WIDTH - box_margin_x, box_margin_y + 4],
        fill=theme["accent"]
    )

    img.save(output_path, 'PNG', quality=95)
    return output_path


# 스타일 함수 목록
_STYLES = [_style_gradient_card, _style_split_card, _style_center_box]


def generate_handwriting_image(text, output_path, style_index=None):
    """
    소제목 텍스트를 카드형 이미지로 생성 (960x540)

    Args:
        text: 소제목 텍스트
        output_path: 저장 경로
        style_index: 스타일 인덱스 (None이면 랜덤)

    Returns:
        str: 저장된 파일 경로
    """
    if style_index is None:
        style_idx = random.randint(0, len(_STYLES) - 1)
    else:
        style_idx = style_index % len(_STYLES)

    # 테마도 이미지마다 다르게
    theme_idx = (style_index or 0) % len(_BG_THEMES)

    return _STYLES[style_idx](text, output_path, theme_index=theme_idx)


def generate_blog_images(topic, content="", image_count=4, user_image_paths=None):
    """
    블로그 본문 이미지 생성 (PIL 카드형 이미지)

    소제목을 추출하여 카드형 텍스트 이미지를 생성합니다.
    960x540 표준 크기로 네이버 이미지 인식 대응.

    Args:
        topic: 주제
        content: 칼럼 본문 (소제목 추출용)
        image_count: 생성할 이미지 수
        user_image_paths: 사용자 업로드 이미지 경로 목록

    Returns:
        dict: {
            'body_images': list[dict],
            'total_count': int,
        }
    """
    body_images = []

    # 사용자 이미지가 있으면 우선 사용
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

    # 소제목 추출
    subtitles = _extract_subtitles(content)
    if not subtitles:
        subtitles = [topic]

    # 출력 디렉토리
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "outputs", "images"
    )
    os.makedirs(output_dir, exist_ok=True)

    # 폰트 미리 다운로드
    ensure_fonts()

    for i in range(remaining):
        subtitle_text = subtitles[i] if i < len(subtitles) else subtitles[i % len(subtitles)]

        filename = f"handwriting_{i+1}_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join(output_dir, filename)

        try:
            generate_handwriting_image(subtitle_text, filepath, style_index=i)
            body_images.append({
                "url": os.path.abspath(filepath),
                "alt": subtitle_text,
                "source": "pil_handwriting",
            })
            logger.info(f"카드 이미지 생성: {filepath}")
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
        if source == "pil_handwriting":
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
    """
    썸네일 이미지 생성 (PIL 카드형 스타일)

    Args:
        topic: 제목
        subtitle: 부제목
        preset: 스타일 프리셋

    Returns:
        dict: {'url': str, 'alt': str, 'preset': str}
    """
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
