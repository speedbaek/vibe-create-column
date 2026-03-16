"""
멀티 에이전트 오케스트레이터
- Planner: 전략 수립, 품질 분석, 개선 루프 (이 모듈 + CLAUDE.md)
- Content Writer: 콘텐츠 생성 파이프라인 (Sub-agent #1)
- Automation: 네이버 발행 자동화 (Sub-agent #2)

사용법:
    from src.agent_orchestrator import run_full_pipeline, run_content_agent, run_automation_agent

    # 전체 파이프라인 (Planner 주도)
    result = run_full_pipeline("상표등록 필수인 이유", mode="human_like")

    # 콘텐츠만 생성
    content = run_content_agent("상표등록", persona_id="yun_ung_chae")

    # 발행만 실행
    pub = run_automation_agent(content, mode="human_like")
"""

import os
import json
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Planner 메모리 경로 ──────────────────────────────
CLAUDE_MD_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "CLAUDE.md")
PLANNER_LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs", "planner_log.json")


def _log(msg):
    print(f"[Orchestrator] {msg}")
    logger.info(msg)


# ══════════════════════════════════════════════════════
#  Sub-agent #1: Content Writer
# ══════════════════════════════════════════════════════

def run_content_agent(
    topic,
    persona_id="yun_ung_chae",
    persona_name="윤웅채",
    model_id="claude-sonnet-4-6",
    temperature=0.7,
    include_images=True,
    image_count=4,
    title_count=3,
    planner_directives=None,
):
    """
    Content Writer 에이전트: 콘텐츠 생성 파이프라인

    Args:
        topic: 키워드/주제
        persona_id: 페르소나 ID
        planner_directives: Planner가 전달하는 품질 지시사항 (dict)
            예: {"reduce_sentence_length": True, "emphasis_ratio": 0.1}

    Returns:
        dict: {
            'success': bool,
            'title': str,
            'raw_content': str,
            'image_data': dict,
            'char_count': int,
            'quality_metrics': dict,  # Planner가 분석할 수 있는 품질 지표
        }
    """
    _log(f"[Content Writer] 콘텐츠 생성 시작: '{topic}'")
    start_time = time.time()

    try:
        from src.orchestrator import generate_preview

        gen_result = generate_preview(
            topic=topic,
            persona_id=persona_id,
            persona_name=persona_name,
            model_id=model_id,
            temperature=temperature,
            include_images=include_images,
            image_count=image_count,
            auto_title=True,
            title_count=title_count,
        )

        if not gen_result.get("success"):
            return {"success": False, "error": "콘텐츠 생성 실패", "agent": "content_writer"}

        # 품질 지표 수집 (Planner가 분석)
        content = gen_result["raw_content"]
        quality_metrics = _analyze_content_quality(content)

        elapsed = time.time() - start_time
        _log(f"[Content Writer] 생성 완료: {gen_result['char_count']}자, {elapsed:.1f}초")

        return {
            "success": True,
            "title": gen_result["title"],
            "title_candidates": gen_result.get("title_candidates", []),
            "raw_content": content,
            "html_content": gen_result.get("html_content", ""),
            "image_data": gen_result.get("image_data"),
            "char_count": gen_result["char_count"],
            "attempts": gen_result.get("attempts", 1),
            "similarity": gen_result.get("similarity", {}),
            "quality_metrics": quality_metrics,
            "elapsed_seconds": elapsed,
            "agent": "content_writer",
        }

    except Exception as e:
        _log(f"[Content Writer] 오류: {e}")
        return {"success": False, "error": str(e), "agent": "content_writer"}


