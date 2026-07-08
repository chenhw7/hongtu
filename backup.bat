@echo off
chcp 65001 >nul
echo ========================================
echo    鸿图建材获客工具 - 数据备份
echo ========================================
echo.

set backup_dir=backups
if not exist %backup_dir% mkdir %backup_dir%

:: 生成时间戳（补零处理，避免空格）
set d=%date:~0,4%%date:~5,2%%date:~8,2%
set t=%time:~0,2%%time:~3,2%
set t=%t: =0%
set timestamp=%d%_%t%

:: 复制数据库文件（含WAL模式相关文件）
copy instance\hongtu.db %backup_dir%\hongtu_%timestamp%.db >nul 2>&1
copy instance\hongtu.db-wal %backup_dir%\hongtu_%timestamp%.db-wal >nul 2>&1
copy instance\hongtu.db-shm %backup_dir%\hongtu_%timestamp%.db-shm >nul 2>&1

echo 备份完成！文件保存在：
echo   %backup_dir%\hongtu_%timestamp%.db
echo.
echo 提示：建议定期将 backups 文件夹复制到U盘或其他位置。
echo.
pause
