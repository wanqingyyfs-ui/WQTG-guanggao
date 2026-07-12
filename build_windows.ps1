$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host "[1/5] 检查 Python..."
python --version

Write-Host "[2/5] 安装运行和打包依赖..."
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python -m pip install -r requirements-build.txt

Write-Host "[3/5] 按 Playwright 官方 PyInstaller 方式安装内置 Chromium..."
$env:PLAYWRIGHT_BROWSERS_PATH = "0"
python -m playwright install chromium

Write-Host "[4/5] 清理旧构建并打包..."
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
python -m PyInstaller --clean --noconfirm "万青TG群发任务.spec"

Write-Host "[5/5] 完成。EXE："
$ExePath = Join-Path $ProjectRoot "dist\万青TG群发任务.exe"
if (-not (Test-Path $ExePath)) {
    throw "未找到打包结果：$ExePath"
}
Get-Item $ExePath | Format-List FullName, Length, LastWriteTime
