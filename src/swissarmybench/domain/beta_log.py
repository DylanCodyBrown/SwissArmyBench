"""The beta log's rules: what an event may hold, and the redaction that keeps the user's data out of it
(the owner, 2026-11-15: "a log that I can dump back to you that doesn't expose data but lets you have
enough info to fix issues the server runs into").

An event is one JSON line: server errors (their stack as file:line and function names), slow requests
(the route's pattern and the time), the app's child processes (kernels, Streamlit, blades, catalogs:
starts, ends, crashes, exit codes), page errors, the beta notes, and the app's version, OS and Python.

Never in it: cell values or rows, SQL or code, secrets, tokens, environment values, file contents, and
the user's names in paths (the home folder is `~`, a path's folders and file name hidden). Table and
column names are aliased (`table#1`, `col#3`), the mapping kept in memory only. Exception messages
are redacted: quoted text, long numbers, e-mail addresses, key=value secrets and long tokens become
the HIDDEN mark; a SQL echo (DuckDB's `LINE 1: ...`) is dropped.

Beta mode is one switch for the log and the notes together. BETA_MODE_DEFAULT is the default for a
server with no saved choice and no SWISSARMYBENCH_BETA: on for the 0.0.1 beta; the release after the
beta flips this one constant (docs/ideas.md, "Beta mode").

Pure rules: the caller gives the clock, the home folder and the secrets.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

# The default when nothing is saved and no environment variable says otherwise. ONE line to flip.
BETA_MODE_DEFAULT: bool = True

HIDDEN = "\u2039\u2026\u203a"  # a small "hidden" mark: single angle quotes around an ellipsis
# The kinds of event, in the order the guide lists them.
KINDS: tuple[str, ...] = ("start", "stop", "error", "refused", "slow", "process", "page", "note", "dropped")
PROCESS_KINDS: tuple[str, ...] = ("kernel", "streamlit", "blade", "catalog", "server")
PROCESS_EVENTS: tuple[str, ...] = ("start", "end", "crash", "failed", "restart", "timeout", "cancelled")

MAX_MESSAGE_CHARS = 600
MAX_FRAMES = 40
MAX_NOTE_CHARS = 4000
MAX_ACTIONS = 20
# Events a minute past which the log drops them (and says how many it dropped). Notes are never dropped.
EVENTS_PER_MINUTE = 600


class BetaError(ValueError):
    """A note or a page error that is not in the shape the page sends."""


# ===== names: aliased, the mapping in memory only =====


@dataclass
class Aliases:
    """Each table and column name the app knows, as a short stable alias."""

    _by_kind: dict[str, dict[str, str]] = field(default_factory=dict)
    _plain: dict[str, str] = field(default_factory=dict)  # a name that is one word, by its case fold
    _other: list[tuple[str, str]] = field(default_factory=list)  # names with spaces or signs, longest first

    PREFIX: ClassVar[dict[str, str]] = {"table": "table", "column": "col", "source": "source"}

    def alias(self, kind: str, name: str) -> str:
        names = self._by_kind.setdefault(kind, {})
        key = name.casefold()
        if key not in names:
            names[key] = f"{self.PREFIX[kind]}#{len(names) + 1}"
            self._index(name, names[key])
        return names[key]

    def learn(self, names: Mapping[str, Iterable[str]]) -> None:
        """Every name the app holds now, by kind ("table", "column", "source"). Tables first, so a name
        that is a table and a column reads as the table."""
        for kind in ("table", "source", "column"):
            for name in names.get(kind, ()):
                if name and (kind == "table" or name.casefold() not in self._plain):
                    self.alias(kind, name)

    def _index(self, name: str, alias: str) -> None:
        if re.fullmatch(r"\w+", name):
            self._plain.setdefault(name.casefold(), alias)
        elif len(name) >= 2:
            self._other.append((name, alias))
            self._other.sort(key=lambda pair: -len(pair[0]))

    def replace(self, text: str) -> str:
        """`text` with every known name as its alias (whole words only)."""
        for name, alias in self._other:
            text = re.sub(re.escape(name), alias, text, flags=re.IGNORECASE)
        if not self._plain:
            return text
        return re.sub(r"\w+", lambda m: self._plain.get(m.group(0).casefold(), m.group(0)), text)


# ===== redaction =====

_ALIAS = re.compile(r"(?:table|col|source)#\d+")
_SQL_ECHO = re.compile(r"^\s*(LINE \d+:.*|\^+\s*)$", re.MULTILINE)
_QUOTED = re.compile(
    r"'[^'\n]{0,500}'|\"[^\"\n]{0,500}\"|`[^`\n]{0,500}`|\u2018[^\u2019\n]{0,500}\u2019|\u201c[^\u201d\n]{0,500}\u201d"
)
_KEYED = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret|authorization)"
    r"(\s*[=:]\s*)([^\s,;&]+)"
)
_BEARER = re.compile(r"(?i)\b(bearer|basic)(\s+)([A-Za-z0-9+/=._\-]{6,})")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_LONG_TOKEN = re.compile(
    r"(?<![\w#])(?=[A-Za-z0-9+/_\-]*\d)(?=[A-Za-z0-9+/_\-]*[A-Za-z])[A-Za-z0-9+/_\-]{24,}={0,2}"
)
_NUMBER = re.compile(r"(?<![\w#])[-+]?\d[\d,._]*\d(?![\w])")
# A file's name on its own (a notebook's tab, "acme_q3.csv"): the user's word, its kind kept.
_FILE_NAME = re.compile(
    r"(?<![\w/\\.\-])[\w\-.]{0,80}?[\w\-]\.(ipynb|py|csv|tsv|xlsx|xlsm|xls|parquet|json|zip|sql|txt|dax|pbix)(?![\w])",
    re.IGNORECASE,
)
_WINDOWS_PATH = re.compile(r"(?<![\w])[A-Za-z]:[\\/][^\s'\"<>|*?]*")
_UNIX_PATH = re.compile(r"(?<![\w:/.~])(~/|/)(?:[^\s'\"<>/]+/)*[^\s'\"<>/]*")


def _digits(text: str) -> int:
    return sum(ch.isdigit() for ch in text)


def mask_path(path: str) -> str:
    """A path's folders and file name as HIDDEN, its extension kept (`~/<hidden>/<hidden>.csv`). The
    home folder is already `~` by then."""
    parts = re.split(r"[\\/]", path)
    shown = []
    for i, part in enumerate(parts):
        if part in ("", "~") or (i == 0 and re.fullmatch(r"[A-Za-z]:", part)):
            shown.append(part)
            continue
        stem, dot, ext = part.rpartition(".")
        shown.append(f"{HIDDEN}.{ext}" if dot and stem and re.fullmatch(r"[A-Za-z0-9]{1,8}", ext) else HIDDEN)
    return "/".join(shown)


def _home_forms(home: str) -> list[str]:
    if not home or len(home) < 3:
        return []
    forms = {home, home.replace("\\", "/"), home.replace("/", "\\")}
    return sorted(forms, key=len, reverse=True)


def redact(text: str, aliases: Aliases | None = None, home: str = "", secrets: Iterable[str] = ()) -> str:
    """A message with nothing of the user's left in it, at most MAX_MESSAGE_CHARS long."""
    text = str(text)[: MAX_MESSAGE_CHARS * 4]
    for secret in sorted({s for s in secrets if s and len(s) >= 6}, key=len, reverse=True):
        text = text.replace(secret, HIDDEN)
    for form in _home_forms(home):
        text = re.sub(re.escape(form), "~", text, flags=re.IGNORECASE)
    text = _SQL_ECHO.sub("", text)
    if aliases is not None:
        text = aliases.replace(text)
    text = _KEYED.sub(lambda m: f"{m.group(1)}{m.group(2)}{HIDDEN}", text)
    text = _BEARER.sub(lambda m: f"{m.group(1)}{m.group(2)}{HIDDEN}", text)

    def quoted(match: re.Match[str]) -> str:
        inner = match.group(0)[1:-1]
        return match.group(0) if _ALIAS.fullmatch(inner) else match.group(0)[0] + HIDDEN + match.group(0)[-1]

    text = _QUOTED.sub(quoted, text)
    text = _WINDOWS_PATH.sub(lambda m: mask_path(m.group(0)), text)
    text = _UNIX_PATH.sub(
        lambda m: (
            mask_path(m.group(0)) if m.group(0).count("/") >= 2 or m.group(0).startswith("~/") else m.group(0)
        ),
        text,
    )
    text = _FILE_NAME.sub(lambda m: f"{HIDDEN}.{m.group(1)}", text)
    text = _EMAIL.sub(HIDDEN, text)
    text = _LONG_TOKEN.sub(HIDDEN, text)
    text = _NUMBER.sub(lambda m: HIDDEN if _digits(m.group(0)) >= 5 else m.group(0), text)
    text = re.sub(r"\n{2,}", "\n", text).strip()
    return text[:MAX_MESSAGE_CHARS] + ("…" if len(text) > MAX_MESSAGE_CHARS else "")


