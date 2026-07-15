param(
    [string]$PythonCommand = "",
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

function Test-CompatiblePython {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [string[]]$PrefixArguments = @()
    )

    try {
        & $Command @PrefixArguments -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 14) else 1)" *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [string[]]$Arguments = @(),
        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

$candidates = @()
if ($PythonCommand.Trim()) {
    $candidates += [pscustomobject]@{
        Command = $PythonCommand.Trim()
        PrefixArguments = @()
        Label = $PythonCommand.Trim()
    }
}

$candidates += @(
    [pscustomobject]@{ Command = "py"; PrefixArguments = @("-3.13"); Label = "Python 3.13 via py launcher" },
    [pscustomobject]@{ Command = "py"; PrefixArguments = @("-3.12"); Label = "Python 3.12 via py launcher" },
    [pscustomobject]@{ Command = "py"; PrefixArguments = @("-3.11"); Label = "Python 3.11 via py launcher" },
    [pscustomobject]@{ Command = "python"; PrefixArguments = @(); Label = "python on PATH" },
    [pscustomobject]@{ Command = "python3"; PrefixArguments = @(); Label = "python3 on PATH" }
)

$localPythonRoot = Join-Path $env:LOCALAPPDATA "Programs\Python"
if (Test-Path $localPythonRoot) {
    Get-ChildItem -Path $localPythonRoot -Filter "python.exe" -File -Recurse -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        ForEach-Object {
            $candidates += [pscustomobject]@{
                Command = $_.FullName
                PrefixArguments = @()
                Label = $_.FullName
            }
        }
}

$selected = $null
foreach ($candidate in $candidates) {
    if (-not (Get-Command $candidate.Command -ErrorAction SilentlyContinue)) {
        continue
    }
    if (Test-CompatiblePython -Command $candidate.Command -PrefixArguments $candidate.PrefixArguments) {
        $selected = $candidate
        break
    }
}

if ($null -eq $selected) {
    Write-Host ""
    Write-Host "未检测到可用的 Python 3.11、3.12 或 3.13。" -ForegroundColor Red
    Write-Host ""
    Write-Host "你的电脑已经有 Python Launcher，可以执行下面两行安装 Python 3.12：" -ForegroundColor Yellow
    Write-Host '$env:PYLAUNCHER_ALLOW_INSTALL = "1"' -ForegroundColor Cyan
    Write-Host 'py -3.12 --version' -ForegroundColor Cyan
    Write-Host ""
    Write-Host "安装完成后关闭并重新打开 PowerShell，再重新运行：" -ForegroundColor Yellow
    Write-Host 'PowerShell -ExecutionPolicy Bypass -File .\scripts\install.ps1' -ForegroundColor Cyan
    exit 2
}

$pythonExe = [string]$selected.Command
$pythonPrefix = [string[]]$selected.PrefixArguments
$versionArgs = @($pythonPrefix) + @("-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))")
$pythonVersion = & $pythonExe @versionArgs
if ($LASTEXITCODE -ne 0) {
    throw "读取 Python 版本失败。"
}
Write-Host "使用 $($selected.Label)，版本 $pythonVersion" -ForegroundColor Green

if ($ValidateOnly) {
    Write-Host "安装脚本检测通过。" -ForegroundColor Green
    exit 0
}

if (Test-Path ".venv") {
    Write-Host "删除旧的 .venv..."
    Remove-Item ".venv" -Recurse -Force
}

$venvArguments = @($pythonPrefix) + @("-m", "venv", ".venv")
Invoke-CheckedCommand -Command $pythonExe -Arguments $venvArguments -FailureMessage "创建 .venv 失败。"

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "虚拟环境创建后未找到 $venvPython。"
}

Invoke-CheckedCommand -Command $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel") -FailureMessage "升级 pip/setuptools/wheel 失败。"
Invoke-CheckedCommand -Command $venvPython -Arguments @("-m", "pip", "install", "-r", "requirements.txt", "pytest") -FailureMessage "安装项目依赖失败。"
Invoke-CheckedCommand -Command $venvPython -Arguments @("-m", "playwright", "install", "chromium") -FailureMessage "安装 Playwright Chromium 失败。"
Invoke-CheckedCommand -Command $venvPython -Arguments @("-m", "compileall", "-q", "app", "main.py") -FailureMessage "Python 编译检查失败。"
Invoke-CheckedCommand -Command $venvPython -Arguments @("-m", "pytest") -FailureMessage "项目测试失败。"

Write-Host ""
Write-Host "安装和本地验证完成。" -ForegroundColor Green
Write-Host "启动命令：.\.venv\Scripts\python.exe main.py" -ForegroundColor Cyan
