"""A key vault's secret names, remembered and read again (domain/vault_names.py; the owner, 2026-11-20: "Every
time I update or reopen the app my Vault variables disappear").

  KEPT      every read of a vault's names (the form's read, Set up this computer's check, a Workbench kernel
            loading the vaults, the start-up read below) is kept in the library's local/vault-names/, names
            only; a vault that loads every secret gives them as its variables from the first second after a
            start (the Variables page, the ${ list, context.md, Set up this computer, a kernel's names)
  START-UP  once the first window is open (as catalog_loading.py's start-up), each vault that loads every
            secret is read for its names again: a child process each (services/blades.py vault_names), a few
            at once, off the event loop; a vault that signs in with a window or a phone prompt is skipped
            (never a pop-up unasked); a failure keeps the remembered names and says so on the vault's card
            ("Names from <time>: Read again"). A change tells the pages (variables_changed)
  FOLLOWS   a vault deleted: its file goes; renamed: it follows; a file whose vault is gone goes at start
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, Protocol

from swissarmybench.domain import connections as connection_rules
from swissarmybench.domain import vault_names as rules
from swissarmybench.domain.blades import Blade

START_WAIT_SECONDS: float = 15.0
SETTLE_SECONDS: float = 2.0
_POLL_SECONDS: float = 0.25


class Files(Protocol):
    """local/vault-names/ (adapters/vault_names.py VaultNameFiles)."""

    def read(self, name: str) -> str | None: ...

    def write(self, name: str, text: str) -> bool: ...

    def remove(self, name: str) -> bool: ...

    def listed(self) -> list[str]: ...


class KeptVaultNames:
    def __init__(self, files: Files, now: Callable[[], str]) -> None:
        self._files = files
        self._now = now  # ISO 8601 in UTC
        self._cache: dict[str, rules.Remembered | None] = {}  # by file name
        self._failed: dict[str, str] = {}  # vault (case folded) -> why its last read failed
        self._reading: set[str] = set()  # vaults (case folded) being read now

    def remembered(self, vault: str) -> rules.Remembered | None:
        name = rules.file_name(vault)
        if name not in self._cache:
            self._cache[name] = rules.parse(self._files.read(name))
        return self._cache[name]

    def mapping(self, blade: Blade) -> dict[str, str]:
        """A vault that loads every secret: its remembered variables (variable -> secret), the user's
        renames kept. Any other blade: none."""
        if blade.kind != "vault" or not blade.vault_all:
            return {}
        found = self.remembered(blade.name)
        return found.mapping(blade.vault_mapping) if found is not None else {}

    def record(self, vault: str, found: Iterable[Any]) -> bool:
        """A read's names kept (names only). Whether they changed (the file is written only then)."""
        vault = vault.strip()
        if not vault:
            return False
        self._failed.pop(vault.casefold(), None)
        names = rules.rows(found)
        was = self.remembered(vault)
        if was is not None and was.names == names and was.vault == vault:
            return False
        made = rules.Remembered(vault, names, self._now())
        self._files.write(rules.file_name(vault), rules.render(made))
        self._cache[rules.file_name(vault)] = made
        return True

    def failed(self, vault: str, why: str) -> None:
        self._failed[vault.casefold()] = (why.strip().splitlines() or ["it could not be read"])[0][:300]

    def reading(self, vault: str, on: bool) -> None:
        (self._reading.add if on else self._reading.discard)(vault.casefold())

    def state(self, blade: Blade) -> dict[str, Any] | None:
        """A vault card's line: how many variables it gives, the names' time, a failed read's words."""
        if blade.kind != "vault":
            return None
        found = self.remembered(blade.name)
        count = len(blade.vault_mapping)
        if blade.vault_all:
            count = len(found.mapping(blade.vault_mapping)) if found is not None else len(blade.vault_mapping)
        out: dict[str, Any] = {"count": count, "read_at": found.read_at if found is not None else None}
        if blade.name.casefold() in self._reading:
            out["reading"] = True
        why = self._failed.get(blade.name.casefold())
        if why is not None:
            out["error"] = why
        return out

    def forget(self, vault: str) -> None:
        name = rules.file_name(vault)
        self._files.remove(name)
        self._cache[name] = None
        self._failed.pop(vault.casefold(), None)

    def rename(self, old: str, new: str) -> None:
        if old == new:
            return
        found = self.remembered(old)
        if found is None:
            return
        self.forget(old)
        made = rules.renamed_to(found, new)
        self._files.write(rules.file_name(new), rules.render(made))
        self._cache[rules.file_name(new)] = made

    def prune(self, vaults: Iterable[str]) -> list[str]:
        """The files whose vault is gone, removed. Their names."""
        kept = {rules.file_name(v) for v in vaults}
        gone = [n for n in self._files.listed() if n not in kept]
        for name in gone:
            self._files.remove(name)
            self._cache[name] = None
        return gone


class Reader(Protocol):
    """services/blades.py BladeService: a vault's names read in a child process (and kept), the blades."""

    async def vault_names(self, data: Any) -> dict[str, Any]: ...

    def everything(self) -> list[Blade]: ...


class VaultNamesAtStart:
    def __init__(
        self,
        reader: Reader,
        kept: KeptVaultNames,
        broadcast: Callable[[dict[str, Any]], Awaitable[None]],
        enabled: bool,
        at_once: int,
        windows: Callable[[], int] = lambda: 1,
    ) -> None:
        self._reader = reader
        self._kept = kept
        self._broadcast = broadcast
        self._enabled = enabled
        self._gate = asyncio.Semaphore(max(1, at_once))
        self._windows = windows

    async def at_start_later(
        self, wait: float = START_WAIT_SECONDS, settle: float = SETTLE_SECONDS
    ) -> list[str]:
        """read_all, once the first window is open and its page has settled, or after `wait` seconds."""
        if not self._enabled:
            return []
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait
        while self._windows() == 0 and loop.time() < deadline:
            await asyncio.sleep(_POLL_SECONDS)
        if self._windows():
            await asyncio.sleep(settle)
        return await self.read_all()

    def wanted(self) -> list[Blade]:
        """The vaults read at start: each that loads every secret, but one that signs in with a window."""
        return [
            b
            for b in self._reader.everything()
            if b.kind == "vault" and b.vault_all and not connection_rules.signs_in_interactively(b.code)
        ]

    async def read_all(self) -> list[str]:
        """Each wanted vault's names read again (a few at once); a file whose vault is gone removed. The
        vaults read."""
        everything = self._reader.everything()
        self._kept.prune(b.name for b in everything if b.kind == "vault")
        wanted = self.wanted()
        await asyncio.gather(*(self._read(b.name) for b in wanted))
        return [b.name for b in wanted]

    async def _read(self, name: str) -> None:
        async with self._gate:
            self._kept.reading(name, True)
            try:
                # Kept (and the pages told when they changed) by the read itself.
                await self._reader.vault_names({"name": name})
            except Exception as error:  # the vault's own failure: its remembered names stay
                self._kept.failed(name, str(error) or type(error).__name__)
                await self._broadcast({"type": "variables_changed"})
            finally:
                self._kept.reading(name, False)
