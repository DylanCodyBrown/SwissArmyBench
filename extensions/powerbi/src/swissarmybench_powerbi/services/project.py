"""The Power BI project (the owner, 2026-11-19): a .pbix imported as a project ready to work (B), the .pbix
file
connection (C), "To finish setting up" (H), Read Power BI from: Published | Local | the file (E), and the
page's
data (F). Reading a .pbix is pbixray's only (adapters/pbix_reader.py); the live Power BI Desktop link is
another
service (services/live_link.py) that this one asks only for E's Local source.

The base's services are reached through `Base` (duck-typed: the composition root hands the app's own).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from swissarmybench.domain.blades import detect_settings
from swissarmybench.domain.connection_tables import Pushed
from swissarmybench.domain.relationships import Model
from swissarmybench.services.workspace import Conflict, NotFound, Refused
from swissarmybench_powerbi.domain import pbix_file as pf
from swissarmybench_powerbi.domain import pbix_import as rules
from swissarmybench_powerbi.domain import power_query as pq

PROJECT_TYPE = "powerbi"
SOURCE_KEY = "powerbi_source"
REGISTRATION_KEY = "powerbi_registration"
SOURCE_WORDS = {"published": "Published", "local": "Local", "file": "the file"}
# The connection kinds an app registration signs in (re-pointed by the project's App registration).
MICROSOFT_TEMPLATES = frozenset(
    {"sqlserver", "azuresql", "dataverse", "sharepoint", "sharepoint_docs", "datalake", "onelake", "delta"}
)


class Reader(Protocol):
    def __call__(self, path: str) -> pf.PbixModel: ...


class Files(Protocol):
    def read_text(self, path: str) -> str | None: ...

    def write_text(self, path: str, text: str) -> bool: ...


class LiveSource(Protocol):
    """E's Local source: DAX over the live link to the target (services/live_link.py)."""

    def open_file(self) -> str | None: ...

    async def evaluate(self, dax: str) -> Any: ...


def _settings_of(code: str) -> dict[str, str]:
    try:
        return {s.name: str(s.value) for s in detect_settings(code) if s.value is not None}
    except Exception:  # code a person wrote that the reader does not follow: no settings
        return {}


