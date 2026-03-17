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
    from src.engine import generate_column, generate_column_stream, generate_hooking_title, replace_link_markers
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
    from src.category_mapper import auto_classify, get_all_categories
    CATEGORY_LOADED = True
except ImportError:
    CATEGORY_LOADED = False

try:
    from src.scheduler import (
        add_job, load_jobs, get_pending_jobs, execute_pending_jobs,
        create_interval_schedule, update_job_status, clear_completed,
        clear_all as clear_all_jobs, get_all_jobs, remove_job,
        start_scheduler, stop_scheduler, is_scheduler_running,
        get_scheduler_status, execute_job,
    )
    SCHEDULER_LOADED = True
except ImportError:
    SCHEDULER_LOADED = False

try:
    from src.image_handler import generate_blog_images, generate_thumbnail
    IMAGE_LOADED = True
except ImportError:
    IMAGE_LOADED = False

try:
    from src.sheet_manager import (
        get_sheet_stats, smart_select_keywords, build_schedule,
        mark_published, auto_fill_categories, get_available_keywords,
    )
    SHEET_LOADED = True
except ImportError:
    SHEET_LOADED = False

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


def run_in_thread(func, *args, **kwargs):
    """Streamlit에서 Playwright 실행 (Windows ProactorEventLoop 보장)"""
    import concurrent.futures
    import sys

    def _worker():
        # Windows에서 Playwright subprocess 생성에 ProactorEventLoop 필수
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        return func(*args, **kwargs)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_worker)
        return future.result(timeout=600)  # 최대 10분


# -- 블로그 설정 로드 --

def load_blog_config():
    """blogs.json에서 블로그 목록 로드"""
    try:
        with open("config/blogs.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("blogs", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "yun_ung_chae": {
                "display_name": "윤웅채 변리사 블로그",
                "blog_id": "jninsa",
                "env_id_key": "NAVER_ID",
                "env_pw_key": "NAVER_PW",
                "default_persona": "yun_ung_chae",
                "personas": ["yun_ung_chae"],
            }
        }

BLOG_CONFIG = load_blog_config()

# 페르소나 옵션 (블로그별 자동 생성)
def get_persona_display_name(persona_id):
    """페르소나 JSON에서 display name 로드"""
    json_path = f"config/personas/{persona_id}.json"
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("name", persona_id)
        except (json.JSONDecodeError, IOError):
            pass
    return persona_id

# -- 사이드바 --

with st.sidebar:
    st.title("🚀 블로그 자동화")
    st.caption("특허법인 테헤란")

    # 블로그 선택 (새로 추가)
    st.markdown("---")
    st.subheader("블로그 선택")
    selected_blog_key = st.selectbox(
        "대상 블로그:",
        options=list(BLOG_CONFIG.keys()),
        format_func=lambda x: BLOG_CONFIG[x].get("display_name", x),
        key="blog_select",
    )
    selected_blog = BLOG_CONFIG[selected_blog_key]

    # 선택된 블로그의 페르소나 목록
    blog_personas = selected_blog.get("personas", [])
    if not blog_personas:
        blog_personas = [selected_blog.get("default_persona", selected_blog_key)]

    st.markdown("---")
    st.subheader("페르소나")
    if len(blog_personas) == 1:
        selected_persona_id = blog_personas[0]
        selected_persona_name = get_persona_display_name(selected_persona_id)
        st.info(f"작성자: **{selected_persona_name}**")
    else:
        selected_persona_id = st.selectbox(
            "작성자:",
            options=blog_personas,
            format_func=lambda x: get_persona_display_name(x),
        )
        selected_persona_name = get_persona_display_name(selected_persona_id)

    st.markdown("---")
    st.subheader("모델 설정")
    selected_model = st.selectbox(
        "AI 모델:", options=list(AVAILABLE_MODELS.keys()),
        format_func=lambda x: AVAILABLE_MODELS[x],
    )
    temperature = st.slider("창의성", 0.0, 1.0, 0.7, 0.05)

    st.markdown("---")
    st.subheader("🖼️ 이미지 설정")
    include_images = st.toggle("이미지 포함", value=True)

    if include_images:
        THUMB_PRESETS = {
            "dark_minimal": "🌑 다크 미니멀",
            "light_clean": "☀️ 라이트 클린",
            "warm_professional": "🔶 웜 프로페셔널",
            "blue_corporate": "🔷 블루 기업형",
        }
        thumbnail_preset = st.selectbox(
            "썸네일 스타일",
            options=list(THUMB_PRESETS.keys()),
            format_func=lambda x: THUMB_PRESETS[x],
        )
        image_auto = st.checkbox("이미지 수 자동 (소제목에 맞춤)", value=True)
        image_count = None if image_auto else st.slider("본문 이미지 수", 3, 7, 4)
    else:
        thumbnail_preset = None
        image_count = 0

    st.markdown("---")
    st.subheader("상태")
    db_dir = f"persona_db/{selected_persona_id}"
    if os.path.exists(db_dir):
        import glob as glob_mod
        data_files = glob_mod.glob(os.path.join(db_dir, "*.json")) + glob_mod.glob(os.path.join(db_dir, "*.txt"))
        # extra_text.txt는 부가 데이터이므로 카운트에서 제외
        ref_files = [f for f in data_files if not f.endswith("extra_text.txt")]
        if ref_files:
            st.success(f"✅ 학습 데이터 적용됨 ({len(ref_files)}건)")
        else:
            st.warning("⚠️ 학습 데이터 없음")
    else:
        st.warning("⚠️ 학습 데이터 없음")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    blog_id_key = selected_blog.get("env_id_key", "NAVER_ID")
    blog_pw_key = selected_blog.get("env_pw_key", "NAVER_PW")
    naver_id = os.environ.get(blog_id_key, "")
    naver_pw_set = bool(os.environ.get(blog_pw_key, ""))
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    st.caption(f"Anthropic API: {'✅' if api_key else '❌'}")
    st.caption(f"OpenAI API: {'✅' if openai_key else '⚠️ 플레이스홀더 이미지'}")
    st.caption(f"블로그 계정 ({blog_id_key}): {'✅ ' + naver_id if naver_id else '❌ .env에 추가 필요'}")
    if not naver_id:
        st.caption(f"💡 .env에 `{blog_id_key}=아이디` `{blog_pw_key}=비밀번호` 추가")


