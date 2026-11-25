"""The Collaboration panel (the owner, 2026-11-25, who named it): "a place where I can leave notes for my
team and like an activity log and I can reference objects in the project with @ like the cell and they can
comment back like a thread and its preserved in the app. It needs rich text and slack like functionality."

Everything is ordinary text files under the project folder's `.sab/collaboration/` (shared in Git with the
project: the team's Pull and Push carry it; no server, no other traffic), laid out so that a Git merge never
conflicts:

  <thread>/thread.toml                         the thread: title, its channel or its anchor (an object), who
                                               made it and when; resolved and pinned as made (events
                                               change them)
  <thread>/<UTC time>-<author>-<id>.md         one message: TOML front matter between `+++` lines, then its
                                               Markdown. An edit rewrites only this file; a delete marks it
  <thread>/<id>-<n>.<png|jpg|gif|webp>         a picture pasted into a message, beside it (5 MB at most)
  <thread>/_events/<UTC time>-<author>-<id>.toml  a reaction, a resolve or a pin: one small file each, so two
                                               people reacting at once never touch the same file
  _channels/<channel>.toml                     a channel the team made (#general is always there)

Only what people write is here (the owner, 2026-11-25: "the change log stays out"): a folder `_activity/` an
earlier build wrote is never read and left alone.

It reads top to bottom: 1. names and ids, 2. TOML as written here, 3. the files, 4. a message's body (object
references, people, pictures), 5. a thread folded, 6. news (what is new since you last read), 7. the timeline
(filters, unread, search), 8. who may do what. Pure rules: no I/O, no clock, no randomness (the service
gives the time and the ids).
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain import project_paths

FOLDER = ".sab/collaboration"
THREAD_FILE = "thread.toml"
EVENTS = "_events"
CHANNELS = "_channels"
GENERAL = "general"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_BODY = 40_000  # a message's Markdown, in characters
MAX_TITLE = 120
MESSAGE_KINDS = ("note", "reply", "system")
ACTIONS = ("react", "unreact", "resolve", "reopen", "pin", "unpin")
# What `@` can point at: kind -> its words. Each is stored as kind + path + id (stable) and the text shown.
REFERENCE_KINDS = {
    "cell": "a notebook's cell (by its number, which never changes)",
    "notebook": "a notebook",
    "script": "a script",
    "function": "a script's function",
    "sql": "a .sql file",
    "table": "an open table",
    "column": "a table's column",
    "connection": "a connection",
    "endpoint": "an endpoint of API.py",
    "widget": "a canvas widget",
    "analysis": "a saved analysis (a dashboard of the Analyze page)",
}
FILTERS = ("all", "mentions", "page", "unresolved")
MAX_EMOJI = 32  # a reaction's characters (a family or a flag is several code points)
IMAGE_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}
GONE_WORDS = "no longer in the project"
AGENT_ONLY_POSTS = (
    "The agent writes only with collaboration_post (a new thread or a reply): {what} is the user's own."
)
NOT_YOURS = "Only its author edits or deletes a message."

_SLUG = re.compile(r"[^a-z0-9]+")
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
# [@data.ipynb cell 7](sab:cell/data.ipynb#7): an object reference in a message's Markdown.
REFERENCE = re.compile(r"\[@([^\]\n]{1,200})\]\(sab:([a-z]+)/([^)#\s]*)(?:#([^)\s]*))?\)")
# @sam-ortiz: a person, when that login is one of the people seen (outside a reference's brackets).
MENTION = re.compile(r"(?<![\w@/\[])@([a-z0-9][a-z0-9-]{0,62})\b")
# ![a picture](sab-image:1a2b3c4d-1.png): a picture beside the message.
IMAGE = re.compile(r"!\[[^\]\n]*\]\(sab-image:([a-z0-9-]+\.(?:png|jpg|gif|webp))\)")


class CollaborationError(ValueError):
    """A request that cannot be: said in one sentence."""


# ===== 1. Names and ids =====


def quote(text: str, safe: str = "") -> str:
    """Percent-encoding for an address's part (as urllib.parse.quote: the domain does no I/O, so its own)."""
    keep = "_.-~" + safe
    return "".join(
        chr(b) if b < 0x80 and (chr(b).isalnum() or chr(b) in keep) else f"%{b:02X}" for b in text.encode()
    )


