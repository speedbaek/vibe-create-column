"""
이미지 핸들러 모듈
- 블로그 본문 이미지 생성 (OpenAI DALL-E 또는 플레이스홀더)
- 썸네일 생성
"""

import os


def _get_placeholder_url(width=800, height=400, text="Blog Image"):
    """플레이스홀더 이미지 URL 생성"""
    safe_text = text.replace(" ", "+")[:30]
    return f"https://placehold.co/{width}x{height}/e8e8e8/333?text={safe_text}"


def generate_blog_images(topic, content="", image_count=4, user_image_paths=None):
    """
    블로그 본문 이미지 생성

    Args:
        topic: 주제
        content: 칼럼 본문
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

    # 부족한 수만큼 플레이스홀더 추가
    remaining = image_count - len(body_images)
    openai_key = os.environ.get("OPENAI_API_KEY", "")

    if remaining > 0 and openai_key:
        # DALL-E는 비용이 크므로 플레이스홀더 사용 (필요 시 활성화)
        for i in range(remaining):
            body_images.append({
                "url": _get_placeholder_url(text=f"{topic[:15]}+{i+1}"),
                "alt": f"{topic} 관련 이미지 {i+1}",
                "source": "placeholder",
            })
    elif remaining > 0:
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

    Args:
        topic: 제목
        subtitle: 부제목
        preset: 스타일 프리셋

    Returns:
        dict: {'url': str, 'alt': str, 'preset': str}
    """
    # 프리셋별 색상
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
    }
