"""
통합 테스트: 키워드 → 칼럼 생성 → 네이버 블로그 발행
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(override=True)


async def main():
    topic = "스타트업 상표등록"
    persona_id = "yun_ung_chae"
    persona_name = "윤웅채"
    blog_id = os.environ.get("NAVER_ID", "jninsa")

    print("=" * 60)
    print(f"통합 테스트: {topic}")
    print("=" * 60)

    # 1. 칼럼 생성
    print("\n[1] 칼럼 생성 중...")
    from src.engine import generate_column_with_validation

    gen_result = generate_column_with_validation(
        persona_id=persona_id,
        persona_name=persona_name,
        topic=topic,
        model_id="claude-sonnet-4-6",
        temperature=0.7,
    )

    content = gen_result["content"]
    print(f"  생성 완료: {len(content)}자, 시도 {gen_result['attempts']}회")
    print(f"  유사도: passed={gen_result['similarity_check']['passed']}, "
          f"max={gen_result['similarity_check']['max_doc_similarity']}")

    # 제목 추출
    title = topic
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped.lstrip("#").strip()
            break

    print(f"  제목: {title}")
    print(f"  본문 미리보기: {content[:200]}...")

    # 2. 발행
    print("\n[2] 네이버 블로그 발행 중...")
    from src.naver_poster import NaverPoster

    poster = NaverPoster()
    try:
        await poster.connect()
        print("  CDP 연결 완료")

        await poster.login()
        print("  로그인 확인 완료")

        result = await poster.post(
            title=title,
            content=content,
            blog_id=blog_id,
        )

        print(f"\n{'=' * 60}")
        if result.get("success"):
            print(f"✅ 발행 성공!")
            print(f"  URL: {result.get('url', '')}")
        else:
            print(f"❌ 발행 실패: {result.get('error', '')}")
            print(f"  상세: {result}")
        print("=" * 60)

    finally:
        await poster.close()


if __name__ == "__main__":
    asyncio.run(main())
