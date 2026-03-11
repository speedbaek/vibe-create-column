import streamlit as st
import os
import time
from dotenv import load_dotenv

load_dotenv()

# Attempt to load the generator engine if dependencies are available
try:
    from src.engine import generate_column
    ENGINE_LOADED = True
except ImportError as e:
    print(f"Error importing engine: {e}")
    ENGINE_LOADED = False

st.set_page_config(page_title="특허 변리사 칼럼 생성기", page_icon="📝", layout="wide")

# Custom CSS for aesthetics
st.markdown("""
<style>
    .reportview-container .main .block-container{
        padding-top: 2rem;
    }
    .stButton>button {
        width: 100%;
        height: 3em;
        font-weight: bold;
        background-color: #4CAF50;
        color: white;
    }
    .stButton>button:hover {
        background-color: #45a049;
    }
    .result-box {
        padding: 20px;
        border-radius: 10px;
        background-color: #f9f9f9;
        border: 1px solid #ddd;
        font-size: 16px;
        line-height: 1.6;
        white-space: pre-wrap;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar configurations
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3050/3050525.png", width=100)
    st.title("⚙️ 시스템 설정")
    
    st.markdown("---")
    st.subheader("1. 페르소나 선택")
    
    persona_options = {
        "yun_ung_chae": "윤웅채 변리사",
        "kim_sin_yeon": "김신연 변리사",
        "lee_sang_dam": "이상담 변리사",
        "kim_bong_geun": "김봉근 변리사",
        "baek_sang_hui": "백상희 변리사"
    }
    
    selected_persona_id = st.selectbox(
        "글을 작성할 변리사를 선택하세요:",
        options=list(persona_options.keys()),
        format_func=lambda x: persona_options[x]
    )
    
    selected_persona_name = persona_options[selected_persona_id]
    
    st.markdown("---")
    st.subheader("2. DB 상태")
    
    db_dir = f"persona_db/{selected_persona_id}"
    
    # Check if there are any valid context files in the directory
    has_data = False
    if os.path.exists(db_dir):
        import glob
        json_files = glob.glob(os.path.join(db_dir, "*.json"))
        txt_files = [f for f in glob.glob(os.path.join(db_dir, "*.txt")) if not f.endswith("links.txt")]
        if json_files or txt_files:
            has_data = True

    if has_data:
        st.success(f"{selected_persona_name}의 맞춤 학습 데이터가 적용되었습니다.")
    else:
        st.warning(f"{selected_persona_name}의 학습 데이터가 없습니다.\n일반 톤으로 작성됩니다.")
        
    st.markdown("---")
    st.info("💡 **사용 팁:**\n구체적인 키워드나 상황을 입력할수록 더 자연스러운 칼럼이 생성됩니다.")

# Main content
st.title("📝 특허법인 AI 칼럼 자동 생성기")
st.markdown("선택한 변리사의 **과거 문체와 성향(페르소나)**을 학습하여 완벽한 전문가 칼럼을 작성합니다.")

tab1, tab2, tab3, tab4 = st.tabs(["✍️ 칼럼 생성 엔진", "⚙️ 프롬프트 및 DB 설정 (V2)", "🌐 블로그 자동 수집기", "📜 과거 생성 기록"])

with tab1:
    topic = st.text_area("✍️ 작성할 칼럼의 주제나 키워드를 상세히 입력하세요:", height=100, 
                        placeholder="예: 스타트업이 초기 단계에서 상표권을 반드시 먼저 출원해야 하는 이유와 실제 분쟁 사례")

    if st.button("🚀 칼럼 생성 시작"):
        if not topic.strip():
            st.error("칼럼 주제를 입력해 주세요.")
        else:
            if not ENGINE_LOADED:
                st.error("엔진 모듈을 불러오지 못했습니다. 환경 설정을 확인해 주세요.")
            else:
                with st.spinner(f"'{selected_persona_name}'의 문체를 분석하여 글을 작성 중입니다... 잠시만 기다려주세요⏳"):
                    try:
                        start_time = time.time()
                        
                        # Call the engine
                        result_text = generate_column(selected_persona_id, selected_persona_name, topic)
                        
                        elapsed = time.time() - start_time
                        st.success(f"🎉 칼럼 작성이 완료되었습니다! (소요 시간: {elapsed:.1f}초)")
                        
                        # Save to history automatically
                        import json
                        output_dir = f"outputs/{selected_persona_id}"
                        os.makedirs(output_dir, exist_ok=True)
                        history_path = os.path.join(output_dir, "history.json")
                        
                        history_data = []
                        if os.path.exists(history_path):
                            try:
                                with open(history_path, "r", encoding="utf-8") as f:
                                    history_data = json.load(f)
                            except Exception:
                                pass
                                
                        from datetime import datetime
                        new_record = {
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "topic": topic,
                            "content": result_text
                        }
                        history_data.insert(0, new_record) # prepend latest
                        
                        with open(history_path, "w", encoding="utf-8") as f:
                            json.dump(history_data, f, ensure_ascii=False, indent=4)
                        
                        st.markdown("### 📄 생성된 칼럼")
                        st.markdown(f'<div class="result-box">{result_text}</div>', unsafe_allow_html=True)
                        
                        st.markdown("---")
                        
                        col_dl, col_copy = st.columns(2)
                        with col_dl:
                            st.download_button(
                                label="💾 텍스트 파일로 저장",
                                data=result_text,
                                file_name=f"{selected_persona_name}_칼럼.txt",
                                mime="text/plain",
                                use_container_width=True
                            )
                        with col_copy:
                            import base64
                            import streamlit.components.v1 as components
                            b64_text = base64.b64encode(result_text.encode("utf-8")).decode("utf-8")
                            js_code = f"""
                            <script>
                            function copyToClipboard() {{
                                const text = decodeURIComponent(escape(window.atob('{b64_text}')));
                                navigator.clipboard.writeText(text).then(function() {{
                                    const btn = document.getElementById("copyBtn");
                                    btn.innerHTML = "✅ 복사 완료!";
                                    btn.style.backgroundColor = "#45a049";
                                    setTimeout(() => {{
                                        btn.innerHTML = "📋 완성된 칼럼 복사하기";
                                        btn.style.backgroundColor = "#4CAF50";
                                    }}, 2000);
                                }});
                            }}
                            </script>
                            <button id="copyBtn" onclick="copyToClipboard()" style="width:100%; height:45px; background-color:#4CAF50; color:white; border:none; border-radius:8px; font-weight:bold; font-size:16px; cursor:pointer; font-family:sans-serif; margin-top:2px;">📋 완성된 칼럼 복사하기</button>
                            """
                            components.html(js_code, height=60)
                            
                    except Exception as e:
                        st.error(f"오류가 발생했습니다: {str(e)}")

with tab2:
    st.markdown("### 🛠️ 전체 프롬프트 템플릿 관리 (`config/base_prompt.md`)")
    st.info("이곳의 내용을 통째로 수정하면, 모든 변리사가 글을 전개하는 방식(인사말, 결론 구조 등)의 뼈대가 변경됩니다.")
    
    base_prompt_path = "config/base_prompt.md"
    base_prompt_content = ""
    if os.path.exists(base_prompt_path):
        with open(base_prompt_path, "r", encoding="utf-8") as f:
            base_prompt_content = f.read()
    
    new_base_prompt = st.text_area("기본 프롬프트 내용", value=base_prompt_content, height=250)
    if st.button("💾 기본 프롬프트 템플릿 변경 저장"):
        with open(base_prompt_path, "w", encoding="utf-8") as f:
            f.write(new_base_prompt)
        st.success("기본 프롬프트 구조가 성공적으로 저장되었습니다.")
        
    st.markdown("---")
    st.markdown(f"### 👤 {selected_persona_name} 맞춤 설정 관리")
    st.info("해당 변리사만의 특수한 글쓰기 성향과 반드시 지켜야 할 규칙을 수정합니다.")
    
    import json
    json_path = f"config/personas/{selected_persona_id}.json"
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            persona_data = json.load(f)
        
        col1, col2 = st.columns(2)
        with col1:
            new_personality = st.text_area("성향 (Personality)", value=persona_data.get("personality", ""), height=150)
        with col2:
            rules_text = "\n".join(persona_data.get("strict_rules", []))
            new_rules = st.text_area("특별 추가 규칙 (한 줄에 하나씩 작성)", value=rules_text, height=150)
            
        if st.button(f"💾 {selected_persona_name} 전용 규칙 저장"):
            persona_data["personality"] = new_personality
            persona_data["strict_rules"] = [r.strip() for r in new_rules.split("\n") if r.strip()]
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(persona_data, f, ensure_ascii=False, indent=2)
            st.success(f"{selected_persona_name}의 규칙 설정이 로컬에 저장되었습니다.")
    
    st.markdown("---")
    st.markdown(f"### 📚 {selected_persona_name} 전용 추가 참고 문헌 주입")
    st.info("이 빈칸에 판례, 관련 법령 기사, 회사 소식 등을 복사해서 붙여넣으세요. AI가 다음 글 작성 시 배경 지식으로 읽고 반영합니다.")
    
    extra_txt_path = f"persona_db/{selected_persona_id}/extra_text.txt"
    extra_content = ""
    if os.path.exists(extra_txt_path):
        with open(extra_txt_path, "r", encoding="utf-8") as f:
            extra_content = f.read()
            
    new_extra_content = st.text_area("참고 문헌 텍스트 (extra_text.txt)", value=extra_content, height=250, placeholder="여기에 참고할 텍스트를 통째로 복사해서 붙여넣으세요.")
    if st.button("💾 참고 문헌 텍스트 주입 완료"):
        with open(extra_txt_path, "w", encoding="utf-8") as f:
            f.write(new_extra_content)
        st.success("참고 문헌이 안전하게 저장되었습니다. 다음 칼럼 생성부터 반영됩니다.")

with tab3:
    st.markdown("### 🌐 모바일 네이버 블로그 자동 수집기")
    st.info("특정 변리사님의 과거 네이버 블로그 포스팅 중 **원하는 기간의 글만 선택적으로 긁어와서** DB에 영구 저장합니다.")
    
    col_a, col_b = st.columns(2)
    with col_a:
        target_blog_id = st.text_input("네이버 블로그 ID (예: jninsa)", value="jninsa")
    with col_b:
        st.write("선택된 페르소나 (좌측 사이드바 기준):")
        st.info(f"**{selected_persona_name}** (`{selected_persona_id}`)")
        
    st.markdown("#### 📅 수집 기간 설정")
    import datetime
    col_c, col_d = st.columns(2)
    with col_c:
        start_date = st.date_input("수집 시작일", value=datetime.date(2020, 12, 17))
    with col_d:
        end_date = st.date_input("수집 종료일", value=datetime.date(2021, 6, 30))
        
    st.warning("경고: 너무 긴 기간을 설정하면 네이버 서버에 의해 IP가 일시 제한될 수 있습니다.")
    
    if st.button(f"🚀 '{selected_persona_name}' DB로 자동 스크래핑 시작", type="primary"):
        from src.scraper import run_scraper
        
        # UI placeholder for live updates
        progress_text = st.empty()
        log_box_placeholder = st.empty()
        
        progress_bar = st.progress(0)
        logs = []
        
        def update_progress(msg, percentage):
            logs.append(msg.strip())
            # Show last 10 lines of logs
            log_str = "\n".join(logs[-10:])
            log_box_placeholder.code(log_str, language="text")
            progress_bar.progress(percentage / 100.0)
            
        try:
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")
            
            result_count = run_scraper(
                persona_id=selected_persona_id, 
                blog_id=target_blog_id, 
                start_date_str=start_str, 
                end_date_str=end_str, 
                progress_callback=update_progress
            )
            
            st.success(f"🎉 성공적으로 {result_count}개의 포스팅 본문을 긁어와 `{selected_persona_name}` DB에 누적 저장했습니다!")
            st.balloons()
            
        except Exception as e:
            st.error(f"스크래핑 중 오류 발생: {e}")

with tab4:
    st.markdown(f"### 📜 {selected_persona_name}의 과거 생성 보관소")
    st.info("이전에 생성했던 칼럼들이 시간순으로 영구 보관됩니다. 클릭해서 내용을 보거나 텍스트를 복사할 수 있습니다.")
    
    import json
    history_file = f"outputs/{selected_persona_id}/history.json"
    
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                histories = json.load(f)
                
            if not histories:
                st.write("아직 생성된 칼럼 기록이 없습니다.")
            else:
                for idx, record in enumerate(histories):
                    timestamp = record.get("timestamp", "알 수 없음")
                    topic_text = record.get("topic", "주제 없음")
                    content = record.get("content", "")
                    
                    # Create an expander for each past column
                    with st.expander(f"🕒 {timestamp} | 주제: {topic_text[:40]}..."):
                        st.markdown("**입력된 주제:**")
                        st.write(topic_text)
                        
                        st.markdown("---")
                        st.markdown("**생성된 본문:**")
                        st.markdown(f'<div class="result-box">{content}</div>', unsafe_allow_html=True)
                        
                        import base64
                        import streamlit.components.v1 as components
                        b64_past = base64.b64encode(content.encode("utf-8")).decode("utf-8")
                        js_past_code = f"""
                        <script>
                        function copyPastToClipboard_{idx}() {{
                            const text = decodeURIComponent(escape(window.atob('{b64_past}')));
                            navigator.clipboard.writeText(text).then(function() {{
                                const btn = document.getElementById("copyBtn_{idx}");
                                btn.innerHTML = "✅ 복사 완료!";
                                btn.style.backgroundColor = "#45a049";
                                setTimeout(() => {{
                                    btn.innerHTML = "📋 이 과거 칼럼 복사하기";
                                    btn.style.backgroundColor = "#4CAF50";
                                }}, 2000);
                            }});
                        }}
                        </script>
                        <button id="copyBtn_{idx}" onclick="copyPastToClipboard_{idx}()" style="width:100%; height:40px; background-color:#4CAF50; color:white; border:none; border-radius:5px; font-weight:bold; font-size:14px; cursor:pointer; font-family:sans-serif; margin-top:10px;">📋 이 과거 칼럼 복사하기</button>
                        """
                        components.html(js_past_code, height=50)
                        
        except Exception as e:
            st.error(f"기록을 불러오는 중 오류가 발생했습니다: {e}")
    else:
        st.write("아직 생성된 칼럼 기록이 없습니다.")
