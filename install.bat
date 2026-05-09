@echo off
chcp 65001 >nul
title AStock-MCP 安装启动
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1"
pause
