param([switch]$Check, [switch]$Tests)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
try {
    $VenvPython = Join-Path $PSScriptRoot '.venv-windows\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        $Candidates = @()
        if ($env:SCRIB3_PYTHON) { $Candidates += $env:SCRIB3_PYTHON }
        else {
            $Found = Get-Command python.exe -ErrorAction SilentlyContinue
            if ($Found) { $Candidates += $Found.Source }
            $InstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\Python'
            if (Test-Path -LiteralPath $InstallRoot) {
                $Candidates += @(Get-ChildItem -LiteralPath $InstallRoot -Directory | Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName 'python.exe' })
            }
        }
        $SelectedPython = $null
        foreach ($Candidate in $Candidates) {
            if (-not (Test-Path -LiteralPath $Candidate)) { continue }
            & $Candidate -c 'import sys, tkinter, venv; sys.exit(0 if sys.version_info >= (3,12) else 1)'
            if ($LASTEXITCODE -eq 0) { $SelectedPython = $Candidate; break }
        }
        if (-not $SelectedPython) { throw 'Install Python 3.12 or newer with Tk, or set SCRIB3_PYTHON to its python.exe path.' }
        & $SelectedPython -m venv (Join-Path $PSScriptRoot '.venv-windows')
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
    }
    $Requirements = if ($Tests) { 'requirements-dev.txt' } else { 'requirements.txt' }
    & $VenvPython -m pip install -r $Requirements
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Keep this console output.' }
    & $VenvPython -c 'import tkinter, serial, shapely, trimesh, scipy; from scrib3 import board, printer_output; print("SCRIB3 dependencies ready")'
    if ($LASTEXITCODE -ne 0) { throw 'Startup dependency check failed.' }
    if ($Tests) {
        $PriorDesktopTests = $env:SCRIB3_DESKTOP_TESTS
        try {
            $env:SCRIB3_DESKTOP_TESTS = '1'
            & $VenvPython -m pytest tests -q
            if ($LASTEXITCODE -ne 0) { throw 'Regression failed. Keep this console output.' }
        } finally { $env:SCRIB3_DESKTOP_TESTS = $PriorDesktopTests }
    } elseif (-not $Check) {
        & $VenvPython -m scrib3
        if ($LASTEXITCODE -ne 0) { throw 'SCRIB3 exited with an error. Keep this console output.' }
    }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
