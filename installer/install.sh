#!/bin/sh
# Install Swiss Army Bench __VERSION__ (macOS and Linux): uv if it is missing, then the grid server as a uv tool,
# with its own Python (uv downloads it; no system Python needed). One wheel: every feature is built in.
#
#   curl -LsSf https://github.com/DylanCodyBrown/SwissArmyBench/releases/download/v__VERSION__/install.sh | sh
#   sh install.sh                                          # download the wheel from the GitHub release
#   sh install.sh ./swissarmybench-__VERSION__-py3-none-any.whl  # or install a wheel you downloaded
#   sh install.sh [wheel] --no-start                       # install only, do not open the app
#   sh install.sh --uninstall                              # remove the app, its launcher and its tool
#
# Swiss Army Bench is a desktop app (PySide6; its pages in Qt WebEngine) over a local server that runs while
# it is open. The installer adds a launcher with the app's icon (Linux: a .desktop entry in
# ~/.local/share/applications; macOS: "Swiss Army Bench.app" in ~/Applications), registers it for this user
# to open .csv, .parquet, .xlsx, .ipynb and .blade.py files (Open with; the default only for .blade.py), takes
# away what an earlier version left (a .sab registration, the tray's start-at-sign-in entry), and opens the app
# once at the end: never on a build machine (CI set) or with no display. --no-autostart (the tray's, gone) is
# still taken.
set -eu

wheel_arg=""
start_now=1
uninstall=0
for arg in "$@"; do
  case "$arg" in
    --no-autostart) ;;  # start at sign-in is gone (2026-11-18); taken for one release so older scripts run
    --no-start) start_now=0 ;;
    --uninstall) uninstall=1 ;;
    *) wheel_arg="$arg" ;;
  esac
done
if [ -n "${CI:-}" ]; then start_now=0; fi

VERSION="__VERSION__"
REPO="DylanCodyBrown/SwissArmyBench"
WHEEL="swissarmybench-${VERSION}-py3-none-any.whl"

say() { printf '%s\n' "$*"; }
fail() { printf 'Swiss Army Bench install: %s\n' "$*" >&2; exit 1; }

DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
DESKTOP_ENTRY="$DATA/applications/swissarmybench.desktop"
ICON="$DATA/icons/hicolor/scalable/apps/swissarmybench.svg"
MAC_APP="$HOME/Applications/Swiss Army Bench.app"
# Open with (Linux): the file types the app opens; a blade's own type (*.blade.py), whose default it is.
MIME_FILE="$DATA/mime/packages/swissarmybench-files.xml"
MIME_TYPES="text/csv;application/vnd.apache.parquet;application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;application/x-ipynb+json;application/x-swissarmybench-blade;inode/directory;"

# What an older version's tray left: its start-at-sign-in entry (only when it is the tray's).
remove_old_tray() {
  old="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/swissarmybench.desktop"
  if [ -f "$old" ] && grep -q "swissarmybench.server tray" "$old" 2>/dev/null; then rm -f "$old"; fi
  plist="$HOME/Library/LaunchAgents/com.swissarmybench.tray.plist"
  if [ -f "$plist" ]; then
    launchctl remove com.swissarmybench.tray >/dev/null 2>&1 || true
    rm -f "$plist"
  fi
}

remove_launcher() {
  rm -f "$DESKTOP_ENTRY" "$ICON" "$MIME_FILE"
  update-mime-database "$DATA/mime" >/dev/null 2>&1 || true
  update-desktop-database "$DATA/applications" >/dev/null 2>&1 || true
  rm -rf "$MAC_APP"
}

if [ "$uninstall" = 1 ]; then
  remove_launcher
  remove_old_tray
  if command -v swissarmybench >/dev/null 2>&1; then swissarmybench stop >/dev/null 2>&1 || true; fi
  if command -v uv >/dev/null 2>&1; then uv tool uninstall swissarmybench >/dev/null 2>&1 || true; fi
  say "Swiss Army Bench is removed (its launcher and its tool). Your projects and ~/.swissarmybench are kept."
  exit 0
fi

