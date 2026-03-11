"""
컨텐츠 생성 엔진 v3
- Anthropic SDK 직접 사용 (LangChain 의존 제거)
- 새로운 프롬프트 구조 (base_prompt + human_style_rules + anti_ai_detection)
- 강화된 페르소나 시스템
- 유사도 검증 연동
- SSL/프록시 환경 대응
"""

import os
import json
import glob
import random
import httpx
import anthropic

BASE_PROMPT_PATH = "config/base_prompt.md"
HUMAN_STYLE_PATH = "config/human_style_rules.md"
ANTI_AI_PATH = "config/anti_ai_detection.md"
PERSONAS_DIR = "config/personas"
PERSONA_DB_DIR = "persona_db"

# 컨텍스트 토큰 예산 (한국어 글자 ≈ 2-3 토큰)
MAX_CONTEXT_CHARS = 30000


def _get_client():
    """Anthropic 클라이언트 생성 (SSL 우회 지원)"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if os.environ.get("DISABLE_SSL_VERIFY", "").lower() in ("1", "true", "yes"):
        http_client = httpx.Client(verify=False)
        return anthropic.Anthropic(api_key=api_key, http_client=http_client)
    return anthropic.Anthropic(api_key=api_key)


def load_base_prompt():
    """기본 프롬프트 로드"""
    try:
        with open(BASE_PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "당신은 {persona_name} 변리사입니다. 주제: {topic}\n\n과거 글: {context}"


def load_human_style_rules():
    """사람냄새 규칙 로드"""
    try:
        with open(HUMAN_STYLE_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "(사람냄새 규칙 파일 없음)"


def load_anti_ai_rules():
    """AI 탐지 방지 규칙 로드"""
    try:
        with open(ANTI_AI_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "(AI 탐지 방지 규칙 파일 없음)"


def load_persona_rules(persona_id):
    """페르소나 규칙 로드 (v2: 확장된 JSON 구조 지원)"""
    json_path = os.path.join(PERSONAS_DIR, f"{persona_id}.json")
    if not os.path.exists(json_path):
        return "- 특별한 추가 규칙 없음 (기본 문체 준수)"

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        rules_parts = []

        # 기본 성향
        rules_parts.append(f"## 성향\n{data.get('personality', '')}")

        # 글쓰기 DNA
        dna = data.get('writing_dna', {})
        if dna:
            openings = dna.get('opening_patterns', [])
            if openings:
                selected = random.sample(openings, min(3, len(openings)))
                rules_parts.append("## 인사말 패턴 (아래 중 하나를 변형해서 사용)")
                for o in selected:
                    rules_parts.append(f"- {o}")

            closings = dna.get('closing_patterns', [])
            if closings:
                selected = random.sample(closings, min(2, len(closings)))
                rules_parts.append("## 맺음말 패턴 (아래 중 하나를 변형해서 사용)")
                for c in selected:
                    rules_parts.append(f"- {c}")

            endings = dna.get('sentence_endings', {})
            if endings:
                freq_rule = endings.get('frequency_rule', '')
                if freq_rule:
                    rules_parts.append(f"## 어미 사용 규칙\n{freq_rule}")

        # strict_rules
        strict = data.get('strict_rules', [])
        if strict:
            rules_parts.append("## 필수 준수 규칙")
            for r in strict:
                rules_parts.append(f"- {r}")

        # human_smell_rules
        human = data.get('human_smell_rules', [])
        if human:
            selected = random.sample(human, min(6, len(human)))
            rules_parts.append("## 사람냄새 세부 규칙 (이번 글에 적용할 것)")
            for h in selected:
                rules_parts.append(f"- {h}")

        # anti_ai_rules
        anti_ai = data.get('anti_ai_rules', [])
        if anti_ai:
            rules_parts.append("## AI 탐지 방지 세부 규칙")
            for a in anti_ai:
                rules_parts.append(f"- {a}")

        # CTA 설정
        cta = data.get('cta_config', {})
        if cta:
            mid_options = cta.get('mid_text_options', [])
            end_options = cta.get('end_text_options', [])
            notice_title = cta.get('notice_post_title', '')
            philosophy_title = cta.get('philosophy_post_title', '')

            rules_parts.append("## CTA (공지글 유도) 규칙")
            rules_parts.append(f"- 스타일: {cta.get('style', 'non-aggressive')}")
            if mid_options:
                mid = random.choice(mid_options)
                rules_parts.append(f"- 글 중간 유도 문구 (이것을 참고해서 자연스럽게): \"{mid}\"")
            if end_options:
                end = random.choice(end_options)
                rules_parts.append(f"- 글 끝 안내 문구 (이것을 참고해서 간결하게): \"{end}\"")
            if notice_title:
                rules_parts.append(f"- 연결할 공지글 제목: [{notice_title}]")
            if philosophy_title:
                rules_parts.append(f"- 연결할 철학글 제목: [{philosophy_title}]")

        # 어휘 선호도
        vocab = data.get('vocabulary_preferences', {})
        if vocab:
            avoid = vocab.get('avoid', [])
            if avoid:
                rules_parts.append(f"## 금지 어휘\n다음 단어/표현 사용 금지: {', '.join(avoid)}")

        return '\n\n'.join(rules_parts)

    except (json.JSONDecodeError, IOError) as e:
        return f"- 설정 파일 로드 실패: {e}"


def _truncate_to_limit(text, max_chars):
    """텍스트를 최대 길이로 자르기 (문단 단위)"""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_break = truncated.rfind("\n\n")
    if last_break > max_chars * 0.5:
        truncated = truncated[:last_break]
    return truncated + "\n\n[... 컨텍스트 길이 제한으로 이하 생략 ...]"


def get_retriever_context(persona_id, topic=""):
    """페르소나 DB에서 관련 컨텍스트 로드"""
    db_path = os.path.join(PERSONA_DB_DIR, persona_id)
    if not os.path.exists(db_path):
        return "[과거 글 데이터가 없습니다. 일반적인 전문가 톤으로 작성하세요.]"

    context_parts = []
    topic_lower = topic.lower() if topic else ""

    # JSON 블로그 데이터 로드
    json_files = glob.glob(os.path.join(db_path, "*.json"))
    all_posts = []
    for jf in json_files:
        try:
            with open(jf, 'r', encoding='utf-8') as f:
                posts = json.load(f)
                if isinstance(posts, list):
                    all_posts.extend(posts)
        except (json.JSONDecodeError, IOError):
            continue

    # 관련성 기반 정렬
    if topic_lower and all_posts:
        def relevance_score(post):
            title = post.get('title', '').lower()
            content = post.get('content', '').lower()
            score = 0
            for keyword in topic_lower.split():
                if keyword in title:
                    score += 3
                if keyword in content[:500]:
                    score += 1
            return score

        all_posts.sort(key=relevance_score, reverse=True)

    # 상위 포스트를 예산 내에서 선택
    char_budget = MAX_CONTEXT_CHARS
    for idx, post in enumerate(all_posts):
        title = post.get('title', '제목없음')
        content = post.get('content', '')
        entry = f"[과거 글 {idx + 1}]\n제목: {title}\n\n{content}"
        if len(entry) > char_budget:
            if idx == 0:
                entry = entry[:char_budget]
            else:
                break
        context_parts.append(entry)
        char_budget -= len(entry)
        if char_budget <= 0:
            break

    # 추가 텍스트 파일
    txt_files = glob.glob(os.path.join(db_path, "*.txt"))
    for txt_file in txt_files:
        if os.path.basename(txt_file) == "links.txt":
            continue
        try:
            with open(txt_file, 'r', encoding='utf-8') as f:
                content = f.read()
                context_parts.append(f"[추가 참고 자료 - {os.path.basename(txt_file)}]\n{content}")
        except IOError:
            continue

    if not context_parts:
        return "[참고할 과거 글이 없습니다.]"

    full_context = "\n\n---\n\n".join(context_parts)
    return _truncate_to_limit(full_context, MAX_CONTEXT_CHARS)


def _build_prompt_text(persona_id, persona_name, topic, context_text):
    """전체 프롬프트를 문자열로 조립"""
    base = load_base_prompt()
    human_rules = load_human_style_rules()
    anti_ai = load_anti_ai_rules()
    persona_rules = load_persona_rules(persona_id)

    # 변수 치환
    prompt_text = base.replace("{human_style_rules}", human_rules)
    prompt_text = prompt_text.replace("{anti_ai_rules}", anti_ai)
    prompt_text = prompt_text.replace("{persona_name}", persona_name)
    prompt_text = prompt_text.replace("{persona_rules}", persona_rules)
    prompt_text = prompt_text.replace("{context}", context_text)
    prompt_text = prompt_text.replace("{topic}", topic)

    return prompt_text


def generate_column(persona_id, persona_name, topic, model_id="claude-sonnet-4-6", temperature=0.7):
    """컬럼 생성 (비스트리밍)"""
    client = _get_client()
    context_text = get_retriever_context(persona_id, topic)
    prompt_text = _build_prompt_text(persona_id, persona_name, topic, context_text)

    message = client.messages.create(
        model=model_id,
        max_tokens=4096,
        temperature=temperature,
        messages=[
            {"role": "user", "content": prompt_text}
        ]
    )

    return message.content[0].text


def generate_column_stream(persona_id, persona_name, topic, model_id="claude-sonnet-4-6", temperature=0.7):
    """컬럼 생성 (스트리밍) - 제너레이터 반환"""
    client = _get_client()
    context_text = get_retriever_context(persona_id, topic)
    prompt_text = _build_prompt_text(persona_id, persona_name, topic, context_text)

    with client.messages.stream(
        model=model_id,
        max_tokens=4096,
        temperature=temperature,
        messages=[
            {"role": "user", "content": prompt_text}
        ]
    ) as stream:
        for text in stream.text_stream:
            yield text


def generate_column_with_validation(persona_id, persona_name, topic,
                                     model_id="claude-sonnet-4-6", temperature=0.7,
                                     max_retries=3, similarity_threshold=0.3):
    """
    유사도 검증이 포함된 컬럼 생성.
    유사도가 높으면 자동으로 재생성합니다.

    Returns:
        dict: {
            'content': str,         # 생성된 컬럼 텍스트
            'attempts': int,        # 시도 횟수
            'similarity_check': dict,  # 최종 유사도 검증 결과
            'success': bool         # 성공 여부
        }
    """
    from src.similarity import check_similarity

    for attempt in range(1, max_retries + 1):
        # temperature를 시도마다 약간 올려서 다양성 확보
        temp = min(temperature + (attempt - 1) * 0.05, 1.0)
        content = generate_column(persona_id, persona_name, topic, model_id, temp)

        sim_result = check_similarity(content, persona_id,
                                       doc_threshold=similarity_threshold)

        if sim_result['passed']:
            return {
                'content': content,
                'attempts': attempt,
                'similarity_check': sim_result,
                'success': True
            }

    # 최대 재시도 후에도 통과 못하면 마지막 결과 반환
    return {
        'content': content,
        'attempts': max_retries,
        'similarity_check': sim_result,
        'success': False
    }


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(override=True)
    topic = "초보 창업자가 상표등록을 무조건 해야 하는 이유"
    print("=== 컬럼 생성 테스트 (v3) ===\n")
    print(generate_column("yun_ung_chae", "윤웅채", topic))
