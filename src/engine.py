import os
import json
import glob
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

BASE_PROMPT_PATH = "config/base_prompt.md"
PERSONAS_DIR = "config/personas"
PERSONA_DB_DIR = "persona_db"

# Approximate token limit for context to avoid blowing up API costs
MAX_CONTEXT_CHARS = 30000  # ~7,500 tokens (Korean chars ≈ 2-3 tokens each)


def load_base_prompt():
    try:
        with open(BASE_PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "당신은 변리사입니다. 주제: {topic}\n\n과거 글: {context}"


def load_persona_rules(persona_id):
    json_path = os.path.join(PERSONAS_DIR, f"{persona_id}.json")
    if not os.path.exists(json_path):
        return "- 특별한 추가 규칙 없음 (기본 문체 준수)"
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            rules_str = f"- 성향: {data.get('personality', '')}\n"
            for row in data.get('strict_rules', []):
                rules_str += f"- {row}\n"
            return rules_str
    except (json.JSONDecodeError, IOError) as e:
        return f"- 설정 파일 로드 실패: {e}"


def _truncate_to_limit(text, max_chars):
    """Truncate text to max_chars, cutting at the last complete paragraph."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_break = truncated.rfind("\n\n")
    if last_break > max_chars * 0.5:
        truncated = truncated[:last_break]
    return truncated + "\n\n[... 컨텍스트 길이 제한으로 이하 생략 ...]"


def get_retriever_context(persona_id, topic=""):
    """Load context from persona DB with token budget management."""
    db_path = os.path.join(PERSONA_DB_DIR, persona_id)
    if not os.path.exists(db_path):
        return "[과거 글 데이터가 없습니다. 일반적인 전문가 톤으로 작성하세요.]"

    context_parts = []
    topic_lower = topic.lower() if topic else ""

    # Process json blogs (scraped data)
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

    # Sort by relevance: posts with topic keywords first, then by recency
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

    # Take top posts within budget
    char_budget = MAX_CONTEXT_CHARS
    for idx, post in enumerate(all_posts):
        title = post.get('title', '제목없음')
        content = post.get('content', '')
        entry = f"[스크랩 글 {idx+1}]\n제목: {title}\n\n{content}"
        if len(entry) > char_budget:
            if idx == 0:
                entry = entry[:char_budget]
            else:
                break
        context_parts.append(entry)
        char_budget -= len(entry)
        if char_budget <= 0:
            break

    # Process manually added extra text files (always include)
    txt_files = glob.glob(os.path.join(db_path, "*.txt"))
    for txt_file in txt_files:
        if os.path.basename(txt_file) == "links.txt":
            continue
        try:
            with open(txt_file, 'r', encoding='utf-8') as f:
                content = f.read()
                context_parts.append(f"[추가 참고 문헌 - {os.path.basename(txt_file)}]\n{content}")
        except IOError:
            continue

    if not context_parts:
        return "[참고할 지난 작성 글이나 추가 문서가 해당 변리사 폴더 안에 존재하지 않습니다.]"

    full_context = "\n\n---\n\n".join(context_parts)
    return _truncate_to_limit(full_context, MAX_CONTEXT_CHARS)


def generate_column(persona_id, persona_name, topic, model_id="claude-sonnet-4-6", temperature=0.7):
    """Generate a column with the given persona and topic."""
    llm = ChatAnthropic(model_name=model_id, temperature=temperature)

    context_text = get_retriever_context(persona_id, topic)
    persona_rules = load_persona_rules(persona_id)

    base_prompt_text = load_base_prompt()
    prompt = PromptTemplate.from_template(base_prompt_text)
    prompt = prompt.partial(persona_name=persona_name, persona_rules=persona_rules)

    chain = (
        {"context": lambda x: context_text, "topic": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    return chain.invoke(topic)


def generate_column_stream(persona_id, persona_name, topic, model_id="claude-sonnet-4-6", temperature=0.7):
    """Generate a column with streaming output."""
    llm = ChatAnthropic(model_name=model_id, temperature=temperature)

    context_text = get_retriever_context(persona_id, topic)
    persona_rules = load_persona_rules(persona_id)

    base_prompt_text = load_base_prompt()
    prompt = PromptTemplate.from_template(base_prompt_text)
    prompt = prompt.partial(persona_name=persona_name, persona_rules=persona_rules)

    chain = (
        {"context": lambda x: context_text, "topic": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    return chain.stream(topic)


if __name__ == "__main__":
    topic = "초보 창업자가 상표등록을 무조건 해야 하는 이유"
    print("Test Output:\n")
    print(generate_column("yun_ung_chae", "윤웅채", topic))
