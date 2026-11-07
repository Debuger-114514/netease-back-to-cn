@echo off
rem silent refresh runner (invoked by Task Scheduler)
cd /d "%~dp0"
set "PYW=pythonw.exe"
if exist "%~dp0_pythonw_path.txt" set /p PYW=<"%~dp0_pythonw_path.txt"
if "%PYW%"=="" set "PYW=pythonw.exe"
"%PYW%" run.py
