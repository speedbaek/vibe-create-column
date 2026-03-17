"""
카테고리 자동 매핑 모듈
- 키워드 기반으로 블로그 카테고리 자동 분류
- config/categories.json 설정 파일 사용
- 첫 발행 시 에디터에서 수집한 _raw_categories로 실제 번호 매핑
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


def _find_category_no_by_name(config, category_name):
    """_raw_categories에서 카테고리명으로 실제 categoryNo 찾기"""
    raw = config.get("_raw_categories", [])
    if not raw:
        return None

    # 정확 매칭
    for item in raw:
        if item.get("text", "").strip() == category_name:
            return item.get("value")

    # 부분 매칭 (카테고리명이 포함된 경우)
    for item in raw:
        text = item.get("text", "").strip()
        if category_name in text or text in category_name:
            return item.get("value")

    return None


def auto_classify(topic, content="", persona_id="yun_ung_chae"):
    """
    키워드/주제 + 본문으로 카테고리 자동 분류

    두 가지 구조 지원:
    1. yun_ung_chae 방식: categories = {번호: {name, keywords}}
    2. teheran_official 방식: keyword_to_category = {카테고리명: [키워드들]}

    Returns:
        dict: {category_no, category_name, confidence, matched_keywords}
    """
    config = load_category_config(persona_id)
    if not config:
        return {
            "category_no": None,
            "category_name": "미분류",
            "confidence": 0.0,
            "matched_keywords": [],
        }

    search_text = (topic + " " + content[:1000]).lower()

    # --- 방식 2: keyword_to_category (teheran_official 등) ---
    ktc = config.get("keyword_to_category")
    if ktc:
        scores = {}
        matched_map = {}

        for cat_name, keywords in ktc.items():
            score = 0
            matched = []
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower in topic.lower():
                    score += 3
                    matched.append(kw)
                elif kw_lower in search_text:
                    score += 1
                    matched.append(kw)

            if score > 0:
                scores[cat_name] = score
                matched_map[cat_name] = matched

        if scores:
            best_name = max(scores, key=scores.get)
            best_score = scores[best_name]
            max_possible = len(ktc.get(best_name, [])) * 3
            confidence = min(best_score / max(max_possible, 1), 1.0)

            # _raw_categories에서 실제 번호 찾기
            cat_no = _find_category_no_by_name(config, best_name)

            return {
                "category_no": cat_no,
                "category_name": best_name,
                "confidence": round(confidence, 2),
                "matched_keywords": matched_map.get(best_name, []),
            }

        # 매칭 없으면 디폴트
        default_name = config.get("default_category_name", "비지니스")
        default_no = _find_category_no_by_name(config, default_name)
        return {
            "category_no": default_no,
            "category_name": default_name,
            "confidence": 0.0,
            "matched_keywords": [],
        }

    # --- 방식 1: categories = {번호: {name, keywords}} (yun_ung_chae) ---
    categories = config.get("categories", {})
    default_cat = config.get("default_category", "10")

    scores = {}
    matched_keywords_map = {}

    for cat_no, cat_info in categories.items():
        if not isinstance(cat_info, dict):
            continue
        keywords = cat_info.get("keywords", [])
        if not keywords:
            continue

        score = 0
        matched = []

        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in topic.lower():
                score += 3
                matched.append(kw)
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
    """사용 가능한 모든 카테고리 목록"""
    config = load_category_config(persona_id)

    # _raw_categories가 있으면 그걸 우선 사용
    raw = config.get("_raw_categories", [])
    if raw:
        return [
            {"no": item["value"], "name": item["text"].strip()}
            for item in raw
            if item.get("value") and item.get("text", "").strip()
        ]

    # 없으면 categories 설정에서
    categories = config.get("categories", {})
    return [
        {"no": no, "name": info["name"]}
        for no, info in categories.items()
        if isinstance(info, dict) and "name" in info
    ]
