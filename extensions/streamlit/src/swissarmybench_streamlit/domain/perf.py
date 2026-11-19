"""The Performance Analyzer's rules (the owner, 2026-11-19: "We can see calls, triggers, network activity and
what is actually traveling through the web socket"). Pure: standard library only, no I/O.

  wire      a small reader of protobuf's wire format: a Streamlit ForwardMsg's kind (a delta's element: a
            dataframe, a chart, markdown; its delta path), a BackMsg's kind (a rerun, its widgets, a
            fragment):
            the outer kinds and sizes only; never a value
  socket    each message as the analyzer keeps it: its direction, kind, element and size; grouped per rerun
  session   the page's own records (sab_perf.py beside the launched pages: each rerun's trigger, each block's
            time, the calls, the caches) joined with the socket's reruns, in order
  hints     plain words from rules: a table sent whole each rerun, a block that reruns though it reads nothing
            of the widget that changed, a cache that always misses (its changing argument), a slow query run
            again with the same text, many small socket messages in one rerun

The analyzer shows names, sizes, times and counts; no row value leaves the app's process.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# ForwardMsg's kinds by field number (Streamlit's forward_msg.proto), and an Element's.
FORWARD_KINDS: dict[int, str] = {
    4: "new_session",
    5: "delta",
    6: "script_finished",
    9: "session_status_changed",
    10: "session_event",
    11: "ref_hash",
    12: "page_info_changed",
    13: "page_config_changed",
    14: "git_info_changed",
    15: "page_not_found",
    18: "page_profile",
    19: "file_urls_response",
    20: "parent_message",
    21: "auto_rerun",
    22: "logo",
    23: "navigation",
    24: "auth_redirect",
    26: "heartbeat_ack",
    27: "backend_operation_response",
    28: "stop_auto_rerun",
}
BACK_KINDS: dict[int, str] = {
    5: "clear_cache",
    6: "set_run_on_save",
    7: "stop_script",
    11: "rerun_script",
    12: "load_git_info",
    16: "file_urls_request",
    17: "app_heartbeat",
    19: "backend_operation_request",
}
ELEMENTS: dict[int, str] = {
    1: "text",
    2: "empty",
    5: "progress",
    6: "image",
    7: "help",
    8: "exception",
    12: "balloons",
    13: "audio",
    14: "video",
    16: "plotly_chart",
    18: "graphviz_chart",
    19: "button",
    20: "checkbox",
    21: "slider",
    22: "text_area",
    23: "radio",
    24: "text_input",
    25: "selectbox",
    26: "time_input",
    27: "date_input",
    28: "multiselect",
    29: "markdown",
    30: "alert",
    31: "json",
    32: "number_input",
    33: "file_uploader",
    34: "deck_gl_json_chart",
    35: "color_picker",
    37: "component_instance",
    38: "iframe",
    39: "table",
    40: "dataframe",
    41: "vega_lite_chart",
    42: "metric",
    43: "download_button",
    44: "spinner",
    47: "heading",
    48: "code",
    49: "chat_input",
    50: "toast",
    51: "link_button",
    53: "page_link",
    54: "html",
    55: "button_group",
    67: "echarts_chart",
}
DELTA_KINDS: dict[int, str] = {3: "new_element", 6: "add_block", 9: "new_transient"}
WIDGET_PREFIX: str = "$$ID-"

# The hints' thresholds.
BIG_TABLE: int = 1_000_000  # bytes a table sends each rerun before it is said
SLOW_BLOCK_MS: float = 50.0
SLOW_QUERY_MS: float = 200.0
SMALL_MESSAGE: int = 300
MANY_MESSAGES: int = 200
MAX_MESSAGES: int = 20_000  # kept per session (the oldest go first)


class WireError(ValueError):
    """Bytes that are not protobuf's wire format."""


# ===== protobuf's wire format =====


def _varint(data: bytes, at: int) -> tuple[int, int]:
    value, shift = 0, 0
    while True:
        if at >= len(data):
            raise WireError("a number runs past the end")
        byte = data[at]
        at += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, at
        shift += 7
        if shift > 63:
            raise WireError("a number is too long")


