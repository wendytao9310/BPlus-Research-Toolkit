$ErrorActionPreference = "Stop"
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$EnvDir = Join-Path $RootDir ".venv-exp"
$Uv = if ($env:UV_BIN) { $env:UV_BIN } else { "uv" }

if (-not (Test-Path (Join-Path $EnvDir "Scripts\python.exe"))) {
    & $Uv venv --python 3.11 $EnvDir
    Write-Host "[PASS] Created $EnvDir"
} else {
    Write-Host "[PASS] Reusing existing $EnvDir"
}
& $Uv pip install --python (Join-Path $EnvDir "Scripts\python.exe") -r (Join-Path $RootDir "requirements-lock.txt")
& (Join-Path $EnvDir "Scripts\python.exe") (Join-Path $RootDir "scripts\check_environment.py") --profile experiment

