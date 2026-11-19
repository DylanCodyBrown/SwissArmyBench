"""The desktop app's rules (standard library only, no I/O): what loads inside the app's windows and what
goes to the system's browser, which window an address reuses, where a window goes and how big it is, the
app's command line, its channel's messages and the one permission it grants.

Swiss Army Bench is a desktop app (the owner, 2026-11-18: "It's not an extension it is the app framework
now and it should have been since the start"): PySide6, a Qt WebEngine (Chromium) window per page of the
app, over the local server it starts (server/desktop_shell.py). Only the app's own origin,
http://127.0.0.1:<the server's port>, is ever shown inside: a link or a window.open to anywhere else opens
in the system browser, and a frame that would load from elsewhere is refused. The token never travels on a
command line or the channel: a page is named by its path (and its fragment without the token), and the
shell adds the running server's token from its connection file.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

HOST = "127.0.0.1"
INSIDE, OUTSIDE, REFUSE = "inside", "outside", "refuse"
# Schemes the system opens (its browser, its mail program); every other one is refused.
OUTSIDE_SCHEMES: tuple[str, ...] = ("http", "https", "mailto")
# The home window's name (web/src/nav.ts's HOME_WINDOW): other windows find it by this name.
HOME_WINDOW = "sab-home"
HOME_PAGE = "/workspace"
# A page of the app the agent opens by a word (desktop_open).
PAGES: dict[str, str] = {"home": "/workspace", "workbench": "/workbench", "blades": "/catalog"}
# Window sizes when nothing is remembered and the page asked for none.
DEFAULT_SIZES: dict[str, tuple[int, int]] = {
    "home": (1360, 860),
    "workbench": (1280, 840),
    "catalog": (1200, 800),
}
DEFAULT_SIZE: tuple[int, int] = (1200, 800)
MIN_WIDTH, MIN_HEIGHT = 360, 240
# A remembered place is used only when this much of the window is on a screen now.
VISIBLE_WIDTH, VISIBLE_HEIGHT = 120, 80
CASCADE = 28
MAX_MESSAGE = 64 * 1024
MAX_PAGE = 4096
MAX_KINDS = 60
_KIND = re.compile(r"^[a-z0-9][a-z0-9:_-]{0,59}$")


# ===== addresses, read here (the domain does no I/O and keeps to its own parsing) =====


@dataclass(frozen=True)
class _Parts:
    scheme: str
    hostname: str | None
    port: int | None
    path: str
    query: str
    fragment: str


def urlsplit(url: str) -> _Parts:
    """An address's parts: scheme://host:port/path?query#fragment (what urllib.parse.urlsplit gives, for the
    addresses the app makes). ValueError for a port that is not a number."""
    rest, _, fragment = url.partition("#")
    rest, _, query = rest.partition("?")
    scheme, sep, after = rest.partition(":")
    if not sep or not scheme.replace("+", "").replace("-", "").replace(".", "").isalnum():
        return _Parts("", None, None, rest, query, fragment)
    if not after.startswith("//"):
        return _Parts(scheme.lower(), None, None, after, query, fragment)
    authority, slash, path = after[2:].partition("/")
    host, colon, port_text = authority.rpartition("@")[2].partition(":")
    port = None
    if colon:
        if not port_text.isdigit():
            raise ValueError(f"{port_text!r} is not a port.")
        port = int(port_text)
    return _Parts(scheme.lower(), host.lower() or None, port, slash + path, query, fragment)


def parse_qsl(text: str, keep_blank_values: bool = True) -> list[tuple[str, str]]:
    """`a=1&b=2` as pairs, as written (the app's words and tokens need no decoding)."""
    pairs: list[tuple[str, str]] = []
    for part in text.split("&"):
        if not part:
            continue
        key, _, value = part.partition("=")
        if value or keep_blank_values:
            pairs.append((key, value))
    return pairs


def urlencode(pairs: list[tuple[str, str]]) -> str:
    return "&".join(f"{k}={v}" for k, v in pairs)


class ShellError(ValueError):
    """A message, page or record that is not one the shell takes."""


# ===== inside, outside or refused =====


def is_ours(url: str, port: int) -> bool:
    """Is `url` on the app's own origin, http://127.0.0.1:<port>?"""
    try:
        parts = urlsplit(url)
        return parts.scheme.lower() == "http" and parts.hostname == HOST and parts.port == port
    except ValueError:
        return False


def decide(url: str, port: int, *, main_frame: bool = True, clicked: bool = False) -> str:
    """Where a navigation goes: INSIDE (shown in the shell), OUTSIDE (the system's browser) or REFUSE.

    The app's origin, about:blank (a window.open's first page) and about:srcdoc (a frame's own HTML), and a
    blob: of the app's origin (a download) load inside. http, https and mailto elsewhere go to the system:
    a window's own navigation, or a click in a frame; a frame that loads one by itself is refused. A data:
    address may fill a frame, never a window. Anything else (file:, javascript:, ...) is refused."""
    text = url.strip()
    scheme = text.split(":", 1)[0].lower() if ":" in text else ""
    if is_ours(text, port):
        return INSIDE
    if text.lower() in ("about:blank", "about:srcdoc"):
        return INSIDE
    if scheme == "blob":
        return INSIDE if is_ours(text[5:], port) else REFUSE
    if scheme == "data":
        return REFUSE if main_frame else INSIDE
    if scheme in OUTSIDE_SCHEMES:
        return OUTSIDE if main_frame or clicked else REFUSE
    return REFUSE


def grant(permission: str, origin: str, port: int) -> bool:
    """The one permission the app grants: the clipboard, to its own origin. Nothing else, to no one."""
    return permission == "clipboard" and is_ours(origin, port)


# ===== pages: named without the token =====


def page_of(address: str) -> str:
    """An address of the app as the shell is told it: its path, query and fragment, the token taken out
    ("/workspace#grid=3"). Raises ShellError for anything but a page of the app's own origin (any port: the
    shell asks the running server's)."""
    if not isinstance(address, str) or not address.strip() or len(address) > MAX_PAGE:
        raise ShellError("Send a page of the app.")
    text = address.strip()
    if text.startswith("/") and not text.startswith("//"):
        parts = urlsplit(f"http://{HOST}{text}")
    else:
        parts = urlsplit(text)
        if parts.scheme.lower() != "http" or parts.hostname != HOST:
            raise ShellError(f"{text[:80]} is not a page of the app.")
    path = parts.path or "/"
    words = [(k, v) for k, v in parse_qsl(parts.fragment, keep_blank_values=True) if k != "token"]
    page = path + (f"?{parts.query}" if parts.query else "")
    return page + (f"#{urlencode(words)}" if words else "")


def address_of(page: str, port: int, token: str) -> str:
    """The page's full address with the running server's token in the fragment, as the browser launch has
    it (server/lifecycle.py's page_address): the fragment is never sent over the network."""
    parts = urlsplit(f"http://{HOST}{page_of(page)}")
    words = [("token", token), *parse_qsl(parts.fragment, keep_blank_values=True)]
    query = f"?{parts.query}" if parts.query else ""
    return f"http://{HOST}:{port}{parts.path}{query}#{urlencode(words)}"


def page_for(word: str) -> str:
    """desktop_open's page: home, workbench or blades."""
    if word not in PAGES:
        raise ShellError(f"Open one of: {', '.join(PAGES)}.")
    return PAGES[word]


def kind_of(url: str) -> str:
    """A window's kind, the key its size and place are remembered by: home (/workspace and a grid's /g/...),
    workbench, catalog, a panel window (?panel=steps: panel-steps), else the path's first word."""
    try:
        parts = urlsplit(url if "://" in url else f"http://{HOST}{url}")
    except ValueError:
        return "other"
    first = parts.path.strip("/").split("/", 1)[0].lower()
    base = {"": "home", "workspace": "home", "g": "home"}.get(first, first)
    panel = dict(parse_qsl(parts.query)).get("panel", "")
    kind = f"{base}-panel-{panel.lower()}" if panel else base
    return kind if _KIND.match(kind) else "other"


def same_page(a: str, b: str) -> bool:
    """The same page of the app (path and query), whatever the fragment says."""
    pa, pb = urlsplit(a), urlsplit(b)
    return (pa.path or "/", pa.query) == (pb.path or "/", pb.query)


def _extra(url: str) -> bool:
    """Does the address's fragment say more than the token (a grid, a document)?"""
    return any(k != "token" for k, _ in parse_qsl(urlsplit(url).fragment, keep_blank_values=True))


@dataclass(frozen=True)
class Open:
    """A window the shell has: its id, its page's window.name, the address it shows."""

    id: int
    name: str
    url: str


def target(url: str, windows: list[Open]) -> tuple[int | None, bool]:
    """Which window an address the shell is asked to open goes to, and whether that window loads it.

    The home page goes to the window named HOME_WINDOW (the pages find it by that name, as a browser's
    named window), else to a window showing the same page; that window is raised, and loads the address only
    when its fragment says more than the token (a grid, a document) or it shows another page. Anything else
    opens a new window: (None, True)."""
    home = kind_of(url) == "home"
    for found in windows:
        if home and found.name == HOME_WINDOW:
            return found.id, _extra(url) or not same_page(found.url, url)
    for found in windows:
        if same_page(found.url, url):
            return found.id, _extra(url)
    return None, True


# ===== a window's place =====


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    def overlap(self, other: Rect) -> tuple[int, int]:
        w = min(self.x + self.w, other.x + other.w) - max(self.x, other.x)
        h = min(self.y + self.h, other.y + other.h) - max(self.y, other.y)
        return max(0, w), max(0, h)


@dataclass(frozen=True)
class Saved:
    rect: Rect
    maximized: bool = False


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and abs(value) < 100_000 else None


def read_saved(data: Any) -> dict[str, Saved]:
    """windows.json read loosely: {kind: {x, y, w, h, maximized}}; anything else left out."""
    out: dict[str, Saved] = {}
    if not isinstance(data, dict):
        return out
    for kind, said in data.items():
        if not isinstance(kind, str) or not _KIND.match(kind) or not isinstance(said, dict):
            continue
        x, y, w, h = (_int(said.get(k)) for k in ("x", "y", "w", "h"))
        if x is None or y is None or w is None or h is None or w < MIN_WIDTH or h < MIN_HEIGHT:
            continue
        out[kind] = Saved(Rect(x, y, w, h), said.get("maximized") is True)
    return out


def remembered(data: Any, kind: str, saved: Saved) -> dict[str, Any]:
    """windows.json with `kind`'s place: sorted, at most MAX_KINDS kinds (the one just saved kept)."""
    places = read_saved(data)
    places.pop(kind, None)
    places[kind] = saved
    kept = list(places.items())[-MAX_KINDS:]
    return {
        k: {"x": s.rect.x, "y": s.rect.y, "w": s.rect.w, "h": s.rect.h, "maximized": s.maximized}
        for k, s in sorted(kept)
    }


def windows_text(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def place(
    kind: str,
    saved: Saved | None,
    requested: tuple[int, int] | None,
    screens: list[Rect],
    open_count: int = 0,
) -> Saved:
    """Where a new window goes. Its kind's remembered place when enough of it is on a screen now; else the
    size the page asked for (window.open's width and height), else the kind's default, on the first screen,
    centred and cascaded by the windows already open; never larger than the screen."""
    screen = screens[0] if screens else Rect(0, 0, 1920, 1080)
    if saved is not None:
        for candidate in screens:
            w, h = saved.rect.overlap(candidate)
            if w >= VISIBLE_WIDTH and h >= VISIBLE_HEIGHT:
                r = saved.rect
                return Saved(Rect(r.x, r.y, min(r.w, candidate.w), min(r.h, candidate.h)), saved.maximized)
    w, h = requested or DEFAULT_SIZES.get(kind, DEFAULT_SIZE)
    w = max(MIN_WIDTH, min(w, screen.w))
    h = max(MIN_HEIGHT, min(h, screen.h))
    step = (open_count % 8) * CASCADE
    x = screen.x + max(0, (screen.w - w) // 2) + step
    y = screen.y + max(0, (screen.h - h) // 2) + step
    x = min(x, screen.x + max(0, screen.w - w))
    y = min(y, screen.y + max(0, screen.h - h))
    return Saved(Rect(x, y, w, h))


# ===== the shell's record, command line and channel =====


RECORD = "desktop.json"  # beside the server's connection file: the app's pid and channel


def record(pid: int, port: int, key: str) -> dict[str, Any]:
    """desktop.json while the app runs: its process id (the update's helper ends it by it) and its
    channel."""
    return {"pid": pid, "shell": {"port": port, "key": key}}


def read_record(data: Any) -> tuple[int, int, str] | None:
    """desktop.json read: (pid, port, key); None when it is not one."""
    if not isinstance(data, dict) or not isinstance(data.get("shell"), dict):
        return None
    pid, shell = _int(data.get("pid")), data["shell"]
    port, key = _int(shell.get("port")), shell.get("key")
    if not pid or not port or not 0 < port < 65536 or not isinstance(key, str) or len(key) < 16:
        return None
    return pid, port, key


def shell_command(python: str, page: str | None = None) -> list[str]:
    """The app as a process of its own: `python -m swissarmybench.server app [page]` (a page of the app,
    with no token in it)."""
    command = [python, "-m", "swissarmybench.server", "app"]
    if page:
        command.append(page_of(page))
    return command


def read_page(word: str | None) -> str | None:
    """The app's argument: a page of the app (no token), or none (the home page)."""
    return page_of(word) if word else None


def message(key: str, said: dict[str, Any]) -> bytes:
    """A message to the shell: one line of JSON with its key."""
    return (json.dumps({"key": key} | said) + "\n").encode("utf-8")


def read_message(line: bytes, key: str) -> dict[str, Any]:
    """A message the shell heard, checked: its key, then one of {"open": page}, {"status": true},
    {"quit": true} (every window closed without asking its page, each window's place kept, the server told:
    `swissarmybench stop`, an update's helper)."""
    import hmac

    if len(line) > MAX_MESSAGE:
        raise ShellError("Too long.")
    try:
        said = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ShellError("Not a message.") from None
    if not isinstance(said, dict) or not isinstance(said.get("key"), str):
        raise ShellError("Not a message.")
    if not hmac.compare_digest(said["key"].encode(), key.encode()):
        raise ShellError("Not this app's key.")
    if "open" in said:
        return {"open": page_of(said["open"])}
    if said.get("status") is True:
        return {"status": True}
    if said.get("quit") is True:
        return {"quit": True}
    if "file" in said:
        return {"file": read_file_path(said["file"])}
    raise ShellError('Send {"open": page}, {"file": path}, {"status": true} or {"quit": true}.')


# ===== a file opened with the app: `swissarmybench open <file>`, Open with, a file dropped on a window =====

# The files the app opens as a table (adapters/datasets.py SUFFIXES), a notebook and a blade.
TABLE_SUFFIXES: tuple[str, ...] = (
    ".csv", ".tsv", ".txt", ".parquet", ".json", ".jsonl", ".ndjson", ".arrow", ".feather", ".xlsx",
)  # fmt: skip
NOTEBOOK_SUFFIXES: tuple[str, ...] = (".ipynb",)
BLADE_SUFFIX = ".blade.py"
TABLE, NOTEBOOK, BLADE, PROJECT = "table", "notebook", "blade", "project"
CANNOT_OPEN = (
    "{name}: Swiss Army Bench opens CSV, TSV, Parquet, JSON, Arrow and Excel files, notebooks (.ipynb), "
    "blades (.blade.py) and project folders."
)
_NAME_PART = re.compile(r"[^A-Za-z0-9_-]+")


def read_file_path(value: Any) -> str:
    """A file's path as the channel carries it: one line of text, absolute, of a sane length."""
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_PAGE:
        raise ShellError("Send the file's path.")
    if any(not c.isprintable() for c in value):
        raise ShellError("A file's path is one line of text.")
    text = value.strip()
    if not (text.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", text) or text.startswith("\\\\")):
        raise ShellError("Send the file's full path.")
    return text


def file_kind(name: str, is_folder: bool, has_sab: bool) -> str:
    """What opening a file with the app does: a project (a folder with .sab/, or any folder: it is asked to
    become one), a table, a notebook (the Workbench) or a blade; "" when the app does not open it."""
    if is_folder:
        return PROJECT
    lowered = name.lower()
    if lowered.endswith(BLADE_SUFFIX):
        return BLADE
    if lowered.endswith(NOTEBOOK_SUFFIXES):
        return NOTEBOOK
    if lowered.endswith(TABLE_SUFFIXES):
        return TABLE
    return ""


def table_name(file_name: str, taken: set[str] | list[str]) -> str:
    """The table a file opens as: its name without the suffix, made a dataset name ([A-Za-z0-9_-]{1,64}),
    with _2, _3 ... when an open table has it already (another table is never replaced)."""
    stem = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
    base = _NAME_PART.sub("_", stem).strip("_")[:60] or "data"
    used = {t.lower() for t in taken}
    name, n = base, 2
    while name.lower() in used:
        name = f"{base[: 60 - len(str(n))]}_{n}"
        n += 1
    return name


def blade_stem(file_name: str) -> str:
    """A blade file's name without .blade.py (the name the library keeps it by)."""
    return file_name[: -len(BLADE_SUFFIX)] if file_name.lower().endswith(BLADE_SUFFIX) else file_name


def download_name(suggested: str) -> str:
    """A download's file name as a Save dialog suggests it: no folder, no control character."""
    name = re.split(r"[\\/]", suggested or "")[-1]
    name = "".join(c for c in name if c.isprintable() and c not in '<>:"|?*').strip(" .")
    return name[:200] or "download"


def pdf_name(title: str) -> str:
    """Print to PDF's suggested file name: the page's title."""
    stem = download_name(title or "")
    stem = stem[:-4] if stem.lower().endswith(".pdf") else stem
    return f"{stem if stem != 'download' else 'Swiss Army Bench'}.pdf"


# host:port/... with no scheme: what Chromium shows as a page's title before the page names itself.
_BARE_ADDRESS = re.compile(r"^[\w.\-\[\]:]+:\d+(/|$)")


def window_title(title: str, app: str = "Swiss Army Bench") -> str:
    """A window's title: the page's own. Before a page has one, Chromium gives its address (with the token in
    its fragment): never shown, the app's name instead."""
    text = (title or "").strip()
    lowered = text.lower()
    if (
        not text
        or "://" in text
        or "token=" in lowered
        or lowered.startswith(("about:", "blob:", "data:", "127.0.0.1", "localhost", "[::1]"))
        or _BARE_ADDRESS.match(text) is not None  # Chromium's first title: the address with no scheme
    ):
        return app
    return text[:200]


# ===== the app's icon, as files (the launcher's: a Windows shortcut's .ico, a PNG) =====

MARK_RED_RGB = (0xD5, 0x2B, 0x1E)
_CROSS = ((42, 23), (58, 23), (58, 42), (77, 42), (77, 58), (58, 58), (58, 77), (42, 77), (42, 58), (23, 58))


def _in_mark(x: float, y: float) -> tuple[int, int, int, int]:
    """The mark's colour at (x, y) on a 100 x 100 square: a red rounded square (radius 20), a white cross."""
    r = 20.0
    cx = min(max(x, r), 100 - r)
    cy = min(max(y, r), 100 - r)
    if not (0 <= x <= 100 and 0 <= y <= 100) or (x - cx) ** 2 + (y - cy) ** 2 > r * r:
        return (0, 0, 0, 0)
    if (42 <= x <= 58 and 23 <= y <= 77) or (23 <= x <= 77 and 42 <= y <= 58):
        return (255, 255, 255, 255)
    return (*MARK_RED_RGB, 255)


def icon_png(size: int) -> bytes:
    """The mark as a PNG of `size` pixels (standard library only; 3 x 3 samples a pixel for its edges)."""
    import struct
    import zlib

    rows = bytearray()
    step = 100 / size
    for j in range(size):
        rows.append(0)
        for i in range(size):
            total = [0, 0, 0, 0]
            for sy in (0.17, 0.5, 0.83):
                for sx in (0.17, 0.5, 0.83):
                    for k, v in enumerate(_in_mark((i + sx) * step, (j + sy) * step)):
                        total[k] += v
            alpha = total[3] // 9
            rgb = [min(255, total[k] * 255 // total[3]) if total[3] else 0 for k in range(3)]
            rows += bytes((*rgb, alpha))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + chunk(b"IEND", b"")
    )


def icon_ico(sizes: tuple[int, ...] = (16, 32, 48, 256)) -> bytes:
    """A Windows .ico holding the mark at `sizes` (PNG images inside, as Windows Vista and later read)."""
    import struct

    images = [icon_png(n) for n in sizes]
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for n, data in zip(sizes, images, strict=True):
        side = 0 if n >= 256 else n
        out += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return out + b"".join(images)
