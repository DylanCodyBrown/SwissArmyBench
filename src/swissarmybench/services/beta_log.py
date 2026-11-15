"""The beta log and the beta notes (domain/beta_log.py has the rules; adapters/beta_log.py the files).

Beta mode is ONE switch for both (the owner, 2026-11-15: "Make it so we can turn off beta mode easily
and turn it back on at any point"). It lasts across restarts (beta.json in the state folder);
SWISSARMYBENCH_BETA=1 or 0 wins when set; with neither, BETA_MODE_DEFAULT. Off: nothing is written and
the pages drop their note item and their listeners; the files already written stay until Clear the log.

What arrives here: a server error or refusal (from the HTTP door), a slow request (its middleware), a
child process's start, end or crash (the kernels', Streamlit's, the blade runner's), a page's error, and a
note. Each is redacted before it is queued; the writer thread puts it on disk.
"""

from __future__ import annotations

import asyncio
import base64
import secrets as random_ids
import traceback
from collections import deque
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any, Protocol

from swissarmybench.domain import beta_log as rules
from swissarmybench.services.workspace import Refused, Workspace

VARIABLE = "SWISSARMYBENCH_BETA"
MAX_PICTURE_BYTES = 16 * 1024 * 1024


class BetaFilesPort(Protocol):
    def write(self, entry: dict[str, Any]) -> bool: ...
    def flush(self, timeout: float = 5.0) -> None: ...
    def read(self) -> list[dict[str, Any]]: ...
    def save_picture(self, note_id: str, data: bytes) -> str: ...
    def pictures(self) -> list[str]: ...
    def size(self) -> dict[str, int]: ...
    def clear(self) -> int: ...
    def zip_to(self, path: str, notes: list[dict[str, Any]], pictures: bool) -> dict[str, Any]: ...


class SwitchPort(Protocol):
    def read(self) -> bool | None: ...
    def write(self, on: bool) -> None: ...


Listener = Callable[[str, BaseException | None], None]


def parse_switch(value: str) -> bool | None:
    """SWISSARMYBENCH_BETA as set: 1/true/on/yes, 0/false/off/no; anything else (or unset) is None."""
    word = value.strip().casefold()
    if word in ("1", "true", "on", "yes"):
        return True
    if word in ("0", "false", "off", "no"):
        return False
    return None


