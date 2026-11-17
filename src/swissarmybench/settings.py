"""Server settings and resource limits (plan section 6a).

One frozen dataclass so every limit lives in one place, the way a C# app keeps its options in
one IOptions<T> record. Defaults follow the plan. Nothing reads a settings file yet; tests and
the command line build a Settings with different values.

Sizes are in bytes and reported in MiB (1,048,576 bytes) so the unit is never ambiguous.
"""

from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from swissarmybench.domain.updates import FEEDS
from swissarmybench.renamed import env, home_state_folder, workbench_folder

MIB: int = 1024 * 1024
GIB: int = 1024 * MIB

# The page's files: bundled inside the package when installed from a wheel (the uv tool), or
# web/static in the repo when running from source (uv sync's editable install).
_PACKAGED_WEB: Path = Path(__file__).resolve().parent / "web_static"
_REPO_WEB: Path = Path(__file__).resolve().parents[2] / "web" / "static"


def physical_memory_bytes() -> int:
    """Total physical memory of this machine, read once at startup."""
    if sys.platform == "win32":

        class _MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = _MemoryStatus()
        status.dwLength = ctypes.sizeof(_MemoryStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return int(status.ullTotalPhys)
    return int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))


def _state_dir() -> Path:
    override = env("SWISSARMYBENCH_STATE")
    return Path(override) if override else home_state_folder()


def _workbench_dir() -> Path:
    """The user's own folder for notebooks and scripts: SwissArmyBench in the home folder (made the first
    time it is needed); SWISSARMYBENCH_WORKBENCH_DIR overrides it (tests, so none lands in a real home)."""
    override = env("SWISSARMYBENCH_WORKBENCH_DIR")
    return Path(override) if override else workbench_folder()


def _claude_dir() -> Path:
    """Claude Code's folder, where installed plugins (packs) live: SWISSARMYBENCH_CLAUDE_DIR (tests),
    else Claude Code's own CLAUDE_CONFIG_DIR, else ~/.claude."""
    override = env("SWISSARMYBENCH_CLAUDE_DIR") or os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(override) if override else Path.home() / ".claude"


def _claude_standin() -> Path | None:
    """SWISSARMYBENCH_CLAUDE_STANDIN (tests): a JSON file says which Claude was found; launches are written
    beside it, so nothing is probed and no terminal opens."""
    override = env("SWISSARMYBENCH_CLAUDE_STANDIN")
    return Path(override) if override else None


def _update_feeds() -> tuple[str, ...]:
    """Where the update check asks (PyPI, then GitHub). SWISSARMYBENCH_UPDATE_FEED names one address
    instead (a stand-in on 127.0.0.1 in tests), or "none": the check never asks anything."""
    override = env("SWISSARMYBENCH_UPDATE_FEED", "\0")
    if override == "\0":
        return FEEDS
    return () if override.strip().lower() in ("", "none", "0", "off") else (override.strip(),)


def _default_dataset_cap() -> int:
    """1 GiB per dataset (room for Excel's 1,048,576 rows on a wide table), or
    SWISSARMYBENCH_MAX_DATASET_MB when set; always within the total budget."""
    override = env("SWISSARMYBENCH_MAX_DATASET_MB", "")
    return int(override) * MIB if override.isdigit() and int(override) > 0 else GIB


EXCEL_MAX_ROWS: int = 1_048_576
QUERY_ROWS_VARIABLE: str = "SWISSARMYBENCH_MAX_QUERY_ROWS"


def _default_query_rows() -> int:
    """5,000,000 rows from one connection's table into a DuckDB query, or SWISSARMYBENCH_MAX_QUERY_ROWS."""
    override = os.environ.get(QUERY_ROWS_VARIABLE, "").replace(",", "").replace("_", "")
    return int(override) if override.isdigit() and int(override) > 0 else 5_000_000


