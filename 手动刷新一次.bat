@echo off
chcp 936 >nul
cd /d "%~dp0"
echo ============================================
echo   手动刷新一次（关掉窗口即结束）
echo ============================================
echo.
python run.py
echo.
echo 完整日志: %~dp0logsun.log
pause