class BetaLog:
    def __init__(
        self,
        ws: Workspace,
        files: BetaFilesPort,
        switch: SwitchPort,
        *,
        variable: str,
        facts: dict[str, str],
        home: str,
        names: Callable[[], dict[str, list[str]]],
        secrets: Callable[[], Iterable[str]] = lambda: (),
        listen: Callable[[Listener], Callable[[], None]] | None = None,
        now: Callable[[], float],
    ) -> None:
        self.ws = ws
        self._files = files
        self._switch = switch
        self._forced = parse_switch(variable)
        self._saved = switch.read()
        self._facts = facts
        self._home = home
        self._names = names
        self._secrets = secrets
        self._listen = listen
        self._stop_listening: Callable[[], None] | None = None
        self._now = now
        self._aliases = rules.Aliases()
        self._cap = rules.RateCap()
        self._recent_errors: deque[str] = deque(maxlen=5)
        self._seen: deque[int] = deque(maxlen=20)  # errors logged already (a route's, then its logger's)

    # ===== the switch =====

    @property
    def on(self) -> bool:
        if self._forced is not None:
            return self._forced
        return rules.BETA_MODE_DEFAULT if self._saved is None else self._saved

    def _set_by(self) -> str:
        return "environment" if self._forced is not None else "default" if self._saved is None else "settings"

    async def state(self) -> dict[str, Any]:
        """Beta mode (on, and what decided it), and what the log holds now."""
        held = await asyncio.to_thread(self._files.size)
        return {
            "on": self.on,
            "set_by": self._set_by(),
            "variable": VARIABLE,
            "default": rules.BETA_MODE_DEFAULT,
            **held,
        }

    async def set(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"on": true|false}: turn beta mode on or off, now and at the next start."""
        on = body.get("on") if isinstance(body, dict) else None
        if not isinstance(on, bool):
            raise ValueError('Send {"on": true} or {"on": false}.')
        if self._forced is not None and on != self._forced:
            raise Refused(
                f"{VARIABLE} is set to {'1' if self._forced else '0'} for this server: it decides beta mode."
            )
        was = self.on
        self._saved = on
        await asyncio.to_thread(self._switch.write, on)
        self.ws.audit.write(who, "beta_mode", None, on=on)
        if on and not was:
            self._write({"kind": "start", "reason": "beta mode on", **self._facts}, force=True)
        state = await self.state()
        await self.ws.live.broadcast({"type": "beta_changed", "on": self.on})
        return state

    # ===== the server's life =====

    def started(self) -> None:
        """The server started: its version, OS and Python; and the crashes its loggers see."""
        self._write({"kind": "start", **self._facts}, force=True)
        if self._listen is not None and self._stop_listening is None:
            self._stop_listening = self._listen(self._logged)

    def stopped(self) -> None:
        self._write({"kind": "stop"}, force=True)
        if self._stop_listening is not None:
            self._stop_listening()
            self._stop_listening = None
        self._files.flush(2.0)

    def _logged(self, message: str, error: BaseException | None) -> None:
        """An error a watched logger saw (a request's exception that escaped, a task nobody awaited)."""
        if error is not None:
            self.server_error(error, route=None, method=None, where="logger")
        else:
            self._write({"kind": "error", "where": "logger", "message": self._redact(message)})

    # ===== writing =====

    def _redact(self, text: str) -> str:
        return rules.redact(text, self._learned(), self._home, self._secrets())

    def _learned(self) -> rules.Aliases:
        try:
            self._aliases.learn(self._names())
        except Exception:  # noqa: S110 (names change under it: the ones learned earlier still apply)
            pass
        return self._aliases

    def _write(self, entry: dict[str, Any], force: bool = False) -> str | None:
        if not self.on:
            return None
        now = self._now()
        if not force and not self._cap.allow(now):
            return None
        dropped = self._cap.take_dropped()
        stamp = datetime.fromtimestamp(now, UTC).isoformat(timespec="milliseconds")
        if dropped:
            self._files.write({"time": stamp, "kind": "dropped", "events": dropped})
        event_id = entry.pop("id", None) or "e" + random_ids.token_hex(4)
        self._files.write({"time": stamp, "id": event_id, **entry})
        return event_id

    def server_error(
        self, error: BaseException, route: str | None, method: str | None, where: str = "request"
    ) -> str | None:
        """An error the server did not expect: its type, its message redacted, its frames. Its id."""
        if not self.on or id(error) in self._seen:
            return None
        self._seen.append(id(error))
        entry: dict[str, Any] = {
            "kind": "error",
            "where": where,
            "route": route,
            "method": method,
            "type": type(error).__name__,
            "message": self._redact(str(error)),
            "frames": rules.frames(
                (f.filename, f.lineno, f.name) for f in traceback.extract_tb(error.__traceback__)
            ),
        }
        led = error.__cause__ or error.__context__
        if led is not None:
            entry["after"] = {"type": type(led).__name__, "message": self._redact(str(led))}
        event_id = self._write({k: v for k, v in entry.items() if v is not None})
        if event_id:
            self._recent_errors.append(event_id)
        return event_id

    def refused(self, error: BaseException, route: str | None, method: str | None, status: int) -> None:
        """A request answered 4xx: which route, the status, the error's type and its redacted words."""
        if self.on:
            self._write(
                {
                    "kind": "refused",
                    "route": route,
                    "method": method,
                    "status": status,
                    "type": type(error).__name__,
                    "message": self._redact(str(error)),
                }
            )

    def slow(self, route: str, method: str, status: int, milliseconds: float) -> None:
        if self.on:
            self._write(
                {
                    "kind": "slow",
                    "route": route,
                    "method": method,
                    "status": status,
                    "ms": round(milliseconds),
                }
            )

    def process(
        self, kind: str, event: str, code: int | None = None, seconds: float | None = None, reason: str = ""
    ) -> None:
        """A child process: a kernel, a Streamlit app, a blade's run, a catalog's load."""
        if self.on:
            self._write(rules.process(kind, event, code, seconds, reason, self._learned(), self._home))

    def page_error(self, body: Any) -> dict[str, Any]:
        """A page's error (window.onerror, an unhandled rejection), redacted. Its id."""
        if not self.on:
            return {"id": None}
        entry = rules.page_error(body, self._learned(), self._home)
        entry["message"] = rules.redact(entry["message"], self._aliases, self._home, self._secrets())
        return {"id": self._write(entry)}

    async def note(self, body: Any, who: str = "user") -> dict[str, Any]:
        """A beta note: the user's words, the element, the panels, the last actions, the last errors."""
        if not self.on:
            raise Refused("Beta mode is off: turn it on in Settings to leave a note.")
        entry = rules.note(body, self._learned())
        note_id = "n" + random_ids.token_hex(4)
        picture = (
            body.get("picture") if isinstance(body, dict) and body.get("attach_picture") is True else None
        )
        if isinstance(picture, str) and picture:
            data = _png(picture)
            entry["picture"] = await asyncio.to_thread(self._files.save_picture, note_id, data)
        entry["server_errors"] = list(self._recent_errors)
        entry["version"] = self._facts.get("version", "")
        entry["id"] = note_id
        self._write(entry, force=True)
        self.ws.audit.write(who, "beta_note", None)
        return {"id": note_id, "picture": "picture" in entry}

    # ===== reading it back =====

    async def events(self, kind: Any = None, since: Any = None, limit: Any = 200) -> dict[str, Any]:
        """The newest events (at most `limit`), of some kinds, within a look-back."""
        kinds = rules.kinds_of(kind)
        back = rules.since_seconds(since)
        most = limit if isinstance(limit, int) and 0 < limit <= 5000 else 200
        every = await asyncio.to_thread(self._files.read)
        if back is not None:
            edge = datetime.fromtimestamp(self._now() - back, UTC).isoformat(timespec="milliseconds")
            every = [e for e in every if str(e.get("time", "")) >= edge]
        if kinds is not None:
            every = [e for e in every if e.get("kind") in kinds]
        return {"on": self.on, "events": every[-most:], "total": len(every)}

    async def notes(self) -> dict[str, Any]:
        """Every note kept (a picture is named, never sent)."""
        every = await asyncio.to_thread(self._files.read)
        return {"on": self.on, "notes": [e for e in every if e.get("kind") == "note"]}

    async def clear(self, who: str = "user") -> dict[str, Any]:
        removed = await asyncio.to_thread(self._files.clear)
        self.ws.audit.write(who, "beta_clear", None, files=removed)
        return {"removed": removed}

    async def export(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"path": "~/beta-log.zip"}: one zip of the log, the notes and (the user's export only) the
        pictures, which show the user's data. The agent's export leaves the pictures out."""
        path = body.get("path") if isinstance(body, dict) else None
        if not isinstance(path, str) or not path.strip():
            raise ValueError('Send {"path": "where to save the .zip"}.')
        notes = (await self.notes())["notes"]
        made = await asyncio.to_thread(self._files.zip_to, path.strip(), notes, who != "agent")
        self.ws.audit.write(who, "beta_export", None, notes=made["notes"], pictures=made["pictures"])
        return made


def _png(data_url: str) -> bytes:
    """A note's picture as the page sends it (a PNG data URL)."""
    head, _, payload = data_url.partition(",")
    if head != "data:image/png;base64" or len(payload) > MAX_PICTURE_BYTES * 4 // 3 + 4:
        raise ValueError("A note's picture is a PNG of at most 16 MiB.")
    try:
        data = base64.b64decode(payload, validate=True)
    except ValueError as error:
        raise ValueError("A note's picture is a PNG of at most 16 MiB.") from error
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("A note's picture is a PNG of at most 16 MiB.")
    return data