def _analyze_content_quality(content):
    """콘텐츠 품질 지표 분석 (Planner용)"""
    import re

    lines = [l.strip() for l in content.split("\n") if l.strip()]
    sentences = re.split(r'[.!?]\s+', content)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 5]

    # 문장 길이 통계
    sent_lengths = [len(s) for s in sentences]
    avg_sent_len = sum(sent_lengths) / len(sent_lengths) if sent_lengths else 0
    sent_len_std = (sum((l - avg_sent_len) ** 2 for l in sent_lengths) / len(sent_lengths)) ** 0.5 if sent_lengths else 0

    # 소제목 수
    heading_count = len(re.findall(r'^##\s+', content, re.MULTILINE))

    # 볼드 키워드 수
    bold_count = len(re.findall(r'\*\*(.+?)\*\*', content))

    # 링크 마커 수
    link_marker_count = len(re.findall(r'\{\{LINK:', content))

    # 문단 수 (빈 줄로 구분)
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

    # 어미 패턴 분석
    endings = {
        "formal": len(re.findall(r'습니다[.!]', content)),
        "casual": len(re.findall(r'(거죠|이죠|인데요|네요)[.!]', content)),
        "imperative": len(re.findall(r'(하세요|하십시오|바랍니다)[.!]', content)),
    }
    total_endings = sum(endings.values()) or 1
    ending_ratios = {k: round(v / total_endings, 2) for k, v in endings.items()}

    return {
        "total_chars": len(content),
        "sentence_count": len(sentences),
        "avg_sentence_length": round(avg_sent_len, 1),
        "sentence_length_std": round(sent_len_std, 1),
        "heading_count": heading_count,
        "paragraph_count": len(paragraphs),
        "bold_keyword_count": bold_count,
        "link_marker_count": link_marker_count,
        "ending_ratios": ending_ratios,
    }


# ══════════════════════════════════════════════════════
#  Sub-agent #2: Automation
# ══════════════════════════════════════════════════════

def run_automation_agent(
    content_result,
    mode="human_like",
    blog_id=None,
    category_no=None,
    override_title=None,
    progress_callback=None,
):
    """
    Automation 에이전트: 네이버 블로그 발행

    Args:
        content_result: run_content_agent()의 반환값 또는 호환 dict
        mode: "human_like" (시뮬레이션) | "fast" (원클릭)
        blog_id: 네이버 블로그 ID
        category_no: 카테고리 번호

    Returns:
        dict: 발행 결과 + 메타데이터
    """
    _log(f"[Automation] 발행 시작: mode={mode}")

    if not content_result.get("success"):
        return {"success": False, "error": "콘텐츠가 유효하지 않음", "agent": "automation"}

    title = override_title or content_result["title"]
    content = content_result["raw_content"]
    image_data = content_result.get("image_data")

    try:
        from src.naver_poster import NaverPoster

        poster = NaverPoster(progress_callback=progress_callback)

        try:
            # 브라우저 실행 + 로그인
            poster.connect()
            poster.login()
            blog_id = blog_id or os.environ.get("NAVER_ID", "")

            # 이미지 다운로드
            local_image_paths = []
            if image_data:
                from src.image_handler import download_dalle_images
                images_dir = os.path.join("outputs", "images")
                local_paths = download_dalle_images(image_data, output_dir=images_dir)
                local_image_paths = [p for p in local_paths if p and os.path.exists(p)]

            # 에디터 이동
            poster._navigate_to_editor(blog_id)

            # 이미지 CDN 업로드
            native_image_components = []
            if local_image_paths:
                native_image_components = poster._upload_images(blog_id, local_image_paths)

            # SmartEditor Document 빌드
            from src.se_converter import build_document_data
            se_doc_data = build_document_data(
                title=title,
                text=content,
                image_urls=native_image_components if native_image_components else None,
            )

            # 콘텐츠 설정 (모드에 따라)
            if mode == "human_like":
                set_result = poster._human_like_set_content(se_doc_data, title)
            else:
                set_result = poster._set_document_data(se_doc_data)

            if not set_result.get("ok"):
                return {"success": False, "error": f"setDocumentData 실패: {set_result.get('error')}", "agent": "automation"}

            # 카테고리
            if category_no:
                poster._set_category(category_no)

            # 검증
            validation = poster._validate()
            if not validation.get("valid"):
                return {"success": False, "error": f"검증 실패: {validation.get('reason')}", "agent": "automation"}

            # 발행 전 사람 행동
            if mode == "human_like":
                poster._human_scroll("up", 2000)
                poster._human_delay(1.0, 2.0)
                poster._human_scroll("down", 500)
                poster._human_delay(0.5, 1.0)
                poster._human_scroll("up", 2000)
                poster._human_delay(1.0, 2.0)

            # 발행
            publish_result = poster._publish()

            publish_result["title"] = title
            publish_result["char_count"] = content_result.get("char_count", len(content))
            publish_result["image_count"] = len(native_image_components)
            publish_result["posting_mode"] = mode
            publish_result["agent"] = "automation"

            return publish_result

        finally:
            poster.close()

    except Exception as e:
        _log(f"[Automation] 오류: {e}")
        return {"success": False, "error": str(e), "agent": "automation"}