def _default_total_budget() -> int:
    # 3 GiB for every dataset together, never above 50% of physical memory (plan section 6a).
    return min(3 * GIB, physical_memory_bytes() // 2)


@dataclass(frozen=True)
class Settings:
    """Limits the server enforces."""

    # Size of one dataset once loaded, measured as its Arrow buffer size.
    max_dataset_bytes: int = field(default_factory=_default_dataset_cap)
    # All datasets and pinned results together. Nothing is ever evicted to make room.
    max_total_bytes: int = field(default_factory=_default_total_budget)
    max_datasets: int = 50
    max_grids: int = 50  # open tabs at once, the same as max_datasets
    # Catalogs (names and types of a source database, plan decision 17): how many at once, and how
    # many rows (one per column of the source) each may hold. A large warehouse has a few hundred
    # thousand columns.
    max_catalogs: int = 20
    max_catalog_rows: int = 2_000_000
    # How long a connection's or blade's run (Test, Refresh, a table opened) may take before it is stopped:
    # 10 minutes (the owner, 2026-11-16: "timouts should default to 10 minutes").
    blade_timeout_seconds: float = 600.0
    # Catalogs load themselves in the background (a child process each): when a connection is saved, at
    # start-up (but not one that signs in with a browser window: that one on first use), and on first use;
    # so many at once.
    auto_load_catalogs: bool = True
    # The update check (services/updates.py): the one request that leaves the computer, at start and every
    # six hours, while the Settings switch is on (the owner's call, 2026-11-16). No feeds: never.
    update_feeds: tuple[str, ...] = field(default_factory=_update_feeds)
    # Start at sign-in (server/autostart.py) writes its entry under this home folder instead of the user's
    # own (tests); None: the user's.
    autostart_home: Path | None = None
    # Launch Claude (services/claude.py): a stand-in for finding and starting Claude (tests); None: the real
    # ones.
    claude_standin: Path | None = field(default_factory=_claude_standin)
    catalogs_at_once: int = 2
    # How long reading the vaults may hold up a Workbench kernel's start (it then starts without them).
    vault_timeout_seconds: float = 60.0
    # Size of a push request body. JSON is several times larger than the same data in
    # memory, so this cap is separate from max_dataset_bytes; otherwise a dataset well under
    # the dataset cap would be refused just for arriving as JSON.
    max_push_body_bytes: int = 2 * GIB
    max_window_rows: int = 1000
    # Longer text is cut in the grid; the detail view and exports carry the full value.
    max_cell_chars: int = 500
    # Excel's sheet limit: the SQL box shows a result as large as a worksheet can hold.
    max_sql_rows: int = EXCEL_MAX_ROWS
    # A connection's table named in a DuckDB query is read whole (every row the query needs, never its
    # first rows only): above this many rows (counted at the source, with the filters sent) it is refused,
    # with how to narrow it (domain/connection_tables.py too_many).
    max_connection_query_rows: int = field(default_factory=_default_query_rows)
    max_chart_points: int = 5_000
    # An analysis blade gets the grid's rows as a DataFrame in a child process: up to this many.
    max_analysis_rows: int = 2_000_000
    max_response_bytes: int = 8 * MIB
    # The SQL box sends its whole result at once (grid windows are paged), so it gets room for it.
    max_sql_response_bytes: int = 1 * GIB
    # Warn in the status bar at this share of any limit.
    warn_fraction: float = 0.8
    # Seconds a SQL box, a SQL step or an agent query may run before it is interrupted: 10 minutes.
    query_timeout_seconds: float = 600.0
    # How long an agent's snapshot request waits for the open page to draw and upload its PNG, and the
    # largest picture the server accepts back (a 4K screen at 2x is a few megabytes).
    snapshot_timeout_seconds: float = 30.0
    max_snapshot_bytes: int = 16 * MIB
    # The Key Finder joins every column of two tables, so it gets longer before it is stopped.
    key_finder_timeout_seconds: float = 600.0
    # The Key Finder's search for the most distinct column combination reads the grid's first
    # rows only, so a large table answers in seconds.
    key_finder_unique_rows: int = 400_000
    # The beta log (domain/beta_log.py): a request slower than this to answer is logged; the log keeps
    # about this many days and bytes (the oldest part goes first).
    beta_slow_seconds: float = 2.0
    beta_log_days: int = 7
    beta_log_bytes: int = 20 * MIB
    # A .sab project file (domain/sab_files.py): the largest file opened, how many entries it may hold,
    # and how much it may unpack to (its rows' Parquet included). Each entry is counted as it is read.
    max_project_file_bytes: int = 4 * GIB
    max_project_entries: int = 5_000
    max_project_unpacked_bytes: int = 8 * GIB
    # Where a .sab's working folder goes while it is open (None: the system's temporary folder).
    project_temp_dir: Path | None = None
    # Autosave (the project's switch): how often it looks; a change saves once it has settled for a look.
    autosave_seconds: float = 2.0
    # Worker threads running DuckDB queries. Grid windows jump ahead of profiling, SQL and
    # agent work in the queue (adapters/database.py).
    worker_threads: int = 4
    # The browser files: index.html, grid.css, and build/ from `npm run build`.
    web_root: Path = field(default=_PACKAGED_WEB if _PACKAGED_WEB.is_dir() else _REPO_WEB)
    # Where the audit log and the other state files live (plan section 18, question 5: user folder for now).
    state_dir: Path = field(default_factory=_state_dir)
    # Exports requested by an agent (MCP) land only here, never as a browser download.
    export_dir: Path = field(default_factory=lambda: _state_dir() / "exports")
    # Where the Workbench's Save as starts: the user's own folder, made the first time it is needed
    # (the file chooser's first look at it, or a save into it).
    workbench_dir: Path = field(default_factory=_workbench_dir)
    # Claude Code's folder: installed plugins that carry blades and tangs (packs) are read from here.
    claude_dir: Path = field(default_factory=_claude_dir)

    @property
    def blades_dir(self) -> Path:
        """Saved blades, one JSON file each (plan decision 14)."""
        return self.state_dir / "blades"

    @property
    def duckdb_memory_limit(self) -> str:
        """Working memory: twice the data budget (plan section 6a), never under 256 MiB so a
        small budget still leaves room for sorting. Spilling stays off."""
        return f"{max(256, (2 * self.max_total_bytes) // MIB)}MiB"
