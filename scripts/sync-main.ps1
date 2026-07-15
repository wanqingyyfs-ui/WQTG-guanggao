param(
  [string]$ProjectPath = "D:\编程\WQTG-guanggao"
)
$ErrorActionPreference = "Stop"
Set-Location $ProjectPath
git status --short
git fetch origin main
git switch main
git pull --ff-only origin main
if (Test-Path .venv) { Remove-Item .venv -Recurse -Force }
PowerShell -ExecutionPolicy Bypass -File .\scripts\install.ps1
