"""
오케스트레이터 모듈
- 키워드 → 칼럼 생성 → 유사도 검증 → HTML 포맷팅 → 발행
- app.py의 Tab1 배치 생성 기능 연동
"""

import os
import json
from datetime import datetime

from src.engine import generate_column_with_validation, generate_column
from src.similarity import check_similarity
from src.formatter import format_column_html, format_column_preview


def generate_preview(topic, persona_id, persona_name,
                     model_id="claude-sonnet-4-6", temperature=0.7,
                     include_images=False, user_image_paths=None,
                     image_count=4, thumbnail_preset=None):
    """
    키워드로 칼럼 생성 + 유사도 검증 + HTML 포맷팅

    Returns:
        dict: {
            'success': bool,
            'title': str,
            'raw_content': str,
            'html_content': str,
            'preview_html': str,
            'char_count': int,
            'attempts': int,
            'similarity': dict,
            'image_data': dict or None,
        }
    """
    # 1. 칼럼 생성 (유사도 검증 포함)
    result = generate_column_with_validation(
        persona_id=persona_id,
        persona_name=persona_name,
        topic=topic,
        model_id=model_id,
        temperature=temperature,
    )

    content = result["content"]

    # 2. 제목 추출 (첫 번째 # 헤딩 또는 첫 줄)
    title = topic
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped.lstrip("#").strip()
            break

    # 3. 이미지 처리
    image_data = None
    if include_images:
        try:
            from src.image_handler import generate_blog_images, generate_thumbnail
            image_data = generate_blog_images(
                topic=topic,
                content=content,
                image_count=image_count or 4,
                user_image_paths=user_image_paths,
            )
            if thumbnail_preset:
                thumb = generate_thumbnail(
                    topic=topic,
                    subtitle="",
                    preset=thumbnail_preset,
                )
                image_data["thumbnail"] = thumb
        except Exception:
            image_data = None

    # 4. HTML 포맷팅
    html_content = format_column_html(
        content, persona_id,
        include_images=bool(image_data),
        image_data=image_data,
    )
    preview_html = format_column_preview(content, persona_id, image_data)

    # 5. 히스토리 저장
    _save_to_history(persona_id, topic, content)

    return {
        "success": True,
        "title": title,
        "raw_content": content,
        "html_content": html_content,
        "preview_html": preview_html,
        "char_count": len(content),
        "attempts": result["attempts"],
        "similarity": result["similarity_check"],
        "image_data": image_data,
    }


def batch_generate(items, persona_id, persona_name,
                   model_id="claude-sonnet-4-6", temperature=0.7,
                   include_images=False, image_count=4,
                   thumbnail_preset=None, progress_callback=None):
    """
    배치 칼럼 생성

    Args:
        items: list of dicts with 'topic', 'publish_mode', 'scheduled_time'
        progress_callback: func(idx, total, result)

    Returns:
        list[dict]: generate_preview 결과 리스트
    """
    results = []
    total = len(items)

    for idx, item in enumerate(items):
        try:
            result = generate_preview(
                topic=item["topic"],
                persona_id=persona_id,
                persona_name=persona_name,
                model_id=model_id,
                temperature=temperature,
                include_images=include_images,
                image_count=image_count,
                thumbnail_preset=thumbnail_preset,
            )
            result["publish_mode"] = item.get("publish_mode", "immediate")
            result["scheduled_time"] = item.get("scheduled_time")
        except Exception as e:
            result = {
                "success": False,
                "error": str(e),
                "title": item["topic"],
                "publish_mode": item.get("publish_mode", "immediate"),
            }

        results.append(result)

        if progress_callback:
            progress_callback(idx, total, result)

    return results


def get_history(persona_id, limit=50):
    """
    발행 히스토리 조회

    Returns:
        list[dict]: 히스토리 항목 리스트
    """
    history_path = os.path.join("outputs", persona_id, "history.json")
    if not os.path.exists(history_path):
        return []

    try:
        with open(history_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data[:limit] if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError):
        return []


def _save_to_history(persona_id, topic, content):
    """히스토리 저장"""
    output_dir = os.path.join("outputs", persona_id)
    os.makedirs(output_dir, exist_ok=True)
    history_path = os.path.join(output_dir, "history.json")

    history_data = []
    if os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                history_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            history_data = []

    history_data.insert(0, {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "topic": topic,
        "content": content,
    })

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, indent=2)
