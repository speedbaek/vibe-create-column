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

def load_base_prompt():
    try:
        with open(BASE_PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"Error loading base prompt: {e}")
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
    except Exception as e:
        return f"- 설정 파일 로드 실패: {e}"

def get_retriever_context(persona_id):
    # V2: Read all txt and json files in the persona's DB directory
    db_path = os.path.join(PERSONA_DB_DIR, persona_id)
    if not os.path.exists(db_path):
        return "[과거 글 데이터가 없습니다. 일반적인 전문가 톤으로 작성하세요.]"
    
    context_parts = []
    
    # Process json blogs (scraped data)
    json_files = glob.glob(os.path.join(db_path, "*.json"))
    for jf in json_files:
        try:
            with open(jf, 'r', encoding='utf-8') as f:
                posts = json.load(f)
                latest_posts = posts[:15] if isinstance(posts, list) else []
                for idx, post in enumerate(latest_posts):
                    context_parts.append(f"[스크랩 글 {idx+1}]\n제목: {post.get('title', '제목없음')}\n\n{post.get('content', '')}")
        except Exception:
            pass

    # Process manually added extra text files
    txt_files = glob.glob(os.path.join(db_path, "*.txt"))
    for txt_file in txt_files:
        # Ignore links.txt as it's meant for the scraper input, not context
        if os.path.basename(txt_file) == "links.txt":
            continue
        try:
            with open(txt_file, 'r', encoding='utf-8') as f:
                content = f.read()
                context_parts.append(f"[추가 참고 문헌 - {os.path.basename(txt_file)}]\n{content}")
        except Exception:
            pass

    if not context_parts:
        return "[참고할 지난 작성 글이나 추가 문서가 해당 변리사 폴더 안에 존재하지 않습니다.]"
        
    return "\n\n---\n\n".join(context_parts)

def generate_column(persona_id, persona_name, topic):
    llm = ChatAnthropic(model_name="claude-sonnet-4-6", temperature=0.7)
    
    context_text = get_retriever_context(persona_id)
    persona_rules = load_persona_rules(persona_id)
    
    base_prompt_text = load_base_prompt()
    prompt = PromptTemplate.from_template(base_prompt_text)
    
    # Pass all 4 variables into the prompt
    prompt = prompt.partial(persona_name=persona_name, persona_rules=persona_rules)
    
    # RAG Chain without vector DB
    chain = (
        {"context": lambda x: context_text, "topic": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )
        
    print(f"Generating column for topic: '{topic}' using persona: {persona_name}...")
    response = chain.invoke(topic)
    return response

if __name__ == "__main__":
    # Test generation
    topic = "초보 창업자가 상표등록을 무조건 해야 하는 이유"
    print("Test Output:\n")
    print(generate_column("yun_ung_chae", "윤웅채", topic))
