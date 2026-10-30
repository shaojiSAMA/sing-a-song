@echo off
chcp 65001 >nul
title 唱练 · 本地练歌工作室
cd /d "%~dp0"

rem 3 秒后用默认浏览器打开页面（等后端起来）
start "" /b cmd /c "ping 127.0.0.1 -n 4 >nul & start """" http://127.0.0.1:8178"

rem 固定使用项目自带虚拟环境，避免误用其他 Python
"venv\Scripts\python.exe" server\app.py

echo.
echo 后端已退出，按任意键关闭窗口。
pause >nul
