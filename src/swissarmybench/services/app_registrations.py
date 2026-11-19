"""App registrations (domain/app_registrations.py): the library's list, add, remove, and the access report
(Test,
Check again, after a project's setting changes, the agent's `app_registration_check`; never on a timer). The
report is read-only calls only; it is kept beside the registration as metadata (names, marks, reasons, when
and
which computer), and each connection's part is its Access section. Each check is an audit entry. A secret's
value is read from the variables for the sign-in only: never answered, kept or logged.
"""

from __future__ import annotations

import asyncio
import platform
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from swissarmybench.domain import app_registrations as rules
from swissarmybench.services.workspace import NotFound, Workspace


class Files(Protocol):
    def all(self) -> list[rules.Registration]: ...

    def save(self, reg: rules.Registration) -> bool: ...

    def remove(self, name: str) -> bool: ...

    def report(self, name: str) -> rules.Report | None: ...

    def save_report(self, report: rules.Report) -> bool: ...


class Probe(Protocol):
    def token(self, tenant: str, client: str, secret: str) -> str: ...

    def workspaces(self, token: str) -> list[dict[str, str]]: ...

    def datasets(self, token: str, workspace: str) -> list[dict[str, str]]: ...

    def can_query(self, token: str, workspace: str, dataset: str, table: str) -> None: ...


