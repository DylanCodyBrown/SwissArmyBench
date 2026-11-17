#!/bin/sh
# Install Swiss Army Bench __VERSION__ (macOS and Linux): uv if it is missing, then the grid server as a uv tool,
# with its own Python (uv downloads it; no system Python needed).
#
#   curl -LsSf https://github.com/DylanCodyBrown/SwissArmyBench/releases/download/v__VERSION__/install.sh | sh
#   sh install.sh                                          # download the wheel from the GitHub release
#   sh install.sh ./swissarmybench-__VERSION__-py3-none-any.whl  # or install a wheel you downloaded
#   sh install.sh [wheel] --no-autostart --no-start             # install only
#
# At the end it registers .sab project files (Linux desktops: a double-click opens one), turns on start at sign-in (the tray, which starts the server), starts the app in the
# background and opens its page once. Never on a build machine (CI set) or with SWISSARMYBENCH_NO_AUTOSTART=1.
set -eu

wheel_arg=""
autostart=1
start_now=1
for arg in "$@"; do
  case "$arg" in
    --no-autostart) autostart=0 ;;
    --no-start) start_now=0 ;;
    *) wheel_arg="$arg" ;;
  esac
done
if [ -n "${CI:-}" ] || [ "${SWISSARMYBENCH_NO_AUTOSTART:-}" = "1" ]; then autostart=0; fi
if [ -n "${CI:-}" ]; then start_now=0; fi

VERSION="__VERSION__"
REPO="DylanCodyBrown/SwissArmyBench"
WHEEL="swissarmybench-${VERSION}-py3-none-any.whl"

say() { printf '%s\n' "$*"; }
fail() { printf 'Swiss Army Bench install: %s\n' "$*" >&2; exit 1; }

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

# 3. Swiss Army Bench was SwissArmyGrid: its old uv tool goes (this one keeps the old commands working).
if uv tool list 2>/dev/null | grep -q '^swissarmygrid '; then
  say "Removing the old SwissArmyGrid tool (Swiss Army Bench replaces it; its old commands still work)..."
  uv tool uninstall swissarmygrid >/dev/null 2>&1 || true
fi

# 4. The server, as a uv tool in its own environment.
say "Installing the Swiss Army Bench server $VERSION..."
uv tool install --force --python 3.12 "${wheel_path}[server]" || fail "uv could not install the server."
uv tool update-shell >/dev/null 2>&1 || true

say ""
say "Swiss Army Bench Streamlit Edition $VERSION is installed."
say "  Start it:              swissarmybench start"
say "  The Python client:     uv pip install \"$WHEEL\"   (in any project's environment)"
say "  Then, in Python:       import swissarmybench as sab; sab.push(df)"
say "(Open a new terminal first if the swissarmybench command is not found.)"

# 5. Start at sign-in, and start it now: the server in the background, its tray, its page opened once.
bin_dir=$(uv tool dir --bin 2>/dev/null || true)
exe="${bin_dir:-$HOME/.local/bin}/swissarmybench"
[ -x "$exe" ] || exe="$HOME/.local/bin/swissarmybench"

# 6. .sab project files open with Swiss Army Bench on a Linux desktop: a MIME type, its icon and a desktop
#    entry that runs `swissarmybench open <file>`, for this user (XDG). macOS: open them with that command.
if [ "$(uname -s)" = "Linux" ] && [ -x "$exe" ]; then
  data="${XDG_DATA_HOME:-$HOME/.local/share}"
  mkdir -p "$data/mime/packages" "$data/applications" "$data/icons/hicolor/scalable/mimetypes"
  cat > "$data/mime/packages/swissarmybench-project.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-swissarmybench-project">
    <comment>Swiss Army Bench project</comment>
    <icon name="application-x-swissarmybench-project"/>
    <glob pattern="*.sab"/>
  </mime-type>
</mime-info>
XML
  cat > "$data/applications/swissarmybench-project.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Swiss Army Bench
Exec="$exe" open %f
MimeType=application/x-swissarmybench-project;
Icon=application-x-swissarmybench-project
NoDisplay=true
Terminal=false
DESKTOP
  tool_dir=$(uv tool dir 2>/dev/null || true)
  for icon in "$tool_dir"/swissarmybench/lib/python*/site-packages/swissarmybench/server/sab-file.svg; do
    [ -f "$icon" ] && cp "$icon" "$data/icons/hicolor/scalable/mimetypes/application-x-swissarmybench-project.svg"
  done
  update-mime-database "$data/mime" >/dev/null 2>&1 || true
  update-desktop-database "$data/applications" >/dev/null 2>&1 || true
  xdg-mime default swissarmybench-project.desktop application/x-swissarmybench-project >/dev/null 2>&1 || true
  say "Project files (.sab) open with Swiss Army Bench."
fi
if [ -x "$exe" ]; then
  if [ "$autostart" = 1 ] && "$exe" autostart on >/dev/null 2>&1; then
    say "It starts when you log in (the tray's Open at login turns that off)."
  fi
  if [ "$start_now" = 1 ]; then
    "$exe" start --background >/dev/null 2>&1 || true
    say "Starting Swiss Army Bench: its page opens in your browser."
  fi
fi