def unquote(text: str) -> str:
    raw = re.sub(rb"%([0-9A-Fa-f]{2})", lambda m: bytes([int(m.group(1), 16)]), text.encode())
    return raw.decode("utf-8", errors="replace")


def slug(text: str) -> str:
    """A person's or a channel's name as a file's part: "Avery Lin" -> "avery-lin" (never empty)."""
    made = _SLUG.sub("-", text.strip().lower()).strip("-")[:48]
    return made or "someone"


def check_id(value: Any, what: str = "thread") -> str:
    if not isinstance(value, str) or not _ID.match(value):
        raise CollaborationError(f"No such {what}.")
    return value


def channel_name(value: Any) -> str:
    """A channel's name as kept: "#Month end" -> "month-end"."""
    if not isinstance(value, str) or not value.strip().lstrip("#").strip():
        raise CollaborationError("A channel has a name.")
    return slug(value.strip().lstrip("#"))


def compact(time: str) -> str:
    """2026-11-25T10:15:00Z -> 20261125T101500Z (a file name's time, sorting as the time does)."""
    return re.sub(r"[-:]", "", time).replace("+0000", "Z")


@dataclass(frozen=True)
class Person:
    name: str
    login: str
    agent: bool = False

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "login": self.login} | ({"agent": True} if self.agent else {})


def person(name: str, login: str | None = None) -> Person:
    """This computer's person: the GitHub login when signed in, else the name's slug."""
    shown = " ".join(str(name or "").split())[:80] or "Someone"
    return Person(shown, slug(login) if login else slug(shown))


def agent_for(user: Person) -> Person:
    """The agent posts as itself, marked as the user's: "Claude for Avery Lin"."""
    return Person(f"Claude for {user.name}", f"claude-for-{user.login}"[:63], agent=True)


def person_of(raw: Any) -> Person:
    if not isinstance(raw, Mapping):
        return Person("Someone", "someone")
    name = str(raw.get("name") or raw.get("login") or "Someone")
    return Person(name, slug(str(raw.get("login") or name)), bool(raw.get("agent")))


# ===== 2. TOML as written here (sorted, the same bytes for the same thing; read back with tomllib) =====


def _string(value: str) -> str:
    out = []
    for ch in value:
        if ch in ('"', "\\"):
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _key(name: str) -> str:
    return name if _BARE_KEY.match(name) else _string(name)


def _value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list | tuple):
        return "[" + ", ".join(_value(v) for v in value) + "]"
    return _string(str(value))


def toml_text(top: Mapping[str, Any], tables: Mapping[str, Mapping[str, Any] | None] | None = None,
              arrays: Mapping[str, Sequence[Mapping[str, Any]]] | None = None) -> str:  # fmt: skip
    """Keys in the order given, then each table, then each array of tables: one way to write one thing."""
    lines = [f"{_key(k)} = {_value(v)}" for k, v in top.items()]
    for name, table in (tables or {}).items():
        if table is None:
            continue
        lines += ["", f"[{_key(name)}]", *(f"{_key(k)} = {_value(v)}" for k, v in table.items())]
    for name, rows in (arrays or {}).items():
        for row in rows:
            lines += ["", f"[[{_key(name)}]]", *(f"{_key(k)} = {_value(v)}" for k, v in row.items())]
    return "\n".join(lines) + "\n"


def _toml(text: str, what: str) -> dict[str, Any]:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        raise CollaborationError(f"This {what} file is not one the app wrote.") from None


# ===== 3. The files =====


@dataclass(frozen=True)
class Reference:
    """A stable reference to an object: its kind, its path (a file relative to the project, a table's or a
    connection's name), its id (a cell's number, a function's or an endpoint's name, a column) and the
    text."""

    kind: str
    path: str
    id: str = ""
    text: str = ""

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.path}" + (f"#{self.id}" if self.id else "")

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "path": self.path, "id": self.id, "text": self.text or self.key}

    def link(self) -> str:
        """As it is written in a message: [@data.ipynb cell 7](sab:cell/data.ipynb#7)."""
        place = quote(self.path, safe="/._-")
        anchor = f"#{quote(self.id, safe='._-')}" if self.id else ""
        shown = (self.text or self.key).replace("]", ")").replace("\n", " ")
        return f"[@{shown}](sab:{self.kind}/{place}{anchor})"


