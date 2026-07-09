@echo off
chcp 65001 >nul
title CarMate 一键启动
cd /d "%~dp0"

echo ============================================================
echo   CarMate 全服务一键启动
echo ============================================================
echo.

:: ── 1. 检查依赖 ──
echo [检查环境] -----------------------------------------------
if exist mediamtx\mediamtx.exe ( echo [✓] MediaMTX ) else (
    echo [✗] mediamtx\mediamtx.exe 未找到! 请从 https://github.com/bluenviron/mediamtx/releases 下载
    pause & exit /b 1
)

where ffmpeg >nul 2>&1
if %errorlevel% equ 0 ( echo [✓] FFmpeg ) else echo [!] FFmpeg 未找到, 推流功能不可用

python --version >nul 2>&1
if %errorlevel% neq 0 ( echo [✗] Python 未安装! & pause & exit /b 1
) else for /f "tokens=*" %%a in ('python --version') do echo [✓] %%a

where node >nul 2>&1
if %errorlevel% neq 0 ( echo [✗] Node.js 未安装! & pause & exit /b 1
) else for /f "tokens=*" %%a in ('node --version') do echo [✓] Node %%a

:: ── 2. 关闭旧进程 ──
echo.
echo [关闭旧进程] --------------------------------------------
taskkill /f /im mediamtx.exe >nul 2>&1 && echo [✓] 已关闭旧 MediaMTX || echo [=] 无旧 MediaMTX

:: 关掉旧的后端
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 "') do (
    if %%a neq 0 (
        taskkill /f /pid %%a >nul 2>&1 && echo [✓] 已关闭旧后端 PID=%%a
    )
)
:: 关掉旧的 vite
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173 "') do (
    if %%a neq 0 (
        taskkill /f /pid %%a >nul 2>&1 && echo [✓] 已关闭旧前端 PID=%%a
    )
)
timeout /t 2 /nobreak >nul

:: ── 3. 启动服务 ──
echo.
echo [启动服务] ------------------------------------------------

:: 3a. MediaMTX
echo   正在启动 MediaMTX...
start "MediaMTX" /min mediamtx\mediamtx.exe mediamtx\mediamtx.yml
timeout /t 2 /nobreak >nul
echo   [✓] MediaMTX    → rtsp://localhost:8554 ^| HLS :8888 ^| WebRTC :8889

:: 3b. 后端
echo   正在启动 FastAPI 后端...
start "CarMate-Backend" /min cmd /c "cd /d backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
timeout /t 5 /nobreak >nul
echo   [✓] 后端 API    → http://localhost:8000 ^| 文档 http://localhost:8000/docs

:: 3c. 前端
echo   正在启动前端...
start "CarMate-Frontend" /min cmd /c "cd /d frontend && npx vite --host 0.0.0.0 --port 5173"
timeout /t 3 /nobreak >nul
echo   [✓] 前端        → http://localhost:5173

:: ── 4. 完成 ──
echo.
echo ============================================================
echo   ✅ 全部已启动!
echo.
echo   ┌─ 前端       http://localhost:5173
echo   ├─ 后端 API   http://localhost:8000
echo   ├─ API 文档   http://localhost:8000/docs
echo   ├─ HLS 播放   http://localhost:8888
echo   └─ WebRTC     http://localhost:8889
echo.
echo   沙盘摄像头: rtsp://10.126.59.120:8554/live/live1 ~ 12
echo   测试推流:   ffmpeg -re -stream_loop -1 -i test_video.mp4 -c copy -f rtsp rtsp://localhost:8554/camera
echo ============================================================
echo.
pause
