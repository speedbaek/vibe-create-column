"""
새 환경 초기 셋업 스크립트
구글드라이브 동기화 폴더 또는 웹 다운로드로 필수 파일을 자동 배치합니다.

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
import shutil
import subprocess
import glob

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 구글드라이브 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 구글드라이브 동기화 폴더 내 비밀 파일 경로 (상대경로: 사용자 홈 기준)
GDRIVE_SECRET_DIR = os.path.join(
    "내 드라이브", "03_Lab", "01_Ai_autotest", "vibe-auto-blog-patent"
)

# 구글드라이브 웹 다운로드용 파일 ID (동기화 폴더 없을 때 fallback)
GDRIVE_FILE_IDS = {
    ".env": "1cDSMI1YpzbFhuTgEojcyAbdw8rHW4KBx",
    "google_service_account.json": "1gBq5xXNCyvQJJ7rxTj9jtJolEoMtIb_2",
}

# 파일 복사 매핑: {구글드라이브 파일명: 프로젝트 내 목적지}
FILE_MAP = {
    ".env": ".env",
    "google_service_account.json": os.path.join("config", "google_service_account.json"),
}


def find_gdrive_local_path():
    """구글드라이브 동기화 폴더 자동 탐색"""
    home = os.path.expanduser("~")

    # 가능한 구글드라이브 루트 경로들
    candidates = [
        os.path.join(home, GDRIVE_SECRET_DIR),                          # Windows 기본
        os.path.join(home, "Google Drive", GDRIVE_SECRET_DIR),          # 영문 설치
        os.path.join(home, "My Drive", GDRIVE_SECRET_DIR),              # 영문 대안
        os.path.join(home, "Google 드라이브", GDRIVE_SECRET_DIR),       # 한글 대안
    ]

    # G: 드라이브 등 별도 마운트 확인 (Windows)
    if sys.platform == "win32":
        for drive_letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            candidates.append(os.path.join(f"{drive_letter}:", os.sep, GDRIVE_SECRET_DIR))

    for path in candidates:
        if os.path.isdir(path):
            return path

    return None


def copy_from_gdrive_local(gdrive_path):
    """구글드라이브 로컬 동기화 폴더에서 파일 복사"""
    results = {}
    for src_name, dest_path in FILE_MAP.items():
        src_path = os.path.join(gdrive_path, src_name)
        if os.path.exists(src_path):
            os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
            shutil.copy2(src_path, dest_path)
            results[dest_path] = True
            print(f"  ✅ {src_name} → {dest_path}")
        else:
            results[dest_path] = False
            print(f"  ❌ {src_name} 없음 ({src_path})")
    return results


def download_from_gdrive_web(file_id, output_path):
    """구글드라이브 웹에서 파일 다운로드 (gdown)"""
    try:
        import gdown
    except ImportError:
        print("  gdown 설치 중...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "gdown", "-q"])
        import gdown

    url = f"https://drive.google.com/uc?id={file_id}"
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    gdown.download(url, output_path, quiet=False)
    return os.path.exists(output_path)


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

    # 1. 이미 존재하는 파일 확인
    all_exist = True
    print("\n📋 필수 파일 상태:")
    for dest_path in FILE_MAP.values():
        exists = os.path.exists(dest_path)
        icon = "✅" if exists else "❌"
        print(f"  {icon} {dest_path}")
        if not exists:
            all_exist = False

    if all_exist:
        print("\n✅ 모든 필수 파일이 이미 존재합니다!")
    else:
        # 2. 구글드라이브 로컬 동기화 폴더 탐색
        gdrive_path = find_gdrive_local_path()

        if gdrive_path:
            print(f"\n📂 구글드라이브 동기화 폴더 발견: {gdrive_path}")
            print("  로컬 복사 중...")
            copy_from_gdrive_local(gdrive_path)
        else:
            print("\n⚠️  구글드라이브 동기화 폴더를 찾을 수 없습니다.")
            print("  웹에서 다운로드를 시도합니다...")

            for src_name, dest_path in FILE_MAP.items():
                if os.path.exists(dest_path):
                    continue
                file_id = GDRIVE_FILE_IDS.get(src_name, "")
                if file_id:
                    print(f"\n  📥 다운로드: {src_name}")
                    try:
                        if download_from_gdrive_web(file_id, dest_path):
                            print(f"  ✅ {dest_path} 다운로드 완료")
                        else:
                            print(f"  ❌ {dest_path} 다운로드 실패")
                    except Exception as e:
                        print(f"  ❌ {dest_path} 오류: {e}")
                else:
                    print(f"  ❌ {src_name}: 파일 ID 없음")

    # 3. 최종 파일 확인
    print("\n📋 최종 확인:")
    ok = True
    for dest_path in FILE_MAP.values():
        exists = os.path.exists(dest_path)
        icon = "✅" if exists else "❌"
        print(f"  {icon} {dest_path}")
        if not exists:
            ok = False

    # 4. 의존성 설치
    ans = input("\n📦 의존성 패키지를 설치할까요? (y/n): ").strip().lower()
    if ans == "y":
        install_dependencies()

    # 5. 완료
    print("\n" + "=" * 50)
    if ok:
        print("✅ 셋업 완료!")
    else:
        print("⚠️  일부 파일 누락 — 수동으로 복사해주세요.")
    print("=" * 50)
    print("  1. 첫 발행 시 네이버 로그인 → 수동 로그인 1회 필요")
    print("  2. 실행: python -m streamlit run app.py")
    print()


if __name__ == "__main__":
    main()