def in_project(ref: Reference, folder: str) -> Reference:
    """A reference whose path is a file inside the project kept relative to it (the same key on every
    computer); any other kept as it is."""
    inner = project_paths.relative_in(ref.path, folder)
    return Reference(ref.kind, inner, ref.id, ref.text) if inner else ref


def reference(raw: Any) -> Reference:
    """A reference sent or read: its kind one of REFERENCE_KINDS, a path, its id as text."""
    if not isinstance(raw, Mapping) or raw.get("kind") not in REFERENCE_KINDS:
        raise CollaborationError(f"A reference's kind is one of {', '.join(REFERENCE_KINDS)}.")
    path = " ".join(str(raw.get("path") or "").split())[:300].replace("\\", "/")
    if not path or ".." in path.split("/"):
        raise CollaborationError("A reference names its object.")
    ident = str(raw.get("id") if raw.get("id") is not None else "")[:200]
    return Reference(str(raw["kind"]), path, ident, " ".join(str(raw.get("text") or "").split())[:200])


@dataclass
class Message:
    id: str
    thread: str
    author: Person
    time: str
    body: str
    kind: str = "note"
    edited: str = ""
    deleted: bool = False
    reactions: dict[str, list[str]] = field(default_factory=dict)  # emoji -> logins
    mentions: list[str] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)

    @property
    def file(self) -> str:
        return f"{compact(self.time)}-{slug(self.author.login)}-{self.id}.md"


def message_text(m: Message) -> str:
    """The message's file: TOML front matter, then the Markdown (the same bytes for the same message)."""
    top = {
        "id": m.id,
        "thread": m.thread,
        "kind": m.kind,
        "time": m.time,
        "edited": m.edited,
        "deleted": m.deleted,
        "mentions": sorted(set(m.mentions)),
    }
    reactions = {k: sorted(set(v)) for k, v in sorted(m.reactions.items()) if v}
    head = toml_text(
        top,
        {"author": m.author.to_json(), "reactions": reactions or None},
        {"references": [r.to_json() for r in m.references]},
    )
    body = "" if m.deleted else m.body.replace("\r\n", "\n").rstrip("\n")
    return f"+++\n{head}+++\n\n{body}\n"


def parse_message(text: str) -> Message:
    if not text.startswith("+++\n") or "\n+++\n" not in text[3:]:
        raise CollaborationError("This message file is not one the app wrote.")
    end = text.index("\n+++\n", 3)
    head = _toml(text[4 : end + 1], "message")
    body = text[end + 5 :].removeprefix("\n").rstrip("\n")
    found_reactions = head.get("reactions")
    reactions: dict[str, Any] = found_reactions if isinstance(found_reactions, dict) else {}
    found: list[Reference] = []
    for raw in head.get("references") or []:
        try:
            found.append(reference(raw))
        except CollaborationError:
            continue
    return Message(
        id=check_id(head.get("id"), "message"),
        thread=check_id(head.get("thread")),
        author=person_of(head.get("author")),
        time=str(head.get("time") or ""),
        body=body,
        kind=str(head.get("kind")) if head.get("kind") in MESSAGE_KINDS else "note",
        edited=str(head.get("edited") or ""),
        deleted=bool(head.get("deleted")),
        reactions={str(k): [str(p) for p in v] for k, v in reactions.items() if isinstance(v, list)},
        mentions=[str(p) for p in head.get("mentions") or []],
        references=found,
    )


@dataclass
class Thread:
    id: str
    title: str
    created_by: Person
    created: str
    channel: str = ""  # a channel's name, or "" for a thread anchored to an object
    anchor: Reference | None = None
    resolved: dict[str, str] | None = None  # {"by": login, "time": ...}
    pinned: bool = False


def thread_text(t: Thread) -> str:
    return toml_text(
        {"id": t.id, "title": t.title, "channel": t.channel, "created": t.created, "pinned": t.pinned},
        {
            "created_by": t.created_by.to_json(),
            "anchor": t.anchor.to_json() if t.anchor else None,
            "resolved": dict(t.resolved) if t.resolved else None,
        },
    )


