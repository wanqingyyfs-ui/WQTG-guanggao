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
        [string[]]$PrefixArguments = @()
    )

    try {
        $checkArguments = @($PrefixArguments) + @(
            "-c",
            "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 14) else 1)"
        )
        & $Executable @checkArguments 1>$null 2>$null
        return ($LASTEXITCODE -eq 0)
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

if ($PythonCommand -and $PythonCommand.Trim()) {
    $customCommand = $PythonCommand.Trim()
    if (-not (Get-Command $customCommand -ErrorAction SilentlyContinue)) {
        throw "The specified Python command was not found: $customCommand"
    }
    if (-not (Test-CompatiblePython -Executable $customCommand)) {
        throw "The specified Python version is not supported. Python 3.11, 3.12, or 3.13 is required: $customCommand"
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
        if (Test-CompatiblePython -Executable $command) {
            $pythonExe = $command
            $pythonLabel = "$command on PATH"
            break
        }
    }
}

if (-not $pythonExe) {
    $localAppData = [Environment]::GetFolderPath("LocalApplicationData")
    $candidatePaths = @(
        (Join-Path $localAppData "Programs\Python\Python313\python.exe"),
        (Join-Path $localAppData "Programs\Python\Python312\python.exe"),
        (Join-Path $localAppData "Programs\Python\Python311\python.exe"),
        "C:\Program Files\Python313\python.exe",
        "C:\Program Files\Python312\python.exe",
        "C:\Program Files\Python311\python.exe"
    )

    foreach ($candidate in $candidatePaths) {
        if ((Test-Path $candidate) -and (Test-CompatiblePython -Executable $candidate)) {
            $pythonExe = $candidate
            $pythonLabel = $candidate
            break
        }
    }
}

if (-not $pythonExe) {
    Write-Host ""
    Write-Host "No supported Python runtime was found." -ForegroundColor Red
    Write-Host "Python 3.11, 3.12, or 3.13 is required." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Install Python 3.12 with:" -ForegroundColor Yellow
    Write-Host "winget install --exact --id Python.Python.3.12" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Then close and reopen PowerShell and run:" -ForegroundColor Yellow
    Write-Host "PowerShell -ExecutionPolicy Bypass -File .\scripts\install.ps1" -ForegroundColor Cyan
    exit 2
}

$versionArguments = @($pythonPrefix) + @(
    "-c",
    "import sys; print('.'.join(map(str, sys.version_info[:3])))"
)
$pythonVersion = & $pythonExe @versionArguments
if ($LASTEXITCODE -ne 0) {
    throw "Failed to read the Python version."
}
Write-Host "Using $pythonLabel, version $pythonVersion" -ForegroundColor Green

if ($ValidateOnly) {
    Write-Host "Install script validation passed." -ForegroundColor Green
    exit 0
}

if (Test-Path ".venv") {
    Write-Host "Removing the existing .venv directory..."
    Remove-Item ".venv" -Recurse -Force
}

$venvArguments = @($pythonPrefix) + @("-m", "venv", ".venv")
Invoke-CheckedCommand -Executable $pythonExe -Arguments $venvArguments -FailureMessage "Failed to create .venv."

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Python was not found in the new virtual environment: $venvPython"
}

Invoke-CheckedCommand -Executable $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel") -FailureMessage "Failed to upgrade pip, setuptools, and wheel."
Invoke-CheckedCommand -Executable $venvPython -Arguments @("-m", "pip", "install", "-r", "requirements.txt", "pytest") -FailureMessage "Failed to install project dependencies."
Invoke-CheckedCommand -Executable $venvPython -Arguments @("-m", "playwright", "install", "chromium") -FailureMessage "Failed to install Playwright Chromium."
Invoke-CheckedCommand -Executable $venvPython -Arguments @("-m", "compileall", "-q", "app", "main.py") -FailureMessage "Python compilation validation failed."
Invoke-CheckedCommand -Executable $venvPython -Arguments @("-m", "pytest") -FailureMessage "Project tests failed."

Write-Host ""
Write-Host "Installation and local validation completed." -ForegroundColor Green
Write-Host "Start command: .\.venv\Scripts\python.exe main.py" -ForegroundColor Cyan
