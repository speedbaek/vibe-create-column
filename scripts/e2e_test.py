"""
E2E 테스트: 칼럼 생성 → 이미지 생성 → 이미지 다운로드 → 네이버 발행
"""
import os
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

# 프로젝트 루트를 path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(override=True)


def main():
    topic = "AI 특허등록"
    persona_id = "yun_ung_chae"
    persona_name = "윤웅채"

    print(f"{'='*60}")
    print(f"E2E 테스트 시작: {topic}")
    print(f"{'='*60}")

    # Step 1: 칼럼 생성 (이미지 포함)
    print("\n[1/6] 칼럼 + 후킹 제목 생성 중...")
    from src.orchestrator import generate_preview
    result = generate_preview(
        topic=topic,
        persona_id=persona_id,
        persona_name=persona_name,
        model_id="claude-sonnet-4-6",
        temperature=0.7,
        include_images=True,
        image_count=4,
        auto_title=True,
        title_count=3,
    )

    if not result.get("success"):
        print("[ERROR] 칼럼 생성 실패")
        return

    print(f"  제목: {result['title']}")
    print(f"  제목 후보: {result.get('title_candidates', [])}")
    print(f"  본문 길이: {result['char_count']}자")
    print(f"  시도 횟수: {result['attempts']}")

    # Step 2: 이미지 생성 결과 확인
    print("\n[2/6] 이미지 생성 결과...")
    image_data = result.get("image_data")
    if image_data:
        body_images = image_data.get("body_images", [])
        print(f"  이미지 수: {len(body_images)}")
        for i, img in enumerate(body_images):
            source = img.get("source", "unknown")
            url = img.get("url", "")[:80]
            print(f"  [{i+1}] source={source}, url={url}...")
    else:
        print("  이미지 없음")

    # Step 3: DALL-E 이미지 로컬 다운로드
    print("\n[3/6] DALL-E 이미지 로컬 다운로드...")
    local_image_paths = []

    if image_data:
        from src.image_handler import download_dalle_images
        images_dir = os.path.join(project_root, "outputs", "images")
        local_paths = download_dalle_images(image_data, output_dir=images_dir)

        for i, path in enumerate(local_paths):
            if path:
                file_size = os.path.getsize(path) / 1024
                print(f"  [{i+1}] {os.path.basename(path)} ({file_size:.0f}KB)")
                local_image_paths.append(path)
            else:
                print(f"  [{i+1}] (실패 또는 플레이스홀더 - 건너뜀)")

        print(f"  다운로드 성공: {len(local_image_paths)}장")
    else:
        print("  이미지 없어서 건너뜀")

    # Step 4: 링크 마커 확인
    raw = result.get("raw_content", "")
    print("\n[4/6] 링크 마커 확인...")
    if "{{LINK:" in raw:
        print("  [WARNING] 링크 마커 미치환 잔존!")
    else:
        print("  링크 마커: 정상 치환됨")

    # Step 5: SE Document Data 미리보기 생성 (CDN URL 없이, 구조 확인용)
    print("\n[5/6] SE Document Data 구조 미리보기...")
    from src.se_converter import build_document_data

    # 미리보기용으로 빈 이미지 URL 사용 (auto_post.py에서 CDN URL로 재빌드)
    preview_doc = build_document_data(
        title=result["title"],
        text=raw,
        image_urls=["placeholder"] * len(local_image_paths) if local_image_paths else None,
    )
    comp_count = len(preview_doc.get("document", {}).get("components", []))
    print(f"  컴포넌트 수: {comp_count}")

    # 컴포넌트 타입 요약
    type_counts = {}
    for comp in preview_doc.get("document", {}).get("components", []):
        ctype = comp.get("@ctype", "unknown")
        type_counts[ctype] = type_counts.get(ctype, 0) + 1
    for ctype, count in type_counts.items():
        print(f"    {ctype}: {count}개")

    # Step 6: _temp_post.json 저장
    print("\n[6/6] _temp_post.json 저장...")
    output_dir = os.path.join(project_root, "outputs")
    os.makedirs(output_dir, exist_ok=True)

    # 제목 직접 지정 (override_title이 있으면 사용)
    override_title = "AI 특허등록, 초심자가 놓치기 쉬운 3가지 주의점"
    final_title = override_title if override_title else result["title"]
    print(f"  최종 제목: {final_title}")

    post_data = {
        "title": final_title,
        "content": raw,
        "local_image_paths": local_image_paths,
        "image_data": image_data,
    }

    temp_path = os.path.join(output_dir, "_temp_post.json")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(post_data, f, ensure_ascii=False, indent=2)

    print(f"  저장 완료: {temp_path}")
    print(f"  로컬 이미지: {len(local_image_paths)}장")

    print(f"\n{'='*60}")
    print("다음 단계: python scripts/auto_post.py 로 발행")
    print(f"  - 이미지 {len(local_image_paths)}장을 네이버 CDN에 업로드")
    print(f"  - CDN URL로 SE Document Data 빌드")
    print(f"  - SmartEditor에 설정 후 발행")
    print(f"{'='*60}")

    # 본문 미리보기
    print(f"\n--- 본문 미리보기 (첫 300자) ---")
    print(raw[:300])
    print("...")


if __name__ == "__main__":
    main()
