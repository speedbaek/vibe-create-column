"""
유사도 검증 모듈
- 생성된 글과 기존 글(blogs.json, history.json) 간의 유사도를 검사
- TF-IDF + 코사인 유사도 기반 (가볍고 빠름)
"""

import os
import re
import json
import math
from collections import Counter

PERSONA_DB_DIR = "persona_db"
OUTPUTS_DIR = "outputs"

# 유사도 검증에서 제외할 정형 표현 패턴 (인사말, 자기소개, CTA 등)
EXCLUDE_PATTERNS = [
    "특허법인 테헤란",
    "대표 변리사",
    "윤웅채입니다",
    "안녕하세요",
    "뜻이 맞는 분들과만",
    "컨설팅 접수 방법",
    "1차상담 신청",
    "비용없는 1차상담",
    "여러분의 고민 해결",
    "노력해 보겠습니다",
    "포기도 실패도 없다",
    "변리사 윤웅채 철학",
    "상담 신청 방법",
    "현재 상황에서의 최선의 방법",
    "최선의 방법을 찾아",
    "감사합니다",
]


def _tokenize_korean(text):
    """간단한 한국어 토크나이저 (형태소 분석 없이 어절 기반)"""
    # 특수문자 제거, 소문자 변환
    text = re.sub(r'[^\w\s가-힣]', ' ', text)
    tokens = text.split()
    # 1글자 토큰 제거 (조사 등)
    tokens = [t for t in tokens if len(t) > 1]
    return tokens


def _compute_tf(tokens):
    """Term Frequency 계산"""
    counter = Counter(tokens)
    total = len(tokens)
    if total == 0:
        return {}
    return {word: count / total for word, count in counter.items()}


def _compute_idf(documents_tokens):
    """Inverse Document Frequency 계산"""
    num_docs = len(documents_tokens)
    if num_docs == 0:
        return {}

    # 각 단어가 몇 개의 문서에 등장하는지
    df = Counter()
    for tokens in documents_tokens:
        unique_tokens = set(tokens)
        for token in unique_tokens:
            df[token] += 1

    idf = {}
    for word, doc_freq in df.items():
        idf[word] = math.log((num_docs + 1) / (doc_freq + 1)) + 1

    return idf


def _tfidf_vector(tokens, idf):
    """TF-IDF 벡터 생성"""
    tf = _compute_tf(tokens)
    return {word: tf_val * idf.get(word, 1.0) for word, tf_val in tf.items()}


def _cosine_similarity(vec_a, vec_b):
    """두 벡터 간 코사인 유사도"""
    common_words = set(vec_a.keys()) & set(vec_b.keys())
    if not common_words:
        return 0.0

    dot_product = sum(vec_a[w] * vec_b[w] for w in common_words)
    mag_a = math.sqrt(sum(v ** 2 for v in vec_a.values()))
    mag_b = math.sqrt(sum(v ** 2 for v in vec_b.values()))

    if mag_a == 0 or mag_b == 0:
        return 0.0

    return dot_product / (mag_a * mag_b)


def _sentence_similarity(sent_a, sent_b):
    """두 문장 간 단순 자카드 유사도"""
    tokens_a = set(_tokenize_korean(sent_a))
    tokens_b = set(_tokenize_korean(sent_b))
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def load_existing_texts(persona_id):
    """기존 블로그 글 + 생성 이력 로드"""
    texts = []

    # 1. blogs.json (기존 포스팅)
    blogs_path = os.path.join(PERSONA_DB_DIR, persona_id, "blogs.json")
    if os.path.exists(blogs_path):
        try:
            with open(blogs_path, 'r', encoding='utf-8') as f:
                posts = json.load(f)
                for post in posts:
                    content = post.get('content', '')
                    if content:
                        texts.append(content)
        except (json.JSONDecodeError, IOError):
            pass

    # 2. history.json (생성 이력)
    history_path = os.path.join(OUTPUTS_DIR, persona_id, "history.json")
    if os.path.exists(history_path):
        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                history = json.load(f)
                for entry in history:
                    content = entry.get('content', '') or entry.get('output', '')
                    if content:
                        texts.append(content)
        except (json.JSONDecodeError, IOError):
            pass

    return texts


