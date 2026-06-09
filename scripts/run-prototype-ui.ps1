<#
.SYNOPSIS
    Windows (PowerShell) launcher for the pySecretary prototype UI.

.DESCRIPTION
    Mirrors scripts/run-prototype-ui.sh but is uv-only (pip on Windows tends to
    fight over PortAudio binaries, user-site bin paths, and PATH). The script:
      1. Ensures `uv` is available (installs it via the official installer if missing).
      2. Creates/refreshes a .venv and installs requirements.txt with uv.
      3. Picks a free port (unless --port is given) and starts the prototype UI.

    On Windows the `sounddevice`/`soundfile` wheels bundle PortAudio/libsndfile,
    so there is NO system-library install step (unlike Linux/WSL).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\run-prototype-ui.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\run-prototype-ui.ps1 --mock
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\run-prototype-ui.ps1 --port 8800
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AppArgs = @()
)

$ErrorActionPreference = 'Stop'

$BaseDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$VenvDir = if ($env:PSEC_VENV_DIR) { $env:PSEC_VENV_DIR } else { Join-Path $BaseDir '.venv' }
$RequirementsFile = Join-Path $BaseDir 'requirements.txt'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'

Write-Host 'pySecretary prototype UI launcher (Windows/uv)'
Write-Host "Project: $BaseDir"
Write-Host "Venv:    $VenvDir"

# --- Parse passthrough args for host/port/help (everything is still forwarded) ---
$RequestedHost = if ($env:PSEC_PROTOTYPE_HOST) { $env:PSEC_PROTOTYPE_HOST } else { '127.0.0.1' }
$RequestedPort = if ($env:PSEC_PROTOTYPE_PORT) { [int]$env:PSEC_PROTOTYPE_PORT } else { 8765 }
$HostExplicit = $false
$PortExplicit = $false
$ShowHelp = $false

for ($i = 0; $i -lt $AppArgs.Count; $i++) {
    $arg = $AppArgs[$i]
    switch -Wildcard ($arg) {
        '-h'        { $ShowHelp = $true }
        '--help'    { $ShowHelp = $true }
        '--host'    { $HostExplicit = $true; if ($i + 1 -lt $AppArgs.Count) { $RequestedHost = $AppArgs[$i + 1] } }
        '--host=*'  { $HostExplicit = $true; $RequestedHost = $arg.Substring('--host='.Length) }
        '--port'    { $PortExplicit = $true; if ($i + 1 -lt $AppArgs.Count) { $RequestedPort = [int]$AppArgs[$i + 1] } }
        '--port=*'  { $PortExplicit = $true; $RequestedPort = [int]$arg.Substring('--port='.Length) }
    }
}

