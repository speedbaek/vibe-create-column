"""
새 환경 초기 셋업 스크립트
깃허브에 올라가지 않는 필수 파일들을 구글드라이브에서 자동 다운로드합니다.

사용법:
    python scripts/setup.py

필요한 파일:
    1. .env (API 키, 네이버 계정)
    2. config/google_service_account.json (구글시트 연동)

브라우저 프로필(로그인 세션)은 기기별로 다르므로,
새 환경에서 첫 발행 시 자동으로 로그인 과정을 거칩니다.
"""

import os
import sys
import subprocess

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 구글드라이브 파일 ID 설정
# 공유 링크에서 ID 추출: https://drive.google.com/file/d/{FILE_ID}/view
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GDRIVE_FILES = {
    ".env": {
        "file_id": "",  # ← 구글드라이브 업로드 후 ID 입력
        "desc": "API 키 + 네이버 계정 정보",
    },
    "config/google_service_account.json": {
        "file_id": "",  # ← 구글드라이브 업로드 후 ID 입력
        "desc": "구글시트 서비스 계정 키",
    },
}


def ensure_gdown():
    """gdown 라이브러리 설치 확인"""
    try:
        import gdown
        return True
    except ImportError:
        print("gdown 설치 중...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "gdown", "-q"])
        return True


def download_from_gdrive(file_id, output_path):
    """구글드라이브에서 파일 다운로드"""
    import gdown
    url = f"https://drive.google.com/uc?id={file_id}"
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    gdown.download(url, output_path, quiet=False)
    return os.path.exists(output_path)


def check_existing_files():
    """이미 존재하는 파일 확인"""
    status = {}
    for filepath in GDRIVE_FILES:
        status[filepath] = os.path.exists(filepath)
    return status


def install_dependencies():
    """requirements.txt 의존성 설치"""
    req_file = "requirements.txt"
    if os.path.exists(req_file):
        print("\n📦 의존성 패키지 설치 중...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_file, "-q"])
        print("✅ 의존성 설치 완료")

    # Playwright 브라우저 설치
    print("\n🌐 Playwright 브라우저 설치 중...")
    subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
    print("✅ Playwright 브라우저 설치 완료")


def main():
    # 프로젝트 루트로 이동
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)

    print("=" * 50)
    print("🚀 Vibe Create Column - 환경 셋업")
    print("=" * 50)

    # 1. 파일 상태 확인
    status = check_existing_files()
    print("\n📋 필수 파일 상태:")
    all_exist = True
    for filepath, exists in status.items():
        desc = GDRIVE_FILES[filepath]["desc"]
        icon = "✅" if exists else "❌"
        print(f"  {icon} {filepath} — {desc}")
        if not exists:
            all_exist = False

    if all_exist:
        print("\n✅ 모든 필수 파일이 이미 존재합니다!")
    else:
        # 2. 구글드라이브에서 다운로드
        missing_with_id = {
            fp: info for fp, info in GDRIVE_FILES.items()
            if not status[fp] and info["file_id"]
        }
        missing_without_id = {
            fp: info for fp, info in GDRIVE_FILES.items()
            if not status[fp] and not info["file_id"]
        }

        if missing_with_id:
            print("\n📥 구글드라이브에서 다운로드 중...")
            ensure_gdown()
            for filepath, info in missing_with_id.items():
                print(f"\n  다운로드: {filepath}")
                try:
                    if download_from_gdrive(info["file_id"], filepath):
                        print(f"  ✅ {filepath} 다운로드 완료")
                    else:
                        print(f"  ❌ {filepath} 다운로드 실패")
                except Exception as e:
                    print(f"  ❌ {filepath} 다운로드 오류: {e}")

        if missing_without_id:
            print("\n⚠️  구글드라이브 ID가 설정되지 않은 파일:")
            for filepath, info in missing_without_id.items():
                print(f"  - {filepath}: {info['desc']}")
            print("\n  → scripts/setup.py의 GDRIVE_FILES에 file_id를 입력하세요.")
            print("  → 또는 이 PC에서 해당 파일을 직접 복사하세요.")

    # 3. 의존성 설치
    ans = input("\n📦 의존성 패키지를 설치할까요? (y/n): ").strip().lower()
    if ans == "y":
        install_dependencies()

    # 4. 최종 확인
    print("\n" + "=" * 50)
    print("📌 셋업 완료 후 확인사항:")
    print("=" * 50)
    print("  1. .env 파일에 API 키가 올바른지 확인")
    print("  2. 첫 발행 시 네이버 로그인 팝업 → 수동 로그인 1회 필요")
    print("  3. 실행: python -m streamlit run app.py")
    print()


if __name__ == "__main__":
    main()
