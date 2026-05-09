# AStock-MCP Windows 瀹夎鍚姩鑴氭湰
# 鐢ㄦ硶: powershell -File install.ps1

param(
    [string]$ProjectDir = (Get-Location).Path
)

$ErrorActionPreference = "Stop"

Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "   AStock-MCP Windows 涓€閿畨瑁呭惎鍔? -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# 鈹€鈹€ 1. 妫€娴?Python 鈹€鈹€
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "[!] 鏈娴嬪埌 Python锛岃鍏堝畨瑁?Python 3.10+" -ForegroundColor Red
    Write-Host "    涓嬭浇: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}
Write-Host "[OK] Python: $((python --version 2>&1))" -ForegroundColor Green

# 鈹€鈹€ 2. 妫€娴?瀹夎 Claude Code CLI 鈹€鈹€
$claude = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claude) {
    Write-Host "[*] 鏈娴嬪埌 Claude Code CLI锛屾鍦ㄥ畨瑁?.." -ForegroundColor Yellow
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) {
        Write-Host "[!] 璇峰厛瀹夎 Node.js (npm)" -ForegroundColor Red
        Write-Host "    涓嬭浇: https://nodejs.org/" -ForegroundColor Yellow
        exit 1
    }
    npm install -g @anthropic-ai/claude-code
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[!] Claude Code 瀹夎澶辫触" -ForegroundColor Red
        exit 1
    }
    # 鍒锋柊鐜鍙橀噺
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
}
Write-Host "[OK] Claude Code: $((claude --version 2>&1))" -ForegroundColor Green

# 鈹€鈹€ 3. 瀹夎椤圭洰渚濊禆 鈹€鈹€
Write-Host "[*] 瀹夎 Python 渚濊禆..." -ForegroundColor Yellow
pip install -e "$ProjectDir" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] 渚濊禆瀹夎澶辫触" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] 渚濊禆瀹夎瀹屾垚" -ForegroundColor Green

# 鈹€鈹€ 4. 浜や簰杈撳叆 鈹€鈹€
Write-Host ""
Write-Host "--- 閰嶇疆 Claude Code ---" -ForegroundColor Cyan
$apiKey = Read-Host "璇疯緭鍏?Anthropic API Key"
while ([string]::IsNullOrWhiteSpace($apiKey)) {
    $apiKey = Read-Host "API Key 涓嶈兘涓虹┖锛岃閲嶆柊杈撳叆"
}

$model = Read-Host "璇疯緭鍏ユā鍨嬪悕绉?(鐩存帴鍥炶溅榛樿 claude-sonnet-4-6)"
if ([string]::IsNullOrWhiteSpace($model)) { $model = "claude-sonnet-4-6" }

# 鈹€鈹€ 5. 娉ㄥ唽 MCP Server锛堝啓涓存椂 Python 鑴氭湰鎵ц锛岄伩鍏?PS 璇硶鍐茬獊锛夆攢鈹€
Write-Host "[*] 娉ㄥ唽 MCP Server..." -ForegroundColor Yellow

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

# 鎶?API Key 娉ㄥ叆鍒拌剼鏈腑
$scriptBlock = $scriptBlock.Replace('$apiKey', $apiKey)

$tmpFile = [IO.Path]::GetTempFileName() + ".py"
try {
    $scriptBlock | Out-File $tmpFile -Encoding UTF8
    python $tmpFile
    if ($LASTEXITCODE -ne 0) {
        throw "Python 鑴氭湰鎵ц澶辫触"
    }
    Write-Host "[OK] MCP Server 宸叉敞鍐? -ForegroundColor Green
} finally {
    if (Test-Path $tmpFile) { Remove-Item $tmpFile -Force }
}

# 鈹€鈹€ 6. 鍒涘缓鍚姩鑴氭湰 鈹€鈹€
$launcherPath = [IO.Path]::Combine($ProjectDir, "start.bat")
@"
@echo off
chcp 65001 >nul
cd /d "$ProjectDir"
echo 鍚姩 Claude Code锛堝凡闆嗘垚 AStock-MCP锛?..
claude --model $model --project "$ProjectDir"
pause
"@ | Out-File $launcherPath -Encoding UTF8

# 涔熷垱寤轰竴涓甫鏈夊嚟鎹殑蹇嵎鍚姩
$launcherWithKeyPath = [IO.Path]::Combine($ProjectDir, "start-with-key.bat")
@"
@echo off
chcp 65001 >nul
cd /d "$ProjectDir"
set ANTHROPIC_API_KEY=$apiKey
echo 鍚姩 Claude Code锛堝凡闆嗘垚 AStock-MCP锛?..
claude --model $model --project "$ProjectDir"
pause
"@ | Out-File $launcherWithKeyPath -Encoding UTF8

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "   瀹夎瀹屾垚锛? -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "鍚姩鏂瑰紡锛? -ForegroundColor Cyan
Write-Host "  1. 鍙屽嚮 start.bat锛堝惎鍔ㄥ悗鎵嬪姩杈撳叆 API Key锛? -ForegroundColor White
Write-Host "  2. 鍙屽嚮 start-with-key.bat锛堢洿鎺ュ惎鍔紝宸插惈 Key锛? -ForegroundColor White
Write-Host "  3. 鎴栫洿鎺ヨ繍琛? claude --project `"$ProjectDir`"" -ForegroundColor White
Write-Host ""
Write-Host "棣栨鍚姩鍚庯紝鍦?Claude Code 涓嵆鍙娇鐢?a-stock-mcp 鐨勫叏閮ㄥ伐鍏? -ForegroundColor Green
