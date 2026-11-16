# Install Swiss Army Bench __VERSION__ (Windows): uv if it is missing, then the grid server as a uv tool, with
# its own Python (uv downloads it; no system Python needed).
#
#   irm https://github.com/DylanCodyBrown/SwissArmyBench/releases/download/v__VERSION__/install.ps1 | iex
#   powershell -ExecutionPolicy Bypass -File install.ps1
#   powershell -ExecutionPolicy Bypass -File install.ps1 .\swissarmybench-__VERSION__-py3-none-any.whl
#   ... -NoAutostart -NoStart        install only: no start at sign-in, and not started now
#
# At the end it turns on start at sign-in (the tray, which starts the server), starts the app in the
# background and opens its page once. Never on a build machine (CI set) or with SWISSARMYBENCH_NO_AUTOSTART=1.
param([string]$Wheel = "", [switch]$NoStart, [switch]$NoAutostart)

$ErrorActionPreference = "Stop"

# Windows PowerShell 5.1 turns anything a program writes to its error stream into an error, and with
# "Stop" above that ends the script, even for a harmless note such as uv's "already in PATH". Quiet runs a
# program with that turned off and its output thrown away; its exit code is still in $LASTEXITCODE.
function Quiet([scriptblock]$Command) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Command *> $null } finally { $ErrorActionPreference = $previous }
}

function ListTools {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { return (uv tool list 2>$null) } finally { $ErrorActionPreference = $previous }
}
$Version = "__VERSION__"
$Repo = "DylanCodyBrown/SwissArmyBench"
$WheelName = "swissarmybench-$Version-py3-none-any.whl"

# throw, not exit: run as `irm ... | iex`, exit would close the person's PowerShell window.
function Fail([string]$Message) {
    throw "Swiss Army Bench install: $Message"
}

# 1. uv: uv's own installer puts it in %USERPROFILE%\.local\bin.
$LocalBin = Join-Path $env:USERPROFILE ".local\bin"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    if (-not (Test-Path (Join-Path $LocalBin "uv.exe"))) {
        Write-Host "Installing uv (the tool that installs Swiss Army Bench and its Python)..."
        try { Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression }
        catch { Fail "uv could not be installed; see https://docs.astral.sh/uv/" }
    }
    $env:Path = "$LocalBin;$env:Path"
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Fail "uv is installed but not on PATH; open a new terminal and run this again." }

# 2. The wheel: a path given on the command line, or the release's wheel.
$Temp = $null
if ($Wheel) {
    if (-not (Test-Path $Wheel)) { Fail "no such file: $Wheel" }
    $WheelPath = (Resolve-Path $Wheel).Path
} else {
    $Temp = Join-Path ([System.IO.Path]::GetTempPath()) ("sab-" + [guid]::NewGuid())
    New-Item -ItemType Directory -Path $Temp | Out-Null
    $WheelPath = Join-Path $Temp $WheelName
    $Url = "https://github.com/$Repo/releases/download/v$Version/$WheelName"
    Write-Host "Downloading $Url ..."
    try { Invoke-WebRequest -Uri $Url -OutFile $WheelPath -UseBasicParsing }
    catch {
        Fail ("could not download the wheel from $Url.`n" +
            "  Download $WheelName from https://github.com/$Repo/releases/tag/v$Version and run: install.ps1 <path to the wheel>")
    }
}

# 3. Swiss Army Bench was SwissArmyGrid: its old uv tool goes (this one keeps the old commands working).
if ((ListTools) -match '^swissarmygrid ') {
    Write-Host "Removing the old SwissArmyGrid tool (Swiss Army Bench replaces it; its old commands still work)..."
    Quiet { uv tool uninstall swissarmygrid }
}

# 4. The server, as a uv tool in its own environment.
Write-Host "Installing the Swiss Army Bench server $Version..."
uv tool install --force --python 3.12 "$WheelPath[server]"
if ($LASTEXITCODE -ne 0) { Fail "uv could not install the server." }
Quiet { uv tool update-shell }
if ($Temp) { Remove-Item -Recurse -Force $Temp -ErrorAction SilentlyContinue }

Write-Host ""
Write-Host "Swiss Army Bench $Version is installed." -ForegroundColor Green
Write-Host "  Start it:              swissarmybench start"
Write-Host "  The Python client:     uv pip install `"$WheelName`"   (in any project's environment)"
Write-Host "  Then, in Python:       import swissarmybench as sab; sab.push(df)"
Write-Host "(Open a new terminal first if the swissarmybench command is not found.)"

# 5. Start at sign-in, and start it now: the server in the background, its tray, its page opened once.
function ToolBin {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { return (uv tool dir --bin 2>$null) } finally { $ErrorActionPreference = $previous }
}
$BuildMachine = [bool]$env:CI
$Exe = $null
$Bin = (ToolBin) | Select-Object -First 1
if ($Bin) { $Exe = Join-Path $Bin "swissarmybench.exe" }
if (-not $Exe -or -not (Test-Path $Exe)) { $Exe = Join-Path $LocalBin "swissarmybench.exe" }
if (Test-Path $Exe) {
    if (-not $NoAutostart -and -not $BuildMachine -and $env:SWISSARMYBENCH_NO_AUTOSTART -ne "1") {
        Quiet { & $Exe autostart on }
        if ($LASTEXITCODE -eq 0) { Write-Host "It starts when you sign in (the tray's Start with Windows turns that off)." }
    }
    if (-not $NoStart -and -not $BuildMachine) {
        Quiet { & $Exe start --background }
        Write-Host "Starting Swiss Army Bench: its page opens in your browser."
    }
}
