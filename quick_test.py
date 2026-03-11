"""
빠른 테스트 스크립트 - 로컬 PC에서 실행
전체 파이프라인을 한번에 테스트합니다.

사용법:
  python quick_test.py
  python quick_test.py "키워드"
"""

import os
import sys
import time
from dotenv import load_dotenv

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(override=True)


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else "스타트업이 상표등록을 미루면 안 되는 이유"

    print("=" * 60)
    print("🚀 블로그 자동화 시스템 - 전체 파이프라인 테스트")
    print(f"   주제: {topic}")
    print("=" * 60)

    # API 키 확인
    print("\n🔑 API 키 상태:")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    naver_id = os.environ.get("NAVER_ID", "")
    print(f"  Anthropic: {'✅' if anthropic_key else '❌'}")
    print(f"  OpenAI:    {'✅' if openai_key else '⚠️ (플레이스홀더 이미지 사용)'}")
    print(f"  Naver:     {'✅' if naver_id else '⚠️ (자동 포스팅 불가)'}")

    if not anthropic_key:
        print("\n❌ ANTHROPIC_API_KEY가 없습니다. .env 파일을 확인하세요.")
        return

    # Step 1: 콘텐츠 생성
    print("\n📝 Step 1: 콘텐츠 생성 (유사도 검증 포함)...")
    start = time.time()
    from src.engine import generate_column_with_validation
    gen = generate_column_with_validation(
        "yun_ung_chae", "윤웅채", topic,
        model_id="claude-sonnet-4-6", temperature=0.7,
    )
    content = gen["content"]
    elapsed = time.time() - start
    print(f"  ✅ {len(content)}자 생성 ({elapsed:.1f}초, {gen['attempts']}회 시도)")
    print(f"  유사도: {gen['similarity_check']['max_doc_similarity']:.3f} "
          f"({'통과' if gen['similarity_check']['passed'] else '주의'})")

    # Step 2: 이미지 생성
    print("\n🖼️ Step 2: 이미지 생성...")
    from src.image_handler import generate_blog_images
    img_start = time.time()
    img_data = generate_blog_images(topic=topic, content=content, image_count=4)
    img_elapsed = time.time() - img_start
    print(f"  썸네일: {'✅' if img_data['thumbnail'] else '❌'}")
    print(f"  본문 이미지: {len(img_data['body_images'])}장 ({img_elapsed:.1f}초)")

    # Step 3: HTML 포맷팅
    print("\n🎨 Step 3: HTML 포맷팅...")
    from src.formatter import format_column_html, format_column_preview
    html = format_column_html(content, "yun_ung_chae", include_images=True, image_data=img_data)
    print(f"  블로그 HTML: {len(html):,}자")

    # Step 4: 미리보기 저장
    print("\n📱 Step 4: 미리보기 파일 생성...")
    preview = format_column_preview(content, "yun_ung_chae", img_data)

    os.makedirs("outputs", exist_ok=True)
    safe_topic = topic.replace(" ", "_")[:20]

    preview_path = f"outputs/test_{safe_topic}.html"
    with open(preview_path, "w", encoding="utf-8") as f:
        f.write(preview)
    print(f"  미리보기: {preview_path}")

    text_path = f"outputs/test_{safe_topic}.txt"
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  텍스트: {text_path}")

    html_path = f"outputs/test_{safe_topic}_blog.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  블로그HTML: {html_path}")

    # 결과 요약
    total_time = time.time() - start
    print("\n" + "=" * 60)
    print("✅ 테스트 완료!")
    print(f"  총 소요 시간: {total_time:.1f}초")
    print(f"  콘텐츠: {len(content)}자")
    print(f"  이미지: {img_data['total_count']}장")
    print(f"  HTML: {len(html):,}자")
    print(f"\n📂 미리보기 파일을 브라우저에서 열어보세요:")
    print(f"  {os.path.abspath(preview_path)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
