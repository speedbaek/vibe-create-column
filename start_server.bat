@echo off

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHON=C:\Users\TEHERAN\AppData\Local\Programs\Python\Python311\python.exe
set NGROK=C:\Users\TEHERAN\AppData\Local\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe

cd /d "C:\Users\TEHERAN\vibe-coding\vibe-create-column"

start /min "Streamlit" "%PYTHON%" -m streamlit run app.py --server.port 8502 --server.headless true

ping 127.0.0.1 -n 11 >nul

start /min "Ngrok" "%NGROK%" http 8502 --domain=harmony-porky-tory.ngrok-free.dev
