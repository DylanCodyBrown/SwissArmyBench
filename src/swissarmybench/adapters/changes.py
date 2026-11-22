"""The open project's .sab/changes.jsonl (services/changes.py): read whole, and one line appended per change
as it happens (names, types and fingerprints, never a value)."""

from __future__ import annotations

from pathlib import Path


class ChangeFiles:
    def read(self, path: str) -> str | None:
        try:
            return Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def append(self, path: str, text: str) -> None:
        target = Path(path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        except OSError:
            pass  # a project folder that went away: the change is said on the Session page all the same