# ══════════════════════════════════════════════════════
#  Planner: 전체 파이프라인 + 품질 분석
# ══════════════════════════════════════════════════════

def run_full_pipeline(
    topic,
    persona_id="yun_ung_chae",
    persona_name="윤웅채",
    mode="human_like",
    model_id="claude-sonnet-4-6",
    temperature=0.7,
    include_images=True,
    image_count=4,
    blog_id=None,
    category_no=None,
    progress_callback=None,
):
    """
    Planner 주도 전체 파이프라인

    1. Content Writer에게 콘텐츠 생성 지시
    2. 품질 분석
    3. Automation에게 발행 지시
    4. 결과 기록 (Planner 로그)

    Returns:
        dict: 전체 파이프라인 결과
    """
    pipeline_start = time.time()
    _log(f"[Planner] 파이프라인 시작: '{topic}' (mode={mode})")

    # Phase 1: Content Writer
    _log("[Planner] Phase 1: Content Writer 실행")
    content_result = run_content_agent(
        topic=topic,
        persona_id=persona_id,
        persona_name=persona_name,
        model_id=model_id,
        temperature=temperature,
        include_images=include_images,
        image_count=image_count,
    )

    if not content_result.get("success"):
        _save_planner_log(topic, content_result, None, "content_failed")
        return {
            "success": False,
            "error": content_result.get("error"),
            "phase": "content_generation",
        }

    # Phase 2: Planner 품질 분석
    _log("[Planner] Phase 2: 품질 분석")
    quality = content_result.get("quality_metrics", {})
    quality_verdict = _evaluate_quality(quality)
    _log(f"[Planner] 품질 평가: {quality_verdict['grade']} ({quality_verdict['notes']})")

    # Phase 3: Automation
    _log("[Planner] Phase 3: Automation 실행")
    publish_result = run_automation_agent(
        content_result=content_result,
        mode=mode,
        blog_id=blog_id,
        category_no=category_no,
        progress_callback=progress_callback,
    )

    # Phase 4: 결과 기록
    pipeline_elapsed = time.time() - pipeline_start
    _log(f"[Planner] 파이프라인 완료: {pipeline_elapsed:.1f}초")

    pipeline_result = {
        "success": publish_result.get("success", False),
        "url": publish_result.get("url", ""),
        "title": content_result.get("title", ""),
        "char_count": content_result.get("char_count", 0),
        "image_count": publish_result.get("image_count", 0),
        "quality_metrics": quality,
        "quality_verdict": quality_verdict,
        "posting_mode": mode,
        "pipeline_elapsed": round(pipeline_elapsed, 1),
        "content_elapsed": content_result.get("elapsed_seconds", 0),
    }

    _save_planner_log(topic, content_result, publish_result, quality_verdict["grade"])

    return pipeline_result


def _evaluate_quality(metrics):
    """품질 지표 기반 등급 평가"""
    notes = []
    score = 100

    # 문장 길이 다양성 체크
    std = metrics.get("sentence_length_std", 0)
    if std < 10:
        score -= 15
        notes.append("문장 길이 균일 (다양성 부족)")
    elif std > 30:
        notes.append("문장 길이 다양성 양호")

    # 어미 비율 체크
    endings = metrics.get("ending_ratios", {})
    formal = endings.get("formal", 0)
    if formal > 0.75:
        score -= 10
        notes.append("~습니다 어미 과다")
    elif formal < 0.5:
        notes.append("어미 다양성 양호")

    # 글자 수 체크
    chars = metrics.get("total_chars", 0)
    if chars < 1500:
        score -= 20
        notes.append("글 길이 부족")
    elif chars > 3500:
        notes.append("글 길이 적절")

    # 소제목 수 체크
    headings = metrics.get("heading_count", 0)
    if headings < 3:
        score -= 10
        notes.append("소제목 부족")
    elif headings > 6:
        score -= 5
        notes.append("소제목 과다")

    # 등급 결정
    if score >= 85:
        grade = "A"
    elif score >= 70:
        grade = "B"
    elif score >= 55:
        grade = "C"
    else:
        grade = "D"

    return {
        "grade": grade,
        "score": score,
        "notes": " | ".join(notes) if notes else "특이사항 없음",
    }


