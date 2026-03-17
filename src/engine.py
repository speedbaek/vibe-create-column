"""
컨텐츠 생성 엔진 v3
- Anthropic SDK 직접 사용 (LangChain 의존 제거)
- 새로운 프롬프트 구조 (base_prompt + human_style_rules + anti_ai_detection)
- 강화된 페르소나 시스템
- 유사도 검증 연동
- SSL/프록시 환경 대응
"""

import os
import re
import json
import glob
import random
import httpx
import anthropic

BASE_PROMPT_PATH = "config/base_prompt.md"
HUMAN_STYLE_PATH = "config/human_style_rules.md"
ANTI_AI_PATH = "config/anti_ai_detection.md"
TITLE_STYLE_PATH = "config/title_style.md"
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
            links = cta.get('links', {})

            rules_parts.append("## CTA (공지글 유도) 규칙")
            rules_parts.append(f"- 스타일: {cta.get('style', 'non-aggressive')}")

            # 사용 가능한 링크 마커 안내
            if links:
                rules_parts.append("- 사용 가능한 링크 마커 (본문에 그대로 삽입하면 발행 시 자동으로 링크카드로 변환됩니다):")
                for link_key, link_info in links.items():
                    marker = link_info.get('marker', '')
                    short_title = link_info.get('short_title', '')
                    rules_parts.append(f"  - {marker} → {short_title}")

            # cta_pairs 방식: core 1개 + consult 1개 밸런스 보장
            cta_pairs = cta.get('cta_pairs', [])
            if cta_pairs:
                core_options = [p for p in cta_pairs if p.get('role') == 'core']
                consult_options = [p for p in cta_pairs if p.get('role') == 'consult']

                mid_cta = random.choice(core_options)['text'] if core_options else None
                end_cta = random.choice(consult_options)['text'] if consult_options else None

                if mid_cta:
                    rules_parts.append(f"- 글 중간에 아래 핵심 컨텐츠 유도 문구를 자연스럽게 삽입하세요 (링크 마커 포함):\n\"{mid_cta}\"")
                if end_cta:
                    rules_parts.append(f"- 글 끝부분에 아래 상담 유도 문구를 삽입하세요 (링크 마커 포함):\n\"{end_cta}\"")
            else:
                # 레거시: mid_text_options / end_text_options 방식 (하위 호환)
                mid_options = cta.get('mid_text_options', [])
                end_options = cta.get('end_text_options', [])
                if mid_options:
                    mid = random.choice(mid_options)
                    rules_parts.append(f"- 글 중간에 아래 유도 문구를 자연스럽게 삽입하세요 (링크 마커 포함):\n\"{mid}\"")
                if end_options:
                    end = random.choice(end_options)
                    rules_parts.append(f"- 글 끝부분에 아래 안내 문구를 삽입하세요 (링크 마커 포함):\n\"{end}\"")

        # 어휘 선호도
        vocab = data.get('vocabulary_preferences', {})
        if vocab:
            avoid = vocab.get('avoid', [])
            if avoid:
                rules_parts.append(f"## 금지 어휘\n다음 단어/표현 사용 금지: {', '.join(avoid)}")

        return '\n\n'.join(rules_parts)

    except (json.JSONDecodeError, IOError) as e:
        return f"- 설정 파일 로드 실패: {e}"