def fields(data: bytes) -> list[tuple[int, int, int | bytes]]:
    """A message's fields in order: (number, wire type, value): a number for varint and fixed fields, the
    bytes for a length-delimited one (a string, bytes, a message, packed numbers)."""
    out: list[tuple[int, int, int | bytes]] = []
    at = 0
    while at < len(data):
        key, at = _varint(data, at)
        number, kind = key >> 3, key & 7
        if number == 0:
            raise WireError("field number 0")
        if kind == 0:
            value, at = _varint(data, at)
            out.append((number, kind, value))
        elif kind == 1:
            out.append((number, kind, int.from_bytes(data[at : at + 8], "little")))
            at += 8
        elif kind == 2:
            size, at = _varint(data, at)
            if at + size > len(data):
                raise WireError("a field runs past the end")
            out.append((number, kind, data[at : at + size]))
            at += size
        elif kind == 5:
            out.append((number, kind, int.from_bytes(data[at : at + 4], "little")))
            at += 4
        else:
            raise WireError(f"wire type {kind}")
        if at > len(data):
            raise WireError("a field runs past the end")
    return out


def _packed(data: bytes) -> list[int]:
    found: list[int] = []
    at = 0
    while at < len(data):
        value, at = _varint(data, at)
        found.append(value)
    return found


@dataclass(frozen=True)
class Message:
    """One websocket message as the analyzer keeps it: never its content."""

    direction: str  # down (to the browser: a ForwardMsg) or up (a BackMsg)
    kind: str
    size: int
    element: str | None = None  # a delta's new element (dataframe, markdown...) or "block"
    path: tuple[int, ...] = ()  # a delta's path on the page
    widgets: tuple[tuple[str, str], ...] = ()  # a rerun's widgets: (its key, a digest of its value)
    fragment: str | None = None  # a rerun of one fragment
    at: float = 0.0  # seconds since the session started

    def to_json(self) -> dict[str, Any]:
        said: dict[str, Any] = {"direction": self.direction, "kind": self.kind, "size": self.size}
        if self.element:
            said["element"] = self.element
        if self.path:
            said["path"] = ".".join(str(p) for p in self.path)
        if self.fragment:
            said["fragment"] = True
        return said | {"at": round(self.at, 3)}


def widget_key(widget_id: str) -> str:
    """A widget's key as the page named it, from Streamlit's id (`$$ID-<hash>-<key>`); else the id."""
    if widget_id.startswith(WIDGET_PREFIX):
        parts = widget_id[len(WIDGET_PREFIX) :].split("-", 1)
        if len(parts) == 2 and parts[1] and parts[1] != "None":
            return parts[1]
    return widget_id


def read_forward(data: bytes, at: float = 0.0) -> Message:
    """A ForwardMsg (the server to the browser): its kind, and a delta's element and path."""
    kind, element = "unknown", None
    path: tuple[int, ...] = ()
    try:
        for number, _, value in fields(data):
            if number == 2 and isinstance(value, bytes):  # metadata
                for inner, _, held in fields(value):
                    if inner == 2 and isinstance(held, bytes):
                        path = tuple(_packed(held))
            elif number in FORWARD_KINDS:
                kind = FORWARD_KINDS[number]
                if number == 5 and isinstance(value, bytes):
                    for inner, _, held in fields(value):
                        if inner == 3 and isinstance(held, bytes):
                            element = next(
                                (ELEMENTS.get(n, f"element {n}") for n, _, _ in fields(held) if n < 57),
                                "element",
                            )
                        elif inner in DELTA_KINDS and inner != 3:
                            element = "block" if inner == 6 else "transient"
    except WireError:
        kind = "unreadable"
    return Message("down", kind, len(data), element, path, at=at)


def _digest(data: bytes) -> str:
    """A widget value's short digest: what tells a change apart, never the value."""
    total = 0
    for byte in data:
        total = (total * 131 + byte) % 2_147_483_647
    return f"{total:x}"


def read_back(data: bytes, at: float = 0.0) -> Message:
    """A BackMsg (the browser to the server): its kind; a rerun's widgets (their keys, a digest each) and
    whether it reruns one fragment."""
    kind = "unknown"
    widgets: list[tuple[str, str]] = []
    fragment: str | None = None
    try:
        for number, _, value in fields(data):
            if number not in BACK_KINDS:
                continue
            kind = BACK_KINDS[number]
            if number != 11 or not isinstance(value, bytes):
                continue
            for inner, _, held in fields(value):
                if inner == 5 and isinstance(held, bytes) and held:
                    fragment = "fragment"
                if inner == 2 and isinstance(held, bytes):  # widget_states
                    for item, _, state in fields(held):
                        if item != 1 or not isinstance(state, bytes):
                            continue
                        widget_id, digest = "", ""
                        for part, _, piece in fields(state):
                            if part == 1 and isinstance(piece, bytes):
                                widget_id = piece.decode("utf-8", "replace")
                            elif part > 1:
                                raw = piece if isinstance(piece, bytes) else str(piece).encode()
                                digest = _digest(bytes([part]) + raw)
                        if widget_id:
                            widgets.append((widget_key(widget_id), digest))
    except WireError:
        kind = "unreadable"
    return Message("up", kind, len(data), widgets=tuple(widgets), fragment=fragment, at=at)


