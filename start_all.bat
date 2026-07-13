@echo off
chcp 65001 >nul
title CarMate 一键启动
cd /d "%~dp0"

echo ============================================================
echo   CarMate 全服务一键启动
echo ============================================================
echo.

:: ── 0. 首次运行：自动 .env + 依赖 ──
echo [初始化] -------------------------------------------------
if not exist "backend\.env" (
    if exist "backend\.env.example" (
        copy /y "backend\.env.example" "backend\.env" >nul
        echo [✓] 已从 backend\.env.example 创建 backend\.env
    )
) else (
    echo [✓] backend\.env 已存在
)

if not exist "frontend\.env" (
    if exist "frontend\.env.example" (
        copy /y "frontend\.env.example" "frontend\.env" >nul
        echo [✓] 已从 frontend\.env.example 创建 frontend\.env
    )
) else (
    echo [✓] frontend\.env 已存在
)

python -c "import fastapi" >nul 2>&1
if %errorlevel% neq 0 (
    echo [..] 正在安装 Python 依赖...
    pip install -r backend\requirements.txt -q
    if %errorlevel% neq 0 ( echo [✗] pip install 失败 & pause & exit /b 1 )
    echo [✓] Python 依赖已安装
) else (
    echo [✓] Python 依赖就绪
)

if not exist "frontend\node_modules" (
    echo [..] 正在安装前端依赖...
    pushd frontend
    call npm install
    if %errorlevel% neq 0 ( popd & echo [✗] npm install 失败 & pause & exit /b 1 )
    popd
    echo [✓] 前端依赖已安装
) else (
    echo [✓] 前端依赖就绪
)

:: ── 1. 检查环境 ──
echo.
echo [检查环境] -----------------------------------------------
if exist mediamtx\mediamtx.exe ( echo [✓] MediaMTX ) else (
    echo [!] mediamtx\mediamtx.exe 未找到，跳过流媒体服务（登录/识别仍可本地调试）
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

:: 3a. MediaMTX（可选）
if exist mediamtx\mediamtx.exe (
    echo   正在启动 MediaMTX...
    start "MediaMTX" /min mediamtx\mediamtx.exe mediamtx\mediamtx.yml
    timeout /t 2 /nobreak >nul
    echo   [✓] MediaMTX    → rtsp://localhost:8554 ^| HLS :8888 ^| WebRTC :8889
) else (
    echo   [=] 跳过 MediaMTX
)

:: 3b. 后端
echo   正在启动 FastAPI 后端...
start "CarMate-Backend" /min cmd /c "cd /d backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
timeout /t 5 /nobreak >nul
echo   [✓] 后端 API    → http://localhost:8000 ^| 文档 http://localhost:8000/docs

:: 3c. 前端
echo   正在启动前端...
start "CarMate-Frontend" /min cmd /c "cd /d frontend && npm run dev -- --host 0.0.0.0 --port 5173"
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
echo   ├─ 邮箱验证码  真实 SMTP（首次 clone 自动从 .env.example 生成，无需手配）
echo   ├─ 短信验证码  后端终端 [SMS Code]（mock）
echo   └─ 测试账号   admin/123456  user/123456
if exist mediamtx\mediamtx.exe (
    echo   ├─ HLS 播放   http://localhost:8888
    echo   └─ WebRTC     http://localhost:8889
)
echo ============================================================
echo.
pause
