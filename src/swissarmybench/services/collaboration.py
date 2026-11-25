"""The Collaboration panel: the team's notes, threads and activity inside a project (domain/collaboration.py
has the format and the rules; the owner, 2026-11-25, who named it).

Everything is files in the open project's `.sab/collaboration/`, so the notes travel with the project's own
Pull and Push (the team repository: CLAUDE.md "A team"); a project that is not shared keeps them on this
computer only. No server and no other network traffic.

  timeline    a channel's or an object's threads (or all of them) mixed with the activity, filtered
              (all, mentions, the page's objects, unresolved, activity only, notes only); the channels and
              the objects that have threads, each with its unread count; whether the project is shared;
              the team's sync words
  thread      one thread folded (its messages, reactions, resolved, pinned); each reference with where it
              opens and whether its object is still in the project
  post, reply, edit, delete, react, resolve, pin, channel     each a small file of its own (a Git merge never
              conflicts); deleting is the user's own (the agent edits its own messages, deletes none)
  search, activity, unread, objects (the `@` picker: people and the project's objects), profile (this
              computer's name: the GitHub login when signed in, else Settings' name, else the system's)
  changed     a change log entry (services/changes.py's listeners): one line of this person's activity
  look        every few seconds, off the loop: files a Pull or another window brought, said as
              `collaboration_changed` {threads} and `collaboration_unread` {total, mentions, places}
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import secrets
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Protocol

from swissarmybench.domain import collaboration as rules
from swissarmybench.services.workspace import Conflict, NotFound, Refused, Workspace

Stamp = tuple[int, int]
Folded = tuple[rules.Thread, list[rules.Message]]


class Files(Protocol):
    """adapters/collaboration.py CollaborationFiles."""

    def read(self, path: str) -> str | None: ...

    def read_bytes(self, path: str) -> bytes | None: ...

    def write(self, path: str, data: str | bytes) -> bool: ...

    def remove(self, path: str) -> None: ...

    def exists(self, path: str) -> bool: ...

    def stamps(self, folder: str) -> dict[str, Stamp]: ...


class Objects(Protocol):
    """adapters/collaboration.py ProjectObjects."""

    def present(self, folder: str, ref: rules.Reference) -> tuple[bool, int | None]: ...

    def candidates(self, folder: str | None) -> list[rules.Reference]: ...


class Kept(Protocol):
    def read(self) -> Any: ...

    def write(self, data: Any) -> None: ...


class TeamPort(Protocol):
    """services/team.py Team: the Team box's status (its sync words)."""

    async def status(self, remote: bool = False, who: str = "user") -> dict[str, Any]: ...


class Where(Protocol):
    """services/project_explorer.py ProjectExplorer: is a project folder shared or local."""

    def where(self, path: str) -> str: ...


