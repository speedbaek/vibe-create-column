@echo off
chcp 65001 >nul
echo ========================================
echo   블로그 자동화 시스템 - 초기 설정
echo   특허법인 테헤란
echo ========================================
echo.

echo [1/3] Python 패키지 설치 중...
pip install -r requirements.txt
echo.

echo [2/3] 필요 디렉토리 생성...
if not exist "outputs" mkdir outputs
if not exist "outputs\images" mkdir outputs\images
if not exist "outputs\previews" mkdir outputs\previews
if not exist "outputs\uploads" mkdir outputs\uploads
if not exist "outputs\history" mkdir outputs\history
if not exist "config\fonts" mkdir config\fonts
echo.

echo [3/3] .env 파일 확인...
if exist ".env" (
    echo .env 파일 확인 완료
) else (
    echo .env 파일이 없습니다!
    echo .env.example을 참고하여 .env 파일을 생성해주세요.
)
echo.

echo ========================================
echo   설정 완료! 아래 명령어로 실행하세요:
echo   streamlit run app.py
echo ========================================
pause