def label(text: Any, aliases: Aliases | None, limit: int = 80) -> str:
    """A short piece of the page's own text (a button's words, a tab's name), redacted, on one line."""
    if not isinstance(text, str):
        return ""
    one = " ".join(text.split())[: limit * 2]
    return redact(one, aliases)[:limit]


# ===== stacks =====


def frame(filename: str, line: int | None, function: str) -> str:
    """One server frame as `swissarmybench/services/grids.py:120 in rows`: the app's files from its
    package, a library's from its own folder, the standard library's as `python/...`, anything else
    (the user's own file) as HIDDEN with its extension."""
    path = filename.replace("\\", "/")
    for marker in ("/site-packages/", "/dist-packages/"):
        if marker in path:
            path = path.split(marker, 1)[1]
            break
    else:
        if "/swissarmybench/" in path:
            path = "swissarmybench/" + path.rsplit("/swissarmybench/", 1)[1]
        elif re.search(r"/lib/python3[\d.]*/", path):
            path = "python/" + re.split(r"/lib/python3[\d.]*/", path, maxsplit=1)[1]
        elif re.search(r"/Lib/", path):
            path = "python/" + path.split("/Lib/", 1)[1]
        elif path.startswith("<"):
            path = path[:40]
        else:
            path = mask_path(path.rsplit("/", 1)[-1])
    name = re.sub(r"[^\w<>.]", "", function)[:60]
    return f"{path}:{line or 0} in {name}"


