"""Connections: the databases and files the user reaches, apart from blades (domain/connections.py).

A connection is kept in the blade store, so this service lists, saves and tests through the blade
service; what it adds is the split (only connections here, and the blades lists without them) and
the Add connection form: each database and file starter as fields, passwords and the code they fill.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol

from swissarmygrid.domain import connections as rules
from swissarmygrid.domain import powerbi
from swissarmygrid.domain.blades import Blade, BladeError, Template
from swissarmygrid.domain.catalogs import count_sql, select_sql
from swissarmygrid.domain.datasets import Opened
from swissarmygrid.domain.relationships import Model
from swissarmygrid.services.blades import BladeService


class ConnectionService:
    def __init__(
        self,
        blades: BladeService,
        templates: Sequence[Template],
        on_saved: Callable[[str], None] = lambda name: None,
        catalog_state: Callable[[str], dict[str, str] | None] = lambda name: None,
        tables: Tables | None = None,
        models: RelationshipModels | None = None,
        catalogs: LoadedCatalogs | None = None,
    ) -> None:
        self._blades = blades
        self._templates = templates
        # A saved connection's catalog loads itself; each one's loading state (services/catalog_loading.py).
        self._on_saved = on_saved
        self._catalog_state = catalog_state
        # Where an opened table goes: the datasets (services/datasets.py), as a grid.
        self._tables = tables
        # Where a Power BI dataset's relationships go: the current model (services/relationships.py).
        self._models = models
        # A Power BI workspace's loaded catalog: its datasets, and the table names several of them hold.
        self._catalogs = catalogs

    def listing(self) -> dict[str, Any]:
        """Every connection: databases first, then files, then key vaults (each with its entries: a
        variable and the secret's name in the vault, never a value), each with what it is."""
        labels = {t.id: t.label for t in self._templates}
        order = {"database": 0, "file": 1, "vault": 2}
        found = []
        for b in self._blades.listing()["blades"]:
            kind = rules.connection_kind(str(b["kind"]), b.get("template"))
            if kind:
                more: dict[str, Any] = {
                    "connection": kind,
                    "type": labels.get(str(b.get("template") or ""), ""),
                    "catalog_state": self._catalog_state(str(b["name"])),  # loading, waiting, failed
                }
                if kind == "vault":
                    vault = self._blades.get(str(b["name"]))
                    entries = vault.vault_mapping.items()
                    more["entries"] = [{"env": env, "secret": secret} for env, secret in entries]
                    more["every"] = vault.vault_all
                found.append(b | more)
        found.sort(key=lambda c: (order[c["connection"]], not c.get("pinned"), str(c["name"]).casefold()))
        return {"connections": found}  # each with its code_name (the blades list names them)

    def types(self) -> dict[str, Any]:
        """The starters a connection is made from (databases, files, key vaults), each as its form."""
        out = []
        for t in self._templates:
            if rules.is_connection(t.kind, t.id):
                out.append(rules.form(t.to_json(), self._blades.inspect(t.code, t.id)))
        return {"types": out}

    def details(self, name: str) -> dict[str, Any]:
        """A saved connection as the form shows it to change: its own code's fields and passwords."""
        blade = self._blades.get(name)
        kind = rules.connection_kind(blade.kind, blade.template)
        if kind is None:
            raise BladeError(f"{blade.name} is a blade, not a connection: open it on the blades page.")
        inspected = self._blades.inspect(blade.code, blade.template, blade.name)
        template = {
            "id": blade.template or "",
            "label": next((t.label for t in self._templates if t.id == blade.template), blade.dialect),
            "group": {"database": "Databases", "file": "Files"}.get(kind, "Vaults"),
            "kind": blade.kind,
            "dialect": blade.dialect,
            "variable": blade.variable or "",
            "catalog": {"language": blade.catalog_language, "command": blade.catalog_command}
            if blade.has_catalog
            else None,
            "code": blade.code,
            "vault_mapping": [{"env": e, "secret": v} for e, v in blade.vault_mapping.items()],
            "vault_all": blade.vault_all,
            "row_limit": blade.row_limit,
            "sign_ins": next(
                (t.to_json()["sign_ins"] for t in self._templates if t.id == blade.template), []
            ),
        }
        return rules.form(template, inspected) | {
            "name": blade.name,
            "description": blade.description,
            "tags": blade.tags,
            "summary": self._blades.summary(blade),
        }

    def _check(self, body: Any) -> None:
        if not isinstance(body, dict):
            raise BladeError("Send the connection as a JSON object.")
        if not rules.is_connection(str(body.get("kind", "")), body.get("template")):
            raise BladeError(
                "A connection is made from a database, file or key vault starter. Other code is saved "
                "as a blade."
            )

    async def save(self, body: Any, previous: str | None) -> dict[str, Any]:
        self._check(body)
        saved = await self._blades.save(body, previous)
        self._on_saved(str(saved["name"]))  # its catalog loads itself, in the background
        return saved

    # ===== where a password comes from: the keyring, an environment variable, or a key vault =====

    def vaults(self) -> dict[str, Any]:
        """The vault blades a password can come from, each with its entries (environment variable ->
        the secret's name in the vault). Names only: no value is read."""
        labels = {t.id: t.label for t in self._templates}
        found = [b for b in self._blades.listing()["blades"] if b["kind"] == "vault"]
        out = []
        for b in found:
            blade = self._blades.get(str(b["name"]))
            mapping = [{"env": env, "secret": secret} for env, secret in blade.vault_mapping.items()]
            out.append(
                {
                    "name": blade.name,
                    "type": labels.get(blade.template or "", ""),
                    "description": blade.description,
                    "entries": mapping,
                    "every": blade.vault_all,
                    "read_only": blade.pack is not None,
                }
            )
        return {"vaults": out}

    async def vault_names(self, body: Any) -> dict[str, Any]:
        """The secrets in a vault, saved or the form's draft, each with a variable to map it to. Names
        only: no value is read or sent."""
        return await self._blades.vault_names(body)

    async def source(self, body: Any) -> dict[str, Any]:
        """Point a password at its source: `{"code", "secret", "from": "keyring" | "env" | "vault", "env",
        "vault", "vault_secret", "connection"}`. An environment variable or a vault's entry is named in the
        code (secret("WAREHOUSE_PASSWORD")); a new entry is added to the vault blade. Returns the code."""
        if not isinstance(body, dict) or not isinstance(body.get("code"), str):
            raise ValueError('Send {"code": "...", "secret": "password", "from": "env", "env": "NAME"}.')
        code, secret, origin = body["code"], body.get("secret"), body.get("from")
        if not isinstance(secret, str) or not secret:
            raise ValueError("Name the password: the secret(...) the code asks for.")
        if origin == "keyring":
            return {"code": code, "secret": secret}
        if origin == "env":
            env = rules.check_env_name(body.get("env"))
            return {"code": rules.rename_secret(code, secret, env), "secret": env}
        if origin != "vault":
            raise ValueError(
                'A password comes "from" the keyring, an environment variable ("env") or a vault.'
            )
        vault = self._blades.get(str(body.get("vault") or ""))
        if vault.kind != "vault":
            raise BladeError(f"{vault.name} is not a vault blade.")
        if body.get("env"):  # one of the vault's entries
            env = rules.check_env_name(body["env"])
            if env not in vault.vault_mapping:
                raise BladeError(f"{vault.name} has no entry {env}.")
        else:  # a new entry: the secret's name in the vault, under a variable named after the connection
            in_vault = body.get("vault_secret")
            if not isinstance(in_vault, str) or not in_vault.strip() or len(in_vault) > 500:
                raise ValueError("Name the secret as it is called in the vault.")
            if vault.vault_all:  # it loads every secret already, each under its own name
                env = rules.env_name_for_secret(in_vault.strip())
                return {"code": rules.rename_secret(code, secret, env), "secret": env, "vault": vault.name}
            if vault.pack:
                raise BladeError(f"{vault.name} comes from a pack: add the entry in that pack's repository.")
            word = body.get("label") if isinstance(body.get("label"), str) else secret
            env = rules.env_name_for(str(body.get("connection") or "connection"), str(word))
            data = vault.to_json()
            data["vault_mapping"] = [*data["vault_mapping"], {"env": env, "secret": in_vault.strip()}]
            await self._blades.save(data, vault.name)
        return {"code": rules.rename_secret(code, secret, env), "secret": env, "vault": vault.name}

    async def test(self, body: Any) -> dict[str, Any]:
        """Run the form's code (not saved) with the passwords typed into it. A form not named yet is
        tested all the same (the name is only needed to save)."""
        self._check(body)
        kind = rules.connection_kind(str(body.get("kind", "")), body.get("template"))
        given: str | None = None
        if not str(body.get("name") or "").strip():
            # A file connection not named yet is called after its file, as the form's Browse… does.
            if kind == "file" and isinstance(body.get("code"), str):
                settings = self._blades.inspect(body["code"], body.get("template")).get("settings", [])
                given = rules.name_from_path(rules.file_setting(settings, body.get("template"))) or None
            body = {**body, "name": given or "Untitled"}
        result = await self._blades.test_draft(body)
        path = result.pop("path", None)
        if given:
            result["name"] = given
        if kind == "file" and isinstance(path, str) and self._tables is not None:
            result |= await self._file_preview(body.get("template"), path)
        return result

    async def _file_preview(self, template: Any, path: str) -> dict[str, Any]:
        """A file connection's Test: the file's columns and first rows (a workbook's first sheet).
        A folder has no one table. A file that cannot be read says why; the test itself has passed."""
        if template == "folder" or self._tables is None:
            return {}
        try:
            sheet: str | None = None
            if template == "excel":
                sheets = await self._tables.sheets(path)
                sheet = sheets[0] if sheets else None
            preview = await self._tables.peek(path, sheet, rules.TEST_ROWS)
        except Exception as error:  # any reader's refusal: said beside the test's result
            return {"preview_error": str(error)}
        return {"preview": preview | ({"sheet": sheet} if sheet else {})}

    # ===== a connection's table as a grid (the catalog, the connection's row, the agent) =====

    def _target(self, name: str, body: Any) -> tuple[Blade, str, dict[str, str]]:
        blade = self._blades.get(name)
        kind = rules.connection_kind(blade.kind, blade.template)
        if not rules.has_catalog(kind):
            raise BladeError(f"{blade.name} has no tables to open.")
        where = body if isinstance(body, dict) else {}
        place = {k: str(where.get(k) or "") for k in ("database", "schema", "table")}
        return blade, str(kind), place

    async def open_table(self, name: str, body: Any, who: str) -> dict[str, Any]:
        """A connection's table as a grid: a database's first Rows to open rows (every row with
        `"all": true`), the grid told how many the source holds; a file connection's file (a sheet, a
        file of a folder) whole. A workbook with several sheets and none named answers its sheets."""
        if self._tables is None:
            raise BladeError("Opening a table needs the datasets.")
        blade, kind, place = self._target(name, body)
        every = isinstance(body, dict) and body.get("all") is True
        if kind == "file":
            reached = await self._blades.rows(blade, None, None, body)
            path, sheet = rules.file_to_open(blade.template, str(reached["path"]), place["table"])
            if blade.template == "excel" and sheet is None:
                sheets = await self._tables.sheets(path)
                if len(sheets) > 1:
                    return {"sheets": sheets}
                sheet = sheets[0] if sheets else None
            dataset = rules.dataset_name(place["table"] or blade.name)
            return await self._tables.load_file(dataset, path, sheet, who)
        if not place["table"]:
            raise ValueError("Name the table to open.")
        limit = None if every else (blade.row_limit or rules.DEFAULT_OPEN_ROWS)
        sql = select_sql(blade.dialect, place["database"], place["schema"], place["table"], [], limit)
        count = (
            None if every else count_sql(blade.dialect, place["database"], place["schema"], place["table"])
        )
        dax = blade.dialect == powerbi.DIALECT
        within = place["schema"] if dax else ""  # a Power BI workspace: the table's dataset
        answer = await self._blades.rows(blade, sql, count, body, within)
        table, total = answer["table"], answer.get("total")
        if table.num_columns == 0:
            # Power BI names an answer's columns only on its rows: an empty table comes with none.
            raise BladeError(f"{place['table']} has no rows, so there is nothing to open.")
        shown = int(table.num_rows)
        opened = (
            Opened(blade.name, place["database"], place["schema"], place["table"], shown, int(total))
            if limit is not None and isinstance(total, int) and total > shown
            else None
        )
        if dax:
            # Its own name; with its dataset's when another dataset of the workspace has one too.
            dataset = powerbi.grid_name(within, place["table"], await self._shared(blade.name))
        else:
            dataset = rules.dataset_name(place["table"])
        origin = powerbi.joined_name(blade.name, within)  # a notebook reads it again: sag.dax(origin, sql)
        stored = await self._tables.store(dataset, table, who, opened, origin, sql, dax)
        return stored | {"shown": shown, "total": total}

    async def _shared(self, name: str) -> set[str]:
        return set() if self._catalogs is None else await self._catalogs.shared_tables(name)

    async def preview(self, name: str, body: Any) -> dict[str, Any]:
        """A table's first rows, for the catalog page beside its columns (nothing is kept)."""
        if self._tables is None:
            raise BladeError("A preview needs the datasets.")
        blade, kind, place = self._target(name, body)
        if kind == "file":
            reached = await self._blades.rows(blade, None, None, body)
            path, sheet = rules.file_to_open(blade.template, str(reached["path"]), place["table"])
            return await self._tables.peek(path, sheet, rules.PREVIEW_ROWS)
        if not place["table"]:
            raise ValueError("Name the table to preview.")
        sql = select_sql(
            blade.dialect, place["database"], place["schema"], place["table"], [], rules.PREVIEW_ROWS
        )
        within = place["schema"] if blade.dialect == powerbi.DIALECT else ""
        table = (await self._blades.rows(blade, sql, None, body, within))["table"]
        return {"columns": list(table.column_names), "rows": [list(r.values()) for r in table.to_pylist()]}

    # ===== a Power BI workspace: its datasets, and a dataset's own relationships into the model =====

    def _workspace(self, name: str) -> Blade:
        blade = self._blades.get(name)
        if blade.dialect != powerbi.DIALECT:
            raise BladeError(
                f"{blade.name} is not a Power BI workspace: only a workspace has datasets, and only a "
                "dataset's own relationships are read this way. For other tables, find them (Find "
                "relationships) or import a .tang."
            )
        return blade

    async def datasets(self, name: str, body: Any, live: bool | None = None) -> dict[str, Any]:
        """A Power BI workspace's datasets. From its loaded catalog (each name, and the note of one
        that could not be read); with `live`, or before the catalog is loaded, from Power BI itself
        (names and ids). `live` False never asks Power BI (a page that only lists: no sign-in window
        opens for it): none until the catalog is loaded. Each is named for a DAX cell too:
        `Finance/Sales model`."""
        blade = self._workspace(name)
        listed = None if live or self._catalogs is None else await self._catalogs.schema_names(blade.name)
        if listed is None and live is False:
            return {"connection": blade.name, "datasets": [], "from": "none"}
        if listed is not None:
            found = [
                {"name": str(s["schema"])} | ({"note": s["note"]} if s.get("note") else {}) for s in listed
            ]
            origin = "catalog"
        else:
            asked = await self._blades.datasets(blade, body)
            found, origin = ([{"name": ""}] if asked is None else list(asked)), "powerbi"
        for dataset in found:
            dataset["cell"] = powerbi.joined_name(blade.name, dataset["name"])
        return {"connection": blade.name, "datasets": found, "from": origin}

    async def import_relationships(self, name: str, body: Any, who: str) -> dict[str, Any]:
        """Read one dataset's relationships (DAX's INFO functions, on the connection) and merge them
        into the current model, the tables named as they open as grids: the Diagram and the Key
        Finder's known joins then show them. `{"dataset"}` names it; a workspace with one dataset
        needs none. Answers the model, what the merge changed, and what came."""
        if self._models is None:
            raise BladeError("Importing relationships needs the relationship model.")
        blade = self._workspace(name)
        dataset = str(body.get("dataset") or "").strip() if isinstance(body, dict) else ""
        try:
            answer = await self._blades.queries(blade, powerbi.RELATIONSHIP_QUERIES, body, dataset)
        except Exception as error:
            if dataset or "name the one to read" not in str(error):
                raise
            # Several datasets and none named: say how to name one here, not in the connection's Python.
            has = str(error).split("It has:", 1)[-1].strip()
            raise BladeError(
                f"{blade.name} has several datasets: name the one to import. It has: {has}"
            ) from None
        try:
            model, skipped = powerbi.relationships_model(
                blade.name,
                int(answer["attempt"]),
                list(answer["results"]),
                dataset,
                await self._shared(blade.name),
            )
        except powerbi.PowerBIError as error:
            raise BladeError(str(error)) from None
        what = powerbi.joined_name(blade.name, dataset)
        if not model.relationships:
            raise BladeError(f"{what} has no relationships to import.")
        merged = await self._models.apply(model, who)
        return {
            "dataset": dataset,
            "model": {k: v for k, v in merged.items() if k != "changed"},
            "changed": merged.get("changed", []),
            "imported": [r.to_json() for r in model.relationships],
            "tables": sorted(model.tables()),
            "skipped": skipped,  # those of the date tables Power BI makes by itself
        }


class LoadedCatalogs(Protocol):
    """The loaded catalogs (services/catalogs.py): a Power BI workspace's datasets are its schemas."""

    async def shared_tables(self, name: str) -> set[str]: ...

    async def schema_names(self, name: str) -> list[dict[str, Any]] | None: ...


class RelationshipModels(Protocol):
    """The current relationship model (services/relationships.py Models)."""

    async def apply(self, model: Model, who: str) -> dict[str, Any]: ...


class Tables(Protocol):
    """Where a connection's table goes as a grid (services/datasets.py)."""

    async def store(
        self,
        name: str,
        table: Any,
        who: str,
        opened: Opened | None,
        connection: str = "",
        sql: str = "",
        dax: bool = False,
    ) -> dict[str, Any]: ...

    async def load_file(self, name: str, path: str, sheet: str | None, who: str) -> dict[str, Any]: ...

    async def sheets(self, path: str) -> list[str]: ...

    async def peek(self, path: str, sheet: str | None, rows: int) -> dict[str, Any]: ...
