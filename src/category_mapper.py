"""
카테고리 자동 매핑 모듈
- 키워드 기반으로 블로그 카테고리 자동 분류
- config/categories.json 설정 파일 사용
"""

import os
import json


CATEGORIES_PATH = "config/categories.json"


def load_category_config(persona_id):
    """카테고리 설정 로드"""
    try:
        with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get(persona_id, {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def auto_classify(topic, content="", persona_id="yun_ung_chae"):
    """
    키워드/주제 + 본문으로 카테고리 자동 분류

    Args:
        topic: 키워드/주제
        content: 본문 텍스트 (선택)
        persona_id: 페르소나 ID

    Returns:
        dict: {
            'category_no': str,
            'category_name': str,
            'confidence': float,  # 0~1
            'matched_keywords': list[str],
        }
    """
    config = load_category_config(persona_id)
    if not config:
        return {
            "category_no": None,
            "category_name": "미분류",
            "confidence": 0.0,
            "matched_keywords": [],
        }

    categories = config.get("categories", {})
    default_cat = config.get("default_category", "10")

    # 검색 대상 텍스트
    search_text = (topic + " " + content[:1000]).lower()

    # 카테고리별 매칭 점수 계산
    scores = {}
    matched_keywords_map = {}

    for cat_no, cat_info in categories.items():
        keywords = cat_info.get("keywords", [])
        if not keywords:
            continue

        score = 0
        matched = []

        for kw in keywords:
            kw_lower = kw.lower()
            # 주제에서 발견 → 가중치 3
            if kw_lower in topic.lower():
                score += 3
                matched.append(kw)
            # 본문에서 발견 → 가중치 1
            elif kw_lower in search_text:
                score += 1
                matched.append(kw)

        if score > 0:
            scores[cat_no] = score
            matched_keywords_map[cat_no] = matched

    if not scores:
        return {
            "category_no": default_cat,
            "category_name": categories.get(default_cat, {}).get("name", "기타"),
            "confidence": 0.0,
            "matched_keywords": [],
        }

    # 최고 점수 카테고리
    best_cat = max(scores, key=scores.get)
    best_score = scores[best_cat]
    max_possible = len(categories.get(best_cat, {}).get("keywords", [])) * 3
    confidence = min(best_score / max(max_possible, 1), 1.0)

    return {
        "category_no": best_cat,
        "category_name": categories[best_cat]["name"],
        "confidence": round(confidence, 2),
        "matched_keywords": matched_keywords_map.get(best_cat, []),
    }


def get_all_categories(persona_id="yun_ung_chae"):
    """
    사용 가능한 모든 카테고리 목록

    Returns:
        list[dict]: [{'no': str, 'name': str}, ...]
    """
    config = load_category_config(persona_id)
    categories = config.get("categories", {})
    return [
        {"no": no, "name": info["name"]}
        for no, info in categories.items()
    ]