class AppRegistrations:
    def __init__(
        self,
        ws: Workspace,
        files: Files,
        probe: Probe,
        values: Callable[[list[str]], Any],  # async: variable names -> their values on this computer
        connections: Callable[[], list[tuple[str, str, str]]],  # (name, kind, code) of every connection
        computer: Callable[[], str] = platform.node,
    ) -> None:
        self.ws = ws
        self._files = files
        self._probe = probe
        self._values = values
        self._connections = connections
        self._computer = computer
        # Tables worth one COUNTROWS, per dataset name (an extension's hint: a Power BI project's tables).
        self.query_hints: Callable[[], dict[str, str]] = dict

    def get(self, name: str) -> rules.Registration:
        found = next((r for r in self._files.all() if r.name.casefold() == str(name or "").casefold()), None)
        if found is None:
            raise NotFound(f"{name} is not an app registration in the library.")
        return found

    def names(self) -> list[str]:
        return rules.names_in(self._files.all())

    def listing(self) -> dict[str, Any]:
        out = []
        for reg in self._files.all():
            report = self._files.report(reg.name)
            out.append(
                reg.to_json()
                | {"used_by": self._using(reg)}
                | ({"checked": report.checked, "summary": rules.one_line(report.items)} if report else {})
            )
        return {"registrations": sorted(out, key=lambda r: str(r["name"]).casefold())}

    def _using(self, reg: rules.Registration) -> list[str]:
        return [name for name, _kind, code in self._connections() if rules.uses(code, reg)]

    async def add(self, body: Any, who: str) -> dict[str, Any]:
        reg = rules.check(body)
        await asyncio.to_thread(self._files.save, reg)
        self.ws.audit.write(who, "app_registration_add", reg.name)
        return {"registration": reg.to_json(), "file": f"{rules.FOLDER}/{rules.file_name(reg.name)}"}

    async def remove(self, body: Any, who: str) -> dict[str, Any]:
        reg = self.get(str(body.get("name") or "") if isinstance(body, dict) else "")
        await asyncio.to_thread(self._files.remove, reg.name)
        self.ws.audit.write(who, "app_registration_remove", reg.name)
        return {"removed": reg.name}

    def report(self, name: str) -> dict[str, Any]:
        reg = self.get(name)
        found = self._files.report(reg.name)
        return {"registration": reg.to_json(), "report": found.to_json() if found else None}

    def access(self, connection: str) -> dict[str, Any]:
        """A connection's Access section: what it reaches, when, by which."""
        out = []
        for reg in self._files.all():
            found = self._files.report(reg.name)
            items = found.for_connection(connection) if found else []
            if items and found:
                out.append(
                    {
                        "registration": reg.name,
                        "checked": found.checked,
                        "computer": found.computer,
                        "line": rules.one_line(items),
                        "items": [i.to_json() for i in items],
                    }
                )
        return {"connection": connection, "access": out}

    async def check(self, name: str, who: str) -> dict[str, Any]:
        """The access report, made now: read-only calls; kept as metadata; an audit entry."""
        reg = self.get(name)
        values: dict[str, str] = await self._values(list(reg.variables()))
        missing = [v for v in reg.variables() if not values.get(v)]
        items: list[rules.Access] = []
        identity: dict[str, Any] = {}
        users = [(n, k) for n, k, code in self._connections() if rules.uses(code, reg)]
        if missing:
            why = f"{', '.join(missing)} {'has' if len(missing) == 1 else 'have'} no value on this computer"
            items.append(rules.Access("Sign-in", reg.name, None, why, "Set it on the Variables page"))
        else:
            items += await asyncio.to_thread(self._powerbi, reg, values, identity, users)
        for connection, kind in users:
            if kind != "powerbi":
                reason = rules.NOT_CHECKED_KINDS.get(kind, "this kind of connection is not checked yet")
                items.append(rules.Access("Connection", connection, None, reason, connection=connection))
        report = rules.Report(
            reg.name,
            datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            self._computer(),
            identity,
            tuple(items),
        )
        await asyncio.to_thread(self._files.save_report, report)
        self.ws.audit.write(
            who,
            "app_registration_check",
            reg.name,
            ok=sum(1 for i in items if i.ok),
            refused=sum(1 for i in items if i.ok is False),
        )
        await self.ws.live.broadcast({"type": "app_registration_checked", "registration": reg.name})
        return {"registration": reg.to_json(), "report": report.to_json()}

    def _powerbi(
        self,
        reg: rules.Registration,
        values: dict[str, str],
        identity: dict[str, Any],
        users: list[tuple[str, str]],
    ) -> list[rules.Access]:
        out: list[rules.Access] = []
        powerbi_connections = [n for n, k in users if k == "powerbi"]
        tag = powerbi_connections[0] if len(powerbi_connections) == 1 else ""
        try:
            token = self._probe.token(values[reg.tenant], values[reg.client], values[reg.secret])
        except rules.Refused as error:
            return [
                rules.Access(
                    "Sign-in",
                    reg.name,
                    False,
                    rules.sign_in_refused(error.status, error.said),
                    "Set its variables again",
                )
            ]
        except OSError as error:
            return [
                rules.Access("Sign-in", reg.name, None, f"Microsoft's sign-in could not be reached ({error})")
            ]
        identity |= rules.identity(rules.token_claims(token), reg)
        out.append(rules.Access("Sign-in", reg.name, True))
        try:
            workspaces = self._probe.workspaces(token)
        except rules.Refused as error:
            reason, fix = rules.powerbi_refused(error.status, error.said)
            return [*out, rules.Access("Power BI", "its workspaces", False, reason, fix, tag)]
        if not workspaces:
            out.append(
                rules.Access(
                    "Power BI",
                    "its workspaces",
                    False,
                    "it is a member of no workspace",
                    "Add it to the workspace as Viewer",
                    tag,
                )
            )
        hints = self.query_hints()
        for workspace in workspaces:
            target = f"the {workspace['name']} workspace"
            try:
                datasets = self._probe.datasets(token, workspace["id"])
            except rules.Refused as error:
                reason, fix = rules.powerbi_refused(error.status, error.said, workspace["name"])
                out.append(rules.Access("Power BI", target, False, reason, fix, tag))
                continue
            out.append(rules.Access("Power BI", target, True, connection=tag))
            for dataset in datasets:
                table = hints.get(dataset["name"])
                if not table:
                    out.append(
                        rules.Access(
                            "Power BI",
                            dataset["name"],
                            None,
                            "no table of it is known to count",
                            connection=tag,
                        )
                    )
                    continue
                try:
                    self._probe.can_query(token, workspace["id"], dataset["id"], table)
                    out.append(rules.Access("Power BI", dataset["name"], True, connection=tag))
                except rules.Refused as error:
                    reason, fix = rules.powerbi_refused(error.status, error.said, workspace["name"])
                    out.append(rules.Access("Power BI", dataset["name"], False, reason, fix, tag))
        return out
