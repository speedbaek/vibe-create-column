"""
예약 발행 스케줄러 v1
- APScheduler 기반 예약 발행
- 배치 큐 관리 (즉시 + 예약 혼합)
- 발행 상태 추적 및 알림
"""

import os
import json
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.memory import MemoryJobStore

logger = logging.getLogger(__name__)

# ── 상수 ──────────────────────────────────────────────

QUEUE_FILE = "outputs/publish_queue.json"
HISTORY_FILE = "outputs/history/post_history.json"


class PublishScheduler:
    """블로그 발행 스케줄러"""

    def __init__(self):
        self.scheduler = BackgroundScheduler(
            jobstores={"default": MemoryJobStore()},
            job_defaults={"coalesce": True, "max_instances": 1},
        )
        self.queue = []
        self._load_queue()

    def _load_queue(self):
        """저장된 큐 로드"""
        if os.path.exists(QUEUE_FILE):
            try:
                with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                    self.queue = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.queue = []

    def _save_queue(self):
        """큐 저장"""
        os.makedirs(os.path.dirname(QUEUE_FILE), exist_ok=True)
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.queue, f, ensure_ascii=False, indent=2)

    def add_to_queue(
        self,
        topic,
        publish_mode="immediate",
        scheduled_time=None,
        category=None,
        tags=None,
        persona_id="yun_ung_chae",
        persona_name="윤웅채",
    ):
        """
        발행 큐에 항목 추가

        Args:
            topic: 키워드/주제
            publish_mode: "immediate" 또는 "scheduled"
            scheduled_time: 예약 시간 (ISO format, publish_mode가 scheduled일 때)
            category: 블로그 카테고리
            tags: 태그 리스트
            persona_id: 페르소나 ID
            persona_name: 페르소나 이름

        Returns:
            dict: 큐 항목 정보
        """
        item = {
            "id": f"post_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(self.queue)}",
            "topic": topic,
            "publish_mode": publish_mode,
            "scheduled_time": scheduled_time,
            "category": category,
            "tags": tags or [],
            "persona_id": persona_id,
            "persona_name": persona_name,
            "status": "pending",  # pending → generating → ready → publishing → published / failed
            "created_at": datetime.now().isoformat(),
            "content": None,
            "html": None,
            "title": None,
            "result": None,
        }

        self.queue.append(item)
        self._save_queue()

        logger.info(
            f"큐 추가: {topic} ({publish_mode}"
            + (f" @ {scheduled_time})" if scheduled_time else ")")
        )
        return item

    def add_batch(self, items):
        """
        배치로 여러 항목 추가

        Args:
            items: list of dicts, 각각 add_to_queue의 인자와 동일

        Returns:
            list: 추가된 큐 항목들
        """
        results = []
        for item_config in items:
            result = self.add_to_queue(**item_config)
            results.append(result)
        return results

    def generate_content(self, queue_id):
        """
        큐 항목의 컨텐츠 생성

        Args:
            queue_id: 큐 항목 ID

        Returns:
            bool: 성공 여부
        """
        from src.engine import generate_column_with_validation
        from src.formatter import format_column_html

        item = self._find_item(queue_id)
        if not item:
            logger.error(f"큐 항목을 찾을 수 없음: {queue_id}")
            return False

        item["status"] = "generating"
        self._save_queue()

        try:
            # 컨텐츠 생성
            gen_result = generate_column_with_validation(
                item["persona_id"], item["persona_name"], item["topic"]
            )

            if gen_result["success"]:
                content = gen_result["content"]
                html = format_column_html(content, item["persona_id"])

                # 제목 추출
                from src.naver_poster import _extract_or_generate_title

                title = _extract_or_generate_title(item["topic"], content)

                item["content"] = content
                item["html"] = html
                item["title"] = title
                item["status"] = "ready"
                item["generation_result"] = {
                    "attempts": gen_result["attempts"],
                    "similarity": gen_result["similarity_check"]["max_doc_similarity"],
                }

                logger.info(f"컨텐츠 생성 완료: {title}")
            else:
                item["status"] = "failed"
                item["result"] = {
                    "error": "유사도 검증 실패",
                    "similarity": gen_result["similarity_check"]["max_doc_similarity"],
                }
                logger.warning(f"컨텐츠 생성 실패 (유사도): {item['topic']}")

        except Exception as e:
            item["status"] = "failed"
            item["result"] = {"error": str(e)}
            logger.error(f"컨텐츠 생성 중 오류: {e}")

        self._save_queue()
        return item["status"] == "ready"

    def publish_item(self, queue_id, blog_id="jninsa"):
        """
        큐 항목 발행

        Args:
            queue_id: 큐 항목 ID
            blog_id: 블로그 ID

        Returns:
            dict: 발행 결과
        """
        from src.naver_poster import quick_post

        item = self._find_item(queue_id)
        if not item:
            return {"success": False, "error": "큐 항목 없음"}

        if item["status"] != "ready":
            return {"success": False, "error": f"발행 불가 상태: {item['status']}"}

        item["status"] = "publishing"
        self._save_queue()

        try:
            result = quick_post(
                title=item["title"],
                html_content=item["html"],
                category=item["category"],
                tags=item["tags"],
                blog_id=blog_id,
            )

            if result["success"]:
                item["status"] = "published"
                item["result"] = result
                logger.info(f"발행 완료: {item['title']} → {result.get('url')}")
            else:
                item["status"] = "failed"
                item["result"] = result
                logger.error(f"발행 실패: {result.get('error')}")

        except Exception as e:
            item["status"] = "failed"
            item["result"] = {"success": False, "error": str(e)}
            logger.error(f"발행 중 오류: {e}")

        self._save_queue()
        return item["result"]

    def process_queue(self, blog_id="jninsa"):
        """
        전체 큐 처리 (즉시 발행 항목 처리)

        Args:
            blog_id: 블로그 ID

        Returns:
            list: 처리 결과 리스트
        """
        results = []

        for item in self.queue:
            if item["status"] == "pending":
                # 1단계: 컨텐츠 생성
                self.generate_content(item["id"])

            if item["status"] == "ready" and item["publish_mode"] == "immediate":
                # 2단계: 즉시 발행
                result = self.publish_item(item["id"], blog_id)
                results.append(
                    {"topic": item["topic"], "title": item["title"], "result": result}
                )

            elif item["status"] == "ready" and item["publish_mode"] == "scheduled":
                # 예약 발행: 스케줄러에 등록
                if item.get("scheduled_time"):
                    self._schedule_publish(item, blog_id)
                    results.append(
                        {
                            "topic": item["topic"],
                            "title": item["title"],
                            "result": {
                                "success": True,
                                "scheduled_for": item["scheduled_time"],
                            },
                        }
                    )

        return results

    def _schedule_publish(self, item, blog_id):
        """예약 발행 등록"""
        try:
            scheduled_dt = datetime.fromisoformat(item["scheduled_time"])

            self.scheduler.add_job(
                func=self.publish_item,
                trigger=DateTrigger(run_date=scheduled_dt),
                args=[item["id"], blog_id],
                id=item["id"],
                replace_existing=True,
            )

            logger.info(f"예약 등록: {item['title']} @ {scheduled_dt}")
        except Exception as e:
            logger.error(f"예약 등록 실패: {e}")

    def start(self):
        """스케줄러 시작"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("스케줄러 시작")

    def stop(self):
        """스케줄러 중지"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("스케줄러 중지")

    def _find_item(self, queue_id):
        """큐에서 항목 찾기"""
        for item in self.queue:
            if item["id"] == queue_id:
                return item
        return None

    def get_queue_status(self):
        """큐 전체 상태 조회"""
        status_summary = {
            "total": len(self.queue),
            "pending": sum(1 for i in self.queue if i["status"] == "pending"),
            "generating": sum(1 for i in self.queue if i["status"] == "generating"),
            "ready": sum(1 for i in self.queue if i["status"] == "ready"),
            "publishing": sum(1 for i in self.queue if i["status"] == "publishing"),
            "published": sum(1 for i in self.queue if i["status"] == "published"),
            "failed": sum(1 for i in self.queue if i["status"] == "failed"),
        }
        return {"summary": status_summary, "items": self.queue}

    def clear_completed(self):
        """완료된 항목 정리"""
        self.queue = [i for i in self.queue if i["status"] not in ("published", "failed")]
        self._save_queue()

    def retry_failed(self):
        """실패한 항목 재시도"""
        for item in self.queue:
            if item["status"] == "failed":
                item["status"] = "pending"
                item["content"] = None
                item["html"] = None
                item["title"] = None
                item["result"] = None
        self._save_queue()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    scheduler = PublishScheduler()

    # 테스트: 배치 큐 추가
    batch = [
        {
            "topic": "스타트업 상표등록 미루면 안 되는 이유",
            "publish_mode": "immediate",
            "tags": ["상표등록", "스타트업", "브랜드보호"],
        },
        {
            "topic": "특허 출원 전 알아야 할 3가지",
            "publish_mode": "scheduled",
            "scheduled_time": (datetime.now() + timedelta(hours=2)).isoformat(),
            "tags": ["특허출원", "발명특허"],
        },
        {
            "topic": "프랜차이즈 상표권 분쟁 예방법",
            "publish_mode": "scheduled",
            "scheduled_time": (datetime.now() + timedelta(hours=5)).isoformat(),
            "tags": ["프랜차이즈", "상표권"],
        },
    ]

    items = scheduler.add_batch(batch)
    print(f"큐 추가 완료: {len(items)}개")

    status = scheduler.get_queue_status()
    print(f"큐 상태: {json.dumps(status['summary'], ensure_ascii=False)}")

    for item in status["items"]:
        mode = "즉시" if item["publish_mode"] == "immediate" else f"예약 @ {item.get('scheduled_time', 'TBD')}"
        print(f"  - [{item['status']}] {item['topic']} ({mode})")
