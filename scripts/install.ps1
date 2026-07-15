param(
    [string]$PythonCommand = "",
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

function Test-CompatiblePython {
    param(
        [string]$Executable,
        [string[]]$PrefixArguments
    )

    try {
        $arguments = @($PrefixArguments) + @(
            "-c",
            "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 14) else 1)"
        )
        & $Executable @arguments *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Invoke-CheckedCommand {
    param(
        [string]$Executable,
        [string[]]$Arguments,
        [string]$FailureMessage
    )

    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

$pythonExe = $null
$pythonPrefix = @()
$pythonLabel = $null

if ($PythonCommand.Trim()) {
    $customCommand = $PythonCommand.Trim()
    if (-not (Get-Command $customCommand -ErrorAction SilentlyContinue)) {
        throw "指定的 Python 命令不存在：$customCommand"
    }
    if (-not (Test-CompatiblePython -Executable $customCommand -PrefixArguments @())) {
        throw "指定的 Python 版本不兼容，需要 Python 3.11、3.12 或 3.13：$customCommand"
    }
    $pythonExe = $customCommand
    $pythonLabel = $customCommand
}

if (-not $pythonExe -and (Get-Command "py" -ErrorAction SilentlyContinue)) {
    foreach ($version in @("3.13", "3.12", "3.11")) {
        $prefix = @("-$version")
        if (Test-CompatiblePython -Executable "py" -PrefixArguments $prefix) {
            $pythonExe = "py"
            $pythonPrefix = $prefix
            $pythonLabel = "Python $version via py launcher"
            break
        }
    }
}

if (-not $pythonExe) {
    foreach ($command in @("python", "python3")) {
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
            continue
        }
        if (Test-CompatiblePython -Executable $command -PrefixArguments @()) {
            $pythonExe = $command
            $pythonLabel = "$command on PATH"
            break
        }
    }
}

if (-not $pythonExe) {
    Write-Host ""
    Write-Host "未检测到可用的 Python 3.11、3.12 或 3.13。" -ForegroundColor Red
    Write-Host ""
    Write-Host "你的电脑已经有 Python Launcher，请执行：" -ForegroundColor Yellow
    Write-Host '$env:PYLAUNCHER_ALLOW_INSTALL = "1"' -ForegroundColor Cyan
    Write-Host 'py -3.12 --version' -ForegroundColor Cyan
    Write-Host ""
    Write-Host "安装完成后关闭并重新打开 PowerShell，再执行：" -ForegroundColor Yellow
    Write-Host 'PowerShell -ExecutionPolicy Bypass -File .\scripts\install.ps1' -ForegroundColor Cyan
    exit 2
}

$versionArguments = @($pythonPrefix) + @(
    "-c",
    "import sys; print('.'.join(map(str, sys.version_info[:3])))"
)
$pythonVersion = & $pythonExe @versionArguments
if ($LASTEXITCODE -ne 0) {
    throw "读取 Python 版本失败。"
}
Write-Host "使用 $pythonLabel，版本 $pythonVersion" -ForegroundColor Green

if ($ValidateOnly) {
    Write-Host "安装脚本检测通过。" -ForegroundColor Green
    exit 0
}

if (Test-Path ".venv") {
    Write-Host "删除旧的 .venv..."
    Remove-Item ".venv" -Recurse -Force
}

$venvArguments = @($pythonPrefix) + @("-m", "venv", ".venv")
Invoke-CheckedCommand -Executable $pythonExe -Arguments $venvArguments -FailureMessage "创建 .venv 失败。"

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "虚拟环境创建后未找到 $venvPython。"
}

Invoke-CheckedCommand -Executable $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel") -FailureMessage "升级 pip/setuptools/wheel 失败。"
Invoke-CheckedCommand -Executable $venvPython -Arguments @("-m", "pip", "install", "-r", "requirements.txt", "pytest") -FailureMessage "安装项目依赖失败。"
Invoke-CheckedCommand -Executable $venvPython -Arguments @("-m", "playwright", "install", "chromium") -FailureMessage "安装 Playwright Chromium 失败。"
Invoke-CheckedCommand -Executable $venvPython -Arguments @("-m", "compileall", "-q", "app", "main.py") -FailureMessage "Python 编译检查失败。"
Invoke-CheckedCommand -Executable $venvPython -Arguments @("-m", "pytest") -FailureMessage "项目测试失败。"

Write-Host ""
Write-Host "安装和本地验证完成。" -ForegroundColor Green
Write-Host "启动命令：.\.venv\Scripts\python.exe main.py" -ForegroundColor Cyan
