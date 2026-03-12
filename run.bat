@echo off
chcp 65001 >nul
echo ========================================
echo   블로그 자동화 시스템 실행
echo   http://localhost:8501
echo ========================================
echo.
streamlit run app.py --server.port 8501
pause