def _save_planner_log(topic, content_result, publish_result, grade):
    """Planner 실행 로그 저장 (개선 루프용)"""
    os.makedirs(os.path.dirname(PLANNER_LOG_PATH), exist_ok=True)

    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "topic": topic,
        "grade": grade,
        "title": content_result.get("title", "") if content_result else "",
        "char_count": content_result.get("char_count", 0) if content_result else 0,
        "quality_metrics": content_result.get("quality_metrics", {}) if content_result else {},
        "publish_success": publish_result.get("success", False) if publish_result else False,
        "publish_url": publish_result.get("url", "") if publish_result else "",
    }

    # 기존 로그 읽기
    log_data = []
    if os.path.exists(PLANNER_LOG_PATH):
        try:
            with open(PLANNER_LOG_PATH, "r", encoding="utf-8") as f:
                log_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            log_data = []

    log_data.insert(0, log_entry)

    # 최대 100건 유지
    log_data = log_data[:100]

    with open(PLANNER_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

    _log(f"[Planner] 로그 저장: grade={grade}, topic={topic}")


def get_planner_insights(limit=10):
    """
    Planner 로그에서 인사이트 추출 (개선 방향 도출)

    Returns:
        dict: {
            'total_posts': int,
            'avg_grade': str,
            'avg_chars': int,
            'common_issues': list,
            'improvement_suggestions': list,
        }
    """
    if not os.path.exists(PLANNER_LOG_PATH):
        return {"total_posts": 0, "message": "발행 이력 없음"}

    try:
        with open(PLANNER_LOG_PATH, "r", encoding="utf-8") as f:
            log_data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"total_posts": 0, "message": "로그 파싱 실패"}

    recent = log_data[:limit]
    if not recent:
        return {"total_posts": 0, "message": "발행 이력 없음"}

    # 등급 분석
    grades = [e.get("grade", "?") for e in recent]
    grade_counts = {}
    for g in grades:
        grade_counts[g] = grade_counts.get(g, 0) + 1

    # 평균 글자 수
    chars = [e.get("char_count", 0) for e in recent if e.get("char_count")]
    avg_chars = int(sum(chars) / len(chars)) if chars else 0

    # 공통 이슈 수집
    all_notes = []
    for entry in recent:
        metrics = entry.get("quality_metrics", {})
        endings = metrics.get("ending_ratios", {})
        if endings.get("formal", 0) > 0.75:
            all_notes.append("~습니다 어미 과다")
        if metrics.get("sentence_length_std", 0) < 10:
            all_notes.append("문장 길이 균일")
        if metrics.get("heading_count", 0) < 3:
            all_notes.append("소제목 부족")

    # 빈도순 정렬
    issue_counts = {}
    for note in all_notes:
        issue_counts[note] = issue_counts.get(note, 0) + 1
    common_issues = sorted(issue_counts.items(), key=lambda x: -x[1])

    # 개선 제안
    suggestions = []
    for issue, count in common_issues:
        if count >= limit * 0.5:  # 50% 이상 발생
            if "어미" in issue:
                suggestions.append("persona JSON의 sentence_endings.frequency_rule 조정 (formal 비율 낮추기)")
            elif "문장 길이" in issue:
                suggestions.append("base_prompt.md에 '문장 길이를 다양하게' 규칙 추가")
            elif "소제목" in issue:
                suggestions.append("base_prompt.md에 '소제목 최소 4개' 규칙 추가")

    return {
        "total_posts": len(log_data),
        "recent_count": len(recent),
        "grade_distribution": grade_counts,
        "avg_chars": avg_chars,
        "common_issues": common_issues[:5],
        "improvement_suggestions": suggestions,
    }
