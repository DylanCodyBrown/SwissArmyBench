"""Edit in Power BI Desktop (domain/live_link.py): the running Desktops found every 15 seconds while a Power
BI
project is open or the ERD page asks (off the event loop; never counted as work for the server's life), the
status
pushed to the pages, the open model's metadata (never rows), a dry run listing each change, and Apply (each
change
an audit entry; the agent's on the user's Allow). E's Local source reads DAX through it.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from swissarmybench.services.ports import Approvals
from swissarmybench.services.workspace import Conflict
from swissarmybench_powerbi.domain import live_link as rules


class LiveLink:
    def __init__(
        self,
        ws: Any,
        discover: Callable[[], list[rules.Instance]],
        opener: Callable[[int], Any],  # a port -> the open model (adapters/live_link.py TomModel, or a fake)
        target: Callable[[], str | None],  # the Power BI project's .pbix (None: no Power BI project open)
        ours: Callable[
            [], tuple[list[dict[str, Any]], list[dict[str, Any]]]
        ],  # our relationships and measures
        approvals: Approvals,
        windows: Callable[[], bool],
        seconds: int = rules.DISCOVERY_SECONDS,
    ) -> None:
        self.ws = ws
        self._discover = discover
        self._opener = opener
        self._target = target
        self._ours = ours
        self._approvals = approvals
        self._windows = windows
        self.seconds = seconds
        self._found: list[rules.Instance] = []
        self._at = 0.0
        self._asked_until = 0.0  # the ERD page asked: looked for a while even with no Power BI project
        self._said: dict[str, Any] | None = None
        self._models: dict[int, Any] = {}
        self._task: asyncio.Task[None] | None = None

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _instances(self, fresh: bool = False) -> list[rules.Instance]:
        if fresh or time.monotonic() - self._at > self.seconds:
            self._found = await asyncio.to_thread(self._discover) if self._windows() else []
            self._at = time.monotonic()
        return self._found

    async def status(self, asked: bool = False) -> dict[str, Any]:
        if self._task is None and self._windows():  # the look every 15 seconds, started once it is asked
            self._task = asyncio.create_task(self.run_forever())
        if asked:
            self._asked_until = time.monotonic() + 120
        target = self._target() or ""
        found = await self._instances()
        said = rules.status_words(found, target, self._windows())
        return said | {"target": target, "running": [i.to_json() for i in found], "note": rules.LOCAL_ONLY}

    def wanted(self) -> bool:
        return bool(self._target()) or time.monotonic() < self._asked_until

    async def run_forever(self) -> None:
        """Look every `seconds` while wanted; push the status when it changes (a notice, never a request)."""
        while True:
            await asyncio.sleep(self.seconds)
            if not self.wanted() or not self._windows():
                continue
            try:
                said = await self.status()
            except Exception:  # noqa: S112 (a failed look is tried again next time)
                continue
            if said.get("words") != (self._said or {}).get("words"):
                self._said = said
                await self.ws.live.broadcast(
                    {"type": "powerbi_live", "words": said["words"], "live": said["live"]}
                )
                # The Power BI page is drawn from data: it reads its panel again on the panel's own notice.
                await self.ws.live.broadcast({"type": "extension_panel_changed", "id": "powerbi"})

    def open_file(self) -> str | None:
        """The target's file name while Power BI Desktop has it open (E's Local source), else None."""
        found = rules.matching(self._found, self._target() or "")
        return found.name if found else None

    async def _model(self) -> Any:
        if not self._windows():
            raise Conflict(rules.WINDOWS_ONLY)
        found = rules.matching(await self._instances(), self._target() or "")
        if found is None:
            said = rules.status_words([], self._target() or "")
            raise Conflict(f"{said['words']}.")
        if found.port not in self._models:
            self._models[found.port] = await asyncio.to_thread(self._opener, found.port)
        return self._models[found.port]

    async def evaluate(self, dax: str) -> Any:
        model = await self._model()
        return await asyncio.to_thread(model.evaluate, dax)

    async def model(self) -> dict[str, Any]:
        model = await self._model()
        meta: rules.OpenModel = await asyncio.to_thread(model.metadata)
        return meta.to_json()

    async def plan(self, body: Any) -> dict[str, Any]:
        """The dry run: each change in words and whether it can go. No changes sent: our relationships and
        measures."""
        model = await self._model()
        meta = await asyncio.to_thread(model.metadata)
        changes = self._changes(body, meta)
        return {"dry_run": True, "changes": rules.check(meta, changes)}

    def _changes(self, body: Any, meta: rules.OpenModel) -> list[rules.Change]:
        sent = body.get("changes") if isinstance(body, dict) else None
        if sent:
            return [rules.change_from(c) for c in sent]
        relationships, measures = self._ours()
        return rules.ours(relationships, measures, meta)

    async def apply(self, body: Any, who: str) -> dict[str, Any]:
        model = await self._model()
        meta = await asyncio.to_thread(model.metadata)
        changes = self._changes(body, meta)
        checked = rules.check(meta, changes)
        going = [c for c, said in zip(changes, checked, strict=True) if said["ok"]]
        if not going:
            return {"applied": [], "skipped": [c for c in checked if not c["ok"]]}
        await self._approvals.allowed(
            who,
            subject="Power BI Desktop",
            action="powerbi_edit",
            detail="; ".join(c.words() for c in going[:5]) + ("…" if len(going) > 5 else ""),
            otherwise="Power BI Desktop's model was not changed",
        )
        applied = []
        for change in going:
            await asyncio.to_thread(model.apply, change)
            self.ws.audit.write(
                who, "powerbi_edit", change.table or change.name, change=change.kind, name=change.name
            )
            applied.append(change.to_json())
        return {"applied": applied, "skipped": [c for c in checked if not c["ok"]]}