# ===== the socket's reruns =====


@dataclass
class SocketRerun:
    """The messages of one rerun: from the browser's ask (or the first load) to its script_finished."""

    trigger: str  # first load, a widget's key, a page switch, a rerun, a fragment
    messages: list[Message] = field(default_factory=list)

    @property
    def size(self) -> int:
        return sum(m.size for m in self.messages if m.direction == "down")

    def to_json(self) -> dict[str, Any]:
        elements: dict[str, dict[str, int]] = {}
        for m in self.messages:
            if m.direction == "down" and m.element:
                held = elements.setdefault(m.element, {"count": 0, "size": 0})
                held["count"] += 1
                held["size"] += m.size
        biggest = sorted((m for m in self.messages if m.direction == "down"), key=lambda m: -m.size)[:10]
        return {
            "trigger": self.trigger,
            "messages": len(self.messages),
            "size": self.size,
            "elements": dict(sorted(elements.items(), key=lambda kv: -kv[1]["size"])),
            "biggest": [m.to_json() for m in biggest],
        }


def socket_reruns(messages: Sequence[Message]) -> list[SocketRerun]:
    """The socket's messages grouped per rerun. A BackMsg rerun starts one (its trigger: the widget whose
    value changed since the last rerun, a page switch, a fragment); a new session starts the first load."""
    reruns: list[SocketRerun] = []
    last: dict[str, str] = {}
    current: SocketRerun | None = None
    for message in messages:
        if message.direction == "up" and message.kind == "rerun_script":
            changed = [k for k, d in message.widgets if last.get(k) != d]
            for k, d in message.widgets:
                last[k] = d
            trigger = changed[0] if changed else ("fragment" if message.fragment else "rerun")
            current = SocketRerun(trigger)
            reruns.append(current)
        elif message.direction == "down" and message.kind == "new_session" and current is None:
            current = SocketRerun("first load")
            reruns.append(current)
        if current is not None:
            current.messages.append(message)
        if message.direction == "down" and message.kind == "script_finished":
            current = None
    return reruns


# ===== the page's own records, joined =====


@dataclass(frozen=True)
class Rerun:
    """One rerun as the timeline draws it."""

    index: int
    trigger: str
    page: str
    ms: float
    blocks: tuple[tuple[str, float], ...]  # each block's id and its time
    calls: tuple[dict[str, Any], ...]
    tables: tuple[dict[str, Any], ...]  # each table drawn: its block, rows, columns
    socket: SocketRerun | None

    def to_json(self, titles: Mapping[str, str]) -> dict[str, Any]:
        return {
            "index": self.index,
            "trigger": self.trigger,
            "page": self.page,
            "ms": round(self.ms, 1),
            "blocks": [{"block": b, "title": titles.get(b, b), "ms": round(ms, 1)} for b, ms in self.blocks],
            "calls": list(self.calls),
            "socket": self.socket.to_json() if self.socket else None,
        }


def reruns_of(records: Iterable[Mapping[str, Any]], socket: Sequence[SocketRerun]) -> list[Rerun]:
    """The page's reruns (its records: kind "run", in order) beside the socket's, the n-th with the n-th."""
    runs = [r for r in records if r.get("kind") == "run"]
    out: list[Rerun] = []
    for index, record in enumerate(runs):
        held = socket[index] if index < len(socket) else None
        trigger = str(record.get("trigger") or (held.trigger if held else "rerun"))
        blocks = tuple((str(b), float(ms)) for b, ms in record.get("blocks") or [])
        out.append(
            Rerun(
                index + 1,
                trigger,
                str(record.get("page") or ""),
                float(record.get("ms") or 0.0),
                blocks,
                tuple(c for c in record.get("calls") or [] if isinstance(c, dict)),
                tuple(t for t in record.get("tables") or [] if isinstance(t, dict)),
                held,
            )
        )
    return out


