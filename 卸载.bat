@echo off
chcp 936 >nul
cd /d "%~dp0"
title 卸载 - 网易云音乐客户端回国脚本
echo 正在移除定时任务...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Unregister-ScheduledTask -TaskName NetEaseRefresh -Confirm:$false -ErrorAction SilentlyContinue" >nul 2>&1
if errorlevel 1 (
    echo [!] 任务可能本来就不存在，或需要管理员权限
) else (
    echo [OK] 定时任务已移除
)
echo.
echo 凭据副本仍保留在 %APPDATA%\ne-refresh
echo 如需彻底清除，手动删除该文件夹即可。
echo.
pause