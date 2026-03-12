import streamlit as st
import os
import json
import time
import html
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(override=True)

# 엔진 모듈 로드
try:
    from src.engine import generate_column, generate_column_stream
    ENGINE_LOADED = True
except ImportError as e:
    ENGINE_LOADED = False

try:
    from src.orchestrator import generate_preview, batch_generate, get_history
    from src.formatter import format_column_html, format_column_preview
    from src.similarity import check_similarity
    ORCHESTRATOR_LOADED = True
except ImportError:
    ORCHESTRATOR_LOADED = False

try:
    from src.image_handler import generate_blog_images, generate_thumbnail
    IMAGE_LOADED = True
except ImportError:
    IMAGE_LOADED = False

# 모델 목록 로드
def load_models():
    try:
        with open("models.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return {m["id"]: m["display_name"] for m in data.get("data", [])}
    except (FileNotFoundError, json.JSONDecodeError):
        return {"claude-sonnet-4-6": "Claude Sonnet 4.6"}

AVAILABLE_MODELS = load_models()

st.set_page_config(
    page_title="블로그 자동화 시스템 | 특허법인 테헤란",
    page_icon="🚀",
    layout="wide",
)

# CSS
st.markdown("""
<style>
    .reportview-container .main .block-container { padding-top: 1.5rem; }
    .stButton>button {
        width: 100%; font-weight: bold;
    }
    .result-box {
        padding: 20px; border-radius: 10px; background-color: #f9f9f9;
        border: 1px solid #ddd; font-size: 15px; line-height: 1.8;
        white-space: pre-wrap; max-height: 500px; overflow-y: auto;
    }
    .status-badge {
        display: inline-block; padding: 2px 8px; border-radius: 12px;
        font-size: 12px; font-weight: bold; color: white;
    }
    .badge-pending { background-color: #ffc107; }
    .badge-ready { background-color: #17a2b8; }
    .badge-published { background-color: #28a745; }
    .badge-failed { background-color: #dc3545; }
</style>
""", unsafe_allow_html=True)


# -- 유틸리티 --

def render_copy_button(text, button_id="copyBtn", label="📋 복사하기"):
    import base64
    import streamlit.components.v1 as components
    b64_text = base64.b64encode(text.encode("utf-8")).decode("utf-8")
    js_code = f"""
    <script>
    function copyText_{button_id}() {{
        const text = decodeURIComponent(escape(window.atob('{b64_text}')));
        navigator.clipboard.writeText(text).then(function() {{
            const btn = document.getElementById("{button_id}");
            btn.innerHTML = "✅ 복사 완료!";
            btn.style.backgroundColor = "#45a049";
            setTimeout(() => {{ btn.innerHTML = "{label}"; btn.style.backgroundColor = "#4CAF50"; }}, 2000);
        }});
    }}
    </script>
    <button id="{button_id}" onclick="copyText_{button_id}()"
        style="width:100%; height:40px; background-color:#4CAF50; color:white;
        border:none; border-radius:6px; font-weight:bold; font-size:13px;
        cursor:pointer; font-family:sans-serif;">
        {label}
    </button>
    """
    components.html(js_code, height=50)


def render_html_copy_button(html_text, button_id="htmlCopyBtn"):
    import base64
    import streamlit.components.v1 as components
    b64_text = base64.b64encode(html_text.encode("utf-8")).decode("utf-8")
    js_code = f"""
    <script>
    function copyHtml_{button_id}() {{
        const text = decodeURIComponent(escape(window.atob('{b64_text}')));
        navigator.clipboard.writeText(text).then(function() {{
            const btn = document.getElementById("{button_id}");
            btn.innerHTML = "✅ HTML 복사 완료!";
            btn.style.backgroundColor = "#0068b7";
            setTimeout(() => {{ btn.innerHTML = "📋 블로그용 HTML 복사"; btn.style.backgroundColor = "#1a73e8"; }}, 2000);
        }});
    }}
    </script>
    <button id="{button_id}" onclick="copyHtml_{button_id}()"
        style="width:100%; height:40px; background-color:#1a73e8; color:white;
        border:none; border-radius:6px; font-weight:bold; font-size:13px;
        cursor:pointer; font-family:sans-serif;">
        📋 블로그용 HTML 복사
    </button>
    """
    components.html(js_code, height=50)


def save_to_history(persona_id, topic, content):
    output_dir = f"outputs/{persona_id}"
    os.makedirs(output_dir, exist_ok=True)
    history_path = os.path.join(output_dir, "history.json")
    history_data = []
    if os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                history_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            history_data = []
    history_data.insert(0, {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "topic": topic,
        "content": content,
    })
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, indent=4)


