"""
Google Sheets 키워드 관리 모듈
- 구글시트에서 키워드 풀 읽기
- 카테고리 자동 분류 + 대상블로그 지정
- 발행 완료 시 발행일/URL 기록
- AI 스마트 키워드 선정 (다양성 보장)
"""

import os
import json
import random
import gspread
from datetime import datetime

# ── 설정 ──────────────────────────────────────────
SERVICE_ACCOUNT_PATH = "config/google_service_account.json"
SHEET_KEY = "1B-9hmCqvdu3QivCPy12z6nSeydTTqk8xnC5YONMmFSA"

# 카테고리 자동 분류 규칙
CATEGORY_RULES = {
    "특허": ["특허", "발명", "명세서", "청구항", "심사", "거절", "PCT", "실용신안", "BM특허", "SW특허",
             "특허출원", "특허등록", "특허비용", "특허기간", "특허변리사", "특허내는법", "특허확인",
             "특허사무소", "특허소송", "특허침해", "특허무효", "특허전략", "가출원", "우선심사"],
    "상표": ["상표", "브랜드", "상호", "네이밍", "상품류", "서비스표", "로고등록", "상표권",
             "상표출원", "상표등록", "상표검색", "상표조회", "상표비용", "상표침해", "상표거절",
             "스마트스토어브랜드", "키프리스상표"],
    "디자인": ["디자인", "외관", "형상", "모양", "의장", "디자인권", "디자인등록", "디자인출원",
              "디자인보호", "디자인침해"],
    "해외/국제": ["해외", "PCT", "마드리드", "미국특허", "중국특허", "일본특허", "국제출원",
                 "해외상표", "해외특허", "글로벌"],
    "분쟁/소송": ["분쟁", "소송", "침해", "무효심판", "취소심판", "경고장", "손해배상",
                 "가처분", "심판", "이의신청", "통상실시권", "전용실시권"],
    "창업/비즈니스": ["스타트업", "창업", "벤처", "사업자", "법인", "투자", "IP전략",
                    "지식재산", "기술이전", "라이선스", "직무발명"],
}

# 대상블로그 분류 규칙
# 윤변 전용: 개인적 경험, 1인칭 시점이 강한 키워드
# 공식 전용: 법인 소개, 제도 설명이 강한 키워드
# 대부분은 "공통"
BLOG_SPECIFIC = {
    "yun": [],  # 특별히 윤변 전용인 키워드는 거의 없음 (대부분 공통)
    "official": [],  # 특별히 공식 전용인 키워드도 거의 없음
}


def _get_client():
    """gspread 클라이언트 생성"""
    return gspread.service_account(filename=SERVICE_ACCOUNT_PATH)


def _get_worksheet():
    """시트 워크시트 반환"""
    gc = _get_client()
    sh = gc.open_by_key(SHEET_KEY)
    return sh.sheet1


def classify_category(keyword):
    """키워드 → 카테고리 자동 분류"""
    kw_lower = keyword.lower().replace(" ", "")

    scores = {}
    for cat, terms in CATEGORY_RULES.items():
        score = 0
        for term in terms:
            if term.replace(" ", "") in kw_lower:
                score += len(term)  # 긴 매칭일수록 높은 점수
        if score > 0:
            scores[cat] = score

    if scores:
        return max(scores, key=scores.get)
    return "기타"


def classify_blog(keyword, category):
    """키워드+카테고리 → 대상블로그 판단"""
    # 현재는 대부분 "공통"
    # 추후 특정 키워드만 윤변/공식 전용으로 분류 가능
    return "공통"


def auto_fill_categories(dry_run=False):
    """
    카테고리/대상블로그 열이 비어있는 행에 자동 채우기

    Args:
        dry_run: True면 실제 쓰기 없이 결과만 반환

    Returns:
        dict: {"filled": int, "total": int, "results": list}
    """
    ws = _get_worksheet()
    all_rows = ws.get_all_values()
    headers = all_rows[0]

    # 열 인덱스 확인
    col_keyword = 0   # A
    col_category = 4  # E
    col_blog = 5      # F

    results = []
    updates = []

    for i, row in enumerate(all_rows[1:], start=2):  # 2행부터 (1-indexed)
        keyword = row[col_keyword].strip() if len(row) > col_keyword else ""
        existing_cat = row[col_category].strip() if len(row) > col_category else ""
        existing_blog = row[col_blog].strip() if len(row) > col_blog else ""

        if not keyword:
            continue

        # 카테고리가 비어있으면 자동 분류
        if not existing_cat:
            cat = classify_category(keyword)
            updates.append({"row": i, "col": col_category + 1, "value": cat})
            results.append({"keyword": keyword, "category": cat, "row": i})

        # 대상블로그가 비어있으면 자동 분류
        if not existing_blog:
            cat = existing_cat or classify_category(keyword)
            blog = classify_blog(keyword, cat)
            updates.append({"row": i, "col": col_blog + 1, "value": blog})

    if not dry_run and updates:
        # 배치 업데이트 (API 호출 최소화)
        batch_cells = []
        for u in updates:
            batch_cells.append(gspread.Cell(u["row"], u["col"], u["value"]))
        ws.update_cells(batch_cells)

    return {
        "filled": len([r for r in results]),
        "total": len(all_rows) - 1,
        "results": results[:20],  # 미리보기용 20개
    }


