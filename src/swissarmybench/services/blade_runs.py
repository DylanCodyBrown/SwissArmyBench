"""A blade's runs through the app, and the vaults read for what the app starts (the craft review, 2026-11-22:
these were the composition root's own closures).

  run_blade          a blade in a child process (Refresh, Test, a catalog load, a table read, a query): a
                     connection's run waits for one of its slots (services/connection_slots.py) and is counted
                     on the Connections page (services/connection_usage.py), however it ends
  stream_blade       the blade IDE's Run: the code as the editor holds it, its output streamed
  vault_environment  every vault's entries for a Workbench kernel about to start, and the vaults that failed
  vault_values       a scheduled script's variables from key vaults (vault -> variable -> secret)
  given_out          a vault that loads every secret: its names as given out here, written into a job
  secrets_of         a connection's or blade's passwords by the names its code asks secret() for
  files_of           a connection's certificate and keystore files read from a variable: those variables

The child process itself is the server's (server/blade_runner.py), handed in as plain callables: nothing here
starts a process or reads a file.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import Any, Protocol

from swissarmybench.domain import connections as connection_rules
from swissarmybench.domain import python_connections
from swissarmybench.domain.blades import Blade, env_settings
from swissarmybench.domain.connection_slots import AGENT
from swissarmybench.services.connection_slots import CURRENT

Job = dict[str, Any]
Report = Callable[..., None]  # (kind, event, code, seconds, reason): a child process, told to the beta log


class Store(Protocol):
    """The saved blades (adapters/blades.py BladeStore)."""

    def get(self, name: str) -> Blade: ...

    def saved_secrets(self, blade: Any) -> dict[str, str]: ...


class KeptNames(Protocol):
    """The vaults' names as kept on this computer (services/vault_names.py KeptVaultNames)."""

    def defined(self) -> Iterable[str]: ...

    def kept_of(self, vault: str) -> dict[str, str]: ...

    def mapping(self, blade: Blade) -> dict[str, str]: ...


