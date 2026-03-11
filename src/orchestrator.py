"""
블로그 자동화 오케스트레이터 v2
- 전체 파이프라인 통합 (생성 → 이미지 → 포맷팅 → 검증 → 발행)
- Streamlit UI에서 호출하는 메인 인터페이스
- 배치 처리 및 상태 관리
- 이미지 생성 파이프라인 통합
"""

import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

OUTPUTS_DIR = "outputs"
PREVIEW_DIR = os.path.join(OUTPUTS_DIR, "previews")
HISTORY_FILE = os.path.join(OUTPUTS_DIR, "history", "post_history.json")


def ensure_dirs():
    """필요한 디렉토리 생성"""
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    os.makedirs(os.path.join(OUTPUTS_DIR, "history"), exist_ok=True)


def generate_preview(
    topic,
    persona_id="yun_ung_chae",
    persona_name="윤웅채",
    model_id="claude-sonnet-4-6",
    temperature=0.7,
    include_images=True,
    user_image_paths=None,
    image_count=None,
    thumbnail_preset=None,
):
    """
    키워드로 컨텐츠 생성 + 이미지 생성 + HTML 미리보기 생성

    Args:
        topic: 주제/키워드
        persona_id: 페르소나 ID
        persona_name: 페르소나 이름
        model_id: Claude 모델 ID
        temperature: 생성 온도
        include_images: 이미지 포함 여부
        user_image_paths: 사용자 제공 이미지 경로 리스트
        image_count: 본문 이미지 수 (None이면 설정 기본값)
        thumbnail_preset: 썸네일 스타일 프리셋

    Returns:
        dict: {
            'success': bool,
            'title': str,
            'raw_content': str,     # 순수 텍스트
            'html_content': str,    # 블로그용 HTML (이미지 포함)
            'preview_html': str,    # 미리보기 전체 HTML
            'preview_path': str,    # 미리보기 파일 경로
            'similarity': dict,     # 유사도 검증 결과
            'char_count': int,      # 글자 수
            'attempts': int,        # 생성 시도 횟수
            'image_data': dict,     # 이미지 정보
            'error': str or None
        }
    """
    ensure_dirs()

    result = {
        "success": False,
        "title": "",
        "raw_content": "",
        "html_content": "",
        "preview_html": "",
        "preview_path": "",
        "similarity": {},
        "char_count": 0,
        "attempts": 0,
        "image_data": None,
        "error": None,
    }

    try:
        from src.engine import generate_column_with_validation
        from src.formatter import format_column_html, format_column_preview
        from src.naver_poster import _extract_or_generate_title

        # 1. 컨텐츠 생성 + 유사도 검증
        gen_result = generate_column_with_validation(
            persona_id, persona_name, topic, model_id, temperature
        )

        content = gen_result["content"]
        result["raw_content"] = content
        result["char_count"] = len(content)
        result["attempts"] = gen_result["attempts"]
        result["similarity"] = gen_result["similarity_check"]

        # 2. 제목 추출
        title = _extract_or_generate_title(topic, content)
        result["title"] = title

        # 3. 이미지 생성 (옵션)
        image_data = None
        if include_images:
            try:
                from src.image_handler import generate_blog_images, generate_thumbnail

                # 썸네일 프리셋 적용
                if thumbnail_preset:
                    image_data = generate_blog_images(
                        topic=topic,
                        content=content,
                        user_image_paths=user_image_paths,
                        image_count=image_count,
                    )
                    # 프리셋으로 썸네일 재생성
                    if image_data.get("thumbnail"):
                        thumb = generate_thumbnail(topic, subtitle="특허법인 테헤란", preset=thumbnail_preset)
                        image_data["thumbnail"] = thumb
                else:
                    image_data = generate_blog_images(
                        topic=topic,
                        content=content,
                        user_image_paths=user_image_paths,
                        image_count=image_count,
                    )

                result["image_data"] = image_data
                logger.info(f"이미지 생성 완료: 썸네일 + 본문 {len(image_data.get('body_images', []))}장")

            except Exception as img_err:
                logger.warning(f"이미지 생성 실패 (텍스트만 사용): {img_err}")
                include_images = False

        # 4. HTML 포맷팅 (이미지 데이터 포함)
        html = format_column_html(content, persona_id, include_images, image_data)
        result["html_content"] = html

        # 5. 미리보기 생성
        preview_html = format_column_preview(content, persona_id, image_data if include_images else None)
        result["preview_html"] = preview_html

        # 6. 미리보기 파일 저장
        safe_topic = topic.replace(" ", "_")[:30]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        preview_filename = f"preview_{safe_topic}_{timestamp}.html"
        preview_path = os.path.join(PREVIEW_DIR, preview_filename)

        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(preview_html)

        result["preview_path"] = preview_path
        result["success"] = gen_result["success"]

        if not gen_result["success"]:
            result["error"] = (
                f"유사도 검증 미통과 (최대: {gen_result['similarity_check']['max_doc_similarity']:.3f})"
            )

        img_info = f", 이미지 {image_data['total_count']}장" if image_data else ""
        logger.info(f"미리보기 생성 완료: {title} ({len(content)}자, {gen_result['attempts']}회 시도{img_info})")

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"미리보기 생성 실패: {e}")

    return result