def caches_of(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Each cached function: its calls, hits, misses and what the misses cost (from the page's records)."""
    found: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.get("kind") != "run":
            continue
        for cache in record.get("caches") or []:
            name = str(cache.get("name"))
            held = found.setdefault(
                name,
                {"name": name, "kind": cache.get("cache", "data"), "calls": 0, "misses": 0, "miss_ms": 0.0},
            )
            held["calls"] += int(cache.get("calls") or 0)
            held["misses"] += int(cache.get("misses") or 0)
            held["miss_ms"] += float(cache.get("miss_ms") or 0.0)
            held.setdefault("arguments", [])
            held["arguments"] += [list(a) for a in cache.get("arguments") or []]
    out = []
    for held in found.values():
        held["hits"] = max(0, held["calls"] - held["misses"])
        held["miss_ms"] = round(held["miss_ms"], 1)
        out.append(held)
    return sorted(out, key=lambda c: -c["miss_ms"])


# ===== hints, in plain words =====


def _size(n: float) -> str:
    for unit, step in (("MB", 1_000_000), ("KB", 1_000)):
        if n >= step:
            return f"{n / step:.1f} {unit}"
    return f"{int(n)} bytes"


@dataclass(frozen=True)
class Facts:
    """What the hints know of the page's blocks: each block's title, the names it makes and reads, and the
    widget keys it owns."""

    titles: Mapping[str, str] = field(default_factory=dict)
    makes: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    reads: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    keys: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


def hints(reruns: Sequence[Rerun], caches: Sequence[Mapping[str, Any]], facts: Facts) -> list[dict[str, str]]:
    """The analyzer's hints, each {rule, words, block?}: what to change, in plain words."""
    said: list[dict[str, str]] = []

    def title(block: str) -> str:
        return facts.titles.get(block, block)

    # 1. A table sent whole on every rerun above a size.
    sent: dict[str, list[int]] = {}
    for run in reruns:
        if run.socket is None:
            continue
        frames = [m for m in run.socket.messages if m.direction == "down" and m.element == "dataframe"]
        tables = [t for t in run.tables]
        for i, message in enumerate(frames):
            name = str(tables[i].get("block")) if i < len(tables) else ".".join(map(str, message.path))
            sent.setdefault(name, []).append(message.size)
    for name, sizes in sent.items():
        if len(sizes) >= 2 and min(sizes) >= BIG_TABLE:
            each = _size(sum(sizes) / len(sizes))
            words = f"{title(name)}: {each} each rerun: cache it, or send fewer rows or columns."
            said.append({"rule": "big_table", "words": words, "block": name})
    # 2. A block that reruns on a widget's change though it reads nothing that widget gives.
    owner = {key: block for block, keys in facts.keys.items() for key in keys}
    seen: dict[tuple[str, str], int] = {}
    for run in reruns:
        maker = owner.get(run.trigger)
        if maker is None:
            continue
        given = set(facts.makes.get(maker, ()))
        for block, ms in run.blocks:
            if block == maker or ms < SLOW_BLOCK_MS or given & set(facts.reads.get(block, ())):
                continue
            seen[(block, run.trigger)] = seen.get((block, run.trigger), 0) + 1
    for (block, key), count in sorted(seen.items()):
        if count >= 2:
            words = (
                f"{title(block)} reruns each time {key} changes though it does not read it: move its work "
                "into a cached function (or run that widget's block alone, as a fragment)."
            )
            said.append({"rule": "needless_rerun", "words": words, "block": block})
    # 3. A cache that misses every time: which argument changes.
    for cache in caches:
        if cache.get("calls", 0) >= 3 and cache.get("hits", 0) == 0:
            arguments = cache.get("arguments") or []
            changing = [
                str(arguments[0][i][0])
                for i in range(len(arguments[0]) if arguments else 0)
                if len({str(a[i][1]) for a in arguments if i < len(a)}) == len(arguments)
            ]
            which = (
                f": its argument {changing[0]} is new each call"
                if changing
                else ": its key changes each call"
            )
            said.append({"rule": "cache_misses", "words": f"{cache['name']} misses every time{which}."})
    # 4. A slow query run again with the same text.
    queries: dict[tuple[str, str], list[float]] = {}
    for run in reruns:
        for call in run.calls:
            if call.get("kind") in ("sql", "dax") and not call.get("cached"):
                asked = (str(call.get("connection")), str(call.get("query")))
                queries.setdefault(asked, []).append(float(call.get("ms") or 0.0))
    for (connection, _), times in queries.items():
        if len(times) >= 2 and min(times) >= SLOW_QUERY_MS:
            words = (
                f"A query on {connection} took {round(sum(times) / len(times))} ms, {len(times)} times with "
                "the same text: cache it."
            )
            said.append({"rule": "slow_query", "words": words})
    # 5. Many small socket messages in one rerun (a loop drawing element by element).
    for run in reruns:
        if run.socket is None:
            continue
        small = [m for m in run.socket.messages if m.direction == "down" and m.size < SMALL_MESSAGE]
        if len(small) >= MANY_MESSAGES:
            words = (
                f"Rerun {run.index} sent {len(small)} small messages: a loop draws element by element. Build "
                "the table or text first, then draw it once."
            )
            said.append({"rule": "many_messages", "words": words})
            break
    return said
