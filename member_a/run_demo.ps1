$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    python .\run_demo.py @args
    if ($LASTEXITCODE -ne 0) { throw "Demo failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}