def parse_thread(text: str) -> Thread:
    raw = _toml(text, "thread")
    anchor = raw.get("anchor")
    resolved = raw.get("resolved")
    return Thread(
        id=check_id(raw.get("id")),
        title=str(raw.get("title") or ""),
        created_by=person_of(raw.get("created_by")),
        created=str(raw.get("created") or ""),
        channel=str(raw.get("channel") or ""),
        anchor=reference(anchor) if isinstance(anchor, dict) else None,
        resolved={"by": str(resolved.get("by") or ""), "time": str(resolved.get("time") or "")}
        if isinstance(resolved, dict)
        else None,
        pinned=bool(raw.get("pinned")),
    )


@dataclass(frozen=True)
class Event:
    id: str
    thread: str
    author: Person
    time: str
    action: str
    message: str = ""
    emoji: str = ""

    @property
    def file(self) -> str:
        return f"{compact(self.time)}-{slug(self.author.login)}-{self.id}.toml"


def event_text(e: Event) -> str:
    top = {"id": e.id, "thread": e.thread, "time": e.time, "action": e.action}
    top |= {"message": e.message} if e.message else {}
    top |= {"emoji": e.emoji} if e.emoji else {}
    return toml_text(top, {"author": e.author.to_json()})


def parse_event(text: str) -> Event:
    raw = _toml(text, "event")
    if raw.get("action") not in ACTIONS:
        raise CollaborationError("This event file is not one the app wrote.")
    return Event(
        id=check_id(raw.get("id"), "event"),
        thread=check_id(raw.get("thread")),
        author=person_of(raw.get("author")),
        time=str(raw.get("time") or ""),
        action=str(raw["action"]),
        message=str(raw.get("message") or ""),
        emoji=str(raw.get("emoji") or "")[:16],
    )


def channel_text(name: str, by: Person, time: str) -> str:
    return toml_text({"name": name, "created": time}, {"created_by": by.to_json()})


def check_emoji(value: Any) -> str:
    text = str(value or "").strip()
    if not text or len(text) > MAX_EMOJI or any(ch.isspace() for ch in text):
        raise CollaborationError("A reaction is one emoji.")
    return text


def image_name(message: str, n: int, mime: str) -> str:
    if mime not in IMAGE_TYPES:
        raise CollaborationError("A picture is a PNG, JPEG, GIF or WebP.")
    return f"{message}-{n}.{IMAGE_TYPES[mime]}"


def check_image(size: int) -> None:
    if size > MAX_IMAGE_BYTES:
        raise CollaborationError("A picture is 5 MB at most.")


# ===== 4. A message's body: references, people, pictures =====


