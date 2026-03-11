"""
이미지 처리 모듈 v1
- 썸네일 생성 (텍스트 오버레이, 스타일 프리셋)
- AI 이미지 생성 (DALL-E 3)
- 사용자 제공 이미지 + AI 이미지 혼합
- 본문 이미지 배치 로직
"""

import os
import re
import json
import random
import logging
import base64
from io import BytesIO
from typing import List, Optional, Dict, Tuple

logger = logging.getLogger(__name__)

CONFIG_PATH = "config/image_styles.json"
IMAGE_OUTPUT_DIR = "outputs/images"
FONT_DIR = "config/fonts"


def _load_config() -> dict:
    """이미지 스타일 설정 로드"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("image_styles.json 로드 실패, 기본값 사용")
        return {}


def _ensure_dirs():
    os.makedirs(IMAGE_OUTPUT_DIR, exist_ok=True)
    os.makedirs(FONT_DIR, exist_ok=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 썸네일 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_thumbnail(
    keyword: str,
    subtitle: str = "",
    preset: str = None,
    output_path: str = None,
) -> str:
    """
    썸네일 이미지 생성 (심플 배경 + 키워드 텍스트)

    Args:
        keyword: 메인 키워드 텍스트
        subtitle: 서브 텍스트 (선택)
        preset: 스타일 프리셋 이름 (None이면 active_preset 사용)
        output_path: 저장 경로 (None이면 자동 생성)

    Returns:
        str: 생성된 이미지 파일 경로
    """
    from PIL import Image, ImageDraw, ImageFont

    _ensure_dirs()
    config = _load_config()
    thumb_config = config.get("thumbnail", {})

    # 프리셋 적용
    active_preset = preset or thumb_config.get("active_preset", "dark_minimal")
    presets = thumb_config.get("presets", {})
    if active_preset in presets:
        preset_data = presets[active_preset]
        # 프리셋 값으로 기본 설정 덮어쓰기
        if "background" in preset_data:
            thumb_config["background"] = {**thumb_config.get("background", {}), **preset_data["background"]}
        if "text" in preset_data:
            thumb_config["text"] = {**thumb_config.get("text", {}), **preset_data["text"]}
        if "decoration" in preset_data:
            thumb_config["decoration"] = {**thumb_config.get("decoration", {}), **preset_data["decoration"]}

    width = thumb_config.get("width", 800)
    height = thumb_config.get("height", 450)
    bg_config = thumb_config.get("background", {})
    text_config = thumb_config.get("text", {})
    deco_config = thumb_config.get("decoration", {})

    # ── 배경 생성 ──
    bg_colors = bg_config.get("colors", ["#1a1a2e", "#16213e"])
    img = _create_gradient_background(width, height, bg_colors)
    draw = ImageDraw.Draw(img)

    padding = deco_config.get("padding", 40)

    # ── 폰트 로드 ──
    font_main = _load_font(text_config.get("font_family", "NanumGothicBold"),
                           text_config.get("font_size_main", 42))
    font_sub = _load_font(text_config.get("font_family", "NanumGothicBold"),
                          text_config.get("font_size_sub", 18))
    font_logo = _load_font("NanumGothic",
                           deco_config.get("logo_font_size", 14))

    font_color = text_config.get("font_color", "#ffffff")

    # ── 악센트 라인 ──
    if deco_config.get("show_accent_line", True):
        accent_color = deco_config.get("accent_line_color", "#4a90d9")
        accent_width = deco_config.get("accent_line_width", 3)
        line_y = height // 2 - 60
        line_len = 60
        center_x = width // 2
        draw.line(
            [(center_x - line_len, line_y), (center_x + line_len, line_y)],
            fill=accent_color, width=accent_width
        )

    # ── 메인 텍스트 ──
    max_chars = text_config.get("max_chars_per_line", 15)
    lines = _wrap_text(keyword, max_chars)
    line_spacing = text_config.get("line_spacing", 1.4)

    # 텍스트 전체 높이 계산
    line_heights = []
    for line in lines:
        bbox = font_main.getbbox(line)
        line_heights.append(bbox[3] - bbox[1])

    total_text_height = sum(line_heights) + (len(lines) - 1) * int(line_heights[0] * (line_spacing - 1))
    start_y = (height - total_text_height) // 2

    # 악센트 라인이 있으면 텍스트를 살짝 아래로
    if deco_config.get("show_accent_line", True):
        start_y = max(start_y, height // 2 - 40)

    current_y = start_y
    for line in lines:
        bbox = font_main.getbbox(line)
        text_width = bbox[2] - bbox[0]
        x = (width - text_width) // 2
        draw.text((x, current_y), line, fill=font_color, font=font_main)
        current_y += int(line_heights[0] * line_spacing)

    # ── 서브텍스트 ──
    if subtitle:
        bbox = font_sub.getbbox(subtitle)
        sub_width = bbox[2] - bbox[0]
        sub_x = (width - sub_width) // 2
        sub_y = current_y + 15
        sub_color = _adjust_alpha(font_color, 0.6)
        draw.text((sub_x, sub_y), subtitle, fill=sub_color, font=font_sub)

    # ── 로고 텍스트 ──
    if deco_config.get("show_logo_text", True):
        logo_text = deco_config.get("logo_text", "특허법인 테헤란")
        logo_color = deco_config.get("logo_color", "#888888")
        bbox = font_logo.getbbox(logo_text)
        logo_width = bbox[2] - bbox[0]
        logo_x = width - logo_width - padding
        logo_y = height - (bbox[3] - bbox[1]) - padding
        draw.text((logo_x, logo_y), logo_text, fill=logo_color, font=font_logo)

    # ── 저장 ──
    if not output_path:
        safe_keyword = re.sub(r'[^\w가-힣]', '_', keyword)[:20]
        output_path = os.path.join(IMAGE_OUTPUT_DIR, f"thumb_{safe_keyword}.png")

    img.save(output_path, "PNG", quality=95)
    logger.info(f"썸네일 생성: {output_path} ({width}x{height}, 프리셋: {active_preset})")
    return output_path


def _create_gradient_background(width: int, height: int, colors: list) -> "Image":
    """그라디언트 배경 생성"""
    from PIL import Image

    img = Image.new("RGB", (width, height))
    pixels = img.load()

    # 두 색상 사이의 그라디언트
    c1 = _hex_to_rgb(colors[0])
    c2 = _hex_to_rgb(colors[1] if len(colors) > 1 else colors[0])

    for y in range(height):
        ratio = y / height
        r = int(c1[0] + (c2[0] - c1[0]) * ratio)
        g = int(c1[1] + (c2[1] - c1[1]) * ratio)
        b = int(c1[2] + (c2[2] - c1[2]) * ratio)
        for x in range(width):
            pixels[x, y] = (r, g, b)

    return img


def _load_font(font_name: str, size: int):
    """폰트 로드 (시스템 폰트 → 번들 폰트 → 기본)"""
    from PIL import ImageFont

    # 시스템 폰트 경로들
    font_paths = [
        # 로컬 번들
        os.path.join(FONT_DIR, f"{font_name}.ttf"),
        # Linux
        f"/usr/share/fonts/truetype/nanum/{font_name}.ttf",
        f"/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        f"/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        # Windows
        f"C:/Windows/Fonts/{font_name}.ttf",
        f"C:/Windows/Fonts/NanumGothicBold.ttf",
        f"C:/Windows/Fonts/malgunbd.ttf",
        f"C:/Windows/Fonts/malgun.ttf",
        # macOS
        f"/Library/Fonts/{font_name}.ttf",
        "/System/Library/Fonts/AppleGothic.ttf",
    ]

    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except (IOError, OSError):
                continue

    # 최후: 기본 폰트
    logger.warning(f"폰트 {font_name} 로드 실패, 기본 폰트 사용")
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except (IOError, OSError):
        return ImageFont.load_default()


def _wrap_text(text: str, max_chars: int) -> list:
    """텍스트 줄바꿈"""
    if len(text) <= max_chars:
        return [text]

    words = text.split()
    lines = []
    current = ""

    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current = f"{current} {word}" if current else word
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    # 한글일 때 글자 단위로 자르기 (단어 분리가 안 되는 경우)
    if len(lines) == 1 and len(lines[0]) > max_chars:
        text = lines[0]
        lines = []
        for i in range(0, len(text), max_chars):
            lines.append(text[i:i + max_chars])

    return lines


def _hex_to_rgb(hex_color: str) -> tuple:
    """HEX → RGB 변환"""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def _adjust_alpha(hex_color: str, alpha: float) -> str:
    """색상 밝기 조절 (alpha 시뮬레이션)"""
    r, g, b = _hex_to_rgb(hex_color)
    r = int(r * alpha)
    g = int(g * alpha)
    b = int(b * alpha)
    return f"#{r:02x}{g:02x}{b:02x}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. AI 이미지 생성 (DALL-E)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_ai_image(
    prompt: str,
    output_path: str = None,
    size: str = "1024x1024",
) -> Optional[str]:
    """
    DALL-E로 AI 이미지 생성

    Args:
        prompt: 이미지 생성 프롬프트
        output_path: 저장 경로
        size: 이미지 사이즈

    Returns:
        str: 생성된 이미지 파일 경로 (실패 시 None)
    """
    _ensure_dirs()
    config = _load_config()
    body_config = config.get("body_images", {}).get("ai_generation", {})
    suffix = body_config.get("base_prompt_suffix", "")
    full_prompt = f"{prompt}. {suffix}"

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("OPENAI_API_KEY가 설정되지 않았습니다. 플레이스홀더 이미지 생성")
        return _generate_placeholder_image(prompt, output_path)

    try:
        import httpx

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": body_config.get("model", "dall-e-3"),
            "prompt": full_prompt,
            "n": 1,
            "size": size,
            "quality": body_config.get("quality", "standard"),
            "style": body_config.get("style", "natural"),
            "response_format": "b64_json",
        }

        # SSL 우회 옵션
        verify = not (os.environ.get("DISABLE_SSL_VERIFY", "").lower() in ("1", "true", "yes"))
        client = httpx.Client(verify=verify, timeout=60.0)

        response = client.post(
            "https://api.openai.com/v1/images/generations",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        # 이미지 디코딩 및 저장
        img_b64 = data["data"][0]["b64_json"]
        img_bytes = base64.b64decode(img_b64)

        if not output_path:
            safe_name = re.sub(r'[^\w가-힣]', '_', prompt[:30])
            output_path = os.path.join(IMAGE_OUTPUT_DIR, f"ai_{safe_name}_{random.randint(100,999)}.png")

        with open(output_path, "wb") as f:
            f.write(img_bytes)

        # 리사이즈 (블로그용 소형)
        _resize_for_blog(output_path)

        logger.info(f"AI 이미지 생성: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"AI 이미지 생성 실패: {e}")
        return _generate_placeholder_image(prompt, output_path)


def _generate_placeholder_image(prompt: str, output_path: str = None) -> str:
    """DALL-E 사용 불가 시 텍스트 기반 플레이스홀더 이미지 생성"""
    from PIL import Image, ImageDraw

    _ensure_dirs()
    config = _load_config()
    body_config = config.get("body_images", {}).get("size", {})
    w = body_config.get("width", 400)
    h = body_config.get("height", 280)

    # 부드러운 색상 팔레트
    palette = [
        ("#e8f4f8", "#5b9bd5"),  # 연한 파랑
        ("#f0f5e9", "#7cb342"),  # 연한 초록
        ("#fef5e7", "#f0a030"),  # 연한 주황
        ("#f3e8f9", "#9c27b0"),  # 연한 보라
        ("#fce4ec", "#e91e63"),  # 연한 핑크
    ]
    bg_color, accent_color = random.choice(palette)

    img = Image.new("RGB", (w, h), bg_color)
    draw = ImageDraw.Draw(img)

    # 심플한 도형 장식
    accent_rgb = _hex_to_rgb(accent_color)
    # 원형 장식
    cx, cy = w // 2, h // 2
    for r in range(80, 20, -20):
        alpha = int(40 + (80 - r))
        color = (*accent_rgb, alpha)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=accent_color, width=1)

    # 중앙 작은 아이콘 느낌
    draw.ellipse([cx - 15, cy - 15, cx + 15, cy + 15], fill=accent_color)

    if not output_path:
        safe_name = re.sub(r'[^\w가-힣]', '_', prompt[:20])
        output_path = os.path.join(IMAGE_OUTPUT_DIR, f"placeholder_{safe_name}_{random.randint(100,999)}.png")

    img.save(output_path, "PNG")
    logger.info(f"플레이스홀더 이미지 생성: {output_path}")
    return output_path


def _resize_for_blog(image_path: str):
    """블로그용 소형 사이즈로 리사이즈"""
    from PIL import Image

    config = _load_config()
    body_config = config.get("body_images", {}).get("size", {})
    max_w = body_config.get("width", 400)
    max_h = body_config.get("height", 280)

    img = Image.open(image_path)
    img.thumbnail((max_w, max_h), Image.LANCZOS)
    img.save(image_path, quality=85)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. 사용자 이미지 처리
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def process_user_images(image_paths: List[str]) -> List[str]:
    """
    사용자 제공 이미지 처리 (리사이즈 + 포맷 변환)

    Args:
        image_paths: 사용자 이미지 파일 경로 리스트

    Returns:
        list: 처리된 이미지 경로 리스트
    """
    from PIL import Image

    _ensure_dirs()
    config = _load_config()
    user_config = config.get("user_images", {}).get("resize", {})
    max_w = user_config.get("max_width", 800)
    max_h = user_config.get("max_height", 600)
    quality = user_config.get("quality", 85)

    processed = []
    for path in image_paths:
        if not os.path.exists(path):
            logger.warning(f"이미지 파일 없음: {path}")
            continue

        try:
            img = Image.open(path)
            img.thumbnail((max_w, max_h), Image.LANCZOS)

            # RGB 변환 (PNG 투명 배경 처리)
            if img.mode in ("RGBA", "P"):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "RGBA":
                    bg.paste(img, mask=img.split()[3])
                else:
                    bg.paste(img)
                img = bg

            # 저장
            filename = os.path.basename(path)
            name, _ = os.path.splitext(filename)
            out_path = os.path.join(IMAGE_OUTPUT_DIR, f"user_{name}.jpg")
            img.save(out_path, "JPEG", quality=quality)
            processed.append(out_path)
            logger.info(f"사용자 이미지 처리: {out_path}")

        except Exception as e:
            logger.error(f"이미지 처리 실패 ({path}): {e}")

    return processed


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. 이미지 믹서 (혼합 + 배치)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_blog_images(
    topic: str,
    content: str,
    user_image_paths: List[str] = None,
    image_count: int = None,
) -> Dict:
    """
    블로그 포스팅용 이미지 세트 생성 (썸네일 + 본문 이미지)

    Args:
        topic: 글 주제/키워드
        content: 생성된 본문 텍스트
        user_image_paths: 사용자 제공 이미지 경로 리스트 (선택)
        image_count: 본문 이미지 수 (None이면 설정에서 로드)

    Returns:
        dict: {
            'thumbnail': str,           # 썸네일 경로
            'body_images': list,        # 본문 이미지 경로 리스트
            'image_positions': list,    # 삽입 위치 (문단 인덱스)
            'total_count': int
        }
    """
    config = _load_config()
    body_config = config.get("body_images", {})

    # 이미지 수 결정
    if image_count is None:
        count_config = body_config.get("count", {})
        image_count = count_config.get("default", 4)

    min_count = body_config.get("count", {}).get("min", 3)
    max_count = body_config.get("count", {}).get("max", 7)
    image_count = max(min_count, min(image_count, max_count))

    result = {
        "thumbnail": None,
        "body_images": [],
        "image_positions": [],
        "total_count": 0,
    }

    # ── 1. 썸네일 생성 ──
    try:
        thumb_path = generate_thumbnail(topic, subtitle="특허법인 테헤란")
        result["thumbnail"] = thumb_path
    except Exception as e:
        logger.error(f"썸네일 생성 실패: {e}")

    # ── 2. 본문 이미지 준비 ──
    body_images = []

    # 사용자 이미지 처리
    user_images = []
    if user_image_paths:
        user_images = process_user_images(user_image_paths)

    # AI 이미지 프롬프트 생성
    ai_prompts = _generate_image_prompts(topic, content, image_count)

    if user_images:
        # ── 혼합 모드: 사용자 이미지 + AI 이미지 ──
        mixing = config.get("user_images", {}).get("mixing_strategy", {})
        priority_positions = mixing.get("user_image_priority_positions", [1, 3, 5])

        for i in range(image_count):
            position_num = i + 1  # 1-indexed

            if position_num in priority_positions and user_images:
                # 사용자 이미지 배치
                body_images.append(user_images.pop(0))
            elif ai_prompts:
                # AI 이미지 생성
                prompt = ai_prompts.pop(0)
                ai_path = generate_ai_image(prompt)
                if ai_path:
                    body_images.append(ai_path)

        # 남은 사용자 이미지가 있으면 추가
        body_images.extend(user_images[:max_count - len(body_images)])

    else:
        # ── AI 전용 모드 ──
        for prompt in ai_prompts[:image_count]:
            ai_path = generate_ai_image(prompt)
            if ai_path:
                body_images.append(ai_path)

    result["body_images"] = body_images
    result["total_count"] = len(body_images) + (1 if result["thumbnail"] else 0)

    # ── 3. 삽입 위치 계산 ──
    result["image_positions"] = _calculate_image_positions(content, len(body_images))

    return result


def _generate_image_prompts(topic: str, content: str, count: int) -> List[str]:
    """본문 내용 기반 AI 이미지 프롬프트 생성"""

    # 본문에서 소제목 추출
    subtitles = re.findall(r'\*\*(.+?)\*\*', content)

    prompts = []

    # 주제 기반 기본 프롬프트들
    base_concepts = [
        f"A professional office desk with legal documents and a pen, related to {topic}",
        f"Abstract concept illustration about brand protection and trademark",
        f"Business meeting scene with professionals discussing intellectual property",
        f"Symbolic image of a shield protecting a brand logo, trademark security concept",
        f"Modern Korean office building exterior, professional law firm atmosphere",
        f"Document signing scene, legal agreement and contract concept",
        f"Startup team working on branding strategy in a modern workspace",
        f"Gavel and legal documents on a wooden desk, justice and law concept",
        f"Digital screen showing trademark registration process flowchart",
        f"Handshake between business professionals, trust and partnership concept",
    ]

    # 소제목 기반 프롬프트 추가
    for subtitle in subtitles[:3]:
        clean = re.sub(r'[^\w\s가-힣]', '', subtitle)
        prompts.append(f"Conceptual illustration about: {clean}")

    # 기본 프롬프트에서 나머지 채우기
    random.shuffle(base_concepts)
    prompts.extend(base_concepts)

    return prompts[:count + 2]  # 여유분 포함


def _calculate_image_positions(content: str, image_count: int) -> List[int]:
    """본문 내 이미지 삽입 위치 계산 (문단 인덱스)"""
    config = _load_config()
    placement = config.get("body_images", {}).get("placement", {})

    first_after = placement.get("first_image_after_paragraph", 3)
    min_gap = placement.get("min_gap_paragraphs", 3)

    # 문단 수 계산 (빈 줄과 구분선 제외)
    lines = content.strip().split('\n')
    paragraphs = [i for i, l in enumerate(lines) if l.strip() and l.strip() != '---']
    total_paragraphs = len(paragraphs)

    if total_paragraphs < 5 or image_count == 0:
        return list(range(first_after, first_after + image_count * min_gap, min_gap))

    # 균등 분배
    positions = []
    # CTA 근처는 피하기 (마지막 20%)
    usable_range = int(total_paragraphs * 0.8)
    if usable_range < first_after + image_count:
        usable_range = total_paragraphs

    interval = max(min_gap, (usable_range - first_after) // max(image_count, 1))

    for i in range(image_count):
        pos = first_after + i * interval
        if pos < total_paragraphs:
            positions.append(pos)

    return positions


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. 이미지 → Base64 (HTML 임베딩용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def image_to_base64(image_path: str) -> str:
    """이미지 파일을 base64 데이터 URI로 변환"""
    if not os.path.exists(image_path):
        return ""
    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")

    ext = os.path.splitext(image_path)[1].lower()
    mime = {"jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".webp": "image/webp", ".gif": "image/gif"}.get(ext, "image/png")
    return f"data:{mime};base64,{data}"


def image_to_html(image_path: str, alt: str = "", align: str = "center") -> str:
    """이미지를 HTML img 태그로 변환 (base64 임베딩)"""
    config = _load_config()
    size_config = config.get("body_images", {}).get("size", {})
    display_width = size_config.get("display_width", "60%")
    max_width = size_config.get("display_max_width", "360px")

    data_uri = image_to_base64(image_path)
    if not data_uri:
        return ""

    style = (
        f"display: block; margin: 15px auto; "
        f"width: {display_width}; max-width: {max_width}; "
        f"height: auto; border-radius: 4px;"
    )

    return f'<div style="text-align: {align}; margin: 10px 0;"><img src="{data_uri}" alt="{alt}" style="{style}"></div>'


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # 썸네일 테스트
    print("=== 썸네일 생성 테스트 ===")
    try:
        path = generate_thumbnail("스타트업 상표등록\n왜 미루면 안 될까?", subtitle="특허법인 테헤란")
        print(f"썸네일: {path}")
    except Exception as e:
        print(f"썸네일 오류: {e}")

    # 플레이스홀더 테스트
    print("\n=== 플레이스홀더 이미지 테스트 ===")
    for i in range(3):
        path = _generate_placeholder_image(f"테스트 이미지 {i+1}")
        print(f"  이미지 {i+1}: {path}")

    print("\n완료!")