def check_similarity(new_text, persona_id, doc_threshold=0.3, sent_threshold=0.8):
    """
    새로 생성된 글의 유사도를 검증합니다.

    Args:
        new_text: 새로 생성된 글
        persona_id: 변리사 페르소나 ID
        doc_threshold: 문서 전체 유사도 임계값 (이 값 이상이면 유사)
        sent_threshold: 문장 단위 유사도 임계값 (이 값 이상이면 경고)

    Returns:
        dict: {
            'passed': bool,          # 검증 통과 여부
            'max_doc_similarity': float,  # 가장 높은 문서 유사도
            'similar_doc_index': int,     # 가장 유사한 문서 인덱스
            'flagged_sentences': list,    # 유사도가 높은 문장 쌍 목록
            'details': str               # 상세 설명
        }
    """
    existing_texts = load_existing_texts(persona_id)

    if not existing_texts:
        return {
            'passed': True,
            'max_doc_similarity': 0.0,
            'similar_doc_index': -1,
            'flagged_sentences': [],
            'details': '비교할 기존 글이 없어 유사도 검증을 건너뜁니다.'
        }

    # 1. 문서 전체 유사도 검사 (TF-IDF + 코사인)
    new_tokens = _tokenize_korean(new_text)
    all_doc_tokens = [_tokenize_korean(t) for t in existing_texts]
    all_doc_tokens.append(new_tokens)  # 새 글도 IDF 계산에 포함

    idf = _compute_idf(all_doc_tokens)
    new_vec = _tfidf_vector(new_tokens, idf)

    max_sim = 0.0
    max_idx = -1

    for idx, doc_tokens in enumerate(all_doc_tokens[:-1]):  # 새 글 제외
        doc_vec = _tfidf_vector(doc_tokens, idf)
        sim = _cosine_similarity(new_vec, doc_vec)
        if sim > max_sim:
            max_sim = sim
            max_idx = idx

    # 2. 문장 단위 유사도 검사
    new_sentences = [s.strip() for s in re.split(r'[.!?\n]', new_text) if len(s.strip()) > 15]
    flagged = []

    def _is_boilerplate(sentence):
        """정형 표현(인사말, 자기소개, CTA 등)인지 검사"""
        for pattern in EXCLUDE_PATTERNS:
            if pattern in sentence:
                return True
        # 40자 미만의 짧은 문장은 정형 표현일 가능성이 높음
        if len(sentence) < 40:
            return False  # 짧다고 무조건 제외하진 않음
        return False

    for new_sent in new_sentences:
        if _is_boilerplate(new_sent):
            continue
        for doc_idx, existing_text in enumerate(existing_texts):
            existing_sents = [s.strip() for s in re.split(r'[.!?\n]', existing_text) if len(s.strip()) > 15]
            for exist_sent in existing_sents:
                if _is_boilerplate(exist_sent):
                    continue
                sim = _sentence_similarity(new_sent, exist_sent)
                if sim >= sent_threshold:
                    flagged.append({
                        'new_sentence': new_sent,
                        'existing_sentence': exist_sent,
                        'similarity': round(sim, 3),
                        'doc_index': doc_idx
                    })

    # 3. 결과 판정
    passed = max_sim < doc_threshold and len(flagged) == 0

    details_parts = []
    details_parts.append(f"문서 유사도: {max_sim:.3f} (임계값: {doc_threshold})")
    if flagged:
        details_parts.append(f"유사 문장 {len(flagged)}개 발견")
        for f in flagged[:3]:  # 최대 3개만 표시
            details_parts.append(f"  - 새 글: '{f['new_sentence'][:40]}...'")
            details_parts.append(f"    기존: '{f['existing_sentence'][:40]}...' (유사도: {f['similarity']})")

    return {
        'passed': passed,
        'max_doc_similarity': round(max_sim, 3),
        'similar_doc_index': max_idx,
        'flagged_sentences': flagged,
        'details': '\n'.join(details_parts)
    }


if __name__ == "__main__":
    # 간단한 테스트
    test_text = "안녕하세요 윤변리사입니다. 상표등록에 대해 말씀드리겠습니다."
    result = check_similarity(test_text, "yun_ung_chae")
    print(f"통과: {result['passed']}")
    print(f"최대 유사도: {result['max_doc_similarity']}")
    print(f"상세:\n{result['details']}")
