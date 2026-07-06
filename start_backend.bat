@echo off
chcp 65001 >nul
title CarMate 一键训练+部署

echo ============================================================
echo   CarMate 交警手势识别 - 一键训练 ^& 部署
echo ============================================================
echo.

cd /d "%~dp0backend"

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

:: 检查依赖
echo [1/4] 检查依赖...
pip install -r requirements.txt -q 2>nul
echo [OK] 依赖就绪

:: 准备数据集 (如果还没准备)
echo.
echo [2/4] 准备数据集...
if not exist "dataset\train" (
    echo [INFO] 首次运行，准备数据集...
    python download_and_prepare.py
    if %errorlevel% neq 0 (
        echo [WARN] 数据集准备遇到问题，将使用占位数据继续
    )
) else (
    echo [OK] 数据集已就绪
)

:: 训练模型 (如果还没有训练)
echo.
echo [3/4] 检查模型...
if not exist "models\carMate_gesture.pt" (
    echo [INFO] 未找到训练好的模型，开始训练...
    echo [INFO] 这可能需要 30 分钟到数小时，取决于你的 GPU
    python train.py --epochs 100 --batch 16
    if %errorlevel% neq 0 (
        echo [WARN] 训练可能未完成，请检查错误信息
    )
) else (
    echo [OK] 模型已就绪: models\carMate_gesture.pt
)

:: 启动推理服务
echo.
echo [4/4] 启动推理服务...
echo [INFO] API 地址: http://localhost:8000
echo [INFO] API 文档: http://localhost:8000/docs
echo.
echo 按 Ctrl+C 停止服务
echo ============================================================
echo.

python server.py

pause
