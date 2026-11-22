# Install Swiss Army Bench __VERSION__ (Windows): uv if it is missing, then the grid server as a uv tool, with
# its own Python (uv downloads it; no system Python needed).
#
#   irm https://github.com/DylanCodyBrown/SwissArmyBench/releases/download/v__VERSION__/install.ps1 | iex
#   powershell -ExecutionPolicy Bypass -File install.ps1
#   powershell -ExecutionPolicy Bypass -File install.ps1 .\swissarmybench-__VERSION__-py3-none-any.whl
#   ... -NoStart                     install only: the app is not opened now
#   ... -DesktopShortcut             a shortcut on the desktop too (the Start menu always has one)
#   ... -Uninstall                   remove the app, its shortcuts and its tool (your projects stay)
#
# Swiss Army Bench is a desktop app (PySide6; its pages in Qt WebEngine) over a local server that runs while it
# is open. The installer adds a Start menu shortcut with the app's icon (the tool's pythonw.exe: no console
# window), registers it for this user (HKCU) to open .csv, .parquet, .xlsx, .ipynb and .py files (Open with,
# never the default: a .blade.py is a .py to Windows), takes away what an earlier version left (a .sab
# registration, the tray's Startup shortcut), and opens the app once at the end: never on a build machine (CI
# set). -NoAutostart (the tray's, gone) is taken.
param([string]$Wheel = "", [switch]$NoStart, [switch]$NoAutostart, [switch]$DesktopShortcut, [switch]$Uninstall)

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
# The Streamlit extension, preinstalled: its own wheel, on the same version.
$StreamlitWheelName = "swissarmybench_streamlit-$Version-py3-none-any.whl"

# throw, not exit: run as `irm ... | iex`, exit would close the person's PowerShell window.
function Fail([string]$Message) {
    throw "Swiss Army Bench install: $Message"
}

$Programs = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$StartShortcut = Join-Path $Programs "Swiss Army Bench.lnk"
$DesktopLink = Join-Path ([Environment]::GetFolderPath("Desktop")) "Swiss Army Bench.lnk"
$OldStartup = Join-Path $Programs "Startup\Swiss Army Bench.lnk"  # the tray's start at sign-in, gone
$IconFile = Join-Path $env:LOCALAPPDATA "SwissArmyBench\swissarmybench.ico"
# Open with, for this user only (HKCU): the app is offered for these files, never made their default.
$Classes = "HKCU:\Software\Classes"
$FileProgId = "SwissArmyBench.File"
$OpenWithTypes = @(".csv", ".parquet", ".xlsx", ".ipynb", ".py")
function UnregisterOpenWith {
    foreach ($ext in $OpenWithTypes) {
        $key = "$Classes\$ext\OpenWithProgids"
        if (Test-Path $key) { Remove-ItemProperty -Path $key -Name $FileProgId -ErrorAction SilentlyContinue }
    }
    if (Test-Path "$Classes\$FileProgId") { Remove-Item -Path "$Classes\$FileProgId" -Recurse -Force }
}
function RegisterOpenWith([string]$Pythonw) {
    New-Item -Path "$Classes\$FileProgId" -Value "Swiss Army Bench" -Force | Out-Null
    $command = "`"$Pythonw`" -m swissarmybench.server open `"%1`""
    New-Item -Path "$Classes\$FileProgId\shell\open\command" -Value $command -Force | Out-Null
    if (Test-Path $IconFile) { New-Item -Path "$Classes\$FileProgId\DefaultIcon" -Value "$IconFile,0" -Force | Out-Null }
    foreach ($ext in $OpenWithTypes) {
        $key = "$Classes\$ext\OpenWithProgids"
        if (-not (Test-Path $key)) { New-Item -Path $key -Force | Out-Null }
        New-ItemProperty -Path $key -Name $FileProgId -Value "" -PropertyType String -Force | Out-Null
    }
}

