# AStock-MCP Windows 安装启动脚本
# 用法: 双击 install.bat 或 powershell -File scripts\install.ps1
# 说明: 不修改 ~/.claude.json，通过 --mcp-config 命令行方式注入 MCP

param(
    [string]$ProjectDir = (Get-Location).Path
)

$ErrorActionPreference = "Stop"

Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "   AStock-MCP Windows 一键安装启动" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. 检测 Python ──
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "[!] 请先安装 Python 3.10+" -ForegroundColor Red
    Write-Host "    下载: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}
Write-Host "[OK] Python: $((python --version 2>&1))" -ForegroundColor Green

# ── 2. 检测/安装 Claude Code CLI ──
$claude = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claude) {
    Write-Host "[*] 未检测到 Claude Code CLI，正在安装..." -ForegroundColor Yellow
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) {
        Write-Host "[!] 请先安装 Node.js (npm)" -ForegroundColor Red
        Write-Host "    下载: https://nodejs.org/" -ForegroundColor Yellow
        exit 1
    }
    npm install -g @anthropic-ai/claude-code
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[!] Claude Code 安装失败" -ForegroundColor Red
        exit 1
    }
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
}
Write-Host "[OK] Claude Code: $((claude --version 2>&1))" -ForegroundColor Green

# ── 3. 安装项目依赖 ──
Write-Host "[*] 安装 Python 依赖..." -ForegroundColor Yellow
pip install -e "$ProjectDir" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] 依赖安装失败" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] 依赖安装完成" -ForegroundColor Green

# ── 4. 交互输入 ──
Write-Host ""
Write-Host "--- 配置 Claude Code ---" -ForegroundColor Cyan
$apiKey = Read-Host "请输入 Anthropic API Key"
while ([string]::IsNullOrWhiteSpace($apiKey)) {
    $apiKey = Read-Host "API Key 不能为空，请重新输入"
}

$model = Read-Host "请输入模型名称 (直接回车默认 claude-sonnet-4-6)"
if ([string]::IsNullOrWhiteSpace($model)) { $model = "claude-sonnet-4-6" }

# ── 5. 创建启动脚本（不修改 ~/.claude.json，用 --mcp-config 传入）──
Write-Host "[*] 创建启动脚本..." -ForegroundColor Yellow

$mcpCfg = Resolve-Path "$ProjectDir\mcp-config.json"

@"
@echo off
cd /d "$ProjectDir"
echo [AStock-MCP] 启动 Claude Code ...
claude --model $model --mcp-config "$mcpCfg" --project "$ProjectDir"
pause
"@ | Out-File "$ProjectDir\start.bat" -Encoding UTF8

@"
@echo off
cd /d "$ProjectDir"
set ANTHROPIC_API_KEY=$apiKey
echo [AStock-MCP] 启动 Claude Code ...
claude --model $model --mcp-config "$mcpCfg" --project "$ProjectDir"
pause
"@ | Out-File "$ProjectDir\start-with-key.bat" -Encoding UTF8

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "   安装完成！" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "启动方式（任选其一）：" -ForegroundColor Cyan
Write-Host "  1. 双击 start-with-key.bat（推荐，已含 Key）" -ForegroundColor White
Write-Host "  2. 双击 start.bat（需先设置 ANTHROPIC_API_KEY 环境变量）" -ForegroundColor White
Write-Host "  3. 手动运行: claude --mcp-config mcp-config.json --project `"$ProjectDir`"" -ForegroundColor White
Write-Host ""
Write-Host "注：MCP 配置通过 --mcp-config 从命令行传入，不会修改你的 ~/.claude.json" -ForegroundColor Green
