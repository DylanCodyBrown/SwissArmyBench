"""`python -m swissarmybench_desktop [--tray] [page]`: the shell (server/shell.py), as `swissarmybench desktop`
and the base's tray command start it."""

from __future__ import annotations

import sys

from swissarmybench_desktop.server.launch import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
