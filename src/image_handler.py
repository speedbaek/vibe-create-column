"""
이미지 핸들러 모듈
- 블로그 본문 이미지 생성 (OpenAI DALL-E 또는 플레이스홀더)
- DALL-E 이미지 로컬 다운로드
- 썸네일 생성
"""

import os
import logging
import re
import requests
import uuid

logger = logging.getLogger(__name__)


def _get_placeholder_url(width=800, height=400, text="Blog Image"):
    """플레이스홀더 이미지 URL 생성"""
    safe_text = text.replace(" ", "+")[:30]
    return f"https://placehold.co/{width}x{height}/e8e8e8/333?text={safe_text}"


def _build_image_prompt(topic, content="", index=0):
    """
    칼럼 주제와 본문을 기반으로 DALL-E용 이미지 프롬프트 생성
    실사 사진 스타일 (사무실, 서류, 업무 환경 등)

    Args:
        topic: 칼럼 주제
        content: 칼럼 본문 (소제목 추출용)
        index: 이미지 인덱스 (다양성을 위해)

    Returns:
        str: DALL-E 프롬프트
    """
    # 본문에서 소제목(## heading) 추출하여 키워드로 활용
    subtopics = re.findall(r'^##\s+(.+)$', content, re.MULTILINE)
    keyword = subtopics[index] if index < len(subtopics) else topic

    # 실사 사진 스타일 프롬프트 (사무실/서류/업무 환경)
    scenes = [
        "a professional Korean office desk with legal documents, patent application forms, and a laptop, natural lighting from window, shallow depth of field",
        "a business meeting room in a Korean law firm, conference table with paperwork and pens, warm ambient lighting, professional atmosphere",
        "close-up of hands reviewing official documents and certificates on a wooden desk, soft natural light, professional business setting",
        "a modern Korean law office interior with bookshelves of legal books, clean desk with documents, warm and welcoming atmosphere",
    ]
    scene = scenes[index % len(scenes)]

    prompt = (
        f"Realistic photograph style: {scene}. "
        f"The scene subtly relates to the concept of '{keyword}' in intellectual property and patent work. "
        f"No text, no watermarks, no logos, no people's faces. "
        f"Shot with natural lighting, high quality, stock photo aesthetic."
    )
    return prompt


def _generate_dalle_image(prompt, size="1024x1024"):
    """
    DALL-E API로 이미지 1장 생성

    Args:
        prompt: 이미지 생성 프롬프트
        size: 이미지 크기

    Returns:
        str | None: 생성된 이미지 URL 또는 None (실패 시)
    """
    try:
        from openai import OpenAI

        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            n=1,
            size=size,
            quality="standard",
        )

        url = response.data[0].url
        logger.info(f"DALL-E 이미지 생성 성공: {url[:80]}...")
        return url

    except Exception as e:
        logger.error(f"DALL-E 이미지 생성 실패: {e}")
        return None


def download_dalle_images(image_data, output_dir="outputs/images"):
    """
    DALL-E 임시 URL 이미지들을 로컬 파일로 다운로드

    Args:
        image_data: generate_blog_images() 반환값
        output_dir: 저장 디렉토리

    Returns:
        list[str]: 로컬 파일 경로 리스트 (다운로드 순서 유지)
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

        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()

            # 확장자 추출
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


def generate_blog_images(topic, content="", image_count=4, user_image_paths=None):
    """
    블로그 본문 이미지 생성

    Args:
        topic: 주제
        content: 칼럼 본문
        image_count: 생성할 이미지 수 (DALL-E 비용 고려, 기본 2장)
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

    # 부족한 수만큼 DALL-E 또는 플레이스홀더로 보충
    remaining = image_count - len(body_images)
    openai_key = os.environ.get("OPENAI_API_KEY", "")

    if remaining > 0 and openai_key:
        logger.info(f"DALL-E로 이미지 {remaining}장 생성 시작 (주제: {topic})")
        for i in range(remaining):
            prompt = _build_image_prompt(topic, content, index=i)
            url = _generate_dalle_image(prompt)
            if url:
                body_images.append({
                    "url": url,
                    "alt": f"{topic} 관련 이미지 {i+1}",
                    "source": "dalle",
                    "prompt": prompt,
                })
            else:
                # DALL-E 실패 → 플레이스홀더 폴백
                body_images.append({
                    "url": _get_placeholder_url(text=f"{topic[:15]}+{i+1}"),
                    "alt": f"{topic} 관련 이미지 {i+1}",
                    "source": "placeholder",
                })
    elif remaining > 0:
        logger.warning("OPENAI_API_KEY 미설정 → 플레이스홀더 이미지 사용")
        for i in range(remaining):
            body_images.append({
                "url": _get_placeholder_url(text=f"Image+{i+1}"),
                "alt": f"본문 이미지 {i+1}",
                "source": "placeholder",
            })

    return {
        "body_images": body_images,
        "total_count": len(body_images),
    }


def generate_thumbnail(topic, subtitle="", preset="dark_minimal"):
    """
    썸네일 이미지 생성

    DALL-E를 사용하여 썸네일을 생성하거나, API 키가 없으면 플레이스홀더 사용.

    Args:
        topic: 제목
        subtitle: 부제목
        preset: 스타일 프리셋

    Returns:
        dict: {'url': str, 'alt': str, 'preset': str}
    """
    openai_key = os.environ.get("OPENAI_API_KEY", "")

    if openai_key:
        prompt = (
            f"A professional blog thumbnail image for a Korean patent law article about '{topic}'. "
            f"Clean, modern design with subtle legal/technology motifs. "
            f"Dark navy blue background, minimal style, no text. "
            f"Suitable as a 1200x630 blog cover image."
        )
        url = _generate_dalle_image(prompt, size="1792x1024")
        if url:
            return {
                "url": url,
                "alt": topic,
                "preset": preset,
                "source": "dalle",
            }

    # 플레이스홀더 폴백
    preset_colors = {
        "dark_minimal": ("1a1a2e", "ffffff"),
        "light_clean": ("f8f9fa", "333333"),
        "warm_professional": ("f4a460", "333333"),
        "blue_corporate": ("1a73e8", "ffffff"),
    }
    bg, fg = preset_colors.get(preset, ("1a1a2e", "ffffff"))
    safe_topic = topic.replace(" ", "+")[:25]

    return {
        "url": f"https://placehold.co/1200x630/{bg}/{fg}?text={safe_topic}",
        "alt": topic,
        "preset": preset,
        "source": "placeholder",
    }
