"""
네이버 블로그 자동 포스팅 테스트 스크립트
로컬 PC (Windows)에서 실행하세요.

사용법:
  python test_naver_post.py              → 기본 테스트 (미리보기만, 발행 안함)
  python test_naver_post.py --publish    → 실제 발행
  python test_naver_post.py --draft      → 임시저장만
"""

import os
import sys
import time
import logging
import argparse
from dotenv import load_dotenv

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(override=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def check_env():
    """환경 변수 확인"""
    print("=" * 60)
    print("🔑 환경 변수 확인")
    print("=" * 60)

    checks = {
        "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", ""),
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),
        "NAVER_ID": os.environ.get("NAVER_ID", ""),
        "NAVER_PW": os.environ.get("NAVER_PW", ""),
    }

    all_ok = True
    for key, val in checks.items():
        status = "✅" if val else "❌"
        display = f"{val[:15]}..." if val and len(val) > 15 else val
        if key == "NAVER_PW" and val:
            display = "****"
        print(f"  {status} {key}: {display}")
        if key in ("ANTHROPIC_API_KEY", "NAVER_ID", "NAVER_PW") and not val:
            all_ok = False

    if not all_ok:
        print("\n❌ 필수 환경 변수가 없습니다. .env 파일을 확인하세요.")
        return False

    print("\n✅ 환경 변수 OK")
    return True


def generate_test_content():
    """테스트용 콘텐츠 생성"""
    print("\n" + "=" * 60)
    print("📝 테스트 콘텐츠 생성")
    print("=" * 60)

    topic = "스타트업 대표가 상표등록을 미루면 안 되는 이유"

    # 콘텐츠 생성
    print(f"\n주제: {topic}")
    print("콘텐츠 생성 중... (1-2분 소요)")
    start = time.time()

    from src.engine import generate_column_with_validation
    gen = generate_column_with_validation(
        "yun_ung_chae", "윤웅채", topic,
        model_id="claude-sonnet-4-6", temperature=0.7,
    )

    content = gen["content"]
    elapsed = time.time() - start
    print(f"✅ {len(content)}자 생성 완료 ({elapsed:.1f}초)")
    print(f"   유사도: {gen['similarity_check']['max_doc_similarity']:.3f}")

    # 이미지 생성
    print("\n🖼️ 이미지 생성 중...")
    from src.image_handler import generate_blog_images
    img_data = generate_blog_images(topic=topic, content=content, image_count=4)
    print(f"   썸네일: {'✅' if img_data['thumbnail'] else '❌'}")
    print(f"   본문 이미지: {len(img_data['body_images'])}장")

    # HTML 포맷팅
    from src.formatter import format_column_html
    html = format_column_html(content, "yun_ung_chae", include_images=True, image_data=img_data)
    print(f"   HTML: {len(html):,}자")

    # 제목 추출
    from src.naver_poster import _extract_or_generate_title
    title = _extract_or_generate_title(topic, content)
    print(f"   제목: {title}")

    return title, html, content


def test_login_only():
    """로그인만 테스트"""
    print("\n" + "=" * 60)
    print("🔐 네이버 로그인 테스트")
    print("=" * 60)

    from src.naver_poster import NaverPoster

    poster = NaverPoster(blog_id="jninsa", headless=False)
    try:
        poster._init_driver()
        print("✅ Chrome 드라이버 초기화 성공")

        print("\n네이버 로그인 시도 중...")
        print("⚠️ 캡차나 2차 인증이 뜨면 직접 처리해주세요. (30초 대기)")
        success = poster.login()

        if success:
            print("✅ 로그인 성공!")
            return poster
        else:
            print("❌ 로그인 실패")
            print("   - ID/PW 확인")
            print("   - 캡차가 뜨는 경우 수동 처리 필요")
            poster.close()
            return None

    except Exception as e:
        print(f"❌ 오류: {e}")
        poster.close()
        return None


def test_post(poster, title, html, publish=False):
    """포스팅 테스트"""
    print("\n" + "=" * 60)
    action = "📤 실제 발행" if publish else "📋 에디터 입력 테스트 (발행 안함)"
    print(action)
    print("=" * 60)

    tags = ["상표등록", "스타트업", "브랜드보호", "특허법인테헤란"]

    if publish:
        result = poster.post(
            title=title,
            html_content=html,
            tags=tags,
            publish_immediately=True,
        )
        if result["success"]:
            print(f"\n✅ 발행 성공!")
            print(f"   URL: {result.get('url', 'N/A')}")
            print(f"   시간: {result.get('published_at', 'N/A')}")
        else:
            print(f"\n❌ 발행 실패: {result.get('error', '알 수 없는 오류')}")
        return result
    else:
        # 에디터만 열고 내용 입력, 발행은 안함
        print("\n에디터로 이동 중...")
        if poster._navigate_to_editor():
            print("✅ 에디터 로딩 완료")

            print("제목 입력 중...")
            poster._set_title(title)
            print(f"✅ 제목: {title}")

            print("본문 HTML 삽입 중...")
            poster._set_content_html(html)
            print("✅ 본문 삽입 완료")

            print("태그 입력 중...")
            poster._set_tags(tags)
            print("✅ 태그 입력 완료")

            print("\n" + "=" * 60)
            print("📋 에디터에 내용이 입력되었습니다.")
            print("   브라우저에서 직접 확인 후 발행 버튼을 눌러주세요.")
            print("   (30초 후 자동으로 종료됩니다)")
            print("=" * 60)

            # 사용자가 확인할 시간
            time.sleep(30)
        else:
            print("❌ 에디터 로딩 실패")

        return {"success": True, "mode": "preview"}


def main():
    parser = argparse.ArgumentParser(description="네이버 블로그 포스팅 테스트")
    parser.add_argument("--publish", action="store_true", help="실제 발행")
    parser.add_argument("--login-only", action="store_true", help="로그인만 테스트")
    parser.add_argument("--skip-generate", action="store_true", help="샘플 HTML로 테스트")
    args = parser.parse_args()

    print("🚀 네이버 블로그 자동 포스팅 테스트")
    print("=" * 60)

    # 1. 환경 확인
    if not check_env():
        return

    # 2. 로그인만 테스트
    if args.login_only:
        poster = test_login_only()
        if poster:
            input("\n엔터를 누르면 브라우저를 닫습니다...")
            poster.close()
        return

    # 3. 콘텐츠 생성
    if args.skip_generate:
        title = "스타트업 대표가 상표등록을 미루면 안 되는 이유"
        html = """
        <div style="font-family: '나눔고딕', sans-serif; font-size: 16px; line-height: 1.8; color: #333;">
            <p>안녕하세요. 특허법인 테헤란 윤웅채 변리사입니다.</p>
            <p>이 글은 <b>자동 포스팅 테스트</b>입니다.</p>
            <p style="color: #888;">테스트 시간: """ + time.strftime("%Y-%m-%d %H:%M:%S") + """</p>
        </div>
        """
        content = "테스트 콘텐츠"
    else:
        title, html, content = generate_test_content()

    # 4. 로그인
    poster = test_login_only()
    if not poster:
        return

    # 5. 포스팅
    try:
        result = test_post(poster, title, html, publish=args.publish)

        if args.publish and result.get("success"):
            print("\n🎉 포스팅이 완료되었습니다!")
        elif not args.publish:
            print("\n💡 실제 발행하려면: python test_naver_post.py --publish")

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
    finally:
        if not args.publish:
            input("\n엔터를 누르면 브라우저를 닫습니다...")
        poster.close()
        print("브라우저 종료 완료")


if __name__ == "__main__":
    main()