# 1. uv: the installer uses uv's own install script, which puts uv in ~/.local/bin.
if ! command -v uv >/dev/null 2>&1; then
  if [ -x "$HOME/.local/bin/uv" ]; then
    PATH="$HOME/.local/bin:$PATH"
  else
    say "Installing uv (the tool that installs Swiss Army Bench and its Python)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh || fail "uv could not be installed; see https://docs.astral.sh/uv/"
    PATH="$HOME/.local/bin:$PATH"
  fi
fi
command -v uv >/dev/null 2>&1 || fail "uv is installed but not on PATH; open a new terminal and run this again."

# 2. The wheel: a path given on the command line, or the release's wheel.
if [ -n "$wheel_arg" ]; then
  [ -f "$wheel_arg" ] || fail "no such file: $wheel_arg"
  wheel_path="$wheel_arg"
else
  dir=$(mktemp -d)
  trap 'rm -rf "$dir"' EXIT
  wheel_path="$dir/$WHEEL"
  url="https://github.com/$REPO/releases/download/v$VERSION/$WHEEL"
  say "Downloading $url ..."
  curl -fLsS -o "$wheel_path" "$url" || fail "could not download the wheel from $url.
  Download $WHEEL from https://github.com/$REPO/releases/tag/v$VERSION and run: sh install.sh <path to the wheel>"
fi

# 3. Swiss Army Bench was SwissArmyGrid: its old uv tool goes.
if uv tool list 2>/dev/null | grep -q '^swissarmygrid '; then
  say "Removing the old SwissArmyGrid tool (Swiss Army Bench replaces it)..."
  uv tool uninstall swissarmygrid >/dev/null 2>&1 || true
fi

# 4. The server, as a uv tool in its own environment.
say "Installing the Swiss Army Bench server $VERSION..."
uv tool install --force --python 3.12 "${wheel_path}[server]" || fail "uv could not install the server."
uv tool update-shell >/dev/null 2>&1 || true

# 5. The launcher: the app with its icon, where the system lists applications.
bin_dir=$(uv tool dir --bin 2>/dev/null || true)
exe="${bin_dir:-$HOME/.local/bin}/swissarmybench"
[ -x "$exe" ] || exe="$HOME/.local/bin/swissarmybench"
remove_old_tray
case "$(uname -s)" in
  Darwin)
    mkdir -p "$MAC_APP/Contents/MacOS"
    cat > "$MAC_APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Swiss Army Bench</string>
  <key>CFBundleIdentifier</key><string>com.swissarmybench.app</string>
  <key>CFBundleExecutable</key><string>swissarmybench</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSUIElement</key><false/>
  <key>CFBundleDocumentTypes</key><array>
    <dict><key>CFBundleTypeName</key><string>Table</string><key>CFBundleTypeRole</key><string>Viewer</string>
      <key>LSHandlerRank</key><string>Alternate</string>
      <key>CFBundleTypeExtensions</key><array><string>csv</string><string>parquet</string><string>xlsx</string></array></dict>
    <dict><key>CFBundleTypeName</key><string>Notebook</string><key>CFBundleTypeRole</key><string>Editor</string>
      <key>LSHandlerRank</key><string>Alternate</string>
      <key>CFBundleTypeExtensions</key><array><string>ipynb</string></array></dict>
    <dict><key>CFBundleTypeName</key><string>Blade</string><key>CFBundleTypeRole</key><string>Editor</string>
      <key>LSHandlerRank</key><string>Owner</string>
      <key>LSItemContentTypes</key><array><string>com.swissarmybench.blade</string></array></dict>
  </array>
  <key>UTExportedTypeDeclarations</key><array>
    <dict><key>UTTypeIdentifier</key><string>com.swissarmybench.blade</string>
      <key>UTTypeDescription</key><string>Swiss Army Bench blade</string>
      <key>UTTypeConformsTo</key><array><string>public.python-script</string></array>
      <key>UTTypeTagSpecification</key><dict><key>public.filename-extension</key><array><string>blade.py</string></array></dict></dict>
  </array>
