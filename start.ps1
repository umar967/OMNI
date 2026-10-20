$ErrorActionPreference = 'Stop'
$repoRoot = $PSScriptRoot
$pythonPath = Join-Path $repoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'First run: python -m venv .venv; then .\.venv\Scripts\python.exe -m pip install -r requirements.txt'
}
Push-Location -LiteralPath $repoRoot
try {
    & $pythonPath -m uvicorn Backend.app.server:app --host 127.0.0.1 --port 8000
    $serverExit = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $serverExit
