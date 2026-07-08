@echo off
chcp 65001 >nul
title 鸿图建材获客工具
echo ========================================
echo    鸿图建材获客工具 - 启动中...
echo ========================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10 以上版本
    echo 下载地址：https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"
    echo.
    pause
    exit /b
)

:: 检查 uv，未安装则自动安装
where uv >nul 2>&1
if errorlevel 1 (
    echo [提示] 未检测到 uv，正在自动安装...
    pip install uv -q
    if errorlevel 1 (
        echo [错误] uv 安装失败，请手动执行：pip install uv
        echo.
        pause
        exit /b
    )
)

:: 创建虚拟环境
echo [1/3] 创建虚拟环境...
uv venv

:: 安装依赖
echo [2/3] 安装依赖...
uv pip install -r requirements.txt -q
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络连接后重试
    echo.
    pause
    exit /b
)

:: 启动服务
echo [3/3] 启动服务...
echo.
echo ========================================
echo    服务已启动！
echo.
echo    本机访问：http://localhost:5000
echo    局域网访问：http://本机IP:5000
echo    （查看本机IP：打开cmd输入 ipconfig）
echo.
echo    首次局域网访问如被拦截，请允许
echo    Windows防火墙对 Python 的访问权限
echo.
echo    按 Ctrl+C 停止服务
echo ========================================
echo.

uv run python run.py

echo.
echo 服务已停止。
pause
