"""
예약 발행 스케줄러 (Sync 버전)
- JSON 파일 기반 작업 큐
- 백그라운드 스레드로 예약 시간 도래 시 자동 발행
- Playwright sync API 사용
- Atomic write + 백업으로 데이터 유실 방지
"""

import os
import json
import threading
import time
import sys
import asyncio
import tempfile
import shutil
from datetime import datetime, timedelta


SCHEDULE_DIR = "outputs/schedules"
SCHEDULE_FILE = os.path.join(SCHEDULE_DIR, "jobs.json")
BACKUP_FILE = os.path.join(SCHEDULE_DIR, "jobs.backup.json")

_scheduler_thread = None
_scheduler_running = False
_scheduler_lock = threading.Lock()
_file_lock = threading.Lock()


def _ensure_dir():
    os.makedirs(SCHEDULE_DIR, exist_ok=True)


def load_jobs():
    """작업 목록 로드 — 메인 파일 실패 시 백업에서 복구"""
    _ensure_dir()
    with _file_lock:
        # 1차: 메인 파일 시도
        data = _try_read(SCHEDULE_FILE)
        if data is not None:
            return data

        # 2차: 백업 파일에서 복구
        data = _try_read(BACKUP_FILE)
        if data is not None:
            print(f"[scheduler] jobs.json 손상 → 백업에서 {len(data)}건 복구")
            _atomic_write(SCHEDULE_FILE, data)
            return data

        return []


def _try_read(path):
    """JSON 파일 읽기 시도. 실패 시 None 반환"""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return None
            data = json.loads(content)
            if isinstance(data, list):
                return data
            return None
    except (json.JSONDecodeError, IOError, OSError):
        return None