def replace_link_markers(text, persona_id):
    """
    생성된 텍스트에서 링크 마커를 실제 URL로 치환

    마커 형태: {{LINK:철학글}}, {{LINK:추천글}}, {{LINK:상담글}}
    치환 결과: 네이버 블로그 링크 텍스트 블록

    Args:
        text: 생성된 칼럼 텍스트
        persona_id: 페르소나 ID

    Returns:
        str: 링크 마커가 치환된 텍스트
    """
    json_path = os.path.join(PERSONAS_DIR, f"{persona_id}.json")
    if not os.path.exists(json_path):
        return text

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return text

    cta = data.get('cta_config', {})
    links = cta.get('links', {})

    if not links:
        return text

    # 마커 → 링크 URL 치환 (oglink 컴포넌트가 KNOWN_LINKS에서 제목/설명 자동 표시)
    for link_key, link_info in links.items():
        marker = link_info.get('marker', '')
        if not marker or marker not in text:
            continue

        url = link_info.get('url', '')

        # URL만 단독 줄로 출력 → se_converter에서 oglink 카드로 자동 변환
        # (KNOWN_LINKS에 등록된 제목/설명/썸네일이 자동 적용됨)
        text = text.replace(marker, f"\n{url}\n")

    return text


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

    # 페르소나 intro 로드
    persona_intro = ""
    json_path = os.path.join(PERSONAS_DIR, f"{persona_id}.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                pdata = json.load(f)
            persona_intro = pdata.get("intro", "")
        except Exception:
            pass

    # 변수 치환
    prompt_text = base.replace("{human_style_rules}", human_rules)
    prompt_text = prompt_text.replace("{anti_ai_rules}", anti_ai)
    prompt_text = prompt_text.replace("{persona_name}", persona_name)
    prompt_text = prompt_text.replace("{persona_intro}", persona_intro)
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
        max_tokens=6000,
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
        max_tokens=6000,
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


def load_title_style():
    """제목 스타일 가이드 로드"""
    try:
        with open(TITLE_STYLE_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "(제목 스타일 가이드 파일 없음)"


def _get_sample_titles(persona_id, count=30):
    """페르소나 DB에서 실제 제목 샘플 추출 (2020~2021 상반기)"""
    db_path = os.path.join(PERSONA_DB_DIR, persona_id)
    json_files = glob.glob(os.path.join(db_path, "*.json"))

    all_titles = []
    for jf in json_files:
        try:
            with open(jf, 'r', encoding='utf-8') as f:
                posts = json.load(f)
                if isinstance(posts, list):
                    for post in posts:
                        title = post.get('title', '')
                        if title and not title.startswith('['):  # [소개], [추천] 등 공지글 제외
                            all_titles.append(title)
        except (json.JSONDecodeError, IOError):
            continue

    # 중복 제거 후 랜덤 샘플링
    unique_titles = list(set(all_titles))
    sample = random.sample(unique_titles, min(count, len(unique_titles)))
    return sample


def generate_hooking_title(topic, persona_id="yun_ung_chae",
                            model_id="claude-sonnet-4-6",
                            count=3):
    """
    키워드/주제로부터 후킹 강한 블로그 제목 생성

    Args:
        topic: 키워드 또는 주제 (예: "상표등록", "스타트업 특허")
        persona_id: 페르소나 ID
        model_id: AI 모델
        count: 생성할 제목 후보 수 (기본 3개)

    Returns:
        list[str]: 생성된 제목 후보 리스트
    """
    client = _get_client()
    title_style = load_title_style()
    sample_titles = _get_sample_titles(persona_id, count=30)

    sample_text = "\n".join(f"- {t}" for t in sample_titles)

    prompt = f"""당신은 네이버 블로그 제목을 작성하는 전문가입니다.
아래의 스타일 가이드와 실제 제목 예시를 참고하여, 주어진 키워드/주제에 맞는 블로그 제목을 {count}개 생성하세요.

## 제목 스타일 가이드
{title_style}

## 실제 블로그 제목 예시 (이 문체와 패턴을 참고)
{sample_text}

## 키워드/주제
{topic}

## 생성 규칙
1. 위 스타일 가이드의 10가지 패턴 중 서로 다른 패턴을 사용하세요.
2. 각 제목은 30~50자 사이여야 합니다.
3. 실제 변리사가 직접 쓴 것처럼 자연스러운 한국어를 사용하세요.
4. AI가 쓴 느낌이 나는 표현은 절대 사용하지 마세요.
5. 키워드를 제목 앞부분에 자연스럽게 배치하세요.

## 출력 형식
제목만 한 줄에 하나씩 출력하세요. 번호, 따옴표, 설명 없이 제목 텍스트만 출력합니다.
"""

    message = client.messages.create(
        model=model_id,
        max_tokens=500,
        temperature=0.9,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    raw_text = message.content[0].text.strip()
    titles = []
    for line in raw_text.split("\n"):
        line = line.strip()
        # 번호 접두사 제거 (1. 2. 3. 또는 1) 2) 3))
        line = re.sub(r'^[\d]+[.)]\s*', '', line)
        # 따옴표 제거
        line = line.strip('"').strip("'").strip()
        if line and len(line) >= 10:
            titles.append(line)

    return titles[:count]


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(override=True)
    topic = "초보 창업자가 상표등록을 무조건 해야 하는 이유"
    print("=== 컬럼 생성 테스트 (v3) ===\n")
    print(generate_column("yun_ung_chae", "윤웅채", topic))