# --- Ensure uv is on PATH, installing it if necessary ---
function Find-Uv {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($candidate in @(
            (Join-Path $env:USERPROFILE '.local\bin\uv.exe'),
            (Join-Path $env:LOCALAPPDATA 'uv\bin\uv.exe'),
            (Join-Path $env:USERPROFILE '.cargo\bin\uv.exe'))) {
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

$Uv = Find-Uv
if (-not $Uv) {
    Write-Host 'uv not found; installing via the official installer (astral.sh)...'
    # Official uv installer. Installs to %USERPROFILE%\.local\bin by default.
    Invoke-RestMethod -Uri 'https://astral.sh/uv/install.ps1' | Invoke-Expression
    # The installer updates PATH for new sessions; make it visible to THIS session too.
    $env:Path = (Join-Path $env:USERPROFILE '.local\bin') + ';' + $env:Path
    $Uv = Find-Uv
    if (-not $Uv) {
        Write-Error 'uv installation did not produce a usable uv.exe. Install it manually from https://docs.astral.sh/uv/ and re-run.'
        exit 1
    }
}
Write-Host "uv:      $Uv"

# --- Create venv if missing (or if a foreign/Linux venv is present) ---
$PyVersion = if ($env:PSEC_PYTHON_VERSION) { $env:PSEC_PYTHON_VERSION } else { '3.12' }
if (-not (Test-Path $VenvPython)) {
    if (Test-Path $VenvDir) {
        # A .venv without Scripts\python.exe is almost always a Linux/WSL venv (bin/python)
        # copied onto a Windows checkout. uv can't reuse it; recreate cleanly.
        Write-Host "Existing '$VenvDir' has no Windows python.exe (likely a Linux/WSL venv); recreating..."
        Remove-Item -Recurse -Force $VenvDir
    }
    Write-Host "Creating virtual environment with uv (Python $PyVersion; uv downloads it if absent)..."
    & $Uv venv $VenvDir --python $PyVersion
    if (-not (Test-Path $VenvPython)) {
        Write-Error "uv venv did not create '$VenvPython'. Ensure Python $PyVersion is installable (uv can fetch it) and re-run."
        exit 1
    }
}

# --- Install/refresh dependencies, stamped against requirements.txt mtime ---
$RequirementsStamp = Join-Path $VenvDir '.pysecretary-requirements.uv.stamp'
$NeedsInstall = $true
if ((Test-Path $RequirementsStamp) -and (Test-Path $RequirementsFile)) {
    $stampTime = (Get-Item $RequirementsStamp).LastWriteTimeUtc
    $reqTime = (Get-Item $RequirementsFile).LastWriteTimeUtc
    if ($reqTime -le $stampTime) { $NeedsInstall = $false }
}
if (Test-Path $RequirementsFile) {
    if ($NeedsInstall) {
        Write-Host 'Installing project dependencies with uv...'
        & $Uv pip install --python $VenvPython -r $RequirementsFile
        New-Item -ItemType File -Path $RequirementsStamp -Force | Out-Null
    }
    else {
        Write-Host 'Dependencies are up to date for this virtual environment using uv.'
    }
}

Set-Location $BaseDir

# --- Audio backend preflight (on Windows the wheel bundles PortAudio, so this rarely fails) ---
& $VenvPython -c 'import sounddevice' 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Warning 'audio backend unavailable (sounddevice failed to import).'
    Write-Host    "  Live microphone capture will fail. Try: $Uv pip install --python `"$VenvPython`" --reinstall sounddevice soundfile"
    Write-Host    "  ('--mock' demo mode does not need audio.)"
}

# --- Free-port selection (skip if --port was explicit; mirrors the bash launcher) ---
$SelectedPort = $RequestedPort
if (-not $ShowHelp -and -not $PortExplicit) {
    $portScript = @'
import socket, sys
host = sys.argv[1]
start = int(sys.argv[2])
for port in range(start, start + 51):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((host, port)); print(port); sys.exit(0)
    except OSError:
        continue
    finally:
        s.close()
sys.exit(1)
'@
    $found = & $VenvPython -c $portScript $RequestedHost $RequestedPort
    if ($LASTEXITCODE -ne 0 -or -not $found) {
        Write-Error "No free port found from $RequestedPort to $($RequestedPort + 50)."
        exit 1
    }
    $SelectedPort = [int]$found
    if ($SelectedPort -ne $RequestedPort) {
        Write-Host "Port $RequestedPort busy; using $SelectedPort instead."
    }
    $AppArgs += @('--port', "$SelectedPort")
}

if (-not $ShowHelp -and -not $HostExplicit) {
    $AppArgs += @('--host', $RequestedHost)
}

if ($ShowHelp) {
    Write-Host 'Showing prototype UI help...'
}
else {
    Write-Host "Starting prototype UI server on ${RequestedHost}:${SelectedPort}..."
    Write-Host 'Pass --mock for scripted demo mode, e.g.: scripts\run-prototype-ui.ps1 --mock'
}

& $VenvPython -m pysecretary prototype-ui @AppArgs
