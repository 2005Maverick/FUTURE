@echo off
rem Temporary wrapper for the ST01.02.02 Task Scheduler probe; logs to %TEMP%\future_probe.log
cd /d "%~dp0.."
".venv\Scripts\python.exe" "scripts\scheduler_probe.py" > "%TEMP%\future_probe.log" 2>&1
