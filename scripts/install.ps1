# AStock-MCP Windows 安装启动脚本
# 用法: powershell -File install.ps1

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
    Write-Host "[!] 未检测到 Python，请先安装 Python 3.10+" -ForegroundColor Red
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
    # 刷新环境变量
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

# ── 5. 注册 MCP Server（写临时 Python 脚本执行，避免 PS 语法冲突）──
Write-Host "[*] 注册 MCP Server..." -ForegroundColor Yellow

$scriptBlock = @'
import json, os
path = os.path.join(os.environ['USERPROFILE'], '.claude.json')
cfg = {}
if os.path.exists(path):
    with open(path, encoding='utf-8') as f:
        cfg = json.load(f)
cfg.setdefault('mcpServers', {})
cfg['mcpServers']['a-stock-mcp'] = {
    'type': 'stdio',
    'command': 'python',
    'args': ['-m', 'a_stock_mcp'],
    'env': {'ANTHROPIC_API_KEY': '$apiKey'}
}
with open(path, 'w', encoding='utf-8') as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
print('OK')
'@

# 把 API Key 注入到脚本中
$scriptBlock = $scriptBlock.Replace('$apiKey', $apiKey)

$tmpFile = [IO.Path]::GetTempFileName() + ".py"
try {
    $scriptBlock | Out-File $tmpFile -Encoding UTF8
    python $tmpFile
    if ($LASTEXITCODE -ne 0) {
        throw "Python 脚本执行失败"
    }
    Write-Host "[OK] MCP Server 已注册" -ForegroundColor Green
} finally {
    if (Test-Path $tmpFile) { Remove-Item $tmpFile -Force }
}

# ── 6. 创建启动脚本 ──
$launcherPath = [IO.Path]::Combine($ProjectDir, "start.bat")
@"
@echo off
chcp 65001 >nul
cd /d "$ProjectDir"
echo 启动 Claude Code（已集成 AStock-MCP）...
claude --model $model --project "$ProjectDir"
pause
"@ | Out-File $launcherPath -Encoding UTF8

# 也创建一个带有凭据的快捷启动
$launcherWithKeyPath = [IO.Path]::Combine($ProjectDir, "start-with-key.bat")
@"
@echo off
chcp 65001 >nul
cd /d "$ProjectDir"
set ANTHROPIC_API_KEY=$apiKey
echo 启动 Claude Code（已集成 AStock-MCP）...
claude --model $model --project "$ProjectDir"
pause
"@ | Out-File $launcherWithKeyPath -Encoding UTF8

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "   安装完成！" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "启动方式：" -ForegroundColor Cyan
Write-Host "  1. 双击 start.bat（启动后手动输入 API Key）" -ForegroundColor White
Write-Host "  2. 双击 start-with-key.bat（直接启动，已含 Key）" -ForegroundColor White
Write-Host "  3. 或直接运行: claude --project `"$ProjectDir`"" -ForegroundColor White
Write-Host ""
Write-Host "首次启动后，在 Claude Code 中即可使用 a-stock-mcp 的全部工具" -ForegroundColor Green
