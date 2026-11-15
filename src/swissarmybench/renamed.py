"""The old name, SwissArmyGrid, for one release: what still answers to it, and how.

Swiss Army Bench was called SwissArmyGrid until 1.7 (the owner, 2026-11-15). For one release the old
names keep working; everything new is written under the new ones, and the next release removes this
module and the `swissarmygrid` package beside this one.

  environment variables   SWISSARMYBENCH_X first, then the old SWISSARMYGRID_X (`env`)
  the state folder        ~/.swissarmygrid becomes ~/.swissarmybench on the server's first start
                          (`move_state_folder`, said once in its log); read where it is while it
                          cannot be moved (`home_state_folder`)
  the Workbench's folder  ~/SwissArmyGrid stays the folder while it is there and ~/SwissArmyBench is not
  the old commands        swissarmygrid, sag, swissarmygrid-mcp, swissarmygrid-context: one line on
                          stderr with the new name, then the new command (stdout stays the command's:
                          the MCP server and the prompt hook speak on it)

Elsewhere, each beside what it keeps: the keyring's old service name (adapters/blades.py), the old
notebook metadata key (domain/notebooks.py), the old blade header (domain/blades.py), the old marks of a
tang, a Streamlit app and its saved pages (domain/relationships.py, domain/streamlit_cells.py), the
`%sag_run`, `%%sag_table`, `%%sag_html` and `%%sag` magics (client/), the old websocket subprotocol
(server/security.py), and the page's remembered settings (web/src/dom.ts).

Standard library only: the plain client uses it.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

NEW_PREFIX: str = "SWISSARMYBENCH_"
OLD_PREFIX: str = "SWISSARMYGRID_"
STATE_FOLDER: str = ".swissarmybench"
OLD_STATE_FOLDER: str = ".swissarmygrid"
WORKBENCH_FOLDER: str = "SwissArmyBench"
OLD_WORKBENCH_FOLDER: str = "SwissArmyGrid"


def env(name: str, default: str = "", environ: Mapping[str, str] | None = None) -> str:
    """An environment variable by its new name (SWISSARMYBENCH_X); else its old one (SWISSARMYGRID_X)."""
    environ = os.environ if environ is None else environ
    if name in environ:
        return environ[name]
    return environ.get(OLD_PREFIX + name.removeprefix(NEW_PREFIX), default)


def home_state_folder(home: Path | None = None) -> Path:
    """The state folder in the home folder: ~/.swissarmybench; the old ~/.swissarmygrid while it is there
    and the new one is not (not moved yet, or it could not be)."""
    home = Path.home() if home is None else home
    new, old = home / STATE_FOLDER, home / OLD_STATE_FOLDER
    return old if not new.exists() and old.is_dir() else new


def workbench_folder(home: Path | None = None) -> Path:
    """The user's own folder for notebooks and scripts: ~/SwissArmyBench, or the old ~/SwissArmyGrid
    while it is there and the new one is not (it holds the user's own files: never moved)."""
    home = Path.home() if home is None else home
    new, old = home / WORKBENCH_FOLDER, home / OLD_WORKBENCH_FOLDER
    return old if not new.exists() and old.is_dir() else new


def move_state_folder(
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
    in_use: Callable[[Path], bool] = lambda info: False,
) -> str | None:
    """On the server's start: move ~/.swissarmygrid to ~/.swissarmybench when only the old one is there.
    The line to say in the log, or None when there was nothing to move. Never when a state folder or a
    connection file was named (SWISSARMYBENCH_STATE, SWISSARMYBENCH_INFO): that is someone's own choice.
    `in_use(connection file)`: an old server still running from the old folder keeps it where it is."""
    if env(NEW_PREFIX + "STATE", environ=environ) or env(NEW_PREFIX + "INFO", environ=environ):
        return None
    home = Path.home() if home is None else home
    new, old = home / STATE_FOLDER, home / OLD_STATE_FOLDER
    if new.exists() or not old.is_dir():
        return None
    if in_use(old / "server.json"):
        return f"{old} is in use by a running SwissArmyGrid server: it is read where it is, not moved."
    try:
        old.rename(new)
    except OSError as error:
        return f"{old} could not be moved to {new} ({error.strerror or error}): it is read where it is."
    return f"Swiss Army Bench was SwissArmyGrid: its state folder {old} is now {new}."


# ===== the old commands, for one release =====


def _renamed(old: str, new: str) -> None:
    print(f"`{old}` is now `{new}`; the old name goes in the next release.", file=sys.stderr)


def swissarmygrid() -> None:
    """The old `swissarmygrid` command: the server's (`swissarmybench`)."""
    _renamed("swissarmygrid", "swissarmybench")
    from swissarmybench.server.launcher import main

    main()


def sag() -> None:
    """The old `sag` command: the agent commands in a terminal (`sab`)."""
    _renamed("sag", "sab")
    from swissarmybench.cli.main import main

    main()


def swissarmygrid_mcp() -> None:
    """The old `swissarmygrid-mcp` command: the MCP server (`swissarmybench-mcp`)."""
    _renamed("swissarmygrid-mcp", "swissarmybench-mcp")
    from swissarmybench.mcp.server import main

    main()


def swissarmygrid_context() -> None:
    """The old `swissarmygrid-context` command: the prompt hook (`swissarmybench-context`)."""
    _renamed("swissarmygrid-context", "swissarmybench-context")
    from swissarmybench.client.context_hook import main

    main()
