"""Launch Claude's files (services/claude.py): the folder Claude Code starts in, the user's choices, and
Claude Desktop's config file.

- `~/.swissarmybench/claude/<project or no-project>/`: CLAUDE.md, .mcp.json, .claude/settings.json,
  written again at each launch (metadata only: names, counts, types, steps in words; no row, no secret);
  its context.md rewritten while the app runs, atomically and only when its text changes, once the
  folder exists (a launch made it).
- `~/.swissarmybench/claude.json`: which Claude Code and Claude Desktop the user chose, bypass permissions
  mode (off unless turned on), and the Desktop config files the user allowed this app to write into.
- A Claude Desktop install's claude_desktop_config.json: a dated backup first, then the file with the
  `swissarmybench` server set (written beside it, then moved over it), every other entry kept.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

INDEX = Path(__file__).resolve().parents[1] / "mcp" / "index.md"


class ClaudeFiles:
    def __init__(self, root: Path, choices: Path | None) -> None:
        self.root = root  # the state folder's claude/
        self._choices = choices  # claude.json; None: kept in memory (tests)
        self._memory: dict[str, Any] = {}
        # The index's and the guide's pages, by path: (modification time and size, text). Read again only
        # when the file changed: context.md is built every few seconds while the app runs.
        self._pages: dict[Path, tuple[tuple[int, int], str]] = {}

    def _page(self, path: Path) -> str:
        """A page's text, kept by its stamp. Raises OSError as reading it does."""
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        kept = self._pages.get(path)
        if kept is None or kept[0] != stamp:
            kept = (stamp, path.read_text(encoding="utf-8"))
            self._pages[path] = kept
        return kept[1]

    # ===== the folder Claude Code starts in =====

    def prepare(self, name: str, files: dict[str, str]) -> str:
        """Write `files` (relative path -> text) into claude/<name>/; the folder's path."""
        folder = self.root / name
        for relative, text in files.items():
            target = folder / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        return str(folder)

    def write_context(self, name: str, text: str, make: bool = False) -> str | None:
        """claude/<name>/context.md: written beside, then moved over, and only when its text changed; only
        into a folder a launch made (`make`: the launch itself). Its path, or None (no folder)."""
        folder = self.root / name
        if not folder.is_dir():
            if not make:
                return None
            folder.mkdir(parents=True, exist_ok=True)
        target = folder / "context.md"
        try:
            if target.read_text(encoding="utf-8") == text:
                return str(target)
        except OSError:
            pass
        temporary = folder / ".context.md.tmp"
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, target)
        return str(target)

    def context_path(self, name: str) -> str | None:
        """claude/<name>/context.md, when it is there."""
        target = self.root / name / "context.md"
        return str(target) if target.is_file() else None

    def guide(self, topic: str) -> str:
        """A guide topic's page (mcp/guide/<topic>.md), "" when there is none."""
        try:
            return self._page(INDEX.parent / "guide" / f"{topic}.md")
        except OSError:
            return ""

    def index(self) -> str:
        """The MCP server's index (mcp/index.md): the folder's CLAUDE.md carries it whole."""
        try:
            return self._page(INDEX)
        except OSError:
            return "Read the resource swissarmybench://index (or call the `guide` tool) first."

    # ===== the user's choices (claude.json) =====

    def load(self) -> dict[str, Any]:
        if self._choices is None:
            return dict(self._memory)
        try:
            data = json.loads(self._choices.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, data: dict[str, Any]) -> None:
        if self._choices is None:
            self._memory = dict(data)
            return
        self._choices.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._choices.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(temporary, self._choices)

    # ===== files the user picks, and Claude Desktop's config =====

    def exists(self, path: str) -> bool:
        return bool(path) and Path(path).expanduser().exists()

    def runnable(self, path: str) -> bool:
        """A file (or a macOS .app bundle) that can be started."""
        found = Path(path).expanduser()
        return found.is_file() or (found.is_dir() and found.suffix.lower() == ".app")

    def read(self, path: str) -> str | None:
        try:
            return Path(path).expanduser().read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def write_config(self, path: str, text: str) -> str | None:
        """Write another app's config file: a dated copy of the old one first (its path, or None when there
        was none), then the new text beside it, moved over it in one step."""
        target = Path(path).expanduser()
        backup: Path | None = None
        if target.exists():
            backup = target.with_name(f"{target.name}.{time.strftime('%Y%m%d-%H%M%S')}.bak")
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".swissarmybench.tmp")
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, target)
        return str(backup) if backup else None