def render_safe_html(text):
    safe_text = html.escape(text).replace("\n", "<br>")
    st.markdown(f'<div class="result-box">{safe_text}</div>', unsafe_allow_html=True)


def run_async(coro):
    """Streamlit에서 async 함수 실행"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# -- 사이드바 --

PERSONA_OPTIONS = {
    "yun_ung_chae": "윤웅채 변리사",
}

with st.sidebar:
    st.title("🚀 블로그 자동화")
    st.caption("특허법인 테헤란")

    st.markdown("---")
    st.subheader("페르소나")
    selected_persona_id = st.selectbox(
        "작성자:",
        options=list(PERSONA_OPTIONS.keys()),
        format_func=lambda x: PERSONA_OPTIONS[x],
    )
    selected_persona_name = PERSONA_OPTIONS[selected_persona_id]

    st.markdown("---")
    st.subheader("모델 설정")
    selected_model = st.selectbox(
        "AI 모델:", options=list(AVAILABLE_MODELS.keys()),
        format_func=lambda x: AVAILABLE_MODELS[x],
    )
    temperature = st.slider("창의성", 0.0, 1.0, 0.7, 0.05)

    st.markdown("---")
    st.subheader("🖼️ 이미지 설정")
    include_images = st.toggle("이미지 포함", value=False)

    if include_images:
        use_dalle = st.toggle("DALL-E 3 사용", value=bool(openai_key),
                              help="OpenAI API 키 필요. OFF면 플레이스홀더 이미지")
        THUMB_PRESETS = {
            "dark_minimal": "다크 미니멀",
            "light_clean": "라이트 클린",
            "warm_professional": "웜 프로페셔널",
            "blue_corporate": "블루 기업형",
        }
        thumbnail_preset = st.selectbox(
            "썸네일 스타일",
            options=list(THUMB_PRESETS.keys()),
            format_func=lambda x: THUMB_PRESETS[x],
        )
        image_count = st.slider("본문 이미지 수", 3, 7, 4)
    else:
        use_dalle = False
        thumbnail_preset = None
        image_count = 0

    st.markdown("---")
    st.subheader("상태")
    db_dir = f"persona_db/{selected_persona_id}"
    if os.path.exists(db_dir):
        import glob as glob_mod
        json_files = glob_mod.glob(os.path.join(db_dir, "*.json"))
        if json_files:
            st.success("✅ 학습 데이터 적용됨")
        else:
            st.warning("⚠️ 학습 데이터 없음")
    else:
        st.warning("⚠️ 학습 데이터 없음")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    naver_id = os.environ.get("NAVER_ID", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    st.caption(f"Anthropic API: {'✅' if api_key else '❌'}")
    st.caption(f"OpenAI API: {'✅' if openai_key else '⚠️ 플레이스홀더 이미지 사용'}")
    st.caption(f"Naver ID: {'✅' if naver_id else '❌ (.env에 추가 필요)'}")


# -- 메인 탭 --

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🚀 자동 생성 & 발행",
    "📝 단건 칼럼 생성",
    "⚙️ 프롬프트 설정",
    "🌐 블로그 스크래퍼",
    "📜 발행 히스토리",
])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tab 1: 자동 생성 & 발행 (메인 기능)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab1:
    st.markdown("### 키워드 → 생성 → 미리보기 → 발행")
    st.caption("키워드를 입력하면 사람냄새 나는 칼럼을 자동 생성하고, 미리보기 후 네이버 블로그에 자동 발행합니다.")

    # 사용자 이미지 업로드
    uploaded_image_paths = []
    if include_images:
        with st.expander("📷 사용자 이미지 업로드 (선택사항)", expanded=False):
            st.caption("제공 이미지가 있으면 AI 이미지와 혼합 배치됩니다.")
            uploaded_files = st.file_uploader(
                "이미지 파일 선택",
                type=["jpg", "jpeg", "png", "webp"],
                accept_multiple_files=True,
                label_visibility="collapsed",
            )
            if uploaded_files:
                os.makedirs("outputs/uploads", exist_ok=True)
                for uf in uploaded_files:
                    save_path = os.path.join("outputs/uploads", uf.name)
                    with open(save_path, "wb") as f:
                        f.write(uf.getbuffer())
                    uploaded_image_paths.append(save_path)
                st.success(f"✅ {len(uploaded_files)}개 이미지 업로드 완료")

    # 배치 키워드 입력
    st.markdown("#### 📋 키워드 등록")

    if "batch_items" not in st.session_state:
        st.session_state.batch_items = []

    col_input, col_add = st.columns([6, 1])

    with col_input:
        new_topic = st.text_input("키워드/주제", placeholder="예: 스타트업 상표등록 필수인 이유", label_visibility="collapsed")
    with col_add:
        if st.button("➕", use_container_width=True):
            if new_topic.strip():
                st.session_state.batch_items.append({
                    "topic": new_topic.strip(),
                    "publish_mode": "immediate",
                })
                st.rerun()

    # 등록된 키워드 테이블
    if st.session_state.batch_items:
        st.markdown("#### 등록된 키워드")
        for idx, item in enumerate(st.session_state.batch_items):
            col_num, col_topic, col_del = st.columns([0.5, 6, 1])
            with col_num:
                st.write(f"**{idx+1}**")
            with col_topic:
                st.write(item["topic"])
            with col_del:
                if st.button("🗑️", key=f"del_{idx}", use_container_width=True):
                    st.session_state.batch_items.pop(idx)
                    st.rerun()

        st.markdown("---")

        # 일괄 생성 버튼
        col_gen, col_clear = st.columns([3, 1])
        with col_gen:
            generate_all = st.button("🚀 전체 생성 시작", type="primary", use_container_width=True)
        with col_clear:
            if st.button("🗑️ 전체 삭제", use_container_width=True):
                st.session_state.batch_items = []
                st.rerun()

        if generate_all and ENGINE_LOADED and ORCHESTRATOR_LOADED:
            st.session_state.generated_results = []
            progress_bar = st.progress(0)

            total = len(st.session_state.batch_items)
            for idx, item in enumerate(st.session_state.batch_items):
                step_label = f"[{idx+1}/{total}] {item['topic']}"
                with st.spinner(f"{step_label} 생성 중..."):
                    try:
                        result = generate_preview(
                            topic=item["topic"],
                            persona_id=selected_persona_id,
                            persona_name=selected_persona_name,
                            model_id=selected_model,
                            temperature=temperature,
                            include_images=include_images,
                            user_image_paths=uploaded_image_paths if uploaded_image_paths else None,
                            image_count=image_count if include_images else None,
                            thumbnail_preset=thumbnail_preset,
                            use_dalle=use_dalle if include_images else False,
                        )
                        result["publish_mode"] = item.get("publish_mode", "immediate")
                        st.session_state.generated_results.append(result)
                    except Exception as e:
                        st.session_state.generated_results.append({
                            "success": False,
                            "error": str(e),
                            "title": item["topic"],
                        })

                progress_bar.progress((idx + 1) / total)

            st.success(f"✅ {len(st.session_state.generated_results)}건 생성 완료!")

        elif generate_all and not ORCHESTRATOR_LOADED:
            st.error("오케스트레이터 모듈을 불러오지 못했습니다.")

    # 생성 결과 미리보기
    if "generated_results" in st.session_state and st.session_state.generated_results:
        st.markdown("---")
        st.markdown("### 📄 생성 결과")

        for idx, result in enumerate(st.session_state.generated_results):
            title = result.get("title", f"결과 {idx+1}")
            success = result.get("success", False)

            with st.expander(
                f"{'✅' if success else '⚠️'} {title} ({result.get('char_count', 0)}자)",
                expanded=(idx == 0),
            ):
                if success:
                    preview_tab, text_tab, info_tab = st.tabs(["미리보기", "텍스트", "정보"])

                    with preview_tab:
                        render_safe_html(result.get("raw_content", ""))

                    with text_tab:
                        render_safe_html(result.get("raw_content", ""))
                        render_copy_button(result.get("raw_content", ""), f"copy_text_{idx}")

                    with info_tab:
                        sim = result.get("similarity", {})
                        st.write(f"- 글자 수: **{result.get('char_count', 0)}자**")
                        st.write(f"- 생성 시도: **{result.get('attempts', 0)}회**")
                        st.write(f"- 유사도: **{sim.get('max_doc_similarity', 0):.3f}** (임계값: 0.3)")
                        st.write(f"- 유사도 통과: {'✅' if sim.get('passed', False) else '⚠️'}")
                else:
                    st.error(f"생성 실패: {result.get('error', '알 수 없는 오류')}")

        # ━━ 발행 버튼 ━━
        st.markdown("---")
        st.markdown("### 📤 네이버 블로그 자동 발행")

        naver_id = os.environ.get("NAVER_ID", "")
        if not naver_id:
            st.error("⚠️ .env 파일에 NAVER_ID와 NAVER_PW를 설정해주세요.")
        else:
            st.info(
                "💡 **자동 발행 안내:**\n"
                "- Chrome이 실행 중이고 네이버 로그인 상태여야 합니다\n"
                "- Chrome을 `--remote-debugging-port=9222` 옵션으로 시작하세요\n"
                "- 발행 버튼을 누르면 각 글이 순차적으로 발행됩니다"
            )

            if st.button("🚀 전체 자동 발행", type="primary", use_container_width=True):
                successful = [r for r in st.session_state.generated_results if r.get("success")]
                if not successful:
                    st.error("발행 가능한 생성 결과가 없습니다.")
                else:
                    try:
                        from src.naver_poster import NaverPoster

                        publish_progress = st.progress(0)
                        publish_log = st.empty()

                        async def publish_all():
                            poster = NaverPoster()
                            results = []
                            try:
                                await poster.connect()
                                await poster.login()

                                for i, result in enumerate(successful):
                                    title = result.get("title", "")
                                    content = result.get("raw_content", "")

                                    publish_log.info(f"[{i+1}/{len(successful)}] '{title[:30]}...' 발행 중...")

                                    try:
                                        post_result = await poster.post(
                                            title=title,
                                            content=content,
                                            blog_id=naver_id,
                                        )
                                        results.append({
                                            "title": title,
                                            **post_result,
                                        })
                                    except Exception as e:
                                        results.append({
                                            "title": title,
                                            "success": False,
                                            "error": str(e),
                                        })

                                    publish_progress.progress((i + 1) / len(successful))

                                    # 발행 간 대기 (연속 발행 시 안전)
                                    if i < len(successful) - 1:
                                        await asyncio.sleep(5)

                            finally:
                                await poster.close()

                            return results

                        publish_results = run_async(publish_all())

                        # 결과 표시
                        success_count = sum(1 for r in publish_results if r.get("success"))
                        fail_count = len(publish_results) - success_count

                        if success_count > 0:
                            st.success(f"✅ {success_count}건 발행 성공!")
                        if fail_count > 0:
                            st.warning(f"⚠️ {fail_count}건 발행 실패")

                        for r in publish_results:
                            if r.get("success"):
                                st.write(f"✅ **{r['title'][:40]}** → {r.get('url', '')}")
                            else:
                                st.write(f"❌ **{r['title'][:40]}** → {r.get('error', '알 수 없는 오류')}")

                    except ImportError:
                        st.error("naver_poster 모듈을 불러올 수 없습니다. playwright가 설치되어 있는지 확인해주세요.")
                    except Exception as e:
                        st.error(f"발행 중 오류: {type(e).__name__}: {e}")

        # 수동 발행 옵션
        with st.expander("📋 수동 발행 (텍스트 복사)"):
            st.info(
                "**수동 발행 방법:**\n"
                "1. 위에서 텍스트 복사\n"
                "2. 네이버 블로그 에디터 열기\n"
                "3. 글쓰기에 붙여넣기"
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tab 2: 단건 칼럼 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab2:
    st.markdown("### 단건 칼럼 생성")
    st.caption("키워드 하나로 칼럼을 스트리밍 생성합니다.")

    topic = st.text_area(
        "작성할 칼럼의 주제:", height=80,
        placeholder="예: 스타트업이 초기 단계에서 상표권을 반드시 먼저 출원해야 하는 이유",
    )

    if st.button("🚀 칼럼 생성", key="single_gen"):
        if not topic.strip():
            st.error("주제를 입력해 주세요.")
        elif not ENGINE_LOADED:
            st.error("엔진 모듈을 불러오지 못했습니다.")
        else:
            try:
                start_time = time.time()
                st.markdown(f"**'{selected_persona_name}'** 문체로 작성 중...")

                result_container = st.empty()
                full_text = ""
                for chunk in generate_column_stream(
                    selected_persona_id, selected_persona_name, topic,
                    model_id=selected_model, temperature=temperature,
                ):
                    full_text += chunk
                    result_container.markdown(full_text + "▌")
                result_container.markdown(full_text)

                elapsed = time.time() - start_time
                st.success(f"✅ 완료! ({elapsed:.1f}초, {len(full_text)}자)")

                save_to_history(selected_persona_id, topic, full_text)

                # 유사도 검증
                if ORCHESTRATOR_LOADED:
                    sim = check_similarity(full_text, selected_persona_id)
                    st.write(f"유사도: {sim['max_doc_similarity']:.3f} | "
                             f"{'✅ 통과' if sim['passed'] else '⚠️ 유사도 높음'}")

                st.markdown("---")
                col_dl, col_copy = st.columns(2)
                with col_dl:
                    st.download_button(
                        "💾 텍스트 저장", data=full_text,
                        file_name=f"{selected_persona_name}_칼럼.txt",
                        mime="text/plain", use_container_width=True,
                    )
                with col_copy:
                    render_copy_button(full_text, "copyBtn_single")

            except Exception as e:
                st.error(f"생성 중 오류: {type(e).__name__}: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tab 3: 프롬프트 & DB 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab3:
    st.markdown("### 프롬프트 관리")

    prompt_tab, rules_tab, persona_tab = st.tabs(["기본 프롬프트", "사람냄새 규칙", "페르소나 설정"])

    with prompt_tab:
        base_prompt_path = "config/base_prompt.md"
        base_content = ""
        if os.path.exists(base_prompt_path):
            with open(base_prompt_path, "r", encoding="utf-8") as f:
                base_content = f.read()
        new_base = st.text_area("base_prompt.md", value=base_content, height=300)
        if st.button("💾 기본 프롬프트 저장", key="save_base"):
            with open(base_prompt_path, "w", encoding="utf-8") as f:
                f.write(new_base)
            st.success("저장 완료")

    with rules_tab:
        col_human, col_anti = st.columns(2)
        with col_human:
            human_path = "config/human_style_rules.md"
            human_content = ""
            if os.path.exists(human_path):
                with open(human_path, "r", encoding="utf-8") as f:
                    human_content = f.read()
            new_human = st.text_area("human_style_rules.md", value=human_content, height=300)
            if st.button("💾 사람냄새 규칙 저장"):
                with open(human_path, "w", encoding="utf-8") as f:
                    f.write(new_human)
                st.success("저장 완료")

        with col_anti:
            anti_path = "config/anti_ai_detection.md"
            anti_content = ""
            if os.path.exists(anti_path):
                with open(anti_path, "r", encoding="utf-8") as f:
                    anti_content = f.read()
            new_anti = st.text_area("anti_ai_detection.md", value=anti_content, height=300)
            if st.button("💾 AI 탐지 방지 규칙 저장"):
                with open(anti_path, "w", encoding="utf-8") as f:
                    f.write(new_anti)
                st.success("저장 완료")

    with persona_tab:
        json_path = f"config/personas/{selected_persona_id}.json"
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                persona_data = json.load(f)

            new_personality = st.text_area(
                "성향", value=persona_data.get("personality", ""), height=120
            )
            rules_text = "\n".join(persona_data.get("strict_rules", []))
            new_rules = st.text_area("필수 규칙 (줄별 1개)", value=rules_text, height=120)

            if st.button(f"💾 {selected_persona_name} 설정 저장"):
                persona_data["personality"] = new_personality
                persona_data["strict_rules"] = [r.strip() for r in new_rules.split("\n") if r.strip()]
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(persona_data, f, ensure_ascii=False, indent=2)
                st.success("저장 완료")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tab 4: 블로그 스크래퍼
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab4:
    st.markdown("### 네이버 블로그 자동 수집기")

    col_a, col_b = st.columns(2)
    with col_a:
        target_blog_id = st.text_input("블로그 ID", value="jninsa")
    with col_b:
        st.info(f"저장 대상: **{selected_persona_name}**")

    import datetime as dt
    col_c, col_d = st.columns(2)
    with col_c:
        start_date = st.date_input("시작일", value=dt.date(2020, 12, 17))
    with col_d:
        end_date = st.date_input("종료일", value=dt.date(2021, 6, 30))

    if st.button("🚀 스크래핑 시작", type="primary"):
        try:
            from src.scraper import run_scraper
            progress_bar = st.progress(0)
            log_box = st.empty()
            logs = []

            def update_progress(msg, percentage):
                logs.append(msg.strip())
                log_box.code("\n".join(logs[-10:]), language="text")
                progress_bar.progress(min(percentage / 100.0, 1.0))

            result_count = run_scraper(
                persona_id=selected_persona_id,
                blog_id=target_blog_id,
                start_date_str=start_date.strftime("%Y-%m-%d"),
                end_date_str=end_date.strftime("%Y-%m-%d"),
                progress_callback=update_progress,
            )
            st.success(f"✅ {result_count}개 포스팅 저장 완료!")
        except Exception as e:
            st.error(f"오류: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tab 5: 발행 히스토리
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab5:
    st.markdown("### 발행 히스토리")

    history_file = f"outputs/{selected_persona_id}/history.json"
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                histories = json.load(f)
            if histories:
                for idx, record in enumerate(histories[:20]):
                    ts = record.get("timestamp", "")
                    topic_text = record.get("topic", "주제 없음")
                    content = record.get("content", "")
                    with st.expander(f"🕒 {ts} | {topic_text[:50]}"):
                        render_safe_html(content)
                        render_copy_button(content, f"hist_copy_{idx}")
            else:
                st.info("아직 생성 기록이 없습니다.")
        except (json.JSONDecodeError, IOError):
            st.info("기록 파일을 불러올 수 없습니다.")
    else:
        st.info("아직 생성 기록이 없습니다.")