def _get_excluded_keywords(blog_key=None):
    """
    이미 예약/발행된 키워드 수집 (중복 방지용)

    Returns:
        set: 제외할 키워드 set
    """
    excluded = set()

    # 1. jobs.json에서 pending/publishing/published 키워드 수집
    try:
        import json
        jobs_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                  "outputs", "schedules", "jobs.json")
        if os.path.exists(jobs_path):
            with open(jobs_path, "r", encoding="utf-8") as f:
                jobs = json.load(f)
            for j in jobs:
                status = j.get("status", "")
                # pending/publishing은 무조건 제외, published도 제외 (같은 키워드 재사용 방지)
                if status in ("pending", "publishing", "published"):
                    topic = (j.get("topic") or "").strip()
                    if topic:
                        # 블로그 키가 지정된 경우 해당 블로그만 필터
                        if blog_key and j.get("blog_key") != blog_key:
                            continue
                        excluded.add(topic)
    except Exception as e:
        print(f"[sheet_manager] jobs.json 읽기 오류: {e}")

    # 2. 발행 히스토리에서 최근 발행 키워드 수집
    try:
        history_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")
        for persona_dir in ["yun_ung_chae", "teheran_official"]:
            hist_path = os.path.join(history_dir, persona_dir, "history.json")
            if os.path.exists(hist_path):
                with open(hist_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
                for entry in history:
                    topic = (entry.get("topic") or "").strip()
                    if topic:
                        excluded.add(topic)
    except Exception as e:
        print(f"[sheet_manager] history.json 읽기 오류: {e}")

    return excluded


def _is_keyword_similar(keyword, excluded_set):
    """
    키워드가 제외 목록과 유사한지 확인
    - 정확 일치
    - 부분 포함 (한쪽이 다른 쪽에 포함되는 경우)

    Args:
        keyword: 확인할 키워드
        excluded_set: 제외 키워드 set

    Returns:
        bool: True면 제외 대상
    """
    kw = keyword.strip()
    kw_no_space = kw.replace(" ", "")

    for ex in excluded_set:
        ex_no_space = ex.replace(" ", "")
        # 정확 일치
        if kw == ex or kw_no_space == ex_no_space:
            return True
        # 부분 포함 (짧은 쪽이 2글자 이상이어야 의미 있는 매칭)
        if len(kw_no_space) >= 2 and len(ex_no_space) >= 2:
            if kw_no_space in ex_no_space or ex_no_space in kw_no_space:
                return True

    return False


def get_available_keywords(persona_id="yun_ung_chae", limit=50, blog_key=None):
    """
    발행 가능한 키워드 목록 가져오기
    - 발행일이 비어있는 키워드만
    - 해당 블로그 대상 키워드만 (공통 포함)
    - 예약 대기/발행 완료 키워드 제외

    Args:
        persona_id: 페르소나 ID
        limit: 최대 반환 수
        blog_key: 블로그 키 (중복 필터용)

    Returns:
        list[dict]: [{keyword, category, pc, mo, total, row_index}, ...]
    """
    ws = _get_worksheet()
    all_rows = ws.get_all_values()

    # 블로그 필터
    if persona_id == "yun_ung_chae":
        blog_filter_set = {"공통", "윤변", ""}
    elif persona_id == "teheran_official":
        blog_filter_set = {"공통", "공식", ""}
    else:
        blog_filter_set = {"공통", ""}

    # 예약/발행 키워드 제외 목록
    excluded = _get_excluded_keywords(blog_key=blog_key)
    excluded_count = 0

    available = []
    for i, row in enumerate(all_rows[1:], start=2):
        keyword = row[0].strip() if len(row) > 0 else ""
        if not keyword:
            continue

        # 발행일이 있으면 이미 사용된 키워드
        pub_date = row[6].strip() if len(row) > 6 else ""
        if pub_date:
            continue

        # 대상블로그 필터
        target_blog = row[5].strip() if len(row) > 5 else ""
        if target_blog and target_blog not in blog_filter_set:
            continue

        # 예약/발행 키워드 중복 체크
        if excluded and _is_keyword_similar(keyword, excluded):
            excluded_count += 1
            continue

        category = row[4].strip() if len(row) > 4 else ""
        pc = int(row[1]) if len(row) > 1 and row[1].strip().isdigit() else 0
        mo = int(row[2]) if len(row) > 2 and row[2].strip().isdigit() else 0
        total = int(row[3]) if len(row) > 3 and row[3].strip().isdigit() else 0

        available.append({
            "keyword": keyword,
            "category": category,
            "pc": pc,
            "mo": mo,
            "total": total,
            "row_index": i,
        })

    if excluded_count > 0:
        print(f"[sheet_manager] 예약/발행 중복 키워드 {excluded_count}개 제외됨")

    return available[:limit]


def smart_select_keywords(persona_id="yun_ung_chae", count=3, min_volume=50, blog_key=None):
    """
    AI 스마트 키워드 선정 — 다양성 + 조회수 균형 + 중복 방지

    규칙:
    1. 카테고리가 겹치지 않게 (가능한 한)
    2. 조회수가 너무 낮은 건 후순위
    3. 예약/발행 키워드와 중복 제외

    Args:
        persona_id: 페르소나 ID
        count: 선정할 키워드 수
        min_volume: 최소 합계 조회수
        blog_key: 블로그 키 (중복 필터용)

    Returns:
        list[dict]: 선정된 키워드 리스트
    """
    available = get_available_keywords(persona_id, limit=200, blog_key=blog_key)

    if not available:
        return []

    # 최소 조회수 필터
    filtered = [k for k in available if k["total"] >= min_volume]
    if len(filtered) < count:
        filtered = available  # 조회수 필터 완화

    # 카테고리별 그룹핑
    by_category = {}
    for kw in filtered:
        cat = kw.get("category") or "기타"
        by_category.setdefault(cat, []).append(kw)

    selected = []
    used_categories = set()

    # 1차: 카테고리 다양성 — 각 카테고리에서 1개씩
    cat_list = list(by_category.keys())
    random.shuffle(cat_list)

    for cat in cat_list:
        if len(selected) >= count:
            break
        if cat in used_categories:
            continue

        candidates = by_category[cat]
        # 조회수 상위 50%에서 랜덤 선택
        candidates.sort(key=lambda x: x["total"], reverse=True)
        top_half = candidates[:max(1, len(candidates) // 2)]
        pick = random.choice(top_half)
        selected.append(pick)
        used_categories.add(cat)

    # 2차: 부족하면 남은 키워드에서 추가 (카테고리 중복 허용)
    if len(selected) < count:
        remaining = [k for k in filtered if k not in selected]
        random.shuffle(remaining)
        # 조회수 높은 순으로 정렬 후 랜덤 요소 추가
        remaining.sort(key=lambda x: x["total"] + random.randint(-50, 50), reverse=True)
        for kw in remaining:
            if len(selected) >= count:
                break
            selected.append(kw)

    return selected


def distribute_times(date_str, count):
    """
    하루 중 발행 시간을 사람처럼 랜덤 분배

    규칙:
    - 발행 가능 시간: 07:00 ~ 22:00
    - 오늘 날짜면 현재 시간 + 10분 이후부터 배정
    - 간격: 10분~90분 사이 랜덤 (균등하지 않게)
    - 너무 밤늦게/새벽은 피함

    Args:
        date_str: 날짜 문자열 "2026-03-20"
        count: 발행 수

    Returns:
        list[str]: ["2026-03-20 08:23", "2026-03-20 09:47", ...]
    """
    from datetime import datetime, timedelta

    # 발행 가능 시간대 (07:00 ~ 22:00 = 15시간 = 900분)
    start_hour = 7
    end_hour = 22
    total_minutes = (end_hour - start_hour) * 60  # 900분

    if count <= 0:
        return []

    # 오늘 날짜인 경우: 현재 시간 + 10분 이후부터 시작
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    if date_str == today_str:
        now_offset = (now.hour - start_hour) * 60 + now.minute + 10  # 현재시간 + 10분
        earliest_offset = max(0, now_offset)
        print(f"[sheet_manager] 오늘 예약: {now.strftime('%H:%M')} 이후 ({earliest_offset}분~) 부터 배정")
    else:
        earliest_offset = 0

    if count == 1:
        if date_str == today_str:
            # 오늘이면 현재 시간 + 10~30분 후
            offset = earliest_offset + random.randint(0, 20)
            if offset >= total_minutes:
                offset = total_minutes - 5
            hour = start_hour + offset // 60
            minute = offset % 60
        else:
            # 미래 날짜면 피크 시간대에서 랜덤
            peak_hours = [9, 10, 12, 13, 14, 17, 18]
            hour = random.choice(peak_hours)
            minute = random.randint(0, 59)
        return [f"{date_str} {hour:02d}:{minute:02d}"]

    # 여러 개: 전체 시간대를 대략 나눈 뒤 랜덤 오프셋
    min_gap = 10
    available_minutes = total_minutes - earliest_offset

    if available_minutes < count * min_gap:
        print(f"[sheet_manager] ⚠️ 남은 시간({available_minutes}분)이 부족 - 간격 축소")
        min_gap = max(5, available_minutes // count)

    # 시작점
    if earliest_offset > 0:
        first_offset = earliest_offset + random.randint(0, min(20, available_minutes // count))
    else:
        first_offset = random.randint(0, 90)

    times = []
    current = first_offset

    for i in range(count):
        if i == 0:
            offset = current
        else:
            remaining_posts = count - i
            remaining_minutes = total_minutes - current
            avg_gap = remaining_minutes / remaining_posts

            max_gap = min(int(avg_gap * 1.8), 120)
            min_g = max(min_gap, int(avg_gap * 0.3))
            gap = random.randint(min_g, max(min_g, max_gap))

            offset = current + gap

        if offset >= total_minutes:
            offset = total_minutes - random.randint(5, 30)

        current = offset

        hour = start_hour + offset // 60
        minute = offset % 60
        times.append(f"{date_str} {hour:02d}:{minute:02d}")

    return times


def build_schedule(date_str, persona_id, count, min_volume=50, blog_key=None):
    """
    스마트 예약발행 스케줄 생성

    Args:
        date_str: 발행 날짜 "2026-03-20"
        persona_id: 페르소나 ID
        count: 발행 수
        min_volume: 최소 조회수
        blog_key: 블로그 키 (중복 필터용)

    Returns:
        list[dict]: [{keyword, category, total, time, row_index}, ...]
    """
    keywords = smart_select_keywords(persona_id, count=count, min_volume=min_volume, blog_key=blog_key)
    times = distribute_times(date_str, len(keywords))

    schedule = []
    for kw, t in zip(keywords, times):
        schedule.append({
            "keyword": kw["keyword"],
            "category": kw["category"],
            "total": kw["total"],
            "time": t,
            "row_index": kw["row_index"],
        })

    return schedule


def mark_published(row_index, publish_date=None, post_url=""):
    """
    발행 완료 후 시트에 기록

    Args:
        row_index: 행 번호 (1-indexed)
        publish_date: 발행일시 (None이면 현재 시각)
        post_url: 발행된 포스트 URL
    """
    ws = _get_worksheet()

    if publish_date is None:
        publish_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    # G열: 발행일, H열: 발행 링크
    ws.update_cell(row_index, 7, str(publish_date))
    if post_url:
        ws.update_cell(row_index, 8, post_url)


def get_sheet_stats():
    """시트 전체 통계"""
    ws = _get_worksheet()
    all_rows = ws.get_all_values()

    total = len(all_rows) - 1
    published = sum(1 for r in all_rows[1:] if len(r) > 6 and r[6].strip())
    categorized = sum(1 for r in all_rows[1:] if len(r) > 4 and r[4].strip())

    # 카테고리별 분포
    cat_dist = {}
    for r in all_rows[1:]:
        cat = r[4].strip() if len(r) > 4 else ""
        if cat:
            cat_dist[cat] = cat_dist.get(cat, 0) + 1

    return {
        "total_keywords": total,
        "published": published,
        "remaining": total - published,
        "categorized": categorized,
        "uncategorized": total - categorized,
        "category_distribution": cat_dist,
    }


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    print("=== 구글시트 연동 테스트 ===\n")

    # 통계
    stats = get_sheet_stats()
    print(f"전체 키워드: {stats['total_keywords']}개")
    print(f"발행 완료: {stats['published']}개")
    print(f"미발행: {stats['remaining']}개")
    print(f"카테고리 분류됨: {stats['categorized']}개")
    print(f"미분류: {stats['uncategorized']}개")
    print()

    # 카테고리 자동 채우기 (dry run)
    print("=== 카테고리 자동 분류 (미리보기) ===")
    result = auto_fill_categories(dry_run=True)
    print(f"분류 대상: {result['filled']}개")
    for r in result["results"][:10]:
        print(f"  {r['keyword']} → {r['category']}")
    print()

    # 스마트 키워드 선정
    print("=== 스마트 키워드 선정 (3개) ===")
    picks = smart_select_keywords("yun_ung_chae", count=3)
    for p in picks:
        print(f"  [{p['category'] or '미분류'}] {p['keyword']} (조회수: {p['total']})")
