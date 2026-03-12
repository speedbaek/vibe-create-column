"""
유사도 검증 모듈
- 생성된 칼럼과 기존 글의 유사도를 비교
- 문서 레벨 + 문장 레벨 검증
"""

import os
import json
import glob
from difflib import SequenceMatcher


def _load_existing_posts(persona_id):
    """기존 포스팅 로드"""
    db_path = os.path.join("persona_db", persona_id)
    if not os.path.exists(db_path):
        return []

    posts = []
    for jf in glob.glob(os.path.join(db_path, "*.json")):
        try:
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    posts.extend(data)
        except (json.JSONDecodeError, IOError):
            continue
    return posts


def _doc_similarity(text_a, text_b):
    """두 문서 간 유사도 (0~1)"""
    if not text_a or not text_b:
        return 0.0
    # 긴 텍스트는 앞부분만 비교 (성능)
    a = text_a[:5000]
    b = text_b[:5000]
    return SequenceMatcher(None, a, b).ratio()


def _extract_sentences(text):
    """텍스트를 문장 단위로 분리"""
    sentences = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # 마침표/물음표/느낌표 기준 분리
        for sep in [".", "?", "!"]:
            line = line.replace(sep, sep + "\n")
        for sent in line.split("\n"):
            sent = sent.strip()
            if len(sent) > 10:
                sentences.append(sent)
    return sentences


def check_similarity(content, persona_id, doc_threshold=0.3, sent_threshold=0.8):
    """
    유사도 검증

    Args:
        content: 생성된 칼럼 텍스트
        persona_id: 페르소나 ID
        doc_threshold: 문서 유사도 임계값 (넘으면 실패)
        sent_threshold: 문장 유사도 임계값 (넘으면 플래그)

    Returns:
        dict: {
            'passed': bool,
            'max_doc_similarity': float,
            'avg_doc_similarity': float,
            'flagged_sentences': list[dict],
            'total_posts_compared': int,
        }
    """
    existing_posts = _load_existing_posts(persona_id)

    if not existing_posts:
        return {
            "passed": True,
            "max_doc_similarity": 0.0,
            "avg_doc_similarity": 0.0,
            "flagged_sentences": [],
            "total_posts_compared": 0,
        }

    # 문서 레벨 유사도
    doc_scores = []
    for post in existing_posts:
        post_content = post.get("content", "")
        if not post_content:
            continue
        score = _doc_similarity(content, post_content)
        doc_scores.append(score)

    max_doc_sim = max(doc_scores) if doc_scores else 0.0
    avg_doc_sim = sum(doc_scores) / len(doc_scores) if doc_scores else 0.0

    # 문장 레벨 유사도 (최대 유사도가 임계값 근처일 때만)
    flagged_sentences = []
    if max_doc_sim > doc_threshold * 0.5:
        new_sentences = _extract_sentences(content)
        existing_sentences = []
        for post in existing_posts[:10]:  # 최근 10개만
            existing_sentences.extend(_extract_sentences(post.get("content", "")))

        for new_sent in new_sentences[:50]:  # 최대 50문장만
            for old_sent in existing_sentences[:200]:
                sim = SequenceMatcher(None, new_sent, old_sent).ratio()
                if sim >= sent_threshold:
                    flagged_sentences.append({
                        "new": new_sent,
                        "existing": old_sent,
                        "similarity": round(sim, 3),
                    })
                    break  # 하나라도 매치되면 다음 문장으로

    passed = max_doc_sim < doc_threshold

    return {
        "passed": passed,
        "max_doc_similarity": round(max_doc_sim, 4),
        "avg_doc_similarity": round(avg_doc_sim, 4),
        "flagged_sentences": flagged_sentences,
        "total_posts_compared": len(doc_scores),
    }
