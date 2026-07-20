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

:: 创建虚拟环境（已存在则跳过）
if exist ".venv\Scripts\python.exe" (
    echo [1/4] 检测到虚拟环境，跳过创建
) else (
    echo [1/4] 创建虚拟环境...
    uv venv
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败
        echo.
        pause
        exit /b
    )
)

:: 安装依赖（仅当 requirements.txt 有更新时才重新安装）
set "REQ_HASH_FILE=.venv\requirements.hash"
for /f %%h in ('certutil -hashfile requirements.txt SHA256 ^| findstr /v "hash CertUtil"') do set "REQ_HASH=%%h"

set "OLD_HASH="
if exist "%REQ_HASH_FILE%" set /p OLD_HASH=<"%REQ_HASH_FILE%"

if "%REQ_HASH%"=="%OLD_HASH%" (
    echo [2/4] 依赖未变化，跳过安装
) else (
    echo [2/4] 安装依赖...
    uv pip install -r requirements.txt -q
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络连接后重试
        echo.
        pause
        exit /b
    )
    >"%REQ_HASH_FILE%" echo %REQ_HASH%
)

:: 安装 Playwright 浏览器（仅当版本变化时重新下载）
set "PW_VER_FILE=.venv\playwright_browser.ver"
for /f "tokens=2 delims==" %%v in ('.venv\Scripts\python.exe -c "import playwright; print(playwright.__version__)" 2^>nul') do set "PW_VER=%%v"
if not defined PW_VER (
    for /f %%v in ('.venv\Scripts\python.exe -c "import playwright; print(playwright.__version__)" 2^>nul') do set "PW_VER=%%v"
)

set "OLD_PW_VER="
if exist "%PW_VER_FILE%" set /p OLD_PW_VER=<"%PW_VER_FILE%"

if "%PW_VER%"=="%OLD_PW_VER%" (
    echo [3/4] Playwright 浏览器未变化，跳过下载
) else (
    echo [3/4] 安装 Playwright 浏览器...
    .venv\Scripts\python.exe -m playwright install chromium
    if errorlevel 1 (
        echo [警告] Playwright 浏览器下载失败，爬虫功能可能不可用
        echo        请手动执行：.venv\Scripts\python.exe -m playwright install chromium
    ) else (
        >"%PW_VER_FILE%" echo %PW_VER%
    )
)

:: 启动服务
echo [4/4] 启动服务...
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