def frames(entries: Iterable[tuple[str, int | None, str]]) -> list[str]:
    """A traceback's frames (file, line, function), innermost last, at most MAX_FRAMES (the last ones)."""
    shown = [frame(file, line, function) for file, line, function in entries]
    return shown[-MAX_FRAMES:]


_CHROME_FRAME = re.compile(
    r"^\s*at (?:(?P<fn>[^(]+?) \()?(?P<url>[^()\s]+?):(?P<line>\d+):(?P<col>\d+)\)?\s*$"
)
_FIREFOX_FRAME = re.compile(r"^\s*(?P<fn>[^@]*)@(?P<url>\S+?):(?P<line>\d+):(?P<col>\d+)\s*$")


def page_frames(stack: Any) -> list[str]:
    """A page error's stack as `fn @ /static/build/main.js:1:2345` lines: only frames in the app's own
    files (by their path on this server, no host, no query); a line that is not a frame is dropped."""
    if not isinstance(stack, str):
        return []
    shown: list[str] = []
    for line in stack.splitlines()[:80]:
        found = _CHROME_FRAME.match(line) or _FIREFOX_FRAME.match(line)
        if not found:
            continue
        url = re.sub(r"^[a-z]+://[^/]+", "", found.group("url")).split("?", 1)[0].split("#", 1)[0]
        if not re.fullmatch(r"/static/[\w./\-]+\.js", url):
            url = HIDDEN
        fn = re.sub(r"[^\w$.<> ]", "", (found.group("fn") or "").strip())[:60] or "?"
        shown.append(f"{fn} @ {url}:{found.group('line')}:{found.group('col')}")
    return shown[:MAX_FRAMES]


# ===== events =====

_SLUG = re.compile(r"[^\w.\-]")


def slug(value: Any, limit: int = 40) -> str:
    return _SLUG.sub("", value)[:limit] if isinstance(value, str) else ""


def page_error(body: Any, aliases: Aliases | None, home: str = "") -> dict[str, Any]:
    """A page's error as the page sends it ({message, stack, page, window, kind}), redacted."""
    if not isinstance(body, dict) or not isinstance(body.get("message"), str):
        raise BetaError('Send {"message": "...", "stack": "...", "page": "grid"}.')
    return {
        "kind": "page",
        "page": slug(body.get("page")),
        "window": slug(body.get("window")),
        "what": "rejection" if body.get("kind") == "rejection" else "error",
        "message": redact(body["message"], aliases, home),
        "frames": page_frames(body.get("stack")),
    }


