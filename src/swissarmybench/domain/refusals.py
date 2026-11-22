"""One shape for every refusal the server answers (design principle 9.5, the owner 2026-11-18: "Errors should
be presented to users in one uniform way as much as possible").

Every route's refusal is JSON of the same fields, so a page draws an error without knowing which route it
came from, and the agent reads the same words:

    {"error":   what happened, one plain sentence,
     "where":   the named thing (a connection, table, file, cell), when known,
     "fixes":   [{"label": "Install now", "action": "install", ...}, ...], the fixes the server knows,
     "details": the source's own message (a driver's words, DuckDB's), folded behind Details on the page}

Fields a page or the agent already reads stay beside them (`missing`, `missing_variables`, `needs`,
`install_here`). A fix's `action` is one of ACTIONS; the page turns each into a button, the agent reads its
`command` where one is named.

Standard library only.
"""

from __future__ import annotations

import re
from typing import Any

# What a fix does, as the page reads it (web/src/errorNote.ts):
#   install        Install now: the missing packages (`missing` beside it)
#   set_variable   Set it: the Add variable form with `name`
#   sign_in        Sign in: the connection's sign-in (`connection`)
#   open_settings  Open its settings: the connection's form (`connection`)
#   try_again      Try again: the same request once more
ACTIONS: tuple[str, ...] = ("install", "set_variable", "sign_in", "open_settings", "try_again")


def fix(label: str, action: str, **more: Any) -> dict[str, Any]:
    """One fix: its button's words, what it does, and what that needs (a name, a connection, a command)."""
    if action not in ACTIONS:
        raise ValueError(f"A fix's action is one of {', '.join(ACTIONS)}.")
    return {"label": label, "action": action, **{k: v for k, v in more.items() if v is not None}}


def install(command: str | None = None) -> dict[str, Any]:
    return fix("Install now", "install", command=command)


def set_variable(name: str) -> dict[str, Any]:
    return fix("Set it", "set_variable", name=name, command="variables_set", page="variables")


def sign_in(connection: str) -> dict[str, Any]:
    return fix("Sign in", "sign_in", connection=connection)


def open_settings(connection: str) -> dict[str, Any]:
    return fix("Open its settings", "open_settings", connection=connection, command="connections_get")


def try_again() -> dict[str, Any]:
    return fix("Try again", "try_again")


class Explained(Exception):
    """An error that knows more than its words: where it happened, the fixes, the source's own message.
    The use cases' outcomes (Refused, NotFound, Conflict, TimedOut) are Explained, so any of them can say
    where and how to fix; a plain `raise NotFound("...")` is the same as before."""

    def __init__(
        self,
        what: str = "",
        *,
        where: str | None = None,
        fixes: list[dict[str, Any]] | None = None,
        details: str | None = None,
    ) -> None:
        super().__init__(what)
        self.where = where
        self.fixes = list(fixes or [])
        self.details = details


def declined(otherwise: str) -> str:
    """The one sentence the agent reads when the user said no to its Allow, or did not answer: what stays as
    it is after the colon ("nothing was exported")."""
    return f"The user declined (or did not answer): {otherwise.strip().rstrip('.')}."


def first_sentence(message: str, limit: int = 240) -> str:
    """The first line of a long message, cut at a sentence when it runs past `limit` (the rest is details)."""
    line = message.strip().split("\n", 1)[0].strip()
    if len(line) <= limit:
        return line
    stop = line[:limit].rfind(". ")
    return line[: stop + 1] if stop > 40 else line[: limit - 1] + "…"


_RUN_FAILED = re.compile(
    r"^(?P<what>.+?) failed: (?P<kind>\w+): (?P<said>.+?)(?P<line> \(line \d+\))?$", re.S
)


def run_failure(message: str) -> tuple[str, str | None]:
    """A blade's or connection's run that failed (adapters/blade_run.py's "Shop failed: OperationalError:
    unable to open database file (line 5)") as the shape's sentence ("Shop failed: unable to open database
    file.") and the source's own words ("OperationalError: unable to open database file (line 5)")."""
    found = _RUN_FAILED.match(message.strip())
    if not found or "\n" in found["said"]:
        return message, None
    said = found["said"].rstrip(".")
    return f"{found['what']} failed: {said}.", f"{found['kind']}: {found['said']}{found['line'] or ''}"


def shape(
    what: str,
    *,
    where: str | None = None,
    fixes: list[dict[str, Any]] | None = None,
    details: str | None = None,
    **kept: Any,
) -> dict[str, Any]:
    """The one refusal: `error` is one plain sentence; a longer message keeps its whole text in `details`.
    `kept` carries today's fields beside it (missing, missing_variables, needs, install_here)."""
    words = what.strip() or "Something went wrong."
    sentence = first_sentence(words)
    if sentence != words and not details:
        details = words
    out: dict[str, Any] = {"error": sentence}
    if where:
        out["where"] = where
    if fixes:
        out["fixes"] = fixes
    if details and details.strip() and details.strip() != sentence:
        out["details"] = details.strip()
    out |= {k: v for k, v in kept.items() if v is not None}
    return out


def of(error: BaseException, what: str | None = None, **kept: Any) -> dict[str, Any]:
    """An error read into the shape: an Explained one's where, fixes and details; anything else its words."""
    words = str(error) if what is None else what
    if isinstance(error, Explained):
        return shape(words, where=error.where, fixes=error.fixes, details=error.details, **kept)
    return shape(words or type(error).__name__, **kept)
