"""Pop out any page or any table into a window of its own (the owner, 2026-11-27).

"I should be able to pop out any page or any grid into a new tab of its own and that grid or page should go
blank on the original app with a reattach button in the pane to bring it back." / "Grids should have a
reattach button to bring them back."

One thing popped out is one entry: its key (`page:connections`, `table:<grid id>`, `doc:<path>`), the name a
person reads, and the address of this app that shows it (what the window opens, and where it is now: the
window says so as it moves, so Reattach brings it back in its current state). It is live in one place only:
its own window, named WINDOW_PREFIX + key so every window finds it by name; every other window shows the
placeholder there. Kept in memory only, never written to disk.

Standard library only; no I/O, no clock.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

PAGE = "page"
TABLE = "table"
DOCUMENT = "doc"
KINDS: tuple[str, ...] = (PAGE, TABLE, DOCUMENT)

# A popped-out window's name: the pages find it by it (window.open's target), as the home window by sab-home.
WINDOW_PREFIX = "sab-pop:"
NOTICE = "pop_outs"  # the whole list, to every window, each time it changes
SHOW_NOTICE = "pop_out_show"  # the popped-out window comes to the front
OPEN_NOTICE = "pop_out_open"  # one main window opens the window (the agent's pop out: a page opens windows)
FRONT_NOTICE = "pop_out_front"  # one main window shows what was reattached from its own window
SAID = "pop_out"  # what a popped-out window says on its socket: its key, its name, where it is now

# How long a window just asked for may take to connect before its page or table shows in its old place
# again (a blocked pop-up, a window that never loads), and how long a popped-out window's socket may be shut
# (a reload) before it counts as closed.
CONNECT_SECONDS: float = 30.0
RELOAD_SECONDS: float = 8.0

MAX_ID = 400
MAX_NAME = 160
MAX_ADDRESS = 2000
MAX_SAID = 4096
_PAGE_WORD = re.compile(r"^[a-z0-9][a-z0-9_-]{0,59}$")
# A page's word as the agent writes it and the kind of window its address makes (WindowPlace.KindOf).
PAGE_WORDS: dict[str, str] = {"projects": "home", "start": "home", "data": "catalog", "grids": "tables"}
PAGE_NAMES: dict[str, str] = {
    "home": "Home",
    "apis": "APIs",
    "catalog": "Catalog",
    "tables": "Tables",
    "erd": "ERD",
    "codeapp": "Code App",
}


class PopOutError(ValueError):
    """What was sent names no page or table, or an address that is not this app's."""


@dataclass
class Entry:
    """One page, table or document in a window of its own."""

    key: str
    name: str
    address: str
    connected: bool = False
    seen: bool = False  # its window connected at least once

    @property
    def kind(self) -> str:
        return self.key.partition(":")[0]

    def said(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "name": self.name,
            "address": self.address,
            "connected": self.connected,
            "placeholder": placeholder(self.name),
        }


def placeholder(name: str) -> str:
    """What the old place says while its page or table is in a window of its own."""
    return f"{name} is open in its own window"


def window_name(key: str) -> str:
    return WINDOW_PREFIX + key


def _line(value: object, most: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text if 0 < len(text) <= most else None


def read_key(value: object) -> str:
    """A key as sent: `page:<word>`, `table:<grid>` or `doc:<path>`."""
    kind, _, ident = value.partition(":") if isinstance(value, str) else ("", "", "")
    if kind not in KINDS or not ident or len(ident) > MAX_ID or ident != ident.strip() or "\n" in ident:
        raise PopOutError("key is page:<page>, table:<the open table's id> or doc:<a document's path>.")
    if kind == PAGE and not _PAGE_WORD.match(ident):
        raise PopOutError("A page's key is page:<its address's first word>, as page:connections.")
    return f"{kind}:{ident}"


def read_address(value: object) -> str:
    """An address of this app under /blazor/ (`connections?name=x`; Home's is empty): never another site's."""
    if not isinstance(value, str) or len(value) > MAX_ADDRESS:
        raise PopOutError("address is the page's address in this app, as connections?name=warehouse.")
    address = value.strip()
    path = address.split("?", 1)[0].split("#", 1)[0]
    bad = any(ord(c) < 32 for c in address) or "\\" in address
    if bad or address.startswith("/") or ":" in path or ".." in path.split("/"):
        raise PopOutError("address is the page's address in this app, as connections?name=warehouse.")
    return address


def page_kind(address: str) -> str:
    """The kind of window an address makes: its first word (home for none; the old grids as tables)."""
    first = address.split("?", 1)[0].split("#", 1)[0].split("/", 1)[0].lower()
    return PAGE_WORDS.get(first, first or "home")


def page_entry(word: object) -> Entry:
    """A whole page by the word the agent writes (connections, settings, tables, home, x-scm...)."""
    if not isinstance(word, str) or not _PAGE_WORD.match(word.strip().lower()):
        raise PopOutError(
            "page is a page's word: home, connections, catalog, tables, erd, analyze, settings…"
        )
    kind = page_kind(word.strip().lower())
    name = PAGE_NAMES.get(kind, kind.removeprefix("x-").replace("-", " ").replace("_", " ").capitalize())
    return Entry(f"{PAGE}:{kind}", name, "" if kind == "home" else kind)


def table_entry(grid: str, name: str) -> Entry:
    return Entry(f"{TABLE}:{grid}", name, f"tables?grid={grid}")


def read_entry(body: object) -> Entry:
    """What a page sends to pop something out: {"key", "name", "address"}."""
    if not isinstance(body, dict):
        raise PopOutError('Send {"page": "connections"} or {"table": "<the open table\'s id>"}.')
    name = _line(body.get("name"), MAX_NAME)
    if name is None:
        raise PopOutError("name is what the window shows, in a few words.")
    return Entry(read_key(body.get("key")), name, read_address(body.get("address", "")))


def read_said(text: str) -> Entry | None:
    """A popped-out window's own word on its socket ({"type": "pop_out", "key", "name", "address"}), or None
    when the message is not that."""
    if len(text) > MAX_SAID:
        return None
    try:
        message = json.loads(text)
    except ValueError:
        return None
    if not isinstance(message, dict) or message.get("type") != SAID:
        return None
    try:
        return read_entry(message)
    except PopOutError:
        return None


def audit_words(entry: Entry) -> str:
    """The audit log's words: the kind and the name, never more."""
    return f"{entry.kind} {entry.name}"