if ($Uninstall) {
    foreach ($link in @($StartShortcut, $DesktopLink, $OldStartup)) {
        if (Test-Path $link) { Remove-Item -Force $link }
    }
    if (Test-Path $IconFile) { Remove-Item -Force $IconFile }
    try { UnregisterOpenWith } catch { }
    if (Get-Command swissarmybench -ErrorAction SilentlyContinue) { Quiet { swissarmybench stop } }
    if (Get-Command uv -ErrorAction SilentlyContinue) { Quiet { uv tool uninstall swissarmybench } }
    Write-Host "Swiss Army Bench is removed (its shortcuts and its tool). Your projects and .swissarmybench are kept."
    return
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

# 2b. The Streamlit extension (preinstalled): beside the wheel given, else the release's. Without it the
#     app is the base alone (the Extensions page installs it later).
$StreamlitPath = $null
if ($Wheel) {
    $Beside = Join-Path (Split-Path -Parent $WheelPath) $StreamlitWheelName
    if (Test-Path $Beside) { $StreamlitPath = $Beside }
    else { Write-Host "No $StreamlitWheelName beside the wheel: installing without the Streamlit extension (the Extensions page adds it)." }
} else {
    $StreamlitPath = Join-Path $Temp $StreamlitWheelName
    $StreamlitUrl = "https://github.com/$Repo/releases/download/v$Version/$StreamlitWheelName"
    Write-Host "Downloading $StreamlitUrl ..."
    try { Invoke-WebRequest -Uri $StreamlitUrl -OutFile $StreamlitPath -UseBasicParsing }
    catch {
        $StreamlitPath = $null
        Write-Host "Could not download the Streamlit extension: installing without it (the Extensions page adds it)."
    }
}

# 3. Swiss Army Bench was SwissArmyGrid: its old uv tool goes.
if ((ListTools) -match '^swissarmygrid ') {
    Write-Host "Removing the old SwissArmyGrid tool (Swiss Army Bench replaces it)..."
    Quiet { uv tool uninstall swissarmygrid }
}

# 4. The server, as a uv tool in its own environment. Windows will not replace files a running program has
#    open, so whatever runs from the installed copy stops first: the app and its server (`swissarmybench stop`
#    quits the app over its channel, each window's place kept, then stops the server), and any agent tool
#    (MCP) server an editor started from it.
function ToolDir {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { return (uv tool dir 2>$null) } finally { $ErrorActionPreference = $previous }
}
function StopRunningCopies {
    if (Get-Command swissarmybench -ErrorAction SilentlyContinue) { Quiet { swissarmybench stop } }
    $tools = ToolDir
    if (-not $tools) { return }
    $installed = Join-Path $tools "swissarmybench"
    $running = Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Path -and $_.Path.StartsWith($installed, [System.StringComparison]::OrdinalIgnoreCase)
    }
    if ($running) {
        Write-Host "Stopping Swiss Army Bench processes still running from the installed copy..."
        $running | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
}
StopRunningCopies
Write-Host "Installing the Swiss Army Bench server $Version..."
$installed = $false
foreach ($try in 1..3) {
    if ($StreamlitPath) { uv tool install --force --python 3.12 "$WheelPath[server]" --with "$StreamlitPath" }
    else { uv tool install --force --python 3.12 "$WheelPath[server]" }
    if ($LASTEXITCODE -eq 0) { $installed = $true; break }
    # Files still held (an editor's agent tools restarting, a virus scan): stop them again and retry.
    Start-Sleep -Seconds 3
    StopRunningCopies
}
if (-not $installed) {
    Fail ("uv could not install the server. A program may still be using the installed copy: close VS Code and " +
        "Claude Code (their Swiss Army Bench tools run from it), then run this installer again.")
}
Quiet { uv tool update-shell }
if ($Temp) { Remove-Item -Recurse -Force $Temp -ErrorAction SilentlyContinue }

Write-Host ""
Write-Host "Swiss Army Bench $Version is installed." -ForegroundColor Green
Write-Host "  Open it:               the Start menu's Swiss Army Bench, or: swissarmybench"
Write-Host "  In the browser:        swissarmybench open --browser"
Write-Host "  The Python client:     uv pip install `"$WheelName`"   (in any project's environment)"
Write-Host "  Then, in Python:       import swissarmybench as sab; sab.push(df)"
Write-Host "  Remove it:             powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall"
Write-Host "(Open a new terminal first if the swissarmybench command is not found.)"

# 5. The Start menu shortcut (and the desktop's on -DesktopShortcut): the tool's pythonw.exe running the app,
#    with no console window, and the app's icon.
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

# 6. A project is a folder now (2026-11-17): .sab files are no longer registered. An earlier install's
#    registration for this user (HKCU\Software\Classes) is taken away, so an old machine is left clean.
function UnregisterProjectFiles {
    $Classes = "HKCU:\Software\Classes"
    $ProgId = "SwissArmyBench.Project"
    $had = (Test-Path "$Classes\$ProgId")
    if ((Test-Path "$Classes\.sab") -and ((Get-Item -Path "$Classes\.sab").GetValue("") -eq $ProgId)) {
        Remove-Item -Path "$Classes\.sab" -Recurse -Force
    }
    if ($had) { Remove-Item -Path "$Classes\$ProgId" -Recurse -Force }
    return $had
}
try { if (UnregisterProjectFiles) { Write-Host "Project files (.sab) are no longer registered: a project is a folder now." } }
catch { }
if (Test-Path $OldStartup) { Remove-Item -Force $OldStartup }  # an older version's tray at sign-in
$ToolsDir = (ToolDir) | Select-Object -First 1
$Pythonw = $null
if ($ToolsDir) { $Pythonw = Join-Path $ToolsDir "swissarmybench\Scripts\pythonw.exe" }
if ($Pythonw -and (Test-Path $Pythonw)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $IconFile) | Out-Null
    if (Test-Path $Exe) { Quiet { & $Exe icon $IconFile } }
    $shell = New-Object -ComObject WScript.Shell
    $links = @($StartShortcut)
    if ($DesktopShortcut) { $links += $DesktopLink }
    foreach ($link in $links) {
        $s = $shell.CreateShortcut($link)
        $s.TargetPath = $Pythonw
        $s.Arguments = "-m swissarmybench.server app"
        $s.WorkingDirectory = $env:USERPROFILE
        $s.Description = "Swiss Army Bench"
        if (Test-Path $IconFile) { $s.IconLocation = "$IconFile,0" }
        $s.Save()
    }
    Write-Host "Swiss Army Bench is in the Start menu."
    try { RegisterOpenWith $Pythonw; Write-Host "Open with: Swiss Army Bench, for .csv, .parquet, .xlsx, .ipynb and .py files." }
    catch { Write-Host "Open with could not be registered: $_" }
    # 7. Open the app once (not on a build machine).
    if (-not $NoStart -and -not $BuildMachine) {
        Start-Process -FilePath $Pythonw -ArgumentList "-m", "swissarmybench.server", "app"
        Write-Host "Opening Swiss Army Bench..."
    }
}