class BladeRuns:
    def __init__(
        self,
        store: Store,
        kept: KeptNames,
        *,
        # The child process a job runs in (server/blade_runner.py's functions, the store already given).
        payload: Callable[..., Job],
        load_payload: Callable[[], Job | None],
        run: Callable[..., Awaitable[dict[str, Any]]],
        run_streaming: Callable[..., Awaitable[dict[str, Any]]],
        failed: type[Exception],
        gate: Callable[..., Awaitable[dict[str, Any]]],
        record: Callable[..., None],
        keep_names: Callable[[str, list[dict[str, str]]], Awaitable[Any]],
        report: Report,
        run_file: Callable[[str], str],
        blade_seconds: float,
        vault_seconds: float,
        install_missing: Callable[[list[str]], Awaitable[list[str]]] | None = None,
    ) -> None:
        self._payload, self._load_payload = payload, load_payload
        self._run, self._run_streaming = run, run_streaming
        self._store = store
        self._kept = kept
        self._failed = failed  # the child process's own refusal (blade_runner.RefreshError)
        self._gate = gate  # the connection's slots: ConnectionSlots.run_blade
        self._record = record  # the Connections page's count: ConnectionUsage.record
        self._keep_names = keep_names  # a vault's names as just read: BladeService.keep_names
        self._report = report
        # The name a streamed run's code is given: one the error panel reads as your file (never the
        # .blade.py itself, whose lines start after its header).
        self._run_file = run_file
        self._blade_seconds = blade_seconds
        self._vault_seconds = vault_seconds
        # What a run's code imports that the app's Python lacks, installed first (server/blade_runner.py).
        self._install_missing = install_missing
        self._installing = asyncio.Lock()

    async def ready(self, job: Job) -> list[str]:
        """The packages a job's code (and its vaults') needs, installed before it runs, one install at a
        time: the user's runs only (the agent's install waits for the user's Allow: Install now)."""
        caller = CURRENT.get()
        if self._install_missing is None or (caller is not None and caller.role == AGENT):
            return []
        codes = [str(job.get("code") or "")] + [
            str(v.get("code") or "") for v in job.get("vaults") or [] if isinstance(v, dict)
        ]
        async with self._installing:
            return await self._install_missing(codes)

    def given_out(self, job: Job) -> None:
        """A vault that loads every secret: its names as given out here (no variable twice, a taken one
        prefixed), the ones it lists now given out the same way (`yours`, `kept`: a kernel's load)."""
        job["yours"] = sorted(self._kept.defined())
        for vault in job.get("vaults") or []:
            if isinstance(vault, dict) and vault.get("every"):
                label = str(vault.get("label") or "")
                vault["kept"] = self._kept.kept_of(label)
                try:
                    vault["mapping"] = self._kept.mapping(self._store.get(label)) | dict(vault["mapping"])
                except KeyError:
                    pass

    async def run_blade(
        self, blade: Blade, mode: str, typed: dict[str, str], extra: Job | None = None
    ) -> dict[str, Any]:
        job = self._payload(blade, mode, typed, extra)
        self.given_out(job)
        await self.ready(job)
        kind = "catalog" if mode == "catalog" else "blade"

        async def work() -> dict[str, Any]:
            return await self._run(job, self._blade_seconds, report=lambda *e: self._report(kind, *e))

        # A connection's run through the app (a catalog load, a table read, a query, a test) is a call the
        # Connections page counts (memory only); each waits for one of the connection's slots first, and
        # gives it back however it ends.
        try:
            answer = await self._gate(blade.name, blade.kind, blade.dialect, mode, extra, work)
        except Exception as error:
            self._record(blade.name, mode, ok=False, error=str(error))
            raise
        about = answer.get("about") if isinstance(answer, dict) else None
        self._record(blade.name, mode, ok=True, about=about if isinstance(about, dict) else None)
        return answer

    async def stream_blade(
        self,
        blade: Blade,
        typed: dict[str, str],
        filename: str,
        on_output: Callable[[str, str], None],
        started: Callable[[Callable[[], None]], None],
    ) -> dict[str, Any]:
        """The blade IDE's Run: the blade (its code the editor's) in a child process, its output streamed."""
        job = self._payload(blade, "run", typed)
        self.given_out(job)
        await self.ready(job)
        job["filename"] = self._run_file(filename)
        answer = await self._run_streaming(
            job, self._blade_seconds, on_output, started, report=lambda *e: self._report("blade", *e)
        )
        self._record(blade.name, "test", ok=bool(answer.get("ok")), error=str(answer.get("failed") or ""))
        return answer

    async def vault_environment(self) -> tuple[dict[str, str], list[str]]:
        """Every vault's entries for a Workbench kernel about to start, and the vaults that failed."""
        job = self._load_payload()
        if job is None:
            return {}, []
        self.given_out(job)
        try:
            answer = await self._run(job, self._vault_seconds)
        except self._failed as error:
            why = str(error)
            if "did not finish" in why:
                seconds = self._vault_seconds
                why = f"Reading the vaults took over {seconds:.0f} seconds: this kernel started without them."
            return {}, [why]
        values = {str(k): str(v) for k, v in dict(answer.get("values") or {}).items()}
        # A vault that loads every secret: the names it listed, kept (names only).
        for vault, listed in dict(answer.get("names") or {}).items():
            if isinstance(listed, list):
                await self._keep_names(str(vault), connection_rules.vault_names(listed))
        return values, [str(p) for p in answer.get("problems") or []]

    async def vault_values(self, wanted: Mapping[str, Mapping[str, str]]) -> tuple[dict[str, str], list[str]]:
        """A scheduled script's variables from key vaults (vault -> variable -> secret), and what failed."""
        sources = {
            variable: {"from": "vault", "vault": vault, "secret": secret}
            for vault, mapping in wanted.items()
            for variable, secret in mapping.items()
        }
        try:
            jobs = python_connections.vault_jobs(sources, self._store.get, self._store.saved_secrets)
            answer = await self._run(
                {"mode": "load", "label": "the vaults", "kind": "load", "vaults": jobs}, self._vault_seconds
            )
        except (python_connections.PythonConnectionError, self._failed) as error:
            return {}, [str(error)]
        values = {str(k): str(v) for k, v in dict(answer.get("values") or {}).items()}
        return values, [str(p) for p in answer.get("problems") or []]

    def secrets_of(self, name: str) -> list[str] | None:
        """A connection's or blade's passwords by the names its code asks secret() for (None: none here)."""
        try:
            return self._store.get(name).secrets
        except KeyError:
            return None

    def files_of(self, name: str) -> list[str]:
        """A connection's certificate and keystore files read from a variable: those variables."""
        try:
            return [m["variable"] for m in env_settings(self._store.get(name).code)]
        except KeyError:
            return []