def publish_content(
    title,
    html_content,
    raw_content="",
    category=None,
    tags=None,
    blog_id="jninsa",
):
    """
    생성된 컨텐츠를 블로그에 발행

    Args:
        title: 글 제목
        html_content: HTML 본문
        raw_content: 원본 텍스트 (히스토리 저장용)
        category: 카테고리
        tags: 태그 리스트
        blog_id: 블로그 ID

    Returns:
        dict: 발행 결과
    """
    from src.naver_poster import quick_post

    result = quick_post(title, html_content, category, tags, blog_id)
    result["raw_content"] = raw_content

    # 히스토리에 저장
    _save_to_history(
        {
            "title": title,
            "topic": title,
            "published_at": result.get("published_at"),
            "url": result.get("url"),
            "success": result.get("success"),
            "char_count": len(raw_content),
        }
    )

    return result


def batch_generate(topics_config):
    """
    배치 미리보기 생성

    Args:
        topics_config: list of dicts, 각각:
            {
                'topic': str,
                'publish_mode': 'immediate' | 'scheduled',
                'scheduled_time': str (ISO format, optional),
                'category': str (optional),
                'tags': list (optional),
            }

    Returns:
        list: 생성 결과 리스트
    """
    results = []
    for idx, config in enumerate(topics_config):
        logger.info(
            f"배치 생성 {idx + 1}/{len(topics_config)}: {config['topic']}"
        )
        preview = generate_preview(config["topic"])
        preview["publish_mode"] = config.get("publish_mode", "immediate")
        preview["scheduled_time"] = config.get("scheduled_time")
        preview["category"] = config.get("category")
        preview["tags"] = config.get("tags", [])
        results.append(preview)

    return results


def batch_publish(batch_results, blog_id="jninsa"):
    """
    배치 발행 (즉시 발행 항목만)

    Args:
        batch_results: batch_generate의 결과
        blog_id: 블로그 ID

    Returns:
        list: 발행 결과
    """
    from src.scheduler import PublishScheduler

    scheduler = PublishScheduler()
    publish_results = []

    for item in batch_results:
        if not item["success"]:
            publish_results.append(
                {"topic": item.get("title", ""), "success": False, "error": item["error"]}
            )
            continue

        if item["publish_mode"] == "immediate":
            result = publish_content(
                title=item["title"],
                html_content=item["html_content"],
                raw_content=item["raw_content"],
                category=item.get("category"),
                tags=item.get("tags"),
                blog_id=blog_id,
            )
            publish_results.append(result)

        elif item["publish_mode"] == "scheduled":
            # 스케줄러에 등록
            queue_item = scheduler.add_to_queue(
                topic=item["title"],
                publish_mode="scheduled",
                scheduled_time=item.get("scheduled_time"),
                category=item.get("category"),
                tags=item.get("tags"),
            )
            # 이미 생성된 컨텐츠를 큐에 세팅
            queue_item["content"] = item["raw_content"]
            queue_item["html"] = item["html_content"]
            queue_item["title"] = item["title"]
            queue_item["status"] = "ready"
            scheduler._save_queue()

            publish_results.append(
                {
                    "topic": item["title"],
                    "success": True,
                    "scheduled_for": item.get("scheduled_time"),
                    "queue_id": queue_item["id"],
                }
            )

    return publish_results


def get_history(limit=20):
    """발행 히스토리 조회"""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
        return history[-limit:]
    except (json.JSONDecodeError, IOError):
        return []


def _save_to_history(record):
    """히스토리에 기록 추가"""
    ensure_dirs()
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    history.append(record)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
