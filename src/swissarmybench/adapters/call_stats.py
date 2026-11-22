"""The open project's .sab/stats.json (services/call_stats.py): read, and written atomically only when its
bytes change (the figures: names, times and sizes, never a value)."""

from __future__ import annotations

from pathlib import Path

from swissarmybench.adapters.atomic_files import write_atomic


class StatsFiles:
    def read(self, path: str) -> str | None:
        try:
            return Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def write(self, path: str, text: str) -> None:
        try:
            write_atomic(path, text, if_changed=True)
        except OSError:
            pass  # a project folder that went away: the figures stay in memory
