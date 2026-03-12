"""
예약 발행 스케줄러
- 예약된 발행 작업을 관리하고 실행
- JSON 파일 기반 작업 큐
- 간격 발행 (n분 간격) 지원
"""

import os
import json
import asyncio
import threading
from datetime import datetime, timedelta


SCHEDULE_DIR = "outputs/schedules"
SCHEDULE_FILE = os.path.join(SCHEDULE_DIR, "jobs.json")


def _ensure_dir():
    os.makedirs(SCHEDULE_DIR, exist_ok=True)


def load_jobs():
    """예약 작업 목록 로드"""
    _ensure_dir()
    if not os.path.exists(SCHEDULE_FILE):
        return []
    try:
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def save_jobs(jobs):
    """예약 작업 목록 저장"""
    _ensure_dir()
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)


def add_job(title, content, blog_id, category_no=None,
            scheduled_time=None, status="pending"):
    """
    예약 작업 추가

    Args:
        title: 글 제목
        content: 본문 텍스트
        blog_id: 블로그 ID
        category_no: 카테고리 번호
        scheduled_time: 예약 시간 (ISO format 문자열). None이면 즉시 발행 대기.
        status: pending / publishing / published / failed

    Returns:
        dict: 추가된 작업 정보
    """
    jobs = load_jobs()

    job = {
        "id": len(jobs) + 1,
        "title": title,
        "content": content,
        "blog_id": blog_id,
        "category_no": category_no,
        "scheduled_time": scheduled_time,
        "status": status,
        "created_at": datetime.now().isoformat(),
        "published_at": None,
        "result_url": None,
        "error": None,
    }

    jobs.append(job)
    save_jobs(jobs)
    return job


def update_job_status(job_id, status, result_url=None, error=None):
    """작업 상태 업데이트"""
    jobs = load_jobs()
    for job in jobs:
        if job["id"] == job_id:
            job["status"] = status
            if result_url:
                job["result_url"] = result_url
            if error:
                job["error"] = error
            if status == "published":
                job["published_at"] = datetime.now().isoformat()
            break
    save_jobs(jobs)


def get_pending_jobs():
    """발행 대기 중인 작업 (시간 도래한 것만)"""
    jobs = load_jobs()
    now = datetime.now()
    pending = []

    for job in jobs:
        if job["status"] != "pending":
            continue

        if job["scheduled_time"]:
            sched_time = datetime.fromisoformat(job["scheduled_time"])
            if sched_time <= now:
                pending.append(job)
        else:
            # scheduled_time이 없으면 즉시 발행 대상
            pending.append(job)

    return pending


def clear_completed():
    """완료된 작업 정리 (published/failed 제거)"""
    jobs = load_jobs()
    active = [j for j in jobs if j["status"] in ("pending", "publishing")]
    save_jobs(active)
    return len(jobs) - len(active)


def create_interval_schedule(items, start_time, interval_minutes):
    """
    간격 발행 스케줄 생성

    Args:
        items: list of dict with 'title', 'content', 'category_no'
        start_time: datetime - 첫 발행 시간
        interval_minutes: int - 발행 간격 (분)

    Returns:
        list[dict]: 생성된 작업 리스트
    """
    blog_id = os.environ.get("NAVER_ID", "")
    created_jobs = []

    for idx, item in enumerate(items):
        sched_time = start_time + timedelta(minutes=interval_minutes * idx)
        job = add_job(
            title=item["title"],
            content=item["content"],
            blog_id=blog_id,
            category_no=item.get("category_no"),
            scheduled_time=sched_time.isoformat(),
        )
        created_jobs.append(job)

    return created_jobs


async def execute_pending_jobs(progress_callback=None):
    """
    대기 중인 예약 작업 실행

    Args:
        progress_callback: func(job_id, status, message)

    Returns:
        list[dict]: 실행 결과
    """
    from src.naver_poster import NaverPoster

    pending = get_pending_jobs()
    if not pending:
        return []

    results = []
    poster = NaverPoster()

    try:
        await poster.connect()
        await poster.login()

        for job in pending:
            update_job_status(job["id"], "publishing")

            if progress_callback:
                progress_callback(job["id"], "publishing",
                                  f"'{job['title'][:30]}' 발행 중...")

            try:
                post_result = await poster.post(
                    title=job["title"],
                    content=job["content"],
                    blog_id=job["blog_id"],
                    category_no=job.get("category_no"),
                )

                if post_result.get("success"):
                    update_job_status(job["id"], "published",
                                     result_url=post_result.get("url"))
                    results.append({
                        "job_id": job["id"],
                        "title": job["title"],
                        "success": True,
                        "url": post_result.get("url"),
                    })
                else:
                    update_job_status(job["id"], "failed",
                                     error=post_result.get("error", "발행 실패"))
                    results.append({
                        "job_id": job["id"],
                        "title": job["title"],
                        "success": False,
                        "error": post_result.get("error"),
                    })

            except Exception as e:
                update_job_status(job["id"], "failed", error=str(e))
                results.append({
                    "job_id": job["id"],
                    "title": job["title"],
                    "success": False,
                    "error": str(e),
                })

            if progress_callback:
                status = "published" if results[-1]["success"] else "failed"
                progress_callback(job["id"], status,
                                  results[-1].get("url") or results[-1].get("error"))

            # 발행 간 대기
            await asyncio.sleep(5)

    finally:
        await poster.close()

    return results
