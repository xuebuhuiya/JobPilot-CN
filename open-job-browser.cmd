@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-job-browser.ps1" -Show
if errorlevel 1 pause
