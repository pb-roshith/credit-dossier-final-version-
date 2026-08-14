$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot "backend\venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $projectPython)) {
    Write-Error "Project Python was not found at $projectPython"
    exit 1
}

& $projectPython $PSScriptRoot @args
exit $LASTEXITCODE