def _utc_now() -> str:
    """UTC to the microsecond, so two writes in one second still sort in the order they were made."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class Collaboration:
    def __init__(
        self,
        ws: Workspace,
        files: Files,
        objects: Objects,
        project: Callable[[], str | None],
        profile: Kept,
        read_marks: Kept,
        *,
        system_name: str,
        hooks: Any = None,
        team: TeamPort | None = None,
        explorer: Where | None = None,
        now: Callable[[], str] = _utc_now,
        new_id: Callable[[], str] = lambda: secrets.token_hex(4),
        every: float = 3.0,
    ) -> None:
        self.ws = ws
        self._files = files
        self._objects = objects
        self._project = project
        self._profile = profile
        self._marks = read_marks
        self._now = now
        self._new_id = new_id
        self._system = system_name
        self._hooks = hooks  # hooks.team (the Git extension's): the GitHub login when signed in
        self._team = team
        self._explorer = explorer
        self._every = every
        self._looked: tuple[str | None, dict[str, Stamp]] = (None, {})
        self._tasks: set[asyncio.Task[None]] = set()

    def _github(self) -> str | None:
        sync = getattr(self._hooks, "team", None)
        account = sync.signed_in().get("account") if sync is not None else None
        return str(account) if account else None

    def _shared(self, project: str) -> bool:
        return self._explorer is not None and self._explorer.where(project) == "shared"

    async def _team_sync(self) -> dict[str, Any] | None:
        if self._team is None:
            return None
        team = (await self._team.status()).get("team")
        return team.get("sync") if isinstance(team, dict) else None

    # ===== who is writing =====

    def me(self) -> rules.Person:
        kept = self._profile.read()
        name = str(kept.get("name") or "") if isinstance(kept, dict) else ""
        login = self._github()
        return rules.person(name or login or self._system, login)

    def _author(self, who: str) -> rules.Person:
        return rules.agent_for(self.me()) if who == "agent" else self.me()

    def profile(self) -> dict[str, Any]:
        kept = self._profile.read()
        named = isinstance(kept, dict) and bool(kept.get("name"))
        source = "settings" if named else "github" if self._github() else "system"
        return self.me().to_json() | {"source": source, "github": self._github()}

    async def set_profile(self, body: Any, who: str = "user") -> dict[str, Any]:
        name = " ".join(str((body or {}).get("name") or "").split())[:80] if isinstance(body, dict) else ""
        self._profile.write({"name": name} if name else {})
        await self.ws.live.broadcast({"type": "collaboration_changed", "threads": []})
        return self.profile()

    # ===== the folder =====

    def _root(self) -> str:
        folder = self._project()
        if not folder:
            raise Conflict("Open a project first: its collaboration is kept in its folder.")
        return folder

    @staticmethod
    def _dir(project: str) -> str:
        return f"{project}/{rules.FOLDER}"

    def _load(self, project: str) -> dict[str, Folded]:
        """Every thread of the project, folded."""
        top = self._dir(project)
        names = sorted(self._files.stamps(top))
        threads: dict[str, Folded] = {}
        for name in names:
            parts = name.split("/")
            if len(parts) != 2 or parts[1] != rules.THREAD_FILE or parts[0].startswith("_"):
                continue
            folder = parts[0]
            try:
                thread = rules.parse_thread(self._files.read(f"{top}/{name}") or "")
            except rules.CollaborationError:
                continue
            messages, events = [], []
            for inner in names:
                if inner.startswith(f"{folder}/") and inner.endswith(".md") and inner.count("/") == 1:
                    try:
                        messages.append(rules.parse_message(self._files.read(f"{top}/{inner}") or ""))
                    except rules.CollaborationError:
                        continue
                elif inner.startswith(f"{folder}/{rules.EVENTS}/") and inner.endswith(".toml"):
                    try:
                        events.append(rules.parse_event(self._files.read(f"{top}/{inner}") or ""))
                    except rules.CollaborationError:
                        continue
            threads[thread.id] = rules.fold(thread, messages, events)
        return threads

    def _one(self, project: str, thread: Any) -> Folded:
        ident = rules.check_id(thread)
        found = self._load(project).get(ident)
        if found is None:
            raise NotFound("No such thread in this project's collaboration.")
        return found

    def _activity(self, project: str) -> list[dict[str, Any]]:
        top = f"{self._dir(project)}/{rules.ACTIVITY}"
        lines: list[dict[str, Any]] = []
        for name in sorted(self._files.stamps(top)):
            if name.endswith(".jsonl"):
                lines += rules.parse_activity(self._files.read(f"{top}/{name}") or "")
        return sorted(lines, key=lambda a: (str(a["time"]), str(a["id"])))

    def _channels(self, project: str, threads: Mapping[str, Folded]) -> list[str]:
        made = {rules.GENERAL}
        made |= {t.channel for t, _ in threads.values() if t.channel}
        top = f"{self._dir(project)}/{rules.CHANNELS}"
        made |= {n.removesuffix(".toml") for n in self._files.stamps(top) if n.endswith(".toml")}
        return [rules.GENERAL, *sorted(made - {rules.GENERAL})]

    def _people(self, threads: Mapping[str, Folded], activity: list[dict[str, Any]]) -> dict[str, str]:
        seen = {self.me().login: self.me().name}
        for thread, messages in threads.values():
            seen.setdefault(thread.created_by.login, thread.created_by.name)
            for m in messages:
                seen.setdefault(m.author.login, m.author.name)
        for line in activity:
            found = rules.person_of(line.get("author"))
            seen.setdefault(found.login, found.name)
        return dict(sorted(seen.items()))

    # ===== reading: the read marks =====

    def _seen(self, project: str) -> dict[str, str]:
        kept = self._marks.read()
        found = kept.get(project) if isinstance(kept, dict) else None
        return {str(k): str(v) for k, v in found.items()} if isinstance(found, dict) else {}

    def _mark(self, project: str, thread: str, time: str) -> None:
        kept = self._marks.read()
        marks: dict[str, Any] = dict(kept) if isinstance(kept, dict) else {}
        mine = dict(marks.get(project) or {})
        if mine.get(thread, "") >= time:
            return
        mine[thread] = time
        marks[project] = dict(sorted(mine.items()))
        self._marks.write(marks)

    def _counts(self, project: str, threads: Mapping[str, Folded]) -> dict[str, Any]:
        seen, me = self._seen(project), self.me().login
        places: dict[str, int] = {}
        total = mentions = 0
        for thread, messages in threads.values():
            after = seen.get(thread.id, "")
            unread = rules.unread_of(messages, after, me)
            total += unread
            mentions += sum(
                1 for m in messages if m.time > after and me in m.mentions and m.author.login != me
            )
            where = rules.where_of(thread)
            places[where] = places.get(where, 0) + unread
        return {"total": total, "mentions": mentions, "places": places}

    def unread(self) -> dict[str, Any]:
        project = self._project()
        if not project:
            return {"total": 0, "mentions": 0, "places": {}}
        return self._counts(project, self._load(project))

    async def mark_read(self, body: Any, who: str = "user") -> dict[str, Any]:
        """The panel showed a thread: read up to its last message (this computer's, the user's own)."""
        project = self._root()
        thread, messages = self._one(project, (body or {}).get("thread") if isinstance(body, dict) else None)
        if who != "agent" and messages:
            self._mark(project, thread.id, messages[-1].time)
            await self._said(project, [])
        return self.unread()

    # ===== views =====

    def _ref_view(self, project: str, ref: rules.Reference) -> dict[str, Any]:
        there, line = self._objects.present(project, ref)
        return ref.to_json() | {"gone": not there, "href": rules.href(ref, project, line)}

    def _message_view(self, project: str, m: rules.Message, who: str) -> dict[str, Any]:
        mine = self._author(who).login
        return {
            "id": m.id,
            "thread": m.thread,
            "kind": m.kind,
            "author": m.author.to_json(),
            "time": m.time,
            "edited": m.edited,
            "deleted": m.deleted,
            "body": "" if m.deleted else m.body,
            "mentions": m.mentions,
            "references": [self._ref_view(project, r) for r in m.references],
            "reactions": [
                {"emoji": e, "people": people, "mine": mine in people} for e, people in m.reactions.items()
            ],
            "mine": m.author.login == mine,
        }

    def _thread_view(self, project: str, folded: Folded, seen: Mapping[str, str], who: str) -> dict[str, Any]:
        thread, messages = folded
        first = messages[0] if messages else None
        return {
            "id": thread.id,
            "title": thread.title,
            "channel": thread.channel,
            "where": rules.where_of(thread),
            "anchor": self._ref_view(project, thread.anchor) if thread.anchor else None,
            "created_by": thread.created_by.to_json(),
            "created": thread.created,
            "resolved": thread.resolved,
            "pinned": thread.pinned,
            "replies": max(0, len(messages) - 1),
            "last": messages[-1].time if messages else thread.created,
            "unread": rules.unread_of(messages, seen.get(thread.id, ""), self.me().login),
            "first": self._message_view(project, first, who) if first else None,
        }

    @staticmethod
    def _activity_view(line: Mapping[str, Any], threads: Mapping[str, Folded]) -> dict[str, Any]:
        on = [
            t.id
            for t, _ in threads.values()
            if t.anchor and t.anchor.kind == "change" and t.anchor.id == line["id"]
        ]
        return {
            "type": "activity",
            "id": line["id"],
            "time": line["time"],
            "author": line.get("author"),
            "object": line.get("object"),
            "words": line.get("words"),
            "threads": on,
            "replies": sum(len(threads[t][1]) for t in on),
        }

    async def timeline(self, query: Mapping[str, Any], who: str = "user") -> dict[str, Any]:
        """{where?: "#general" | an object's key, filter?, page?}: the timeline, oldest first (the last
        200)."""
        project = self._project()
        me = self.me()
        if not project:
            return {
                "project": None,
                "me": me.to_json(),
                "items": [],
                "channels": [],
                "objects": [],
                "unread": {},
            }
        threads = self._load(project)
        activity = self._activity(project)
        shown = rules.check_filter(query.get("filter"))
        where = str(query.get("where") or "")
        page = str(query.get("page") or "")
        seen = self._seen(project)
        items: list[dict[str, Any]] = []
        for folded in threads.values():
            thread, messages = folded
            if where and rules.where_of(thread) != where:
                continue
            if thread.anchor and thread.anchor.kind == "change" and not where:
                continue  # shown under its activity line
            if shown != "notes" and not rules.kept(shown, thread, messages, me.login, page):
                continue
            items.append({"type": "thread"} | self._thread_view(project, folded, seen, who))
        if not where and shown in ("all", "activity"):
            items += [self._activity_view(line, threads) for line in activity]
        items.sort(key=lambda i: (str(i.get("created") or i.get("time")), str(i["id"])))
        counts = self._counts(project, threads)
        places = counts["places"]
        anchored = {
            t.anchor.key: t.anchor for t, _ in threads.values() if t.anchor and t.anchor.kind != "change"
        }
        return {
            "project": project,
            "me": me.to_json(),
            "shared": self._shared(project),
            "team": await self._team_sync(),
            "channels": [
                {"name": c, "key": f"#{c}", "unread": places.get(f"#{c}", 0)}
                for c in self._channels(project, threads)
            ],
            "objects": [
                self._ref_view(project, ref) | {"key": key, "unread": places.get(key, 0)}
                for key, ref in sorted(anchored.items())
            ],
            "people": [{"login": k, "name": v} for k, v in self._people(threads, activity).items()],
            "items": items[-200:],
            "unread": counts,
        }

    def thread(self, ident: Any, who: str = "user") -> dict[str, Any]:
        project = self._root()
        folded = self._one(project, ident)
        view = self._thread_view(project, folded, self._seen(project), who)
        return (
            {"type": "thread"} | view | {"messages": [self._message_view(project, m, who) for m in folded[1]]}
        )

    # ===== writing =====

    def _known(self, project: str) -> list[str]:
        return list(self._people(self._load(project), self._activity(project)))

    def _images(self, project: str, thread: str, message: str, text: str, sent: Any) -> str:
        """The pictures pasted into a message, each a file beside it; `sab-image:new-<n>` in the body
        named."""
        if not sent:
            return text
        if not isinstance(sent, list):
            raise rules.CollaborationError('Send "images" as a list of {"type", "data"} (base64).')
        for n, image in enumerate(sent, 1):
            if not isinstance(image, dict):
                raise rules.CollaborationError('A picture is {"type", "data"} (base64).')
            name = rules.image_name(message, n, str(image.get("type") or ""))
            try:
                data = base64.b64decode(str(image.get("data") or ""), validate=True)
            except (binascii.Error, ValueError):
                raise rules.CollaborationError("A picture's data is base64.") from None
            rules.check_image(len(data))
            self._files.write(f"{self._dir(project)}/{thread}/{name}", data)
            text = text.replace(f"sab-image:new-{n})", f"sab-image:{name})")
        return text

    def _message(self, project: str, thread: str, body: Any, who: str, kind: str) -> rules.Message:
        sent = body if isinstance(body, dict) else {}
        ident = self._new_id()
        text = self._images(project, thread, ident, rules.check_body(sent.get("body")), sent.get("images"))
        return rules.Message(
            id=ident,
            thread=thread,
            author=self._author(who),
            time=self._now(),
            body=text,
            kind=kind,
            mentions=rules.mentions_in(text, self._known(project)),
            references=rules.references_in(text),
        )

    def _write_message(self, project: str, m: rules.Message, file: str | None = None) -> None:
        self._files.write(f"{self._dir(project)}/{m.thread}/{file or m.file}", rules.message_text(m))

    async def post(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{channel? (default general) | anchor? (a reference), title?, body, images?}: a new thread."""
        project = self._root()
        sent = body if isinstance(body, dict) else {}
        anchor = rules.in_project(rules.reference(sent["anchor"]), project) if sent.get("anchor") else None
        channel = "" if anchor else rules.channel_name(sent.get("channel") or rules.GENERAL)
        ident = f"t-{self._new_id()}"
        first = self._message(project, ident, sent, who, "note")
        title = " ".join(str(sent.get("title") or "").split())[: rules.MAX_TITLE] or rules.title_of(
            first.body
        )
        thread = rules.Thread(ident, title, first.author, first.time, channel, anchor)
        self._files.write(f"{self._dir(project)}/{ident}/{rules.THREAD_FILE}", rules.thread_text(thread))
        self._write_message(project, first)
        if who != "agent":
            self._mark(project, ident, first.time)
        self.ws.audit.write(who, "collaboration_post", None, thread=ident)
        await self._said(project, [ident])
        return self.thread(ident, who)

    async def reply(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{thread, body, images?}, or {activity: a line's id, body}: a reply (a change's own thread made)."""
        project = self._root()
        sent = body if isinstance(body, dict) else {}
        if sent.get("activity") and not sent.get("thread"):
            return await self._reply_to_change(project, sent, who)
        thread, _ = self._one(project, sent.get("thread"))
        made = self._message(project, thread.id, sent, who, "reply")
        self._write_message(project, made)
        if who != "agent":
            self._mark(project, thread.id, made.time)
        self.ws.audit.write(who, "collaboration_reply", None, thread=thread.id)
        await self._said(project, [thread.id])
        return self.thread(thread.id, who)

    async def _reply_to_change(self, project: str, sent: Mapping[str, Any], who: str) -> dict[str, Any]:
        line = next((a for a in self._activity(project) if a["id"] == str(sent["activity"])), None)
        if line is None:
            raise NotFound("No such change in this project's activity.")
        anchor = rules.change_reference(line)
        for thread, _ in self._load(project).values():
            if thread.anchor and thread.anchor.key == anchor.key:
                return await self.reply(dict(sent) | {"thread": thread.id}, who)
        return await self.post(
            {"anchor": anchor.to_json(), "title": anchor.text, "body": sent.get("body")}, who
        )

    def _find(self, project: str, sent: Mapping[str, Any]) -> tuple[rules.Thread, rules.Message, str]:
        thread, messages = self._one(project, sent.get("thread"))
        ident = rules.check_id(sent.get("message"), "message")
        found = next((m for m in messages if m.id == ident), None)
        if found is None:
            raise NotFound("No such message in that thread.")
        return thread, found, found.file

    async def edit(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{thread, message, body}: its author's (the agent its own); only that message's file is
        rewritten."""
        project = self._root()
        sent = body if isinstance(body, dict) else {}
        thread, message, file = self._find(project, sent)
        try:
            rules.may_change(message, self.me(), who == "agent", deleting=False)
        except PermissionError as error:
            raise Refused(str(error)) from None
        message.body = rules.check_body(sent.get("body"))
        message.edited = self._now()
        message.mentions = rules.mentions_in(message.body, self._known(project))
        message.references = rules.references_in(message.body)
        message.reactions = {}  # the reactions are the events' (folded on read); the file keeps its own
        self._write_message(project, message, file)
        self.ws.audit.write(who, "collaboration_edit", None, thread=thread.id)
        await self._said(project, [thread.id])
        return self.thread(thread.id, who)

    async def delete(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{thread, message}: the user's own message, marked deleted (its pictures gone). Never the
        agent's."""
        if who == "agent":
            raise Refused(rules.AGENT_DELETE)
        project = self._root()
        sent = body if isinstance(body, dict) else {}
        thread, message, file = self._find(project, sent)
        try:
            rules.may_change(message, self.me(), False, deleting=True)
        except PermissionError as error:
            raise Refused(str(error)) from None
        for name in rules.images_in(message.body):
            self._files.remove(f"{self._dir(project)}/{thread.id}/{name}")
        message.deleted, message.body, message.edited = True, "", self._now()
        self._write_message(project, message, file)
        self.ws.audit.write(who, "collaboration_delete", None, thread=thread.id)
        await self._said(project, [thread.id])
        return self.thread(thread.id, who)

    async def _event(self, project: str, thread: str, action: str, who: str, **more: str) -> None:
        event = rules.Event(self._new_id(), thread, self._author(who), self._now(), action, **more)
        self._files.write(
            f"{self._dir(project)}/{thread}/{rules.EVENTS}/{event.file}", rules.event_text(event)
        )
        self.ws.audit.write(who, f"collaboration_{action}", None, thread=thread)
        await self._said(project, [thread])

    async def react(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{thread, message, emoji}: your reaction on, or off when it is there (a small file of its own)."""
        project = self._root()
        sent = body if isinstance(body, dict) else {}
        thread, message, _ = self._find(project, sent)
        emoji = rules.check_emoji(sent.get("emoji"))
        on = self._author(who).login not in message.reactions.get(emoji, [])
        await self._event(
            project, thread.id, "react" if on else "unreact", who, message=message.id, emoji=emoji
        )
        return self.thread(thread.id, who)

    async def resolve(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{thread, resolved?: true | false}: resolved, or opened again."""
        project = self._root()
        sent = body if isinstance(body, dict) else {}
        thread, _ = self._one(project, sent.get("thread"))
        await self._event(project, thread.id, "reopen" if sent.get("resolved") is False else "resolve", who)
        return self.thread(thread.id, who)

    async def pin(self, body: Any, who: str = "user") -> dict[str, Any]:
        project = self._root()
        sent = body if isinstance(body, dict) else {}
        thread, _ = self._one(project, sent.get("thread"))
        await self._event(project, thread.id, "unpin" if sent.get("pinned") is False else "pin", who)
        return self.thread(thread.id, who)

    async def channel(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{name}: a channel the team can post in (#general is always there)."""
        project = self._root()
        name = rules.channel_name((body or {}).get("name") if isinstance(body, dict) else None)
        path = f"{self._dir(project)}/{rules.CHANNELS}/{name}.toml"
        if not self._files.exists(path) and name != rules.GENERAL:
            self._files.write(path, rules.channel_text(name, self._author(who), self._now()))
            self.ws.audit.write(who, "collaboration_channel", None, channel=name)
            await self._said(project, [])
        return {"channel": name, "key": f"#{name}"}

    async def show(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{anchor? | where?}: every window opens the panel there (Collaborate on an object; the agent's
        collaboration_show). Nothing is written."""
        sent = body if isinstance(body, dict) else {}
        found = rules.reference(sent["anchor"]) if sent.get("anchor") else None
        project = self._project()
        anchor = rules.in_project(found, project) if found and project else found
        where = anchor.key if anchor else str(sent.get("where") or "")
        notice = {
            "type": "collaboration_show",
            "where": where,
            "anchor": anchor.to_json() if anchor else None,
        }
        await self.ws.live.broadcast(notice)
        return {"shown": True, "where": where}

    # ===== search, activity, the picker, pictures =====

    def search(self, words: Any, who: str = "user") -> dict[str, Any]:
        project = self._root()
        said = " ".join(str(words or "").split())
        if not said:
            raise rules.CollaborationError("Search for some words.")
        threads = self._load(project)
        found: list[dict[str, Any]] = []
        for thread, messages in threads.values():
            for m in messages:
                refs = " ".join(r.text for r in m.references)
                if not m.deleted and rules.matches(said, thread.title, m.body, refs, m.author.name):
                    found.append(
                        {"type": "message", "thread": thread.id, "title": thread.title, "message": m.id}
                        | {
                            "time": m.time,
                            "author": m.author.to_json(),
                            "snippet": rules.snippet(m.body, said),
                        }
                    )
        for line in self._activity(project):
            obj = line.get("object") or {}
            if rules.matches(said, str(line.get("words")), str(obj.get("name")), str(obj.get("kind"))):
                found.append(self._activity_view(line, threads) | {"snippet": str(line.get("words"))})
        found.sort(key=lambda f: str(f["time"]), reverse=True)
        return {"words": said, "found": found[:100]}

    def activity(self, query: Mapping[str, Any]) -> dict[str, Any]:
        project = self._root()
        try:
            most = int(query.get("n") or 50)
        except (TypeError, ValueError):
            raise rules.CollaborationError("n is a whole number.") from None
        person = str(query.get("who") or "")
        lines = [
            a
            for a in self._activity(project)
            if not person or rules.person_of(a.get("author")).login == person
        ]
        threads = self._load(project)
        return {"activity": [self._activity_view(a, threads) for a in reversed(lines)][:most]}

    def objects(self, words: Any = "") -> dict[str, Any]:
        """The `@` picker: the people who wrote here, then the project's objects, matching the words."""
        project = self._project()
        said = str(words or "").strip()
        people = self._people(self._load(project), self._activity(project)) if project else {}
        found_people = [
            {"login": k, "name": v} for k, v in people.items() if not said or rules.matches(said, k, v)
        ]
        refs = [
            r
            for r in self._objects.candidates(project)
            if not said or rules.matches(said, r.text, r.path, r.kind)
        ]
        return {
            "people": found_people[:20],
            "objects": [r.to_json() | {"link": r.link()} for r in refs[:60]],
        }

    def image(self, thread: Any, name: Any) -> tuple[bytes, str]:
        project = self._root()
        ident = rules.check_id(thread)
        file = str(name or "")
        if not rules.IMAGE.fullmatch(f"![](sab-image:{file})"):
            raise NotFound("No such picture.")
        data = self._files.read_bytes(f"{self._dir(project)}/{ident}/{file}")
        if data is None:
            raise NotFound("No such picture.")
        mime = next(m for m, ext in rules.IMAGE_TYPES.items() if file.endswith(f".{ext}"))
        return data, mime

    # ===== the activity, heard from the change log =====

    def changed(self, event: Mapping[str, Any]) -> None:
        """A change log entry (stamped): one line of this person's activity, the file trimmed to 90 days."""
        project = self._project()
        me = self.me()
        line = rules.activity_line(event, me) if project else None
        if line is None or project is None:
            return
        path = f"{self._dir(project)}/{rules.ACTIVITY}/{rules.slug(me.login)}.jsonl"
        lines = rules.trimmed([*rules.parse_activity(self._files.read(path) or ""), line], self._now())
        self._files.write(path, rules.activity_text(lines))
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # written off the loop: the next look says it
        task = loop.create_task(self._said(project, []))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # ===== the notices: a write here, or a look at the folder =====

    async def _said(self, project: str, threads: list[str]) -> None:
        stamps = await asyncio.to_thread(self._files.stamps, self._dir(project))
        self._looked = (project, stamps)
        await self.ws.live.broadcast({"type": "collaboration_changed", "threads": threads})
        await self.ws.live.broadcast({"type": "collaboration_unread"} | self.unread())

    async def look(self) -> list[str]:
        """The project's folder looked at (off the loop): the threads whose files changed since."""
        project = self._project()
        if not project:
            self._looked = (None, {})
            return []
        stamps = await asyncio.to_thread(self._files.stamps, self._dir(project))
        was_for, was = self._looked
        self._looked = (project, stamps)
        if was_for != project or stamps == was:
            return []
        changed = {p.split("/")[0] for p in set(stamps) ^ set(was)}
        changed |= {p.split("/")[0] for p in stamps.keys() & was.keys() if stamps[p] != was[p]}
        threads = sorted(t for t in changed if not t.startswith("_"))
        await self.ws.live.broadcast({"type": "collaboration_changed", "threads": threads})
        await self.ws.live.broadcast({"type": "collaboration_unread"} | await asyncio.to_thread(self.unread))
        return threads

    async def run_forever(self) -> None:
        while True:
            try:
                await self.look()
            except Exception:  # noqa: S110 (a folder that went away: the next look again)
                pass
            await asyncio.sleep(self._every)