</dict></plist>
PLIST
    printf '#!/bin/sh\nexec "%s" "$@"\n' "$exe" > "$MAC_APP/Contents/MacOS/swissarmybench"
    chmod +x "$MAC_APP/Contents/MacOS/swissarmybench"
    say "The app is in ~/Applications: Swiss Army Bench."
    ;;
  *)
    mkdir -p "$(dirname "$DESKTOP_ENTRY")" "$(dirname "$ICON")"
    cat > "$ICON" <<'SVG'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" rx="20" fill="#d52b1e"/><path d="M42 23h16v19h19v16H58v19H42V58H23V42h19z" fill="#fff"/></svg>
SVG
    cat > "$DESKTOP_ENTRY" <<ENTRY
[Desktop Entry]
Type=Application
Name=Swiss Army Bench
Comment=Your data in live grids, notebooks and SQL
Exec="$exe" open %f
Icon=swissarmybench
Terminal=false
Categories=Development;Science;
StartupWMClass=swissarmybench
MimeType=$MIME_TYPES
ENTRY
    # Open with: the types it opens, for this user; the app is the default only for a blade (*.blade.py).
    mkdir -p "$(dirname "$MIME_FILE")"
    cat > "$MIME_FILE" <<'MIME'
<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-swissarmybench-blade">
    <comment>Swiss Army Bench blade</comment>
    <sub-class-of type="text/x-python"/>
    <glob pattern="*.blade.py" weight="60"/>
  </mime-type>
  <mime-type type="application/vnd.apache.parquet">
    <comment>Parquet table</comment>
    <glob pattern="*.parquet"/>
  </mime-type>
  <mime-type type="application/x-ipynb+json">
    <comment>Jupyter notebook</comment>
    <sub-class-of type="application/json"/>
    <glob pattern="*.ipynb"/>
  </mime-type>
</mime-info>
MIME
    update-mime-database "$DATA/mime" >/dev/null 2>&1 || true
    update-desktop-database "$DATA/applications" >/dev/null 2>&1 || true
    xdg-mime default swissarmybench.desktop application/x-swissarmybench-blade >/dev/null 2>&1 || true
    say "The app is in your applications menu: Swiss Army Bench."
    ;;
esac

say ""
say "Swiss Army Bench $VERSION is installed."
say "  Open it:               swissarmybench   (or Swiss Army Bench in your applications)"
say "  In the browser:        swissarmybench open --browser"
say "  A file in it:          swissarmybench open orders.csv   (or Open with: Swiss Army Bench)"
say "  The Python client:     uv pip install \"$WHEEL\"   (in any project's environment)"
say "  Then, in Python:       import swissarmybench as sab; sab.push(df)"
say "  Remove it:             sh install.sh --uninstall"
say "(Open a new terminal first if the swissarmybench command is not found.)"

# 6. A project is a folder now (2026-11-17): .sab files are no longer registered. An earlier install's
#    registration (a MIME type, its desktop entry) is taken away, for this user (XDG), so an old machine is
#    left clean.
if [ "$(uname -s)" = "Linux" ]; then
  data="${XDG_DATA_HOME:-$HOME/.local/share}"
  if [ -f "$data/mime/packages/swissarmybench-project.xml" ] || [ -f "$data/applications/swissarmybench-project.desktop" ]; then
    rm -f "$data/mime/packages/swissarmybench-project.xml" "$data/applications/swissarmybench-project.desktop" \
      "$data/icons/hicolor/scalable/mimetypes/application-x-swissarmybench-project.svg"
    update-mime-database "$data/mime" >/dev/null 2>&1 || true
    update-desktop-database "$data/applications" >/dev/null 2>&1 || true
    say "Project files (.sab) are no longer registered: a project is a folder now."
  fi
fi
# 7. Open the app once (not on a build machine, nor with no display to show it on).
display=1
if [ "$(uname -s)" != "Darwin" ] && [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then display=0; fi
if [ -x "$exe" ] && [ "$start_now" = 1 ] && [ "$display" = 1 ]; then
  nohup "$exe" >/dev/null 2>&1 &
  say "Opening Swiss Army Bench..."
fi