def _box(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {k: int(v) for k, v in value.items() if k in ("x", "y", "w", "h") and isinstance(v, int | float)}


def _css_path(value: Any, aliases: Aliases | None) -> str:
    """The element's path through the app's own ids and classes (`div.ribbon > button.btn`), redacted
    like a message, then only the signs a CSS path uses."""
    if not isinstance(value, str):
        return ""
    kept = redact(" ".join(value.split())[:600], aliases)
    return re.sub(rf"[^\w#.\->: \[\]=\"{HIDDEN}]", "", kept)[:400]


# Where the page shows the user's data: an element there never has its words or its name kept, whatever
# the page sent (the page sends none; this is the server's own guard).
DATA_ROLES = frozenset({"gridcell", "cell", "row", "textbox", "searchbox", "combobox", "document", "log"})
DATA_PLACES = ("ag-cell", "ag-row", "wb-output", "monaco", "value-viewer", "sab-card-body", "wb-err")


def element(value: Any, aliases: Aliases | None) -> dict[str, Any]:
    """The picked element's description: role, name (aria-label or title), its words (a button's, a
    tab's; never a cell's), its CSS path through the app's ids and classes, and its box."""
    if not isinstance(value, dict):
        return {}
    role, path = slug(value.get("role"), 30), _css_path(value.get("path"), aliases)
    data = role in DATA_ROLES or any(place in path for place in DATA_PLACES)
    shown = {
        "tag": slug(value.get("tag"), 20),
        "role": role,
        "name": "" if data else label(value.get("name"), aliases),
        "text": "" if data else label(value.get("text"), aliases),
        "path": path,
        "box": _box(value.get("box")),
    }
    return {k: v for k, v in shown.items() if v}


def note(body: Any, aliases: Aliases | None) -> dict[str, Any]:
    """A note as the page sends it. The note's own words are kept as the user typed them; everything the
    page worked out (the element, the panels, the actions) is redacted."""
    if not isinstance(body, dict):
        raise BetaError('Send {"text": "what is wrong", "element": {...}}.')
    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        raise BetaError("Say what is wrong in the note.")
    if len(text) > MAX_NOTE_CHARS:
        raise BetaError(f"A note is at most {MAX_NOTE_CHARS:,} characters.")

    def listed(key: str, most: int, limit: int) -> list[str]:
        items = body.get(key)
        return [
            shown
            for item in (items if isinstance(items, list) else [])[:most]
            if (shown := label(item, aliases, limit))
        ]

    return {
        "kind": "note",
        "text": text.strip(),
        "page": slug(body.get("page")),
        "window": slug(body.get("window")),
        "element": element(body.get("element"), aliases),
        "panels": listed("panels", 40, 40),
        "tabs": listed("tabs", 40, 40),
        "actions": listed("actions", MAX_ACTIONS, 80),
        "page_errors": [
            e
            for e in (body.get("page_errors") or [])[:10]
            if isinstance(e, str) and re.fullmatch(r"e[0-9a-f]{6,16}", e)
        ],
        "viewport": _box(body.get("viewport")),
    }


def process(
    kind: str,
    event: str,
    code: int | None = None,
    seconds: float | None = None,
    reason: str = "",
    aliases: Aliases | None = None,
    home: str = "",
) -> dict[str, Any]:
    """A child process's start, end, crash, failed start, restart or timeout."""
    entry: dict[str, Any] = {
        "kind": "process",
        "process": kind if kind in PROCESS_KINDS else "other",
        "event": event if event in PROCESS_EVENTS else "end",
    }
    if code is not None:
        entry["exit_code"] = int(code)
    if seconds is not None:
        entry["seconds"] = round(float(seconds), 3)
    if reason:
        entry["reason"] = redact(reason, aliases, home)
    return entry


# ===== reading it back =====


def since_seconds(value: Any) -> float | None:
    """A look-back as the agent gives it: "90m", "2h", "3d", "45s" (None: everything)."""
    if value in (None, ""):
        return None
    found = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smhd]?)\s*", str(value))
    if not found:
        raise BetaError('since is a look-back like "30m", "2h" or "7d".')
    return float(found.group(1)) * {"": 60, "s": 1, "m": 60, "h": 3600, "d": 86400}[found.group(2)]


def kinds_of(value: Any) -> set[str] | None:
    """Kinds as the agent gives them: "error,page" or ["note"] (None: every kind)."""
    if value in (None, "", []):
        return None
    listed = value.split(",") if isinstance(value, str) else value if isinstance(value, list) else []
    chosen = {str(k).strip() for k in listed if str(k).strip()}
    unknown = sorted(chosen - set(KINDS))
    if unknown:
        raise BetaError(f"No event kind {unknown[0]!r}. The kinds: {', '.join(KINDS)}.")
    return chosen


@dataclass
class RateCap:
    """At most `per_minute` events in any minute; past that they are counted, not written."""

    per_minute: int = EVENTS_PER_MINUTE
    _window: float = 0.0
    _count: int = 0
    dropped: int = 0

    def allow(self, now: float) -> bool:
        if now - self._window >= 60:
            self._window, self._count = now, 0
        if self._count >= self.per_minute:
            self.dropped += 1
            return False
        self._count += 1
        return True

    def take_dropped(self) -> int:
        dropped, self.dropped = self.dropped, 0
        return dropped
