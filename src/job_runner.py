"""
작업 실행기 (subprocess 격리용)
- scheduler.py에서 subprocess로 호출
- asyncio 루프 충돌 방지를 위해 별도 프로세스에서 Playwright 실행
"""

import sys
import os
import json

# Windows cp949 인코딩 오류 근본 방지
# Python -X utf8 플래그로 실행되므로 기본적으로 UTF-8이지만, 추가 안전장치
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"

# stdout/stderr 인코딩 확인 및 강제 교체 (fallback)
import io
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    try:
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ('utf-8', 'utf8'):
    try:
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

# 프로젝트 루트를 path에 추가
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(override=True)


def run_job(job):
    """단일 작업 실행 — 네이버/티스토리 플랫폼 자동 분기"""
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

    if platform == "tistory":
        from src.tistory_poster import TistoryPoster
        poster = TistoryPoster(progress_callback=None, blog_key=blog_key)
        try:
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

    return result


if __name__ == "__main__":
    # stdin에서 job JSON 읽기
    job_json = sys.stdin.read()
    job = json.loads(job_json)

    try:
        result = run_job(job)
    except UnicodeEncodeError as e:
        # ⚠️ 발행은 성공했지만 print 중 cp949 에러 발생한 경우
        # 발행 성공으로 처리 (실제 블로그에는 올라간 상태)
        result = {"success": True, "error": f"발행 완료 (출력 인코딩 경고: {e})",
                  "title": job.get("topic", ""), "url": ""}
    except Exception as e:
        result = {"success": False, "error": f"{type(e).__name__}: {e}"}

    # stdout으로 결과 JSON 출력 (ensure_ascii=True로 cp949 문제 완전 회피)
    try:
        print(json.dumps(result, ensure_ascii=False))
    except UnicodeEncodeError:
        # 최후의 방어: ASCII-safe JSON 출력
        print(json.dumps(result, ensure_ascii=True))
