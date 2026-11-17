#!/bin/sh
# Install Swiss Army Bench __VERSION__ (macOS and Linux): uv if it is missing, then the grid server as a uv tool,
# with its own Python (uv downloads it; no system Python needed), and the Streamlit extension (preinstalled:
# its wheel beside a wheel given, else from the same release; the Extensions page can remove it).
#
#   curl -LsSf https://github.com/DylanCodyBrown/SwissArmyBench/releases/download/v__VERSION__/install.sh | sh
#   sh install.sh                                          # download the wheel from the GitHub release
#   sh install.sh ./swissarmybench-__VERSION__-py3-none-any.whl  # or install a wheel you downloaded
#   sh install.sh [wheel] --no-autostart --no-start             # install only
#
# At the end it takes away an earlier .sab registration (a project is a folder now), turns on start at sign-in (the tray, which starts the server), starts the app in the
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
# The Streamlit extension, preinstalled: its own wheel, on the same version.
STREAMLIT_WHEEL="swissarmybench_streamlit-${VERSION}-py3-none-any.whl"

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

# 2b. The Streamlit extension (preinstalled): beside the wheel given, else the release's. Without it the
#     app is the base alone (the Extensions page installs it later).
streamlit_path=""
if [ -n "$wheel_arg" ]; then
  beside="$(dirname "$wheel_path")/$STREAMLIT_WHEEL"
  if [ -f "$beside" ]; then streamlit_path="$beside"; else
    say "No $STREAMLIT_WHEEL beside the wheel: installing without the Streamlit extension (the Extensions page adds it)."
  fi
else
  streamlit_path="$dir/$STREAMLIT_WHEEL"
  surl="https://github.com/$REPO/releases/download/v$VERSION/$STREAMLIT_WHEEL"
  say "Downloading $surl ..."
  if ! curl -fLsS -o "$streamlit_path" "$surl"; then
    streamlit_path=""
    say "Could not download the Streamlit extension: installing without it (the Extensions page adds it)."
  fi
fi

# 3. Swiss Army Bench was SwissArmyGrid: its old uv tool goes (this one keeps the old commands working).
if uv tool list 2>/dev/null | grep -q '^swissarmygrid '; then
  say "Removing the old SwissArmyGrid tool (Swiss Army Bench replaces it; its old commands still work)..."
  uv tool uninstall swissarmygrid >/dev/null 2>&1 || true
fi

# 4. The server, as a uv tool in its own environment.
say "Installing the Swiss Army Bench server $VERSION..."
if [ -n "$streamlit_path" ]; then
  uv tool install --force --python 3.12 "${wheel_path}[server]" --with "$streamlit_path" ||
    fail "uv could not install the server."
else
  uv tool install --force --python 3.12 "${wheel_path}[server]" || fail "uv could not install the server."
fi
uv tool update-shell >/dev/null 2>&1 || true

say ""
say "Swiss Army Bench $VERSION is installed."
say "  Start it:              swissarmybench start"
say "  The Python client:     uv pip install \"$WHEEL\"   (in any project's environment)"
say "  Then, in Python:       import swissarmybench as sab; sab.push(df)"
say "(Open a new terminal first if the swissarmybench command is not found.)"

# 5. Start at sign-in, and start it now: the server in the background, its tray, its page opened once.
bin_dir=$(uv tool dir --bin 2>/dev/null || true)
exe="${bin_dir:-$HOME/.local/bin}/swissarmybench"
[ -x "$exe" ] || exe="$HOME/.local/bin/swissarmybench"

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
if [ -x "$exe" ]; then
  if [ "$autostart" = 1 ] && "$exe" autostart on >/dev/null 2>&1; then
    say "It starts when you log in (the tray's Open at login turns that off)."
  fi
  if [ "$start_now" = 1 ]; then
    "$exe" start --background >/dev/null 2>&1 || true
    say "Starting Swiss Army Bench: its page opens in your browser."
  fi
fi
