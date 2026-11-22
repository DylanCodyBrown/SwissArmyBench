"""A script's run settings (domain/script_runs.py): the Workbench's Script mode (Run file takes their
arguments), the Variables page (their variables and where each comes from) and the agent's
workbench_script_settings.

The settings are kept by the script's path (run_settings.json in the state folder: arguments and each
variable's source; a plain value only, never a secret's). Run as scheduled and its run history went
(the owner's simplicity pass, 2026-11-21)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
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


class ScriptRuns:
    def __init__(
        self,
        ws: Workspace,
        kept: Kept,
        documents: Documents,
        secrets_of: Callable[[str], Sequence[str] | None],
        files_of: Callable[[str], Sequence[str]] = lambda _: (),
    ) -> None:
        self.ws = ws
        self._kept = kept
        self._documents = documents
        self._secrets_of = secrets_of
        self._files_of = files_of  # a connection's mapped certificate files

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
        """A variable renamed on the Variables page: each script's Run settings follow; those changed."""
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
