"""A script's run settings, Run as scheduled and its run history (domain/script_runs.py): the Workbench's
Script mode, and the agent's workbench_script_* commands.

The settings are kept by the script's path (run_settings.json in the state folder: arguments and each
variable's source; a plain value only, never a secret's). A scheduled run is a fresh process with no
app; the history is memory only."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Protocol

from swissarmybench.domain import script_runs as rules
from swissarmybench.domain.notebooks import kind_of
from swissarmybench.services.workspace import NotFound, Workspace


class Kept(Protocol):
    def read(self) -> Any: ...

    def write(self, data: Any) -> None: ...


class Documents(Protocol):
    def read(self, path: str) -> tuple[str, str, float]: ...  # text, the whole path, when it changed

    def environment(self, path: str) -> str | None: ...


class Runner(Protocol):
    async def run(
        self, python: str, script: str, arguments: list[str], environ: dict[str, str], seconds: float
    ) -> tuple[int | None, float, str]: ...  # exit code (None: stopped), seconds, output


VaultValues = Callable[[dict[str, dict[str, str]]], Awaitable[tuple[dict[str, str], list[str]]]]


class ScriptRuns:
    def __init__(
        self,
        ws: Workspace,
        kept: Kept,
        documents: Documents,
        runner: Runner,
        environ: Mapping[str, str],
        default_python: Callable[[], str],
        secrets_of: Callable[[str], Sequence[str] | None],
        vault_values: VaultValues,
        now: Callable[[], float],
        files_of: Callable[[str], Sequence[str]] = lambda _: (),
    ) -> None:
        self.ws = ws
        self._kept = kept
        self._documents = documents
        self._runner = runner
        self._environ = environ
        self._default_python = default_python
        self._secrets_of = secrets_of
        self._vault_values = vault_values
        self._now = now
        self._files_of = files_of  # a connection's mapped certificate files
        self._history: dict[str, list[rules.Run]] = {}

    # ----- the script and its settings

    def _script(self, path: Any) -> tuple[str, str]:
        if not isinstance(path, str) or not path.strip():
            raise rules.ScriptRunError('Send {"path": "...\\\\daily_sales.py"}.')
        if kind_of(path) != "script":
            raise rules.ScriptRunError("Run settings are a script's (.py).")
        try:
            text, full, _ = self._documents.read(path)
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        return text, full

    def _all(self) -> dict[str, Any]:
        raw = self._kept.read()
        return raw if isinstance(raw, dict) else {}

    def _settings(self, full: str) -> rules.RunSettings:
        return rules.read_settings(self._all().get(full))

    def settings(self, path: Any) -> dict[str, Any]:
        """The script's arguments and the variables it needs, each with its source (never a value but a
        plain one's)."""
        text, full = self._script(path)
        settings = self._settings(full)
        found = rules.needed(text, self._secrets_of, self._files_of)
        return {"path": full, "arguments": settings.arguments, "variables": rules.rows(settings, found)}

    def every(self) -> dict[str, dict[str, dict[str, str]]]:
        """Each script's Run settings' variables (script -> variable -> source): the Variables page."""
        return {path: rules.read_settings(raw).variables for path, raw in self._all().items()}

    def rename_variable(self, old: str, new: str) -> list[str]:
        """A variable renamed on the Variables page: each script's Run settings follow; the scripts changed."""
        kept = self._all()
        changed = []
        for path, raw in kept.items():
            settings = rules.read_settings(raw)
            if old in settings.variables and new not in settings.variables:
                variables = {new if n == old else n: s for n, s in settings.variables.items()}
                kept[path] = rules.RunSettings(settings.arguments, variables).to_json()
                changed.append(path)
        if changed:
            self._kept.write(kept)
        return changed

    def set_settings(self, body: Any, who: str = "user") -> dict[str, Any]:
        if not isinstance(body, dict):
            raise rules.ScriptRunError('Send {"path", "arguments", "variables"}.')
        _, full = self._script(body.get("path"))
        settings = rules.check_settings(body)
        kept = self._all()
        kept[full] = settings.to_json()
        self._kept.write(kept)
        self.ws.audit.write(who, "script_run_settings", full)
        return self.settings(full)

    # ----- runs

    def _keep(self, full: str, run: rules.Run) -> dict[str, Any]:
        runs = self._history.setdefault(full, [])
        runs.insert(0, run)
        del runs[rules.MAX_RUNS :]
        return {"path": full} | run.to_json()

    async def run(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Run as scheduled: the script in its own Python, as a fresh process with no app, with its
        arguments and its variables from their sources. {"path", "python"?}."""
        if not isinstance(body, dict):
            raise rules.ScriptRunError('Send {"path": "...\\\\daily_sales.py"}.')
        text, full = self._script(body.get("path"))
        python = body.get("python") if isinstance(body.get("python"), str) and body.get("python") else None
        python = python or self._documents.environment(full) or self._default_python()
        settings = self._settings(full)
        found = rules.needed(text, self._secrets_of, self._files_of)
        planned = rules.plan(settings, found, lambda name: name in self._environ)
        values, problems = await self._vault_values(planned.vaults) if planned.vaults else ({}, [])
        environ = dict(self._environ) | planned.values | values
        started = self._now()
        code, seconds, output = await self._runner.run(
            python, full, planned.arguments, environ, rules.RUN_SECONDS
        )
        said = [*problems, *(f"{name} is not set on this computer." for name in planned.missing)]
        log = [rules.command_line(full, planned.arguments), *rules.tail(output)]
        if code is None:
            log.append(f"Stopped: it ran over {rules.RUN_SECONDS / 60:.0f} minutes.")
        run = rules.Run(
            "scheduled",
            started,
            seconds,
            code,
            rules.command_line(full, planned.arguments),
            tuple(planned.sources),
            tuple([*said, *log])[-rules.MAX_LOG_LINES :],
        )
        self.ws.audit.write(who, "run_script_as_scheduled", full, exit_code=code)
        return self._keep(full, run)

    def record(self, body: Any) -> dict[str, Any]:
        """A Run file of the script (the window's kernel ran it): kept in the history."""
        if not isinstance(body, dict):
            raise rules.ScriptRunError('Send {"path", "seconds", "exit_code"}.')
        _, full = self._script(body.get("path"))
        run = rules.recorded(body)
        if not run.started:
            run = rules.Run(
                run.how, self._now() - run.seconds, run.seconds, run.exit_code, run.command, (), run.log
            )
        return self._keep(full, run)

    def history(self, path: Any) -> dict[str, Any]:
        """The script's runs, the newest first, each with its log."""
        _, full = self._script(path)
        return {"path": full, "runs": [r.to_json() for r in self._history.get(full, [])]}