def check_body(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").strip("\n")
    if not text.strip():
        raise CollaborationError("A message says something.")
    if len(text) > MAX_BODY:
        raise CollaborationError(f"A message is {MAX_BODY:,} characters at most.")
    return text


def references_in(body: str) -> list[Reference]:
    """The objects a message's Markdown names (each once, in the order they come)."""
    found: dict[str, Reference] = {}
    for text, kind, path, ident in REFERENCE.findall(body):
        if kind not in REFERENCE_KINDS:
            continue
        made = Reference(kind, unquote(path), unquote(ident or ""), text.strip())
        found.setdefault(made.key, made)
    return list(found.values())


def in_project_links(body: str, folder: str) -> str:
    """Each reference to a file inside the project written relative to it (a page names its files by their
    whole path: the same note on every computer names them alike)."""

    def relative(found: re.Match[str]) -> str:
        made = Reference(
            found.group(2), unquote(found.group(3)), unquote(found.group(4) or ""), found.group(1)
        )
        inner = in_project(made, folder)
        return inner.link() if inner is not made else found.group(0)

    return REFERENCE.sub(relative, body)


def mentions_in(body: str, people: Iterable[str]) -> list[str]:
    """The people a message names (@login), among the people known; a reference's own @ is not one."""
    known = set(people)
    plain = REFERENCE.sub(" ", body)
    plain = re.sub(r"```.*?```|`[^`\n]*`", " ", plain, flags=re.S)  # code is not a mention
    return sorted({m for m in MENTION.findall(plain) if m in known})


def images_in(body: str) -> list[str]:
    return IMAGE.findall(body)


def title_of(body: str) -> str:
    """A thread's title from its first message: its first line of words, short."""
    for line in body.splitlines():
        words = REFERENCE.sub(lambda m: m.group(1), line)
        words = re.sub(r"[#>*_`~\[\]()!-]+", " ", IMAGE.sub(" ", words))
        words = " ".join(words.split())
        if words:
            return words[:MAX_TITLE]
    return "A note"


# ===== 5. A thread folded: its messages, its events =====


def fold(
    thread: Thread, messages: Iterable[Message], events: Iterable[Event]
) -> tuple[Thread, list[Message]]:
    """The thread as it is now: the messages in their order, each one's reactions with the events' on top;
    resolved and pinned as the last event says."""
    shown = sorted(messages, key=lambda m: (m.time, m.kind != "note", m.id))  # the first note first
    by_id = {m.id: m for m in shown}
    reactions = {m.id: {k: set(v) for k, v in m.reactions.items()} for m in shown}
    now = Thread(**{k: getattr(thread, k) for k in thread.__dataclass_fields__})
    for e in sorted(events, key=lambda e: (e.time, e.id)):
        if e.action in ("react", "unreact") and e.message in by_id and e.emoji:
            people = reactions[e.message].setdefault(e.emoji, set())
            (people.add if e.action == "react" else people.discard)(e.author.login)
        elif e.action == "resolve":
            now.resolved = {"by": e.author.login, "time": e.time}
        elif e.action == "reopen":
            now.resolved = None
        elif e.action in ("pin", "unpin"):
            now.pinned = e.action == "pin"
    for m in shown:
        m.reactions = {k: sorted(v) for k, v in sorted(reactions[m.id].items()) if v}
    return now, shown


# ===== 6. News: what is new to you since you last read, as a project opens or a Pull brings files =====

MOST_NAMED = 2  # the people a notice names before "and N others"
MOST_COUNTED = 99  # past it, "99+ new messages"


@dataclass(frozen=True)
class News:
    count: int
    authors: tuple[str, ...]  # their names, the newest writer first
    thread: str  # the newest unread message's thread ("": none)
    first_time: bool  # nothing read here yet: this computer's first look at the project

    @property
    def words(self) -> str:
        """ "3 new messages from Sam Ortiz and Avery Lin"; the first time: "12 new messages"."""
        if self.count == 0:
            return ""
        counted = f"{MOST_COUNTED}+" if self.count > MOST_COUNTED else str(self.count)
        said = f"{counted} new message" + ("" if self.count == 1 else "s")
        if self.first_time or not self.authors:
            return said
        named = list(self.authors[:MOST_NAMED])
        more = len(self.authors) - len(named)
        if more:
            who = f"{', '.join(named)} and {more} other" + ("" if more == 1 else "s")
        else:
            who = " and ".join(named)
        return f"{said} from {who}"

    def to_json(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "words": self.words,
            "thread": self.thread,
            "first_time": self.first_time,
        }


def news(threads: Iterable[tuple[Thread, Sequence[Message]]], seen: Mapping[str, str], me: str) -> News:
    """Every message newer than its thread's read mark that someone else wrote (the agent's count: it is not
    you), the people, the newest one's thread; no mark at all: the first time."""
    fresh = [
        m
        for thread, messages in threads
        for m in messages
        if m.time > seen.get(thread.id, "") and m.author.login != me and not m.deleted
    ]
    fresh.sort(key=lambda m: (m.time, m.id), reverse=True)
    authors = tuple(dict.fromkeys(m.author.name for m in fresh))
    return News(len(fresh), authors, fresh[0].thread if fresh else "", first_time=not seen)


# ===== 7. The timeline: filters, unread, search =====


def where_of(thread: Thread) -> str:
    """The channel a thread is in: "#general", or its anchor's key."""
    return f"#{thread.channel}" if thread.channel else (thread.anchor.key if thread.anchor else f"#{GENERAL}")


def unread_of(messages: Sequence[Message], seen: str, me: str) -> int:
    """The messages after `seen` that someone else wrote."""
    return sum(1 for m in messages if m.time > seen and m.author.login != me and not m.deleted)


def page_paths(page: Any) -> list[str]:
    """The page in front as the paths and names of its objects: one ("data.ipynb", "orders") or a JSON list
    of them (the panel sends the page's objects)."""
    text = str(page or "").strip()
    if text.startswith("["):
        try:
            found = json.loads(text)
        except ValueError:
            found = []
        items = [str(p) for p in found if isinstance(p, str)] if isinstance(found, list) else []
    else:
        items = [text]
    return [p.replace("\\", "/").strip() for p in items if p.strip()]


def on_page(refs: Iterable[Reference], page: Sequence[str]) -> bool:
    """A reference to an object of the page in front: its file, or its table or connection by name."""
    return any(r.path == wanted or wanted.endswith("/" + r.path) for r in refs for wanted in page if wanted)


def kept(
    filter_by: str, thread: Thread, messages: Sequence[Message], me: str, page: Sequence[str] = ()
) -> bool:
    """Whether a thread shows under a filter."""
    if filter_by == "mentions":
        return any(me in m.mentions for m in messages)
    if filter_by == "unresolved":
        return thread.resolved is None
    if filter_by == "page":
        refs = [thread.anchor] if thread.anchor else []
        return on_page([*refs, *(r for m in messages for r in m.references)], page)
    return True


def check_filter(value: Any) -> str:
    found = str(value or "all")
    if found not in FILTERS:
        raise CollaborationError(f"A filter is one of {', '.join(FILTERS)}.")
    return found


def matches(words: str, *texts: str) -> bool:
    """Every word of the search in one of the texts, in any case."""
    wanted = words.lower().split()
    whole = " ".join(texts).lower()
    return bool(wanted) and all(w in whole for w in wanted)


def snippet(text: str, words: str, width: int = 120) -> str:
    plain = " ".join(REFERENCE.sub(lambda m: "@" + m.group(1), text).split())
    first = next((w for w in words.lower().split() if w in plain.lower()), "")
    at = max(0, plain.lower().find(first) - width // 3) if first else 0
    cut = plain[at : at + width]
    return ("…" if at else "") + cut + ("…" if at + width < len(plain) else "")


# ===== 8. Who may do what =====


def agent_may_not(what: str) -> str:
    """The refusal of every write but a post (the owner, 2026-11-25: the agent posts only with
    collaboration_post)."""
    return AGENT_ONLY_POSTS.format(what=what)


def may_change(message: Message, me: Person) -> None:
    """Only its author edits or deletes a message (the agent edits and deletes none: agent_may_not)."""
    if message.author.login != me.login:
        raise PermissionError(NOT_YOURS)
    if message.deleted:
        raise CollaborationError("That message was deleted.")


# ===== Where an object opens (the front end follows the href; the server knows every kind) =====


def href(ref: Reference, folder: str, line: int | None = None) -> str | None:
    """The page that shows a reference's object, as the app's own addresses: a notebook at its cell, a
    script at a line, the Tables page at a table, a connection's card."""
    full = (
        ref.path if ref.path.startswith("/") or re.match(r"^[A-Za-z]:", ref.path) else f"{folder}/{ref.path}"
    )
    at = quote(full, safe="")
    if ref.kind == "cell":
        return f"notebooks?path={at}&cell={quote(ref.id)}"
    if ref.kind == "notebook":
        return f"notebooks?path={at}"
    if ref.kind in ("script", "sql", "function", "endpoint"):
        return f"scripts?path={at}" + (f"&line={line}" if line else "")
    if ref.kind in ("table", "column"):
        return f"tables?table={quote(ref.path, safe='')}"
    if ref.kind == "connection":
        return f"connections?name={quote(ref.path, safe='')}"
    if ref.kind == "widget":
        return f"canvas?path={at}"
    return "analyze"


def cell_numbers(notebook: Mapping[str, Any]) -> dict[int, str]:
    """A notebook's (nbformat JSON) cells by their own numbers: each one's first line, for the picker."""
    out: dict[int, str] = {}
    for cell in notebook.get("cells") or []:
        if not isinstance(cell, Mapping):
            continue
        marks = (cell.get("metadata") or {}).get("swissarmybench") or {}
        number = marks.get("number") if isinstance(marks, Mapping) else None
        if isinstance(number, int):
            source = cell.get("source")
            text = "".join(source) if isinstance(source, list) else str(source or "")
            first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
            out[number] = str(marks.get("name") or first)[:80]
    return out


def widget_ids(canvas: Any) -> dict[str, str]:
    """A canvas file's widget instances: id -> its widget's name."""
    out: dict[str, str] = {}

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            if node.get("kind") == "widget" and isinstance(node.get("id"), str):
                out[str(node["id"])] = str(node.get("widget") or "widget")
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(canvas)
    return out