def _atomic_write(path, data):
    """임시 파일에 쓴 뒤 rename — 중간 크래시에도 파일이 깨지지 않음"""
    _ensure_dir()
    fd, tmp_path = tempfile.mkstemp(
        dir=SCHEDULE_DIR, suffix=".tmp", prefix="jobs_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        # Windows: os.rename 실패 가능 → shutil.move 사용
        shutil.move(tmp_path, path)
    except Exception:
        # 임시 파일 정리
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def save_jobs(jobs):
    """작업 목록 저장 — atomic write + 백업"""
    with _file_lock:
        # 기존 파일이 유효하면 백업 생성
        if os.path.exists(SCHEDULE_FILE):
            existing = _try_read(SCHEDULE_FILE)
            if existing is not None and len(existing) > 0:
                _atomic_write(BACKUP_FILE, existing)

        # atomic write로 메인 파일 저장
        _atomic_write(SCHEDULE_FILE, jobs)


def _next_id():
    jobs = load_jobs()
    if not jobs:
        return 1
    return max(j.get("id", 0) for j in jobs) + 1


def add_job(topic, persona_id, persona_name, blog_key,
            model_id="claude-sonnet-4-6", temperature=0.7,
            include_images=True, image_count=None,
            category_no=None, scheduled_time=None,
            override_title=None, blog_id=None,
            sheet_row_index=None):
    """
    예약 작업 추가

    Args:
        topic: 키워드/주제
        scheduled_time: 예약 시간 (ISO format). None이면 즉시 발행.
        sheet_row_index: 구글시트 행 번호 (발행 완료 시 시트 기록용)
    """
    jobs = load_jobs()
    job = {
        "id": _next_id(),
        "topic": topic,
        "persona_id": persona_id,
        "persona_name": persona_name,
        "blog_key": blog_key,
        "blog_id": blog_id or "",
        "model_id": model_id,
        "temperature": temperature,
        "include_images": include_images,
        "image_count": image_count,
        "category_no": category_no,
        "scheduled_time": scheduled_time,
        "override_title": override_title,
        "sheet_row_index": sheet_row_index,
        "mode": "scheduled" if scheduled_time else "immediate",
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "published_at": None,
        "result_url": None,
        "result_title": None,
        "error": None,
    }
    jobs.append(job)
    save_jobs(jobs)
    return job


def update_job_status(job_id, status, result_url=None, result_title=None, error=None):
    jobs = load_jobs()
    for job in jobs:
        if job["id"] == job_id:
            job["status"] = status
            if result_url:
                job["result_url"] = result_url
            if result_title:
                job["result_title"] = result_title
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
        st = job.get("scheduled_time")
        if st:
            try:
                sched_time = datetime.fromisoformat(st)
                if sched_time <= now:
                    pending.append(job)
            except (ValueError, TypeError):
                pending.append(job)
        else:
            pending.append(job)
    pending.sort(key=lambda j: j.get("scheduled_time") or "")
    return pending


def get_all_jobs():
    jobs = load_jobs()
    status_order = {"publishing": 0, "pending": 1, "published": 2, "failed": 3}
    jobs.sort(key=lambda j: (
        status_order.get(j.get("status", "pending"), 9),
        j.get("id", 0),
    ))
    return jobs


def remove_job(job_id):
    jobs = load_jobs()
    jobs = [j for j in jobs if not (j["id"] == job_id and j["status"] == "pending")]
    save_jobs(jobs)


def clear_completed():
    jobs = load_jobs()
    active = [j for j in jobs if j["status"] in ("pending", "publishing")]
    removed = len(jobs) - len(active)
    save_jobs(active)
    return removed


def clear_all():
    save_jobs([])


def create_interval_schedule(topics, persona_id, persona_name, blog_key,
                             start_time, interval_minutes,
                             model_id="claude-sonnet-4-6", temperature=0.7,
                             include_images=True, image_count=None):
    """간격 발행 스케줄 생성"""
    created_jobs = []
    for idx, topic in enumerate(topics):
        sched_time = start_time + timedelta(minutes=interval_minutes * idx)
        job = add_job(
            topic=topic, persona_id=persona_id, persona_name=persona_name,
            blog_key=blog_key, model_id=model_id, temperature=temperature,
            include_images=include_images, image_count=image_count,
            scheduled_time=sched_time.isoformat(),
        )
        created_jobs.append(job)
    return created_jobs


def execute_job(job, progress_callback=None):
    """단일 작업 실행 (sync) — 네이버/티스토리 플랫폼 자동 분기"""
    job_id = job["id"]
    update_job_status(job_id, "publishing")
    if progress_callback:
        progress_callback(job_id, "publishing", f"발행 중: {job['topic'][:30]}")

    blog_key = job.get("blog_key", "yun_ung_chae")
    try:
        with open("config/blogs.json", "r", encoding="utf-8") as f:
            blogs = json.load(f).get("blogs", {})
        blog_conf = blogs.get(blog_key, {})
        blog_id_key = blog_conf.get("env_id_key", "NAVER_ID")
        blog_id = os.environ.get(blog_id_key, "")
        platform = blog_conf.get("platform", "naver")
    except Exception:
        blog_id = os.environ.get("NAVER_ID", "")
        platform = "naver"

    max_retries = 2
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            if platform == "tistory":
                from src.tistory_poster import TistoryPoster
                poster = TistoryPoster(progress_callback=None, blog_key=blog_key)
                try:
                    poster.connect()
                    result = poster.post_full_pipeline(
                        topic=job["topic"],
                        persona_id=job["persona_id"],
                        persona_name=job["persona_name"],
                        model_id=job.get("model_id", "claude-sonnet-4-6"),
                        temperature=job.get("temperature", 0.7),
                        include_images=job.get("include_images", True),
                        image_count=job.get("image_count"),
                        override_title=job.get("override_title"),
                    )
                finally:
                    poster.close()
            else:
                from src.naver_poster import NaverPoster
                poster = NaverPoster(progress_callback=None, blog_key=blog_key)
                try:
                    result = poster.post_human_like(
                        topic=job["topic"],
                        persona_id=job["persona_id"],
                        persona_name=job["persona_name"],
                        model_id=job.get("model_id", "claude-sonnet-4-6"),
                        temperature=job.get("temperature", 0.7),
                        include_images=job.get("include_images", True),
                        image_count=job.get("image_count"),
                        blog_id=blog_id,
                        category_no=job.get("category_no"),
                        override_title=job.get("override_title"),
                    )
                finally:
                    poster.close()

            if result.get("success"):
                break  # 성공하면 재시도 루프 탈출
            else:
                last_error = result.get("error", "발행 실패")
                if attempt < max_retries:
                    import time as _time
                    print(f"[scheduler] 발행 실패 (시도 {attempt}/{max_retries}), 30초 후 재시도: {last_error}")
                    _time.sleep(30)
                    continue
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            if attempt < max_retries:
                import time as _time
                print(f"[scheduler] 오류 (시도 {attempt}/{max_retries}), 30초 후 재시도: {last_error}")
                _time.sleep(30)
                continue
            else:
                result = {"success": False, "error": last_error}
                break

    # ── 결과 처리 ──
    if result.get("success"):
        update_job_status(
            job_id, "published",
            result_url=result.get("url"),
            result_title=result.get("title"),
        )
        if progress_callback:
            progress_callback(job_id, "published", result.get("url", ""))

        # 발행 히스토리 기록 (순환 임포트 방지: app.py의 save_to_history 대신 직접 저장)
        try:
            persona_id = job.get("persona_id", "unknown")
            hist_dir = os.path.join("outputs", persona_id)
            os.makedirs(hist_dir, exist_ok=True)
            hist_path = os.path.join(hist_dir, "history.json")
            hist_data = []
            if os.path.exists(hist_path):
                try:
                    with open(hist_path, "r", encoding="utf-8") as hf:
                        hist_data = json.load(hf)
                except (json.JSONDecodeError, IOError):
                    hist_data = []
            entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "topic": job.get("topic", ""),
                "content": result.get("title", job.get("topic", "")),
                "url": result.get("url", ""),
                "blog_id": blog_id,
                "source": "scheduler",
            }
            hist_data.insert(0, entry)
            with open(hist_path, "w", encoding="utf-8") as hf:
                json.dump(hist_data, hf, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"[scheduler] 히스토리 기록 실패 (발행은 성공): {e}")

        # 구글시트에 발행 완료 기록
        sheet_row = job.get("sheet_row_index")
        if sheet_row:
            try:
                from src.sheet_manager import mark_published
                mark_published(
                    row_index=sheet_row,
                    post_url=result.get("url", ""),
                )
            except Exception as e:
                print(f"[scheduler] 시트 기록 실패 (발행은 성공): {e}")

        return {
            "job_id": job_id, "success": True,
            "url": result.get("url"), "title": result.get("title"),
        }
    else:
        err = result.get("error", "발행 실패")
        update_job_status(job_id, "failed", error=err)
        if progress_callback:
            progress_callback(job_id, "failed", err)
        return {"job_id": job_id, "success": False, "error": err}


