"""
이미지 핸들러 모듈
- 블로그 본문 이미지 생성 (OpenAI DALL-E 3 또는 플레이스홀더)
- 썸네일 생성
- 이미지 저장 및 관리
"""

import os
import re
import json
import httpx


def _get_placeholder_url(width=800, height=400, text="Blog Image"):
    """플레이스홀더 이미지 URL 생성"""
    safe_text = text.replace(" ", "+")[:30]
    return f"https://placehold.co/{width}x{height}/e8e8e8/333?text={safe_text}"


def _extract_sections(content, count=4):
    """칼럼 본문에서 이미지 프롬프트용 섹션 키워드 추출"""
    sections = []
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## ") or stripped.startswith("### "):
            heading = re.sub(r"^#+\s*", "", stripped)
            sections.append(heading)
    # 섹션이 부족하면 본문에서 키워드 추출
    if len(sections) < count:
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and len(stripped) > 20:
                sections.append(stripped[:40])
            if len(sections) >= count:
                break
    return sections[:count]


def _generate_dalle_image(prompt, size="1024x1024", quality="standard"):
    """DALL-E 3로 이미지 생성

    Args:
        prompt: 이미지 프롬프트
        size: 이미지 크기 (1024x1024, 1792x1024, 1024x1792)
        quality: standard 또는 hd

    Returns:
        dict: {'url': str, 'revised_prompt': str} or None
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return None

    try:
        # httpx로 직접 호출 (openai 패키지 불필요)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "dall-e-3",
            "prompt": prompt,
            "n": 1,
            "size": size,
            "quality": quality,
            "response_format": "url",
        }

        # SSL 우회 옵션
        verify = not os.environ.get("DISABLE_SSL_VERIFY", "").lower() in ("1", "true")
        with httpx.Client(timeout=60.0, verify=verify) as client:
            resp = client.post(
                "https://api.openai.com/v1/images/generations",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        img_data = data["data"][0]
        return {
            "url": img_data["url"],
            "revised_prompt": img_data.get("revised_prompt", prompt),
        }
    except Exception as e:
        print(f"[DALL-E] 이미지 생성 실패: {e}")
        return None


def _build_image_prompt(topic, section_hint="", style="professional"):
    """블로그 이미지용 프롬프트 생성"""
    base = (
        f"A clean, professional blog illustration for a Korean legal/IP article. "
        f"Topic: '{topic}'. "
    )
    if section_hint:
        base += f"Section context: '{section_hint}'. "

    style_map = {
        "professional": (
            "Modern flat design, soft blue and white color palette, "
            "minimalist business illustration style. No text in the image. "
            "Suitable for a Korean law firm blog post."
        ),
        "warm": (
            "Warm-toned illustration with gentle gradients, "
            "professional yet approachable style. No text overlay."
        ),
        "corporate": (
            "Corporate blue-themed infographic-style illustration. "
            "Clean lines, geometric shapes. No text in the image."
        ),
    }
    base += style_map.get(style, style_map["professional"])
    return base


def generate_blog_images(topic, content="", image_count=4,
                         user_image_paths=None, use_dalle=None):
    """
    블로그 본문 이미지 생성

    Args:
        topic: 주제
        content: 칼럼 본문
        image_count: 생성할 이미지 수
        user_image_paths: 사용자 업로드 이미지 경로 목록
        use_dalle: True면 DALL-E 사용 (None이면 API 키 유무로 자동 결정)

    Returns:
        dict: {
            'body_images': list[dict],
            'thumbnail': dict or None,
            'total_count': int,
            'dalle_used': bool,
        }
    """
    body_images = []
    dalle_used = False

    # 사용자 이미지가 있으면 우선 사용
    if user_image_paths:
        for path in user_image_paths[:image_count]:
            body_images.append({
                "url": path,
                "alt": f"{topic} 관련 이미지",
                "source": "user_upload",
            })

    # 부족한 수만큼 생성
    remaining = image_count - len(body_images)
    openai_key = os.environ.get("OPENAI_API_KEY", "")

    # DALL-E 사용 여부 결정
    if use_dalle is None:
        use_dalle = bool(openai_key)

    if remaining > 0 and use_dalle and openai_key:
        # 섹션별 키워드 추출
        sections = _extract_sections(content, remaining)

        for i in range(remaining):
            section_hint = sections[i] if i < len(sections) else ""
            prompt = _build_image_prompt(topic, section_hint)

            result = _generate_dalle_image(prompt, size="1792x1024")
            if result:
                body_images.append({
                    "url": result["url"],
                    "alt": f"{topic} - {section_hint}" if section_hint else f"{topic} 이미지 {i+1}",
                    "source": "dalle3",
                    "prompt": prompt,
                    "revised_prompt": result.get("revised_prompt", ""),
                })
                dalle_used = True
            else:
                # DALL-E 실패 시 플레이스홀더 폴백
                body_images.append({
                    "url": _get_placeholder_url(text=f"{topic[:15]}+{i+1}"),
                    "alt": f"{topic} 관련 이미지 {i+1}",
                    "source": "placeholder",
                })

    elif remaining > 0:
        # 플레이스홀더 사용
        for i in range(remaining):
            body_images.append({
                "url": _get_placeholder_url(text=f"Image+{i+1}"),
                "alt": f"본문 이미지 {i+1}",
                "source": "placeholder",
            })

    return {
        "body_images": body_images,
        "thumbnail": None,  # 썸네일은 별도 함수
        "total_count": len(body_images),
        "dalle_used": dalle_used,
    }


def generate_thumbnail(topic, subtitle="", preset="dark_minimal", use_dalle=None):
    """
    썸네일 이미지 생성

    Args:
        topic: 제목
        subtitle: 부제목
        preset: 스타일 프리셋
        use_dalle: True면 DALL-E 사용

    Returns:
        dict: {'url': str, 'alt': str, 'preset': str, 'source': str}
    """
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if use_dalle is None:
        use_dalle = bool(openai_key)

    if use_dalle and openai_key:
        prompt = (
            f"Blog thumbnail image for article titled '{topic}'. "
            f"Clean, modern design with subtle Korean business aesthetic. "
            f"Minimalist, no text, professional color scheme. "
            f"Suitable as a Naver blog post thumbnail."
        )
        result = _generate_dalle_image(prompt, size="1792x1024", quality="standard")
        if result:
            return {
                "url": result["url"],
                "alt": topic,
                "preset": preset,
                "source": "dalle3",
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
