# AStock-MCP Windows install script
# Usage: double-click install.bat or powershell -File scripts\install.ps1
# Note: Does NOT modify ~/.claude.json, uses --mcp-config flag instead

param(
    [string]$ProjectDir = (Get-Location).Path
)

$ErrorActionPreference = "Stop"

# Helper: run native command without PS5.1 error-stream noise
function Run-Native {
    param([scriptblock]$Cmd)
    $oldPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $Cmd
    $global:LastNativeExit = $LASTEXITCODE
    $ErrorActionPreference = $oldPref
}

Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "   AStock-MCP Windows Setup" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# -- 1. Detect Python --
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "[!] Please install Python 3.10+" -ForegroundColor Red
    Write-Host "    Download: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}
$pyVer = Run-Native { python --version 2>&1 }
Write-Host "[OK] Python: $pyVer" -ForegroundColor Green

# -- 2. Detect/Install Claude Code CLI --
$claude = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claude) {
    Write-Host "[*] Claude Code CLI not found, installing..." -ForegroundColor Yellow
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) {
        Write-Host "[!] Please install Node.js (npm)" -ForegroundColor Red
        Write-Host "    Download: https://nodejs.org/" -ForegroundColor Yellow
        exit 1
    }
    Run-Native { npm install -g @anthropic-ai/claude-code 2>&1 | Out-Null }
    if ($global:LastNativeExit -ne 0) {
        Write-Host "[!] Claude Code install failed" -ForegroundColor Red
        exit 1
    }
    # Refresh PATH
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $env:Path = $userPath + ";" + $machinePath
}
$claudeVer = Run-Native { claude --version 2>&1 }
Write-Host "[OK] Claude Code: $claudeVer" -ForegroundColor Green

# -- 3. Install Python deps --
Write-Host "[*] Installing Python dependencies..." -ForegroundColor Yellow
Run-Native { pip install -e "$ProjectDir" 2>&1 | Out-Null }
if ($global:LastNativeExit -ne 0) {
    Write-Host "[!] Dependency install failed" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Dependencies installed" -ForegroundColor Green

# -- 4. Interactive input --
Write-Host ""
Write-Host "--- Claude Code Configuration ---" -ForegroundColor Cyan
$apiKey = Read-Host "Enter Anthropic API Key"
while ([string]::IsNullOrWhiteSpace($apiKey)) {
    $apiKey = Read-Host "API Key cannot be empty, please re-enter"
}

$model = Read-Host "Enter model name (Enter for default: claude-sonnet-4-6)"
if ([string]::IsNullOrWhiteSpace($model)) { $model = "claude-sonnet-4-6" }

# -- 5. Create launch scripts --
Write-Host "[*] Creating launch scripts..." -ForegroundColor Yellow

$mcpCfg = "$ProjectDir\mcp-config.json"

function Write-BatFile {
    param([string]$Path, [string[]]$Lines)
    $content = $Lines -join "`r`n"
    [System.IO.File]::WriteAllText($Path, $content + "`r`n", [System.Text.Encoding]::Default)
}

$startBat = @()
$startBat += "@echo off"
$startBat += 'cd /d "' + $ProjectDir + '"'
$startBat += "echo [AStock-MCP] Starting Claude Code ..."
$startBat += 'claude --model ' + $model + ' --mcp-config "' + $mcpCfg + '" --project "' + $ProjectDir + '"'
$startBat += "pause"

Write-BatFile -Path "$ProjectDir\start.bat" -Lines $startBat

$startWithKeyBat = @()
$startWithKeyBat += "@echo off"
$startWithKeyBat += 'cd /d "' + $ProjectDir + '"'
$startWithKeyBat += "set ANTHROPIC_API_KEY=" + $apiKey
$startWithKeyBat += "echo [AStock-MCP] Starting Claude Code ..."
$startWithKeyBat += 'claude --model ' + $model + ' --mcp-config "' + $mcpCfg + '" --project "' + $ProjectDir + '"'
$startWithKeyBat += "pause"

Write-BatFile -Path "$ProjectDir\start-with-key.bat" -Lines $startWithKeyBat

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "   Install Complete!" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Launch methods:" -ForegroundColor Cyan
Write-Host "  1. Double-click start-with-key.bat (recommended, has API key)" -ForegroundColor White
Write-Host "  2. Double-click start.bat (set ANTHROPIC_API_KEY first)" -ForegroundColor White
Write-Host "  3. Manual: claude --mcp-config mcp-config.json --project """$ProjectDir"""" -ForegroundColor White
Write-Host ""
Write-Host "Note: MCP config via --mcp-config flag, your ~/.claude.json is untouched." -ForegroundColor Green