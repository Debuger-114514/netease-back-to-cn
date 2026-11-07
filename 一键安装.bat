@echo off
chcp 936 >nul
setlocal
cd /d "%~dp0"
title 网易云音乐客户端回国脚本 - 安装
echo ============================================
echo   网易云音乐客户端回国脚本 - 一键安装
echo ============================================
echo.

rem ---- 1. 检查 Python ----
where python >nul 2>&1
if errorlevel 1 (
    echo [X] 没找到 Python
    echo.
    echo     请先安装 Python 3.8 及以上版本，安装时务必勾选
    echo     "Add Python to PATH"
    echo.
    echo     下载地址: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)
for /f "delims=" %%v in ('python -V 2^>^&1') do echo [OK] 检测到 %%v

rem ---- 2. 检查客户端是否登录 ----
if not exist "%LOCALAPPDATA%\NetEase\CloudMusic" (
    echo.
    echo [!] 没找到网易云音乐客户端数据目录
    echo     请先安装客户端并登录一次，再回来运行本安装器。
    echo.
    pause
    exit /b 1
)

rem ---- 3. 安装依赖 ----
echo.
echo [1/3] 安装依赖，首次约需 1-2 分钟...
python -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo [X] 依赖安装失败，请检查网络后重试
    pause
    exit /b 1
)
echo [OK] 依赖就绪

rem ---- 4. 注册定时任务 ----
echo.
echo [2/3] 注册定时任务...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_task.ps1"
if errorlevel 1 (
    echo [X] 任务注册失败
    pause
    exit /b 1
)

rem ---- 5. 立刻跑一次 ----
echo.
echo [3/3] 立即刷新一次并验证...
schtasks /Run /TN NetEaseRefresh >nul 2>&1

echo.
echo ============================================
echo   安装完成
echo ============================================
echo.
echo   之后每 6 小时自动运行一次，全程无窗口，不用管它。
echo   首次验证约需 1-2 分钟，可看:
echo     %~dp0logs\run.log
echo.
echo   想立刻手动跑一次: 双击 手动刷新一次.bat
echo   想卸载:           双击 卸载.bat
echo.
pause