def execute_pending_jobs(progress_callback=None):
    """대기 중인 예약 작업 모두 실행 (sync)"""
    pending = get_pending_jobs()
    if not pending:
        return []
    results = []
    for job in pending:
        result = execute_job(job, progress_callback)
        results.append(result)
        if job != pending[-1]:
            time.sleep(10)
    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 백그라운드 스케줄러 스레드
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _scheduler_loop(check_interval=30, log_callback=None):
    global _scheduler_running
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    if log_callback:
        log_callback("scheduler_started")
    while _scheduler_running:
        try:
            pending = get_pending_jobs()
            if pending:
                if log_callback:
                    log_callback(f"found_{len(pending)}_jobs")
                for job in pending:
                    if not _scheduler_running:
                        break
                    if log_callback:
                        log_callback(f"job_{job['id']}_start")
                    result = execute_job(job)
                    if log_callback:
                        status = "ok" if result.get("success") else "fail"
                        log_callback(f"job_{job['id']}_{status}")
                    if _scheduler_running:
                        time.sleep(10)
        except Exception as e:
            if log_callback:
                log_callback(f"error:{e}")
        for _ in range(check_interval):
            if not _scheduler_running:
                break
            time.sleep(1)
    if log_callback:
        log_callback("scheduler_stopped")


def start_scheduler(check_interval=30, log_callback=None):
    global _scheduler_thread, _scheduler_running
    with _scheduler_lock:
        if _scheduler_running:
            return False
        _scheduler_running = True
        _scheduler_thread = threading.Thread(
            target=_scheduler_loop,
            args=(check_interval, log_callback),
            daemon=True,
            name="blog-scheduler",
        )
        _scheduler_thread.start()
        return True


def stop_scheduler():
    global _scheduler_running
    _scheduler_running = False


def is_scheduler_running():
    return _scheduler_running


def get_scheduler_status():
    jobs = load_jobs()
    pending_jobs = [j for j in jobs if j["status"] == "pending"]
    published_jobs = [j for j in jobs if j["status"] == "published"]
    failed_jobs = [j for j in jobs if j["status"] == "failed"]
    publishing_jobs = [j for j in jobs if j["status"] == "publishing"]
    next_time = None
    for j in pending_jobs:
        st = j.get("scheduled_time")
        if st:
            try:
                t = datetime.fromisoformat(st)
                if next_time is None or t < next_time:
                    next_time = t
            except (ValueError, TypeError):
                pass
    return {
        "running": _scheduler_running,
        "total": len(jobs),
        "pending": len(pending_jobs),
        "publishing": len(publishing_jobs),
        "published": len(published_jobs),
        "failed": len(failed_jobs),
        "next_scheduled": next_time.isoformat() if next_time else None,
    }
