"""The Scripts page's debugger (2026-11-21): the rules beside the kernel's own debugger (ipykernel's debugpy,
spoken to with the Jupyter debug protocol's debug_request, the Debug Adapter Protocol inside).

A script is debugged in its document's kernel: its text is dumped to the kernel's own file for it (dumpCell),
the breakpoints are set on that file, and the text runs as a cell; a stop's frames in that file are the
script's lines (the same text, so the same line numbers), any other a library's or another cell's. Breakpoints
are the page's (the gutter's): plain, conditional (`condition`), or a log point (`log`: a message with
`{expressions}`, printed instead of stopping). Pure: requests in, the protocol's arguments and the page's
shapes out.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

STEPS: dict[str, str] = {"over": "next", "into": "stepIn", "out": "stepOut", "continue": "continue"}
MAX_BREAKPOINTS = 200
MAX_TEXT = 500
MAX_VARIABLES = 300
MAX_OUTPUT_CHARS = 200_000
STATES: tuple[str, ...] = ("idle", "running", "paused", "ended")

INITIALIZE: dict[str, Any] = {
    "clientID": "swissarmybench",
    "clientName": "Swiss Army Bench",
    "adapterID": "python",
    "pathFormat": "path",
    "linesStartAt1": True,
    "columnsStartAt1": True,
    "supportsVariableType": True,
    "supportsVariablePaging": True,
    "supportsRunInTerminalRequest": False,
    "locale": "en",
}


class DebugError(ValueError):
    """A debugger request that cannot be taken, in plain words."""


@dataclass(frozen=True)
class Breakpoint:
    line: int
    condition: str = ""
    log: str = ""

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"line": self.line}
        if self.condition:
            out["condition"] = self.condition
        if self.log:
            out["log"] = self.log
        return out

    def protocol(self) -> dict[str, Any]:
        """As setBreakpoints takes it."""
        out: dict[str, Any] = {"line": self.line}
        if self.condition:
            out["condition"] = self.condition
        if self.log:
            out["logMessage"] = self.log
        return out


def breakpoints_of(raw: Any) -> list[Breakpoint]:
    """The page's or the agent's breakpoints, checked: [{line, condition?, log?}] (a bare line number is a
    plain one); one per line, the last given wins, in line order."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise DebugError('Breakpoints are a list: [{"line": 4}, {"line": 9, "condition": "n > 3"}].')
    if len(raw) > MAX_BREAKPOINTS:
        raise DebugError(f"At most {MAX_BREAKPOINTS} breakpoints.")
    found: dict[int, Breakpoint] = {}
    for item in raw:
        row = {"line": item} if isinstance(item, int) else item
        if not isinstance(row, Mapping):
            raise DebugError("Each breakpoint is a line number or {line, condition?, log?}.")
        line = row.get("line")
        if not isinstance(line, int) or isinstance(line, bool) or line < 1:
            raise DebugError("A breakpoint's line is a number from 1.")
        texts = {}
        for key in ("condition", "log"):
            value = row.get(key) or ""
            if not isinstance(value, str) or len(value) > MAX_TEXT or "\n" in value:
                raise DebugError(f"A breakpoint's {key} is one line of at most {MAX_TEXT} characters.")
            texts[key] = value.strip()
        found[line] = Breakpoint(line, texts["condition"], texts["log"])
    return [found[k] for k in sorted(found)]


def step_command(action: Any) -> str:
    """The protocol's request for a step: over (next), into (stepIn), out (stepOut), continue."""
    if action not in STEPS:
        raise DebugError(f"A step is one of {', '.join(STEPS)}.")
    return STEPS[str(action)]


def frames_of(stack: Sequence[Mapping[str, Any]], source: str, document: str | None) -> list[dict[str, Any]]:
    """A stop's call stack for the page: each frame's id, name, line, and whose it is: `yours` (the script,
    its own line), else the file it is in (a library's, another cell's)."""
    out: list[dict[str, Any]] = []
    for frame in stack:
        path = str((frame.get("source") or {}).get("path") or "")
        yours = bool(source) and path == source
        out.append(
            {
                "id": frame.get("id"),
                "name": str(frame.get("name") or ""),
                "line": int(frame.get("line") or 0),
                "yours": yours,
                "path": document if yours else path,
            }
        )
    return out


def variables_of(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The protocol's variables as the page lists them: name, value, type, and `reference` (non-zero: it
    unfolds). The debugger's own entries (special and function variables) are left out."""
    out: list[dict[str, Any]] = []
    for row in rows[:MAX_VARIABLES]:
        name = str(row.get("name") or "")
        if not name or name in ("special variables", "function variables"):
            continue
        out.append(
            {
                "name": name,
                "value": str(row.get("value") or "")[:2000],
                "type": str(row.get("type") or ""),
                "reference": int(row.get("variablesReference") or 0),
            }
        )
    return out


@dataclass
class Session:
    """One kernel's debugging: the script, its dumped file, its breakpoints, where it is."""

    kernel: str
    document: str | None = None
    source: str = ""
    breakpoints: list[Breakpoint] = field(default_factory=list)
    state: str = "idle"
    thread: int | None = None
    frames: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""
    output: str = ""
    ok: bool | None = None
    error: str = ""

    def heard(self, text: str) -> None:
        self.output = (self.output + text)[-MAX_OUTPUT_CHARS:]

    def to_json(self) -> dict[str, Any]:
        line = next((f["line"] for f in self.frames if f.get("yours")), None)
        return {
            "kernel": self.kernel,
            "document": self.document,
            "state": self.state,
            "reason": self.reason,
            "line": line if self.state == "paused" else None,
            "frames": self.frames if self.state == "paused" else [],
            "breakpoints": [b.to_json() for b in self.breakpoints],
            "output": self.output[-20_000:],
            "ok": self.ok,
            "error": self.error,
        }