# -- 메인 탭 --

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🚀 자동 생성 & 발행",
    "📅 스마트 예약",
    "📝 단건 칼럼 생성",
    "⚙️ 프롬프트 설정",
    "🌐 블로그 스크래퍼",
    "📜 발행 히스토리",
])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tab 1: 원클릭 자동 발행 (메인 기능)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab1:
    st.markdown("### 원클릭 자동 발행")
    st.caption("키워드 입력 → 버튼 클릭 한번 → 칼럼 생성 + 이미지 + 네이버 블로그 발행까지 자동 완료")

    # 환경 체크 (선택된 블로그의 계정)
    blog_id_env = selected_blog.get("env_id_key", "NAVER_ID")
    blog_pw_env = selected_blog.get("env_pw_key", "NAVER_PW")
    naver_id = os.environ.get(blog_id_env, "")
    naver_pw = os.environ.get(blog_pw_env, "")
    env_ok = bool(naver_id and naver_pw)
    if not env_ok:
        st.error(f"⚠️ .env 파일에 `{blog_id_env}`와 `{blog_pw_env}`를 설정해주세요.")

    # 발행 모드 선택
    posting_mode = st.radio(
        "발행 모드",
        options=["human_like", "fast"],
        format_func=lambda x: {
            "human_like": "🧑 휴먼 시뮬레이션 (사람처럼 행동)",
            "fast": "⚡ 원클릭 (빠른 발행)",
        }[x],
        index=0,
        horizontal=True,
        key="posting_mode",
    )

    # 키워드 입력
    oneclick_topic = st.text_input(
        "발행 키워드",
        placeholder="예: 스타트업 상표등록 필수인 이유",
        key="oneclick_topic",
    )

    # 제목 직접 지정 (선택)
    with st.expander("🎯 제목 직접 지정 (선택사항)", expanded=False):
        override_title = st.text_input(
            "제목 (비워두면 AI가 자동 생성)",
            placeholder="예: 스타트업 상표등록, 대표가 반드시 알아야 할 3가지",
            key="override_title",
        )

    # 발행 버튼
    btn_label = {"human_like": "🧑 휴먼 시뮬레이션 발행", "fast": "⚡ 원클릭 발행"}
    oneclick_clicked = st.button(
        btn_label.get(posting_mode, "🚀 발행"),
        type="primary",
        use_container_width=True,
        disabled=not env_ok,
        key="oneclick_btn",
    )

    if oneclick_clicked and oneclick_topic.strip():
        try:
            # 진행 상황은 콘솔 로그로만 출력 (Streamlit 스레드 제한 회피)
            def log_progress(step, total, msg):
                print(f"[{step}/{total}] {msg}")

            mode_label = {"human_like": "🧑 휴먼 시뮬레이션", "fast": "⚡ 원클릭"}
            with st.spinner(f"{mode_label.get(posting_mode, '')} 발행 진행 중... (최대 5~10분 소요)"):

                if posting_mode == "human_like":
                    # 휴먼 시뮬레이션 모드
                    def _do_human_like():
                        from src.naver_poster import NaverPoster
                        poster = NaverPoster(progress_callback=log_progress, blog_key=selected_blog_key)
                        try:
                            return poster.post_human_like(
                                topic=oneclick_topic.strip(),
                                persona_id=selected_persona_id,
                                persona_name=selected_persona_name,
                                model_id=selected_model,
                                temperature=temperature,
                                include_images=include_images,
                                image_count=image_count if include_images else 0,
                                blog_id=naver_id,
                                override_title=override_title.strip() if override_title.strip() else None,
                            )
                        finally:
                            poster.close()
                    result = run_in_thread(_do_human_like)

                else:
                    # 원클릭 빠른 발행
                    def _do_one_click():
                        from src.naver_poster import NaverPoster
                        poster = NaverPoster(progress_callback=log_progress, blog_key=selected_blog_key)
                        try:
                            return poster.one_click_post(
                                topic=oneclick_topic.strip(),
                                persona_id=selected_persona_id,
                                persona_name=selected_persona_name,
                                model_id=selected_model,
                                temperature=temperature,
                                include_images=include_images,
                                image_count=image_count if include_images else 0,
                                blog_id=naver_id,
                                override_title=override_title.strip() if override_title.strip() else None,
                            )
                        finally:
                            poster.close()
                    result = run_in_thread(_do_one_click)

            if result.get("success"):
                st.success(f"✅ 발행 완료!")
                st.markdown(f"**제목:** {result.get('title', '')}")
                if result.get('url'):
                    st.markdown(f"**URL:** {result.get('url', '')}")
                st.markdown(f"**본문:** {result.get('char_count', 0)}자 | **이미지:** {result.get('image_count', 0)}장")

                # 제목 후보
                gen = result.get("generation", {})
                if gen.get("title_candidates"):
                    with st.expander("📝 제목 후보"):
                        for i, t in enumerate(gen["title_candidates"]):
                            st.write(f"{i+1}. {t}")
            else:
                st.error(f"❌ 발행 실패: {result.get('error', '알 수 없는 오류')}")

        except ImportError as ie:
            st.error(f"모듈 로드 실패: {ie}. playwright 설치: `pip install playwright && playwright install chromium`")
        except Exception as e:
            st.error(f"❌ 오류: {type(e).__name__}: {e}")

    elif oneclick_clicked and not oneclick_topic.strip():
        st.warning("키워드를 입력해주세요.")

    # 구분선
    st.markdown("---")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 배치 & 예약 발행
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with st.expander("📋 배치 & 예약 발행", expanded=False):
        st.caption("여러 키워드를 등록하고, 각각 즉시 발행 또는 예약 발행할 수 있습니다.")

        if "batch_items" not in st.session_state:
            st.session_state.batch_items = []

        # --- 키워드 입력 ---
        st.markdown("##### ➕ 키워드 추가")
        col_input, col_mode, col_add = st.columns([4, 2, 1])
        with col_input:
            new_topic = st.text_input(
                "키워드", placeholder="예: 스타트업 상표등록 필수인 이유",
                label_visibility="collapsed", key="batch_new_topic",
            )
        with col_mode:
            new_mode = st.selectbox(
                "모드", options=["immediate", "scheduled"],
                format_func=lambda x: "⚡ 즉시 발행" if x == "immediate" else "🕐 예약 발행",
                label_visibility="collapsed", key="batch_new_mode",
            )
        with col_add:
            add_clicked = st.button("➕", use_container_width=True, key="batch_add_btn")

        # 예약 시간 입력 (예약 모드일 때만)
        scheduled_dt = None
        if new_mode == "scheduled":
            col_date, col_time = st.columns(2)
            with col_date:
                sched_date = st.date_input("예약 날짜", value=datetime.now().date(), key="batch_sched_date")
            with col_time:
                sched_time = st.time_input("예약 시간", value=(datetime.now() + timedelta(hours=1)).time(), key="batch_sched_time")
            scheduled_dt = datetime.combine(sched_date, sched_time)

        if add_clicked and new_topic.strip():
            auto_cat = None
            if CATEGORY_LOADED:
                auto_cat = auto_classify(new_topic.strip(), persona_id=selected_persona_id)
            item = {
                "topic": new_topic.strip(),
                "category": auto_cat,
                "mode": new_mode,
                "scheduled_time": scheduled_dt.isoformat() if scheduled_dt else None,
            }
            st.session_state.batch_items.append(item)
            st.rerun()

        # --- 간격 예약 일괄 등록 ---
        with st.popover("🔄 간격 예약 일괄 등록"):
            st.caption("등록된 키워드를 일정 간격으로 예약 발행합니다.")
            interval_start_date = st.date_input("시작 날짜", value=datetime.now().date(), key="interval_date")
            interval_start_time = st.time_input("시작 시간", value=datetime.now().time(), key="interval_time")
            interval_min = st.number_input("발행 간격 (분)", min_value=5, max_value=1440, value=60, step=5, key="interval_min")
            if st.button("✅ 간격 예약 적용", key="interval_apply"):
                start_dt = datetime.combine(interval_start_date, interval_start_time)
                for idx, item in enumerate(st.session_state.batch_items):
                    item["mode"] = "scheduled"
                    item["scheduled_time"] = (start_dt + timedelta(minutes=interval_min * idx)).isoformat()
                st.rerun()

        # --- 등록된 키워드 목록 ---
        if st.session_state.batch_items:
            st.markdown("##### 📝 등록된 키워드")
            for idx, item in enumerate(st.session_state.batch_items):
                col_num, col_topic, col_mode_disp, col_time_disp, col_del = st.columns([0.4, 3.5, 1.5, 2, 0.6])
                with col_num:
                    st.write(f"**{idx+1}**")
                with col_topic:
                    st.write(item["topic"])
                with col_mode_disp:
                    if item.get("mode") == "scheduled":
                        st.markdown('<span class="status-badge badge-ready">🕐 예약</span>', unsafe_allow_html=True)
                    else:
                        st.markdown('<span class="status-badge badge-pending">⚡ 즉시</span>', unsafe_allow_html=True)
                with col_time_disp:
                    if item.get("scheduled_time"):
                        try:
                            dt = datetime.fromisoformat(item["scheduled_time"])
                            st.write(dt.strftime("%m/%d %H:%M"))
                        except (ValueError, TypeError):
                            st.write("-")
                    else:
                        st.write("-")
                with col_del:
                    if st.button("🗑️", key=f"batch_del_{idx}", use_container_width=True):
                        st.session_state.batch_items.pop(idx)
                        st.rerun()

            st.markdown("---")

            # --- 발행 방법 선택 ---
            col_immediate, col_schedule, col_clear = st.columns([2, 2, 1])

            with col_immediate:
                batch_now_clicked = st.button(
                    "⚡ 즉시 항목만 발행",
                    type="primary", use_container_width=True,
                    key="batch_immediate_btn",
                )
            with col_schedule:
                if SCHEDULER_LOADED:
                    batch_schedule_clicked = st.button(
                        "🕐 예약 등록 & 스케줄러 시작",
                        use_container_width=True,
                        key="batch_schedule_btn",
                    )
                else:
                    batch_schedule_clicked = False
                    st.button("🕐 예약 (스케줄러 미로드)", disabled=True, use_container_width=True)
            with col_clear:
                if st.button("🗑️ 전체 삭제", use_container_width=True, key="batch_clear_all"):
                    st.session_state.batch_items = []
                    st.rerun()

            # --- 즉시 발행 실행 ---
            if batch_now_clicked and env_ok:
                immediate_items = [it for it in st.session_state.batch_items if it.get("mode") != "scheduled"]
                if not immediate_items:
                    st.warning("즉시 발행 키워드가 없습니다. 모드를 확인해주세요.")
                else:
                    try:
                        from src.naver_poster import NaverPoster
                        batch_progress = st.progress(0)
                        batch_status = st.empty()
                        batch_results = []
                        total_items = len(immediate_items)

                        for idx, item in enumerate(immediate_items):
                            batch_status.info(f"[{idx+1}/{total_items}] '{item['topic']}' 발행 중...")

                            cat = item.get("category")
                            cat_no = cat.get("category_no") if cat else None

                            def _do_batch(topic, c_no):
                                poster = NaverPoster(progress_callback=None, blog_key=selected_blog_key)
                                try:
                                    return poster.one_click_post(
                                        topic=topic,
                                        persona_id=selected_persona_id,
                                        persona_name=selected_persona_name,
                                        model_id=selected_model,
                                        temperature=temperature,
                                        include_images=include_images,
                                        image_count=image_count if include_images else 0,
                                        blog_id=naver_id,
                                        category_no=c_no,
                                    )
                                finally:
                                    poster.close()

                            result = run_in_thread(_do_batch, item["topic"], cat_no)
                            batch_results.append({"topic": item["topic"], **result})
                            batch_progress.progress((idx + 1) / total_items)

                            if idx < total_items - 1:
                                import time as _time
                                _time.sleep(5)

                        batch_progress.progress(1.0)
                        batch_status.empty()

                        success_count = sum(1 for r in batch_results if r.get("success"))
                        fail_count = len(batch_results) - success_count
                        if success_count > 0:
                            st.success(f"✅ {success_count}건 발행 성공!")
                        if fail_count > 0:
                            st.warning(f"⚠️ {fail_count}건 발행 실패")
                        for r in batch_results:
                            if r.get("success"):
                                st.write(f"✅ **{r.get('title', r['topic'])[:40]}** → {r.get('url', '')}")
                            else:
                                st.write(f"❌ **{r['topic'][:40]}** → {r.get('error', '알 수 없는 오류')}")

                        # 발행 완료된 즉시 항목 제거
                        st.session_state.batch_items = [
                            it for it in st.session_state.batch_items if it.get("mode") == "scheduled"
                        ]

                    except ImportError:
                        st.error("playwright가 설치되어 있지 않습니다.")
                    except Exception as e:
                        st.error(f"오류: {type(e).__name__}: {e}")

            # --- 예약 등록 & 스케줄러 시작 ---
            if batch_schedule_clicked and env_ok and SCHEDULER_LOADED:
                scheduled_items = [it for it in st.session_state.batch_items if it.get("mode") == "scheduled"]
                immediate_to_schedule = [it for it in st.session_state.batch_items if it.get("mode") != "scheduled"]

                registered = 0
                # 예약 항목 등록
                for item in scheduled_items:
                    cat = item.get("category")
                    cat_no = cat.get("category_no") if cat else None
                    add_job(
                        topic=item["topic"],
                        persona_id=selected_persona_id,
                        persona_name=selected_persona_name,
                        blog_key=selected_blog_key,
                        model_id=selected_model,
                        temperature=temperature,
                        include_images=include_images,
                        image_count=image_count if include_images else 0,
                        category_no=cat_no,
                        scheduled_time=item.get("scheduled_time"),
                    )
                    registered += 1

                # 즉시 항목도 즉시 발행으로 등록
                for item in immediate_to_schedule:
                    cat = item.get("category")
                    cat_no = cat.get("category_no") if cat else None
                    add_job(
                        topic=item["topic"],
                        persona_id=selected_persona_id,
                        persona_name=selected_persona_name,
                        blog_key=selected_blog_key,
                        model_id=selected_model,
                        temperature=temperature,
                        include_images=include_images,
                        image_count=image_count if include_images else 0,
                        category_no=cat_no,
                        scheduled_time=None,
                    )
                    registered += 1

                # 스케줄러 시작
                def _sched_log(msg):
                    print(f"[Scheduler] {msg}")

                started = start_scheduler(check_interval=30, log_callback=_sched_log)

                st.session_state.batch_items = []
                if started:
                    st.success(f"✅ {registered}건 등록 완료! 스케줄러가 시작되었습니다.")
                else:
                    st.info(f"✅ {registered}건 등록 완료! (스케줄러 이미 실행 중)")
                st.rerun()

        # --- 스케줄러 상태 & 작업 현황 ---
        if SCHEDULER_LOADED:
            st.markdown("---")
            st.markdown("##### 📊 스케줄러 & 작업 현황")

            status = get_scheduler_status()

            # 스케줄러 ON/OFF
            col_status, col_toggle = st.columns([4, 1])
            with col_status:
                if status["running"]:
                    st.markdown("🟢 **스케줄러 실행 중** (30초마다 예약 확인)")
                else:
                    st.markdown("🔴 **스케줄러 꺼짐**")

                if status["next_scheduled"]:
                    try:
                        next_dt = datetime.fromisoformat(status["next_scheduled"])
                        st.caption(f"다음 예약: {next_dt.strftime('%Y-%m-%d %H:%M')}")
                    except (ValueError, TypeError):
                        pass

            with col_toggle:
                if status["running"]:
                    if st.button("⏹️ 중지", key="sched_stop", use_container_width=True):
                        stop_scheduler()
                        st.rerun()
                else:
                    if st.button("▶️ 시작", key="sched_start", use_container_width=True):
                        def _sched_log2(msg):
                            print(f"[Scheduler] {msg}")
                        start_scheduler(check_interval=30, log_callback=_sched_log2)
                        st.rerun()

            # 상태 요약
            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
            with col_s1:
                st.metric("대기", status["pending"])
            with col_s2:
                st.metric("진행 중", status["publishing"])
            with col_s3:
                st.metric("완료", status["published"])
            with col_s4:
                st.metric("실패", status["failed"])

            # 작업 목록
            all_jobs = get_all_jobs()
            if all_jobs:
                for job in all_jobs[-20:]:
                    status_emoji = {
                        "pending": "🟡", "publishing": "🔵",
                        "published": "🟢", "failed": "🔴",
                    }.get(job.get("status", ""), "⚪")
                    status_text = {
                        "pending": "대기", "publishing": "진행 중",
                        "published": "완료", "failed": "실패",
                    }.get(job.get("status", ""), job.get("status", ""))

                    time_str = ""
                    if job.get("scheduled_time"):
                        try:
                            dt = datetime.fromisoformat(job["scheduled_time"])
                            time_str = f" | 예약: {dt.strftime('%m/%d %H:%M')}"
                        except (ValueError, TypeError):
                            pass

                    result_str = ""
                    if job.get("result_url"):
                        result_str = f" → [{job['result_url']}]({job['result_url']})"
                    elif job.get("error"):
                        result_str = f" → {job['error'][:50]}"

                    col_j1, col_j2 = st.columns([6, 1])
                    with col_j1:
                        st.write(f"{status_emoji} **#{job['id']}** {job['topic'][:40]} ({status_text}{time_str}){result_str}")
                    with col_j2:
                        if job.get("status") == "pending":
                            if st.button("🗑️", key=f"job_del_{job['id']}", use_container_width=True):
                                remove_job(job["id"])
                                st.rerun()

                # 정리 버튼
                col_clean1, col_clean2 = st.columns(2)
                with col_clean1:
                    if st.button("🧹 완료/실패 정리", key="clean_done", use_container_width=True):
                        removed = clear_completed()
                        st.success(f"{removed}건 정리 완료")
                        st.rerun()
                with col_clean2:
                    if st.button("🗑️ 전체 작업 삭제", key="clean_all", use_container_width=True):
                        clear_all_jobs()
                        st.rerun()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tab 2: 스마트 예약발행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab2:
    st.markdown("### 📅 스마트 예약발행")
    st.caption("날짜 + 블로그 + 포스팅 수만 입력하면 키워드 자동 선정 → 예약 등록")

    if not SHEET_LOADED:
        st.error("sheet_manager 모듈을 불러오지 못했습니다.")
    else:
        # 시트 통계
        try:
            stats = get_sheet_stats()
            col_stat1, col_stat2, col_stat3 = st.columns(3)
            col_stat1.metric("전체 키워드", f"{stats['total_keywords']}개")
            col_stat2.metric("발행 완료", f"{stats['published']}개")
            col_stat3.metric("미발행", f"{stats['remaining']}개")

            if stats.get("category_distribution"):
                with st.expander("카테고리 분포"):
                    for cat, cnt in sorted(stats["category_distribution"].items(), key=lambda x: -x[1]):
                        pct = cnt / stats["total_keywords"] * 100
                        st.write(f"**{cat}**: {cnt}개 ({pct:.0f}%)")
        except Exception as e:
            st.warning(f"시트 통계 로드 실패: {e}")

        st.divider()

        # 입력 폼
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            schedule_date = st.date_input(
                "발행 날짜",
                value=datetime.now().date() + timedelta(days=1),
                min_value=datetime.now().date(),
            )
        with col_b:
            schedule_blog = st.selectbox(
                "블로그 선택",
                options=list(BLOG_CONFIG.keys()) if BLOG_CONFIG else ["yun_ung_chae"],
                format_func=lambda x: BLOG_CONFIG.get(x, {}).get("display_name", x) if BLOG_CONFIG else x,
                key="schedule_blog",
            )
        with col_c:
            schedule_count = st.number_input("포스팅 수", min_value=1, max_value=10, value=3, key="schedule_count")

        col_btn1, col_btn2 = st.columns(2)
        preview_clicked = col_btn1.button("🔍 키워드 미리보기", use_container_width=True)
        register_clicked = col_btn2.button("🚀 예약 등록", use_container_width=True, type="primary")

        # 세션 상태로 스케줄 관리
        if "smart_schedule" not in st.session_state:
            st.session_state.smart_schedule = None

        if preview_clicked:
            with st.spinner("키워드 선정 + 시간 분배 중..."):
                try:
                    # 블로그 키에서 persona_id 추출
                    blog_conf = BLOG_CONFIG.get(schedule_blog, {})
                    persona_id = blog_conf.get("default_persona", schedule_blog)

                    schedule = build_schedule(
                        date_str=schedule_date.strftime("%Y-%m-%d"),
                        persona_id=persona_id,
                        count=schedule_count,
                    )
                    st.session_state.smart_schedule = schedule
                    st.session_state._sched_blog_key = schedule_blog
                    st.session_state._sched_date = schedule_date.strftime("%Y-%m-%d")
                except Exception as e:
                    st.error(f"키워드 선정 실패: {e}")

        # 스케줄 미리보기 표시
        if st.session_state.smart_schedule:
            schedule = st.session_state.smart_schedule

            st.markdown("#### 선정된 키워드 + 발행 시간")

            # 카테고리 다양성 표시
            cats = [s["category"] for s in schedule if s["category"]]
            unique_cats = set(cats)
            st.success(f"카테고리 분포: {', '.join(f'{c}' for c in unique_cats)} ({len(unique_cats)}종류)")

            for i, item in enumerate(schedule):
                time_str = item["time"].split(" ")[1] if " " in item["time"] else item["time"]
                col_t, col_k, col_c2, col_v = st.columns([1, 3, 1.5, 1])
                col_t.markdown(f"**{time_str}**")
                col_k.write(item["keyword"])
                col_c2.write(f"`{item['category']}`")
                col_v.write(f"조회수 {item['total']}")

            st.divider()

        if register_clicked:
            schedule = st.session_state.get("smart_schedule")
            if not schedule:
                st.warning("먼저 '키워드 미리보기'를 클릭하세요.")
            elif not SCHEDULER_LOADED:
                st.error("스케줄러 모듈이 로드되지 않았습니다.")
            else:
                blog_key = st.session_state.get("_sched_blog_key", schedule_blog)
                blog_conf = BLOG_CONFIG.get(blog_key, {})
                persona_id = blog_conf.get("default_persona", blog_key)
                # persona_name은 persona json에서 가져오기
                try:
                    with open(f"config/personas/{persona_id}.json", "r", encoding="utf-8") as _pf:
                        persona_name = json.load(_pf).get("name", "")
                except Exception:
                    persona_name = ""
                blog_id = blog_conf.get("blog_id", "")

                registered = 0
                for item in schedule:
                    try:
                        job = add_job(
                            topic=item["keyword"],
                            persona_id=persona_id,
                            persona_name=persona_name,
                            scheduled_time=item["time"],
                            model_id=selected_model,
                            blog_id=blog_id,
                            blog_key=blog_key,
                            sheet_row_index=item.get("row_index"),
                        )
                        if job:
                            registered += 1
                    except Exception as e:
                        st.error(f"예약 실패 ({item['keyword']}): {e}")

                if registered > 0:
                    st.success(f"✅ {registered}건 예약 등록 완료! ({st.session_state.get('_sched_date', '')})")
                    st.session_state.smart_schedule = None
                    st.rerun()

        # ── 예약 대기 현황 ──
        st.divider()
        st.markdown("### 📋 예약 대기 현황")

        if SCHEDULER_LOADED:
            all_jobs = get_all_jobs()
            pending_jobs = [j for j in all_jobs if j.get("status") == "pending"]
            publishing_jobs = [j for j in all_jobs if j.get("status") == "publishing"]
            published_jobs = [j for j in all_jobs if j.get("status") == "published"]
            failed_jobs = [j for j in all_jobs if j.get("status") == "failed"]

            col_p1, col_p2, col_p3, col_p4 = st.columns(4)
            col_p1.metric("대기중", f"{len(pending_jobs)}건")
            col_p2.metric("발행중", f"{len(publishing_jobs)}건")
            col_p3.metric("완료", f"{len(published_jobs)}건")
            col_p4.metric("실패", f"{len(failed_jobs)}건")

            if pending_jobs:
                # 날짜별 그룹핑
                by_date = {}
                for j in pending_jobs:
                    sched_time = j.get("scheduled_time", "")
                    date_part = sched_time.split(" ")[0] if " " in sched_time else "즉시"
                    by_date.setdefault(date_part, []).append(j)

                for date_key in sorted(by_date.keys()):
                    jobs_list = by_date[date_key]
                    # 블로그별 구분
                    blog_names = set()
                    for j in jobs_list:
                        bk = j.get("blog_key", "")
                        bconf = BLOG_CONFIG.get(bk, {})
                        blog_names.add(bconf.get("display_name", bk))

                    st.markdown(f"**📅 {date_key}** — {', '.join(blog_names)} ({len(jobs_list)}건)")

                    for j in sorted(jobs_list, key=lambda x: x.get("scheduled_time", "")):
                        sched_time = j.get("scheduled_time", "")
                        time_part = sched_time.split(" ")[1] if " " in sched_time else "즉시"
                        bk = j.get("blog_key", "")
                        bconf = BLOG_CONFIG.get(bk, {})
                        blog_label = bconf.get("display_name", bk)[:6]

                        col_j1, col_j2, col_j3, col_j4 = st.columns([1, 3, 1.5, 0.5])
                        col_j1.write(f"`{time_part}`")
                        col_j2.write(j.get("topic", ""))
                        col_j3.write(f"_{blog_label}_")
                        if col_j4.button("❌", key=f"del_job_{j['id']}"):
                            remove_job(j["id"])
                            st.rerun()

            elif not published_jobs and not failed_jobs:
                st.info("예약된 작업이 없습니다. 위에서 키워드 미리보기 → 예약 등록을 진행해보세요.")

            # 완료/실패 내역 (접힘)
            if published_jobs or failed_jobs:
                with st.expander(f"최근 발행 내역 ({len(published_jobs)}건 완료 / {len(failed_jobs)}건 실패)"):
                    for j in sorted(published_jobs + failed_jobs, key=lambda x: x.get("published_at", x.get("created_at", "")), reverse=True)[:10]:
                        status_icon = "✅" if j["status"] == "published" else "❌"
                        url = j.get("result_url", "")
                        title = j.get("result_title", j.get("topic", ""))
                        st.write(f"{status_icon} **{title}** {'— [링크](' + url + ')' if url else ''}")

                    if len(published_jobs) > 0:
                        if st.button("완료 내역 정리", key="clear_completed_smart"):
                            clear_completed()
                            st.rerun()
        else:
            st.warning("스케줄러 모듈이 로드되지 않았습니다.")


