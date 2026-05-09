@echo off
title AStock-MCP 瀹夎鍚姩
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1"
pause
