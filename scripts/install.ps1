$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
if (Test-Path .venv) { Remove-Item .venv -Recurse -Force }
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m compileall -q app main.py
.\.venv\Scripts\python.exe -m pytest
Write-Host "安装和本地验证完成。启动命令：.\.venv\Scripts\python.exe main.py"