class PowerBIProject:
    def __init__(
        self,
        base: Any,
        reader: Reader,
        files: Files,
        approvals: Any,
        live: LiveSource | None = None,
        registrations: Callable[[], list[str]] = list,
    ) -> None:
        self.base = base
        self.reader = reader
        self.files = files
        self.approvals = approvals
        self.live = live
        self.registrations = registrations
        self.last_import: dict[str, Any] | None = None
        # Edit in Power BI Desktop's dry run shown on the Power BI page (each change listed, Apply), until
        # applied or put away; and a plug-in the page opens right there (another report's pages).
        self.review: dict[str, Any] | None = None
        self._opens: dict[str, Any] | None = None
        self.pending: str | None = None  # a .pbix/.pbit/.pbip opened with the app or dropped on a window

    # ===== C: the .pbix file connection =====

    async def add_file_connection(self, body: Any, who: str) -> dict[str, Any]:
        """{"name", "path", "variables"?}: a .pbix file connection (Python, reading it with pbixray)."""
        body = body if isinstance(body, dict) else {}
        made = pf.connection_body(
            str(body.get("name") or ""), str(body.get("path") or ""), body.get("variables") or []
        )
        saved: dict[str, Any] = await self.base.connections.save(made, None, who)
        return saved | {"card": await self.describe(made["name"])}

    async def _path(self, name: str) -> str:
        blade = self.base.connections.blade(name)[0]
        if not pf.is_pbix_connection(blade.tags):
            raise NotFound(f"{name} is not a Power BI file connection.")
        return pf.path_of(blade.code)

    async def describe(self, name: str) -> dict[str, Any]:
        """A .pbix connection's card: its path, tables, "as of", read-only and why, the portability note."""
        text = await self._path(name)
        try:
            path = await self.base.variables.resolve(text, name)
            model = await asyncio.to_thread(self.reader, path)
            return {"connection": name} | pf.card(model, text)
        except Exception as error:
            return {"connection": name} | pf.card(None, text, str(error))

    async def file_relationships(self, name: str, who: str) -> dict[str, Any]:
        """The file's relationships offered to the ERD (into the model; active or not kept)."""
        path = await self.base.variables.resolve(await self._path(name), name)
        model = await asyncio.to_thread(self.reader, path)
        joins = pf.relationships_for_model(model)
        if not joins:
            return {"relationships": 0}
        applied = await self.base.models.apply(Model(name="Power BI file", relationships=tuple(joins)), who)
        return {"relationships": len(joins)} | {
            k: v for k, v in applied.items() if k in ("added", "kept", "conflicts")
        }

    # ===== B: a .pbix imported as a project =====

    def _existing(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in self.base.connections.listing()["connections"]:
            try:
                blade = self.base.connections.blade(row["name"])[0]
            except Exception:  # noqa: S112 (a connection that cannot be read is not reused)
                continue
            kind = pq.TEMPLATE_KINDS.get(str(blade.template or ""))
            if kind:
                settings = _settings_of(blade.code)
                out.append(
                    {
                        "name": blade.name,
                        "kind": kind,
                        "settings": settings,
                        "database": settings.get("database", ""),
                    }
                )
        return out

    async def _published(self) -> list[dict[str, str]]:
        """Every dataset the Power BI workspace connections reach ({connection, dataset}); one that cannot be
        asked is skipped."""
        out: list[dict[str, str]] = []
        for row in self.base.connections.listing()["connections"]:
            try:
                blade = self.base.connections.blade(row["name"])[0]
                if blade.template != "powerbi" and blade.dialect != "dax":
                    continue
                found = await self.base.connections.datasets(blade.name, {}, True)
            except Exception:  # noqa: S112 (a workspace that cannot be reached is not searched)
                continue
            out += [
                {"connection": blade.name, "dataset": d["name"]}
                for d in found.get("datasets", [])
                if d.get("name")
            ]
        return out

    async def plan(self, body: Any) -> rules.ImportPlan:
        body = body if isinstance(body, dict) else {}
        path = str(body.get("path") or "")
        if not path:
            raise ValueError('Send {"path": "<a .pbix on this computer>"}.')
        model = await asyncio.to_thread(self.reader, path)
        project = str(body.get("name") or model.name).strip() or model.name
        return rules.plan(model, project, self._existing(), await self._published(), body.get("dataset"))

    async def import_project(self, body: Any, who: str) -> dict[str, Any]:
        """{"path", "name"?, "folder"?, "dataset"?, "dry_run"?}: the project made ready to work. The import
        always finishes; what it could not resolve is the To finish list."""
        body = body if isinstance(body, dict) else {}
        plan_ = await self.plan(body)
        if body.get("dry_run"):
            return {"dry_run": True} | plan_.to_json()
        if who == "agent" and not await self.approvals.ask(
            plan_.project, "powerbi_import", f"Make the Power BI project {plan_.project}"
        ):
            raise Refused("The user declined: no project was made.")
        base = self.base
        new = {"name": plan_.project, "type": PROJECT_TYPE} | {
            k: body[k] for k in ("folder", "path_to") if body.get(k)
        }
        if body.get("folder"):
            new["folder"] = body["folder"]
        opened = await base.sab_projects.new(new, who)
        folder = str(base.sab_projects.current.folder)
        problems: list[dict[str, str]] = []
        # 1. variables from the Power Query parameters (plain values: never a secret)
        for name, value in sorted(plan_.variables.items()):
            try:
                await base.variables.put({"name": name, "value": value, "from": "value"}, who)
            except Exception as error:
                problems.append({"what": f"variable {name}", "why": str(error)})
        # 2. back-end connections (reused or made)
        for c in plan_.connections:
            if c.reused:
                continue
            try:
                await base.connections.save(self._connection_body(c), None, who)
            except Exception as error:
                problems.append({"what": f"connection {c.name}", "why": str(error)})
        # 3. the .pbix file connection to the target
        target = str(body.get("path"))
        file_connection = f"{plan_.model.name} file"
        try:
            await base.connections.save(pf.connection_body(file_connection, target), None, who)
        except Exception as error:
            problems.append({"what": f"connection {file_connection}", "why": str(error)})
        dataset_connection = plan_.dataset["connection"] if plan_.dataset else ""
        # 4. state kept: the round trip and the settings
        state = rules.state_json(plan_, target, dataset_connection, file_connection)
        state["uses_microsoft"] = any(c.kind in rules.MICROSOFT_KINDS for c in plan_.connections) or bool(
            plan_.dataset
        )
        await asyncio.to_thread(
            self.files.write_text, str(Path(folder) / rules.STATE_PATH), rules.write_state(state)
        )
        await base.sab_projects.set_setting(SOURCE_KEY, "published", who)
        # 5. relationships into the model and the ERD
        joins = pf.relationships_for_model(plan_.model)
        if joins:
            try:
                await base.models.apply(Model(name="Power BI file", relationships=tuple(joins)), who)
            except Exception as error:
                problems.append({"what": "relationships", "why": str(error)})
        # 6. the data notebook: its %%dax cells name the project's one dataset connection (E resolves it)
        cells = rules.notebook_cells(plan_, rules.dataset_name(state))
        await asyncio.to_thread(
            self.files.write_text, str(Path(folder) / "data.ipynb"), rules.notebook_json(cells)
        )
        # 7. every table as two grids
        grids = await self._open_pairs(state, plan_.tables, who, problems)
        base.ws.audit.write(
            who, "powerbi_import", plan_.project, tables=len(plan_.tables), connections=len(plan_.connections)
        )
        answer = {
            "project": plan_.project,
            "folder": folder,
            "type": opened.get("type", PROJECT_TYPE),
            "grids": grids,
            "problems": problems,
            "plan": plan_.to_json(),
            "to_finish": await self.to_finish(),
        }
        self.last_import = answer
        return answer

    def _connection_body(self, c: rules.SourceConnection) -> dict[str, Any]:
        """A new back-end connection: its starter's code with the server and database set (a `${NAME}` kept as
        a variable); its password and sign-in asked on this computer as usual."""
        from swissarmybench.domain import sql_server
        from swissarmybench.domain.blades import apply_settings
        from swissarmybench.server.blade_templates import BY_ID

        template = rules.TEMPLATES[c.kind]
        if c.kind == "sqlserver":
            code = sql_server.code("sql_login", "my-server")
        else:
            code = BY_ID[template].code
        values = dict(c.settings) | ({"database": c.database} if c.database else {})
        found = {s.name: s.id for s in detect_settings(code)}
        filled = {found[k]: {"text": v} for k, v in values.items() if k in found and v}
        if filled:
            code = apply_settings(code, filled)
        kind = "sql" if c.kind in pq.DIALECTS else "file"
        template_ = BY_ID[template]
        return {
            "name": c.name,
            "kind": template_.kind or kind,
            "template": template,
            "dialect": template_.dialect or template,
            "code": code,
        }

    async def _open_pairs(
        self,
        state: Mapping[str, Any],
        tables: list[rules.TablePlan],
        who: str,
        problems: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """Each table's Source and In Power BI grids, side by side, and a Compare between them."""
        out: list[dict[str, Any]] = []
        for t in tables:
            pair: dict[str, Any] = {"table": t.name, "source": None, "in_power_bi": None, "compare": None}
            if t.connection and (t.table or t.query):
                where = {"schema": t.schema, "table": t.table, "as": rules.grid_names(t.name)[0]}
                try:
                    pair["source"] = (await self.base.connections.open_table(t.connection, where, who)).get(
                        "grid"
                    )
                except Exception as error:
                    pair["source_error"] = str(error).splitlines()[0][:200]
            else:
                pair["source_error"] = t.why or "no source to read"
            try:
                pair["in_power_bi"] = await self._read_in_power_bi(state, t.name, who)
            except Exception as error:
                pair["in_power_bi_error"] = str(error).splitlines()[0][:200]
            if pair["source"] and pair["in_power_bi"]:
                try:
                    keys = self._compare_keys(state, t.name)
                    made = await self.base.compares.create(
                        {"left": pair["source"], "right": pair["in_power_bi"], "keys": keys}, who
                    )
                    pair["compare"] = made.get("compare")
                except Exception as error:  # Compare is one click on the page: said, never in the way
                    pair["compare_error"] = str(error).splitlines()[0][:200]
            out.append(pair)
        return out

    def _compare_keys(self, state: Mapping[str, Any], table: str) -> list[list[str]]:
        """The Compare's key: a column both grids have that a relationship names, else their first shared
        column (matched in any case)."""
        names = rules.grid_names(table)
        found = [self.base.ws.store.get(n) for n in names]
        if any(f is None for f in found):
            raise NotFound(f"{table}'s two grids are not both open.")
        left = [c.name for c in found[0].columns]
        right = {c.name.casefold(): c.name for c in found[1].columns}
        shared = [c for c in left if c.casefold() in right]
        joined = {
            str(r.get(side + "_column", ""))
            for r in state.get("relationships", [])
            for side in ("from", "to")
            if r.get(side + "_table") == table
        }
        keys = [c for c in shared if c in joined] or shared[:1]
        if not keys:
            raise NotFound(f"{table}'s two grids share no column to compare by.")
        return [[keys[0], right[keys[0].casefold()]]]

    # ===== E: Read Power BI from =====

    def state(self) -> dict[str, Any]:
        return self._state()

    def _state(self) -> dict[str, Any]:
        current = self.base.sab_projects.current
        if current is None:
            raise NotFound("Open a Power BI project first.")
        import json

        text = self.files.read_text(str(Path(current.folder) / rules.STATE_PATH))
        if not text:
            raise NotFound("This project was not made from a .pbix (it has no .sab/powerbi.json).")
        return dict(json.loads(text))

    def kept(self) -> tuple[dict[str, Any] | None, str | None]:
        """The round trip's two inputs for part 1's export: .sab/powerbi.json and data.ipynb's text as it is
        now (saved); (None, None) outside a Power BI project made from a .pbix."""
        current = self.base.sab_projects.current
        if current is None:
            return None, None
        try:
            state = self._state()
        except NotFound:
            return None, None
        return state, self.files.read_text(str(Path(current.folder) / "data.ipynb"))

    def _write_state(self, state: Mapping[str, Any]) -> None:
        current = self.base.sab_projects.current
        self.files.write_text(str(Path(current.folder) / rules.STATE_PATH), rules.write_state(state))

    def source(self) -> dict[str, Any]:
        """Which source In Power BI reads: the project's choice, and what answers it now."""
        state = self._state()
        chosen = str(self.base.sab_projects.setting(SOURCE_KEY) or "published")  # the file: only a fallback
        effective, note = self._effective(state, chosen)
        model = (state.get("dataset") or {}).get("dataset") or Path(str(state.get("target", ""))).stem
        return {
            "source": chosen,
            "effective": effective,
            "note": note,
            "words": f"{model} · {SOURCE_WORDS[effective]}",
            "choices": [
                {"value": "published", "label": "Published"},
                {"value": "local", "label": "Local (Power BI Desktop)"},
            ],
        }

    def _effective(self, state: Mapping[str, Any], chosen: str) -> tuple[str, str]:
        if chosen == "local":
            if self.live is not None and self.live.open_file():
                return "local", ""
            return (
                "file",
                f"Open {Path(str(state.get('target', ''))).name} in Power BI Desktop. "
                + self._file_note(state),
            )
        if chosen == "published" and state.get("dataset"):
            return "published", ""
        return "file", (
            "Publish it, or pick its workspace. " if chosen == "published" else ""
        ) + self._file_note(state)

    def _file_note(self, state: Mapping[str, Any]) -> str:
        try:
            model = self.reader(str(state.get("target")))
            when = pf.as_of(model.refreshed).removeprefix("as of ")
        except Exception:
            when = ""
        return (
            f"Reading the file as of its last save: {when}."
            if when
            else "Reading the file as of its last save."
        )

    async def set_source(self, body: Any, who: str) -> dict[str, Any]:
        """{"source": "published" | "local"}: kept in .sab/project.json; the In Power BI grids read again."""
        value = body.get("source") if isinstance(body, dict) else None
        if value not in ("published", "local"):
            raise ValueError('Send {"source": "published"} or {"source": "local"}.')
        state = self._state()
        await self.base.sab_projects.set_setting(SOURCE_KEY, value, who)
        reloaded = []
        for t in state.get("tables", []):
            try:
                reloaded.append(await self._read_in_power_bi(state, str(t["name"]), who))
            except Exception as error:
                reloaded.append({"table": t["name"], "error": str(error).splitlines()[0][:200]})
        return self.source() | {"reloaded": reloaded}

    async def _read_in_power_bi(self, state: Mapping[str, Any], table: str, who: str) -> Any:
        chosen = str(self.base.sab_projects.setting(SOURCE_KEY) or "published")
        effective, _ = self._effective(state, chosen)
        name = rules.grid_names(table)[1]
        if effective == "published":
            ds = state["dataset"]
            where = {"schema": ds["dataset"], "table": table, "as": name}
            return (await self.base.connections.open_table(ds["connection"], where, who)).get("grid")
        if effective == "local" and self.live is not None:
            rows = await self.live.evaluate("EVALUATE '" + table.replace("'", "''") + "'")
            stored = await self.base.datasets.store_table(name, rows, "powerbi_local", False, who)
            return stored.get("grid")
        where = {"schema": pf.SCHEMA, "table": table, "as": name}
        return (await self.base.connections.open_table(str(state["file_connection"]), where, who)).get("grid")

    # ===== E everywhere: the project's one dataset connection name =====

    def aliases(self) -> dict[str, Any]:
        """The open Power BI project's dataset connection name (the model's) resolving through Read Power BI
        from: what DuckDB SQL `[Sales model].Sales`, a `%%dax Sales model` cell and the grids read."""
        try:
            state = self._state()
        except Exception:  # no Power BI project open
            return {}
        return {rules.dataset_name(state): DatasetAlias(self)}

    async def read_table(self, table: str) -> Any:
        """One model table, whole, through what Read Power BI from answers now (an Arrow table)."""
        state = self._state()
        effective, _ = self._effective(state, str(self.base.sab_projects.setting(SOURCE_KEY) or "published"))
        most = self.base.ws.settings.max_connection_query_rows
        if effective == "local" and self.live is not None:
            return await self.live.evaluate("EVALUATE '" + table.replace("'", "''") + "'")
        if effective == "published":
            ds = state["dataset"]
            place = {"database": "", "schema": str(ds["dataset"]), "table": table}
            connection = str(ds["connection"])
        else:
            place = {"database": "", "schema": pf.SCHEMA, "table": table}
            connection = str(state["file_connection"])
        read = await self.base.connections.read_for_query(connection, place, Pushed(), most)
        return read.table

    async def dax(self, query: str) -> Any:
        """DAX through what Read Power BI from answers now. The file answers whole tables only."""
        state = self._state()
        effective, _ = self._effective(state, str(self.base.sab_projects.setting(SOURCE_KEY) or "published"))
        if effective == "local" and self.live is not None:
            return await self.live.evaluate(query)
        if effective == "published":
            ds = state["dataset"]
            read = await self.base.connections.read_query(
                str(ds["connection"]), query, {"dataset": str(ds["dataset"])}
            )
            return read.table
        table = rules.table_of(query)
        if table is None:
            raise Refused(
                "The .pbix file answers whole tables only (EVALUATE 'Sales'): publish it, or open it in "
                "Power BI Desktop and read from Local."
            )
        return await self.read_table(table)

    # ===== H: To finish setting up =====

    async def to_finish(self) -> list[dict[str, Any]]:
        try:
            state = self._state()
        except NotFound:
            return []
        state = dict(state) | {"registration": self.base.sab_projects.setting(REGISTRATION_KEY)}
        if state["registration"] == "none":
            state["registration_none"] = True
        needs: dict[str, str] = {}
        for c in {str(t.get("connection")) for t in state.get("tables", []) if t.get("connection")}:
            try:
                status = self.base.blades.summary(self.base.blades.get(c))["secrets"]
                missing = [s for s, saved in status.items() if not saved]
            except Exception:  # noqa: S112 (gone: nothing to set up)
                continue
            if missing:
                needs[c] = "a password" if len(missing) == 1 else f"{len(missing)} values"
        return rules.to_finish(state, self.registrations(), needs)

    async def fix(self, body: Any, who: str) -> dict[str, Any]:
        """One row's fix: {"action": "dataset", "connection", "dataset"} | {"action": "not_published"} |
        {"action": "registration", "registration"} (or "none"). Sign-ins and passwords are the user's
        (Set up this computer)."""
        body = body if isinstance(body, dict) else {}
        action = body.get("action")
        state = self._state()
        if action == "dataset":
            if not body.get("connection") or not body.get("dataset"):
                raise ValueError('Send {"action": "dataset", "connection": ..., "dataset": ...}.')
            state["dataset"] = {"connection": str(body["connection"]), "dataset": str(body["dataset"])}
            state["dataset_connection"] = state["dataset"]["connection"]
            state.pop("not_published", None)
        elif action == "not_published":
            state["not_published"] = True
        elif action == "registration":
            return await self.registration({"registration": body.get("registration")}, who)
        else:
            raise ValueError("Send an action: dataset, not_published or registration.")
        await asyncio.to_thread(self._write_state, state)
        self.base.ws.audit.write(who, "powerbi_setup", str(action))
        return {"to_finish": await self.to_finish()}

    # ===== G: the project's app registration =====

    def query_hints(self) -> dict[str, str]:
        """A table of the project's published dataset worth one COUNTROWS in an access report."""
        try:
            state = self._state()
        except NotFound:
            return {}
        dataset = (state.get("dataset") or {}).get("dataset")
        tables = [str(t["name"]) for t in state.get("tables", [])]
        return {str(dataset): tables[0]} if dataset and tables else {}

    def _microsoft_connections(self, state: Mapping[str, Any]) -> list[str]:
        names = {str(t.get("connection")) for t in state.get("tables", []) if t.get("connection")}
        out = []
        for name in sorted(names):
            try:
                blade = self.base.connections.blade(name)[0]
            except Exception:  # noqa: S112 (gone)
                continue
            if blade.template in MICROSOFT_TEMPLATES:
                out.append(name)
        return out

    async def registration(self, body: Any, who: str) -> dict[str, Any]:
        """Get ({}), or set {"registration": name | "none", "dry_run"?}: the Microsoft sources the import made
        re-pointed to sign in with its variables after a dry run; one set otherwise keeps its own sign-in."""
        body = body if isinstance(body, dict) else {}
        state = self._state()
        current = self.base.sab_projects.setting(REGISTRATION_KEY)
        if "registration" not in body:
            return {"registration": current, "registrations": self.registrations()}
        name = str(body.get("registration") or "")
        if name != "none" and name not in self.registrations():
            raise NotFound(f"{name} is not an app registration in the library.")
        own = set(state.get("own_sign_in", []))
        changes = [
            {"connection": c, "change": "keeps its own sign-in" if c in own else f"signs in with {name}"}
            for c in self._microsoft_connections(state)
        ]
        if name == "none":
            changes = [
                {"connection": c["connection"], "change": "keeps its sign-in (as you)"} for c in changes
            ]
        if body.get("dry_run"):
            return {"dry_run": True, "registration": name, "changes": changes}
        repoints = name != "none" and any(c["change"].startswith("signs in with") for c in changes)
        asked = f"Sign in with {name}"
        if repoints and who == "agent" and not await self.approvals.ask(name, "powerbi_registration", asked):
            raise Refused("The user declined: the app registration was not changed.")
        await self.base.sab_projects.set_setting(REGISTRATION_KEY, name, who)
        if name != "none":
            reg = self.base.app_registrations.get(name)
            for change in changes:
                if change["connection"] not in own:
                    await self._repoint(change["connection"], reg, who)
            try:
                await self.base.app_registrations.check(name, who)  # G: checked after the setting changes
            except Exception as error:  # the report says what it can; a failure is said, never in the way
                changes.append({"connection": "", "change": f"the access check did not run: {error}"})
        return {"registration": name, "changes": changes, "to_finish": await self.to_finish()}

    async def _repoint(self, name: str, reg: Any, who: str) -> None:
        """A Microsoft connection (Azure SQL or SQL Server with Entra, Dataverse, SharePoint, OneLake, Data
        Lake) made to sign in with the registration's variables: its kind's app-registration code, its place
        settings kept (domain/app_registrations.py signed_in_with)."""
        from swissarmybench.domain import app_registrations as registrations

        blade = self.base.connections.blade(name)[0]
        code = registrations.signed_in_with(str(blade.template or ""), blade.code, reg)
        if code is None:
            return
        body = {
            "name": name,
            "kind": blade.kind,
            "template": blade.template,
            "dialect": blade.dialect,
            "code": code,
        }
        await self.base.connections.save(body, name, who)

    # ===== F: the page, as data =====

    async def page(self) -> dict[str, Any]:
        """The Power BI page as data: the target, its status, the source, the app registration, To finish,
        the measures, and the big buttons (each with one sentence)."""
        try:
            state = self._state()
        except NotFound:
            return {
                "project": False,
                "actions": [
                    {
                        "id": "import",
                        "label": "Make a Power BI project from a .pbix",
                        "note": "Its connections, tables, relationships and measures, ready to work.",
                    }
                ],
            }
        source = self.source()
        return {
            "project": True,
            "target": state.get("target"),
            "status": source["words"],
            "source": source,
            "registration": self.base.sab_projects.setting(REGISTRATION_KEY),
            "registrations": self.registrations(),
            "to_finish": await self.to_finish(),
            "measures": state.get("measures", []),
            "actions": [
                {
                    "id": "refresh",
                    "label": "Refresh from the file",
                    "note": "Reads the .pbix again: new tables, measures and relationships.",
                },
                {
                    "id": "edit",
                    "label": "Edit in Power BI Desktop",
                    "note": "Our relationships and measures into the open model, after a dry run.",
                },
                {
                    "id": "pages",
                    "label": "Use another report's pages",
                    "note": "Another report's pages on this model.",
                },
                {
                    "id": "export",
                    "label": "Export as a Power BI Project",
                    "note": "A .pbip that Power BI Desktop opens.",
                },
            ],
        }

    async def panel(self, body: Any, who: str) -> dict[str, Any]:
        """The Power BI page drawn by the base's generic panel (web/src/extensionPanel.ts): GET ({}) its data;
        POST {choice, value} (Read Power BI from, App registration) or {action}."""
        body = body if isinstance(body, dict) else {}
        said: list[dict[str, str]] = []
        self._opens = None
        try:
            if body.get("choice") == "source":
                await self.set_source({"source": body.get("value")}, who)
            elif body.get("choice") == "registration":
                await self.registration({"registration": body.get("value")}, who)
            elif body.get("action"):
                said = await self._panel_action(str(body["action"]), who)
        except Exception as error:  # said on the page, in place
            said = [{"text": str(error).splitlines()[0][:300], "tone": "error"}]
        page = await self.page()
        offered = self._offered(page["project"])
        if not page["project"]:
            lines = [
                {
                    "text": "Open a Power BI project, or make one from a .pbix (New project, Power BI).",
                    "tone": "",
                }
            ]
            return {
                "lines": said + offered["lines"] + ([] if offered["lines"] else lines),
                "switches": [],
                "actions": offered["actions"],
            }
        source = page["source"]
        regs = [{"value": "", "label": "Choose…"}] if not page["registration"] else []
        regs += [{"value": r, "label": r} for r in page["registrations"]]
        regs.append({"value": "none", "label": "None (sign in as you)"})
        rows = [
            {
                "id": r["id"],
                "text": r["words"],
                "tone": "warn",
                "action": {"id": f"fix:{r['id']}", "label": r["fix"]["label"]},
            }
            for r in page["to_finish"]
        ]
        lines = [{"text": f"{Path(str(page['target'])).name} · {page['status']}", "tone": "ok"}]
        if source["note"]:
            lines.append({"text": source["note"], "tone": "warn"})
        if page["registration"] in (None, "none"):
            lines.append({"text": "Only works on your machine: signed in as you.", "tone": "warn"})
        lines += [
            {
                "text": f"{m['name']}{f' ({m["folder"]})' if m.get('folder') else ''} = {m['expression']}",
                "tone": "",
            }
            for m in page["measures"]
        ]
        return {
            "heading": "To finish setting up",
            "review": self.review,
            "open": self._opens,
            "rows": rows,
            "choices": [
                {
                    "id": "source",
                    "label": "Read Power BI from",
                    "value": source["source"],
                    "options": source["choices"],
                },
                {
                    "id": "registration",
                    "label": "App registration",
                    "value": page["registration"] or "",
                    "options": regs,
                },
            ],
            "lines": said + offered["lines"] + lines,
            "switches": [],
            "actions": offered["actions"]
            + [{"id": a["id"], "label": a["label"], "note": a["note"]} for a in page["actions"]],
        }

    def opened(self, body: Any) -> dict[str, Any]:
        """A Power BI file opened with the app (`swissarmybench open report.pbix`, Open with) or dropped on a
        window: offered on the Power BI page (never handed to the default program). The page to show."""
        path = str(body.get("path") or "") if isinstance(body, dict) else ""
        if not path.lower().endswith((".pbix", ".pbit", ".pbip")):
            raise ValueError("Send the path of a .pbix, .pbit or .pbip.")
        self.pending = path
        return {
            "page": "/workspace?open=powerbi",
            "offered": self._offered(self.base.sab_projects.current is not None),
        }

    def _offered(self, project: bool) -> dict[str, Any]:
        """What the opened file is offered for: no project open, Make a Power BI project for it; one open,
        Import its model or Use its pages on our model."""
        if not self.pending:
            return {"lines": [], "actions": []}
        name = Path(self.pending).name
        pbix = self.pending.lower().endswith(".pbix")
        if not project:
            actions = (
                [{"id": "open:import", "label": "Make a Power BI project for it", "primary": True}]
                if pbix
                else []
            )
            words = f"{name} was opened." + ("" if pbix else " A project is made from a .pbix.")
            return {"lines": [{"text": words, "tone": "ok"}], "actions": actions}
        actions = [{"id": "open:pages", "label": "Use its pages on our model"}]
        if pbix:
            actions.insert(0, {"id": "open:model", "label": "Import its model"})
        return {"lines": [{"text": f"{name} was opened.", "tone": "ok"}], "actions": actions}

    async def _panel_action(self, action: str, who: str) -> list[dict[str, str]]:
        if action.startswith("open:") and self.pending:
            path, self.pending = self.pending, None
            if action == "open:import":
                done = await self.import_project({"path": path}, who)
                return [{"text": f"Made the Power BI project {done['project']}.", "tone": "ok"}]
            if action == "open:model":
                name = f"{Path(path).stem} file"
                await self.add_file_connection({"name": name, "path": path}, who)
                joined = await self.file_relationships(name, who)
                return [
                    {
                        "text": f"Added {name}: its tables, and {joined['relationships']} relationships.",
                        "tone": "ok",
                    }
                ]
            return [
                {
                    "text": "On the ERD page: Export to Power BI…, then Use an existing report's pages.",
                    "tone": "",
                }
            ]
        if action == "fix:not_published" or action == "fix:dataset":
            found = await self._published()
            state = self._state()
            pick, _ = rules.find_dataset(self.reader(str(state["target"])), found, None)
            if pick is None:
                return [
                    {
                        "text": "No single published dataset matches: name it with powerbi_setup_status.",
                        "tone": "warn",
                    }
                ]
            await self.fix({"action": "dataset"} | pick, who)
            return [{"text": f"Found {pick['dataset']} in {pick['connection']}.", "tone": "ok"}]
        if action.startswith("fix:connection:"):
            return [{"text": "Set it on this computer: Settings, Team, Set up this computer.", "tone": ""}]
        if action == "fix:registration":
            return [{"text": "Choose it above.", "tone": ""}]
        if action == "refresh":
            plan_ = await self.plan({"path": self._state()["target"]})
            model = plan_.model
            words = f"{len(plan_.tables)} tables, {len(model.measures)} measures, "
            words += f"{len(model.relationships)} relationships"
            return [{"text": f"Read the file again: {words}.", "tone": "ok"}]
        if action == "edit":
            if self.live is None:
                return [
                    {
                        "text": "Edit in Power BI Desktop needs Power BI Desktop on this computer (Windows).",
                        "tone": "warn",
                    }
                ]
            planned = await self.live.plan({})
            changes = planned["changes"]
            self.review = {
                "id": "edit",
                "heading": "Edit in Power BI Desktop: the dry run",
                "items": [
                    {"text": c["words"], "tone": "ok" if c["ok"] else "warn"}
                    | ({"why": c["why"]} if c.get("why") else {})
                    for c in changes
                ],
                "apply": {
                    "id": "edit:apply",
                    "label": "Apply",
                    "disabled": not any(c["ok"] for c in changes),
                },
                "cancel": {"id": "edit:cancel", "label": "Cancel"},
                "empty": "Nothing to change: the open model has our relationships and measures.",
            }
            return []
        if action == "edit:cancel":
            self.review = None
            return []
        if action == "edit:apply":
            if self.live is None:
                raise Conflict("Edit in Power BI Desktop needs Power BI Desktop on this computer (Windows).")
            done = await self.live.apply({}, who)  # the agent's waits for the user's Allow
            self.review = None
            n = len(done["applied"])
            words = f"Applied {n} change{'' if n == 1 else 's'} to the open model in Power BI Desktop."
            return [{"text": words, "tone": "ok"}]
        if action == "export":
            done = await self.base.powerbi_export.export({}, who)
            return [
                {
                    "text": f"Exported: {done.get('folder') or done.get('file') or 'the Power BI Project'}.",
                    "tone": "ok",
                }
            ]
        if action == "pages":
            # The export dialog with its report part, right there on the page (the ERD's plug-in).
            tables = [str(t["name"]) for t in self._state().get("tables", []) if t.get("name")]
            self._opens = {"plugin": "powerbi_report_pages", "context": tables}
            return []
        return [{"text": f"{action} is not an action here.", "tone": "error"}]

    def check_conflict(self) -> None:
        if self.base.sab_projects.current is None:
            raise Conflict("Open a project first.")


class DatasetAlias:
    """The project's dataset connection name, as the base's connection tables take it (services/hooks.py)."""

    def __init__(self, project: PowerBIProject) -> None:
        self._project = project

    def words(self) -> str:
        return str(self._project.source()["words"])

    async def tables(self) -> list[str]:
        state = self._project.state()
        return [str(t["name"]) for t in state.get("tables", []) if t.get("name")]

    async def read(self, table: str) -> Any:
        return await self._project.read_table(table)

    async def dax(self, query: str) -> Any:
        return await self._project.dax(query)
