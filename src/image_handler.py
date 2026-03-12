"""
이미지 핸들러 모듈
- 소제목 텍스트를 손글씨 스타일로 렌더링한 PIL 이미지 생성
- 680x200 가로형 직사각형
- NanumPen / NanumBrush 폰트 자동 다운로드
- DALL-E 레거시 지원 유지
"""

import os
import re
import logging
import random
import uuid
import requests
import textwrap
import urllib.request

logger = logging.getLogger(__name__)

# ── 폰트 관련 설정 ─────────────────────────────────
FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")
FONTS = {
    "NanumPen": "https://github.com/google/fonts/raw/main/ofl/nanumpenscript/NanumPenScript-Regular.ttf",
    "NanumBrush": "https://github.com/google/fonts/raw/main/ofl/nanumbrushscript/NanumBrushScript-Regular.ttf",
}

# 이미지 크기
IMG_WIDTH = 680
IMG_HEIGHT = 200


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
    # 폴백: 시스템 기본 폰트
    try:
        return ImageFont.truetype("malgun.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _wrap_text(text, font, max_width, draw):
    """텍스트가 max_width를 넘으면 2줄로 줄바꿈"""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]

    if text_width <= max_width:
        return [text]

    # 중간 지점에서 분할 시도
    mid = len(text) // 2
    # 분할 포인트 찾기 (공백, 쉼표, 마침표 등)
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


def _adjust_font_size(text, font_name, max_width, max_height, draw):
    """텍스트에 맞게 폰트 크기 자동 조정 (40~50px 범위)"""
    for size in [48, 44, 40, 36, 32]:
        font = _get_font(font_name, size)
        lines = _wrap_text(text, font, max_width, draw)
        # 전체 높이 계산
        total_h = 0
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            total_h += bbox[3] - bbox[1]
        total_h += (len(lines) - 1) * 8  # 줄 간격
        if total_h <= max_height:
            return font, lines, size
    # 최소 크기로 폴백
    font = _get_font(font_name, 28)
    lines = _wrap_text(text, font, max_width, draw)
    return font, lines, 28


def _style_white_brush(text, output_path):
    """스타일 1: 흰 배경 + 붓글씨"""
    from PIL import Image, ImageDraw

    img = Image.new('RGB', (IMG_WIDTH, IMG_HEIGHT), '#FFFFFF')
    draw = ImageDraw.Draw(img)

    font, lines, fsize = _adjust_font_size(
        text, "NanumBrush", IMG_WIDTH - 80, IMG_HEIGHT - 40, draw
    )

    # 텍스트 중앙 배치 (살짝 랜덤 오프셋)
    y_offset = random.randint(-2, 2)
    total_h = 0
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        total_h += h
    total_h += (len(lines) - 1) * 8

    y = (IMG_HEIGHT - total_h) // 2 + y_offset
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (IMG_WIDTH - w) // 2 + random.randint(-2, 2)
        draw.text((x, y), line, fill='#1a1a1a', font=font)
        y += line_heights[i] + 8

    # 하단에 얇은 밑줄 장식
    line_y = IMG_HEIGHT - 30
    line_w = min(len(text) * 12, IMG_WIDTH - 120)
    x_start = (IMG_WIDTH - line_w) // 2
    draw.line([(x_start, line_y), (x_start + line_w, line_y)], fill='#cccccc', width=1)

    img.save(output_path, 'PNG')
    return output_path


def _style_canvas_multiline(text, output_path):
    """스타일 2: 캔버스 질감 배경 + 펜글씨 + 여러 줄"""
    from PIL import Image, ImageDraw

    # 연한 아이보리 배경
    img = Image.new('RGB', (IMG_WIDTH, IMG_HEIGHT), '#FAFAF8')
    draw = ImageDraw.Draw(img)

    # 미세한 질감 (점선 노이즈)
    for _ in range(200):
        rx = random.randint(0, IMG_WIDTH - 1)
        ry = random.randint(0, IMG_HEIGHT - 1)
        gray = random.randint(230, 245)
        draw.point((rx, ry), fill=(gray, gray, gray))

    font, lines, fsize = _adjust_font_size(
        text, "NanumPen", IMG_WIDTH - 80, IMG_HEIGHT - 40, draw
    )

    y_offset = random.randint(-2, 2)
    total_h = 0
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        total_h += h
    total_h += (len(lines) - 1) * 10

    y = (IMG_HEIGHT - total_h) // 2 + y_offset
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (IMG_WIDTH - w) // 2 + random.randint(-1, 1)
        draw.text((x, y), line, fill='#1a1a3e', font=font)
        y += line_heights[i] + 10

    img.save(output_path, 'PNG')
    return output_path


def _style_note_pen(text, output_path):
    """스타일 3: 노트 줄 배경 + 펜글씨"""
    from PIL import Image, ImageDraw

    img = Image.new('RGB', (IMG_WIDTH, IMG_HEIGHT), '#FFFFFF')
    draw = ImageDraw.Draw(img)

    # 가로 줄 (노트 느낌)
    for y_line in range(40, IMG_HEIGHT, 28):
        draw.line([(40, y_line), (IMG_WIDTH - 40, y_line)], fill='#e0e0e0', width=1)

    # 세로 빨간 줄 (왼쪽)
    draw.line([(60, 20), (60, IMG_HEIGHT - 20)], fill='#ffcccc', width=1)

    font, lines, fsize = _adjust_font_size(
        text, "NanumPen", IMG_WIDTH - 120, IMG_HEIGHT - 50, draw
    )

    y_offset = random.randint(-1, 1)
    total_h = 0
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        total_h += h
    total_h += (len(lines) - 1) * 8

    y = (IMG_HEIGHT - total_h) // 2 + y_offset
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (IMG_WIDTH - w) // 2 + random.randint(-1, 1)
        draw.text((x, y), line, fill='#1a1a1a', font=font)
        y += line_heights[i] + 8

    img.save(output_path, 'PNG')
    return output_path


# 3가지 스타일 함수 목록
_STYLES = [_style_white_brush, _style_canvas_multiline, _style_note_pen]


def generate_handwriting_image(text, output_path, style_index=None):
    """
    소제목 텍스트를 손글씨 스타일 이미지로 생성

    Args:
        text: 소제목 텍스트
        output_path: 저장 경로
        style_index: 스타일 인덱스 (None이면 랜덤)

    Returns:
        str: 저장된 파일 경로
    """
    if style_index is None:
        style_fn = random.choice(_STYLES)
    else:
        style_fn = _STYLES[style_index % len(_STYLES)]

    return style_fn(text, output_path)


def generate_blog_images(topic, content="", image_count=4, user_image_paths=None):
    """
    블로그 본문 이미지 생성 (PIL 손글씨 스타일)

    소제목을 추출하여 손글씨 텍스트 이미지를 생성합니다.
    DALL-E 대신 PIL을 사용하여 비용 없이 즉시 생성.

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
        # 소제목이 없으면 주제를 기반으로 생성
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
            logger.info(f"손글씨 이미지 생성: {filepath}")
        except Exception as e:
            logger.error(f"손글씨 이미지 생성 실패 [{i}]: {e}")
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

        # PIL 손글씨 이미지 → 이미 로컬 파일
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
    썸네일 이미지 생성 (PIL 손글씨 스타일)

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