# Tab 3: 단건 칼럼 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab3:
    st.markdown("### 단건 칼럼 생성")
    st.caption("키워드 하나로 칼럼을 스트리밍 생성합니다.")

    topic = st.text_area(
        "작성할 칼럼의 주제:", height=80,
        placeholder="예: 스타트업이 초기 단계에서 상표권을 반드시 먼저 출원해야 하는 이유",
    )

    col_gen, col_title = st.columns([3, 1])
    with col_gen:
        gen_clicked = st.button("🚀 칼럼 생성", key="single_gen", use_container_width=True)
    with col_title:
        title_only = st.button("📝 제목만 생성", key="title_only_gen", use_container_width=True)

    # 제목만 생성
    if title_only:
        if not topic.strip():
            st.error("주제를 입력해 주세요.")
        elif not ENGINE_LOADED:
            st.error("엔진 모듈을 불러오지 못했습니다.")
        else:
            with st.spinner("후킹 제목 생성 중..."):
                try:
                    titles = generate_hooking_title(
                        topic=topic.strip(),
                        persona_id=selected_persona_id,
                        model_id=selected_model,
                        count=5,
                    )
                    if titles:
                        st.markdown("#### 생성된 제목 후보")
                        for i, t in enumerate(titles):
                            st.write(f"**{i+1}.** {t}")
                    else:
                        st.warning("제목 생성 결과가 없습니다.")
                except Exception as e:
                    st.error(f"제목 생성 오류: {type(e).__name__}: {e}")

    # 칼럼 생성
    if gen_clicked:
        if not topic.strip():
            st.error("주제를 입력해 주세요.")
        elif not ENGINE_LOADED:
            st.error("엔진 모듈을 불러오지 못했습니다.")
        else:
            try:
                start_time = time.time()

                # 후킹 제목 먼저 생성
                st.markdown(f"**'{selected_persona_name}'** 문체로 작성 중...")
                title_container = st.empty()
                with st.spinner("후킹 제목 생성 중..."):
                    try:
                        hooking_titles = generate_hooking_title(
                            topic=topic.strip(),
                            persona_id=selected_persona_id,
                            model_id=selected_model,
                            count=5,
                        )
                        if hooking_titles:
                            title_container.markdown("**생성된 제목:** " + " | ".join(hooking_titles))
                    except Exception:
                        hooking_titles = []

                result_container = st.empty()
                full_text = ""
                for chunk in generate_column_stream(
                    selected_persona_id, selected_persona_name, topic,
                    model_id=selected_model, temperature=temperature,
                ):
                    full_text += chunk
                    result_container.markdown(full_text + "▌")
                # 링크 마커 치환
                full_text = replace_link_markers(full_text, selected_persona_id)
                result_container.markdown(full_text)

                elapsed = time.time() - start_time
                st.success(f"✅ 완료! ({elapsed:.1f}초, {len(full_text)}자)")

                save_to_history(selected_persona_id, topic, full_text)

                # 제목 선택
                if hooking_titles:
                    st.markdown("---")
                    st.markdown("#### 제목 선택")
                    for i, t in enumerate(hooking_titles):
                        st.write(f"**{i+1}.** {t}")

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
# Tab 4: 프롬프트 & DB 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab4:
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
# Tab 5: 블로그 스크래퍼
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab5:
    st.markdown("### 네이버 블로그 자동 수집기")

    col_a, col_b = st.columns(2)
    with col_a:
        target_blog_id = st.text_input("블로그 ID", value=selected_blog.get("blog_id", "jninsa"))
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
# Tab 6: 발행 히스토리
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab6:
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
