"""Updates at the edge: the one GET of a release list, the switch's file (update.json) and the helper's
note of a failed update (update_failed.json), read once at start.

The GET sends nothing but itself: no cookies, no identifiers, Python's own User-Agent; the answer is
capped at 8 MB of JSON.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

MAX_ANSWER_BYTES: int = 8 * 1024 * 1024
TIMEOUT_SECONDS: float = 15.0


class HttpFeed:
    def fetch(self, url: str) -> Any:
        if not url.startswith(("https://", "http://127.0.0.1:", "http://localhost:")):
            raise ValueError("A release list is read over https (or from this computer, in tests).")
        request = urllib.request.Request(url, headers={"Accept": "application/json"})  # noqa: S310
        # A fixed https address (PyPI, GitHub), or a stand-in on 127.0.0.1 in tests.
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as answer:  # noqa: S310
            body = answer.read(MAX_ANSWER_BYTES + 1)
        if len(body) > MAX_ANSWER_BYTES:
            raise ValueError("The release list is too large.")
        return json.loads(body)


class UpdateSwitchFile:
    """Check for updates as the user last set it: update.json in the state folder (None: never set).
    Without a state folder (a test's server) it is kept in memory."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._held: bool | None = None

    def read(self) -> bool | None:
        if self.path is None or not self.path.is_file():
            return self._held
        try:
            on = json.loads(self.path.read_text(encoding="utf-8")).get("check")
        except (OSError, ValueError, AttributeError):
            return None
        return on if isinstance(on, bool) else None

    def write(self, on: bool) -> None:
        self._held = on
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"check": on}) + "\n", encoding="utf-8")


def take_server_events(path: Path | None) -> list[dict[str, Any]]:
    """What the tray saw while no server could log it (a crash, a restart, giving up), removed once read."""
    if path is None or not path.is_file():
        return []
    try:
        events: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        events = []
    try:
        path.unlink()
    except OSError:
        pass
    if not isinstance(events, list):
        return []
    return [e for e in events[-50:] if isinstance(e, dict) and isinstance(e.get("event"), str)]


def take_failure_note(path: Path | None) -> dict[str, Any] | None:
    """The helper's note of an update that failed ({"version", "reason"}), removed once read."""
    if path is None or not path.is_file():
        return None
    try:
        note: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        note = None
    try:
        path.unlink()
    except OSError:
        pass
    if not isinstance(note, dict) or not isinstance(note.get("version"), str):
        return None
    reason = note.get("reason")
    return {"version": note["version"][:64], "reason": str(reason or "")[:2000]}
