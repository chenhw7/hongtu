@echo off
chcp 65001 >nul
title 鸿图建材获客工具 - 打包构建

echo ========================================
echo    鸿图建材获客工具 - 打包构建
echo ========================================
echo.

:: 检查uv是否可用
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到uv，请先安装：pip install uv
    pause
    exit /b 1
)

:: 安装打包依赖
echo [1/5] 安装打包依赖...
uv pip install pyinstaller pystray Pillow

:: 确保Playwright chromium已下载
echo [2/5] 检查Playwright浏览器...
uv run python -m playwright install chromium

:: 生成应用图标
echo [3/5] 生成应用图标...
uv run python generate_icon.py

:: 执行打包
echo [4/6] 执行PyInstaller打包（可能需要几分钟）...
uv run pyinstaller hongtu.spec --distpath ./dist --workpath ./build --noconfirm

:: 验证浏览器文件已打包
echo [5/6] 验证Playwright浏览器...
if not exist "dist\hongtu\browsers" (
    echo [警告] Playwright浏览器目录未打包，尝试手动复制...
    xcopy "%LOCALAPPDATA%\ms-playwright" "dist\hongtu\browsers\" /E /I /Q
)

:: 创建必要的空目录
echo [6/6] 创建数据目录...
if not exist "dist\hongtu\instance" mkdir "dist\hongtu\instance"
if not exist "dist\hongtu\instance\attachments" mkdir "dist\hongtu\instance\attachments"
if not exist "dist\hongtu\instance\snapshots" mkdir "dist\hongtu\instance\snapshots"
if not exist "dist\hongtu\logs" mkdir "dist\hongtu\logs"

echo.
echo ========================================
echo    打包完成！
echo    输出目录: dist\hongtu\
echo    启动程序: dist\hongtu\hongtu.exe
echo ========================================
echo.
pause
