"""Connections: the databases and files the user reaches, apart from blades (domain/connections.py).

A connection is kept in the blade store, so this service lists, saves and tests through the blade
service; what it adds is the split (only connections here, and the blades lists without them) and
the Add connection form: each database and file starter as fields, passwords and the code they fill.
"""

from __future__ import annotations

import base64
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from swissarmybench.domain import connection_tables as table_rules
from swissarmybench.domain import connection_usage as usage_rules
from swissarmybench.domain import connections as rules
from swissarmybench.domain import dataverse, lakes, powerbi, python_connections, sql_server, write_capability
from swissarmybench.domain import project_scope as scope_rules
from swissarmybench.domain.blades import Blade, BladeError, Template
from swissarmybench.domain.catalogs import count_sql, select_sql
from swissarmybench.domain.datasets import Opened
from swissarmybench.domain.relationships import Model
from swissarmybench.services.blades import BladeService
from swissarmybench.services.workspace import Refused


def _form(template: dict[str, Any], inspected: dict[str, Any]) -> dict[str, Any]:
    """A connection type's form, with the heading over its secrets (by its kind: the page names none)."""
    form = rules.form(template, inspected)
    return form | {"secrets_legend": usage_rules.secrets_legend(form.get("dialect"))}


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
        colours: Colours | None = None,
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
        # Connection colours (services/connection_colours.py): a new connection's next free one, and a
        # colour sent with one checked against the rail's.
        self._colours = colours
        # The Variables page (services/variables.py, set once built): a setting's ${NAME} checked before a
        # Test runs, so a name not set here is the one error (12.7), not the driver's.
        self.variable_check: CodeCheck | None = None
        # sab.write for the agent (connections_write), set once built: the user's Allow (services/agent.py)
        # and an open table's grid view as an Arrow IPC stream (services/table_cells.py).
        self.approvals: Any = None
        self.open_view: Callable[[str], Awaitable[bytes]] | None = None

    def listing(self) -> dict[str, Any]:
        """Every connection: databases first, then files, then key vaults (each with its entries: a
        variable and the secret's name in the vault, never a value), each with what it is."""
        labels = {t.id: t.label for t in self._templates}
        order = {"database": 0, "file": 1, "python": 2, "vault": 3}
        found = []
        writers = self._write_starters()
        for b in self._blades.listing()["blades"]:
            kind = rules.connection_kind(str(b["kind"]), b.get("template"))
            if kind:
                more: dict[str, Any] = {
                    "connection": kind,
                    "type": labels.get(str(b.get("template") or ""), ""),
                    "catalog_state": self._catalog_state(str(b["name"])),  # loading, waiting, failed
                }
                # A project opened on another computer: a password with no source here, and its fix.
                missing = self._blades.needs_passwords(str(b["name"]))
                more["needs_password"] = (
                    scope_rules.password_fix(str(b["name"]), missing) if missing else None
                )
                saved = self._blades.get(str(b["name"]))
                # How it lists and reads its tables (domain/connection_tables.py); none for a key vault.
                more["tables_kind"] = table_rules.tables_kind(
                    saved.kind, saved.template, saved.dialect, saved.catalog_language, saved.tags, saved.code
                )
                # What the pages draw for its kind (domain/connection_usage.py: they name no kind).
                more["facts"] = usage_rules.kind_facts(
                    str(b["name"]), kind, saved.dialect, more["tables_kind"], more["type"]
                )
                if kind != "vault":  # what it can write: "Writes: <the starters>" or "Read-only: <why>"
                    more["writes"] = write_capability.capability(
                        b.get("template"), writers, more["tables_kind"]
                    )
                if kind == "vault":
                    vault = saved
                    entries = vault.vault_mapping.items()
                    more["entries"] = [{"env": env, "secret": secret} for env, secret in entries]
                    more["every"] = vault.vault_all
                    # How many variables it gives; a vault that loads every secret: when its names were
                    # read, and why the last read failed (its remembered names kept: services/vault_names.py).
                    more["names"] = self._blades.vault_state(vault)
                found.append(b | more)
        found.sort(key=lambda c: (order[c["connection"]], not c.get("pinned"), str(c["name"]).casefold()))
        return {"connections": found}  # each with its code_name (the blades list names them)

    def _write_starters(self) -> list[dict[str, Any]]:
        """The starter pack's Write starters (each names the connection kinds it writes to): what
        write_capability reads of each, from the starters as they are (not their summaries: a listing
        asks on every call)."""
        return [
            {"name": b.name, "family": b.family, "kind": b.kind, "tags": list(b.tags)}
            for b in self._blades.starter_blades()
            if b.family == write_capability.WRITE_FAMILY
        ]

    def needs_passwords(self, name: str) -> list[str]:
        """The passwords a connection asks for that nothing on this computer gives (names only)."""
        return self._blades.needs_passwords(name)

    def types(self) -> dict[str, Any]:
        """The starters a connection is made from (databases, files, key vaults), each as its form."""
        out = []
        writers = self._write_starters()
        for t in self._templates:
            if rules.is_connection(t.kind, t.id):
                form = _form(t.to_json(), self._blades.inspect(t.code, t.id))
                own = rules.connection_kind(t.kind, t.id) == "python"
                reads = self._reads(t.code, t.catalog_command, t.read_command) if own else {"reads": []}
                writes = {} if t.kind == "vault" else {"writes": write_capability.capability(t.id, writers)}
                out.append(form | reads | writes)
        return {"types": out}

    def _reads(self, code: str, tables: str | None, read: str | None) -> dict[str, Any]:
        """A form's environment variables: the ones its boxes read (the user's own Python only)."""
        return {"reads": self._blades.variables_read(code, tables, read)["variables"]}

    def variables(self, body: Any) -> dict[str, Any]:
        """The environment variables the three boxes read, as the form is typed: `{"code", "tables",
        "read"}` -> `{"variables": [{"name", "required", "secret", "set"}]}`. Names only; nothing runs."""
        if not isinstance(body, dict):
            raise ValueError('Send {"code": "...", "tables": "...", "read": "..."}.')
        return self._blades.variables_read(body.get("code"), body.get("tables"), body.get("read"))

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
            "group": {"database": "Databases", "file": "Files", "python": "Your own code"}.get(
                kind, "Vaults"
            ),
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
            "read": {"command": blade.read_command} if blade.read_command else None,
            "variables": python_connections.sources_json(blade.variables),
            "sign_ins": next(
                (t.to_json()["sign_ins"] for t in self._templates if t.id == blade.template), []
            ),
            # Where its passwords may come from (Dataverse's: a key vault only), as its type says.
            "secrets_from": next((t.secrets_from for t in self._templates if t.id == blade.template), ""),
        }
        reads = self._reads(blade.code, blade.catalog_command, blade.read_command)
        return (
            _form(template, inspected)
            | (reads if kind == "python" else {"reads": []})
            | {
                "name": blade.name,
                "description": blade.description,
                "tags": blade.tags,
                "colour": self._colours.colour_of(blade.name) if self._colours is not None else None,
                "summary": self._blades.summary(blade),
            }
        )

    def _check(self, body: Any) -> None:
        if not isinstance(body, dict):
            raise BladeError("Send the connection as a JSON object.")
        if not rules.is_connection(str(body.get("kind", "")), body.get("template")):
            raise BladeError(
                "A connection is made from a database, file or key vault starter, or from your own "
                'Python (template "python"). Other code is saved as a blade.'
            )
        typed = body.get("secrets")
        only = next((t for t in self._templates if t.id == body.get("template")), None)
        if (
            isinstance(typed, dict)
            and any(typed.values())
            and only
            and only.secrets_from == dataverse.VAULT_ONLY
        ):
            # Its app registration's client secret is a key vault's secret, never typed into the app.
            raise BladeError(
                f"A {only.label} connection's secret comes from a key vault (or an environment variable), "
                "never typed here: point it at the vault's entry (connections_password_source)."
            )

    async def save(self, body: Any, previous: str | None, who: str = "user") -> dict[str, Any]:
        self._check(body)
        sent = None
        if isinstance(body, dict) and "colour" in body:
            body = dict(body)
            raw = body.pop("colour")
            sent = self._colours.check(raw) if self._colours is not None and raw is not None else None
        saved = await self._blades.save(body, previous, who)
        if self._colours is not None:
            # This computer's colours.toml: a new connection's next free colour, a renamed one's kept.
            self._colours.saved(str(saved["name"]), previous, sent)
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
        only: no value is read or sent. `{"named": ["Sql--Password"]}`: those names' variables alone (a name
        typed into the form: nothing runs, the one rule names it)."""
        if isinstance(body, dict) and isinstance(body.get("named"), list):
            return {"names": rules.vault_names(body["named"])}
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

    async def read_draft(self, body: Any, place: dict[str, str], limit: int) -> dict[str, Any]:
        """A table's first rows from a Python connection not saved yet (Add API's Try it), with the
        passwords typed for it: {"columns", "rows", "total"}. Nothing is saved."""
        self._check(body)
        answer = await self._blades.read_draft(body, place, limit)
        read = answer["table"]
        rows = [[_plain(v) for v in r.values()] for r in read.to_pylist()]
        return {"columns": [str(c) for c in read.column_names], "rows": rows, "total": answer.get("total")}

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
        if self.variable_check is not None and isinstance(body.get("code"), str):
            self.variable_check.check_code(body["code"], str(body.get("name") or "the connection"))
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
        if not place["schema"] and blade.dialect == powerbi.DIALECT:
            # A Power BI workspace's table lives in one of its datasets: named as the schema or as dataset.
            place["schema"] = str(where.get("dataset") or "")
        return blade, str(kind), place

    async def write(self, name: str, body: Any, who: str) -> dict[str, Any]:
        """sab.write for the agent (connections_write): rows (records, or an open table by its name: its
        grid's view) written to a connection's table through the adapter, in a child process. A dry run
        counts and writes nothing; the agent's write to the live source waits for the user's Allow."""
        table, mode, key, dry_run = write_capability.write_request(body)
        blade = self._blades.get(name)
        if not rules.has_catalog(rules.connection_kind(blade.kind, blade.template)):
            raise BladeError(f"{blade.name} has no tables to write to.")
        request: dict[str, Any] = {"table": table, "mode": mode, "key": key, "dry_run": dry_run}
        count = "no rows"  # a truncate's: the table cleared
        if isinstance(body.get("from_table"), str) and body.get("rows") is None:
            if self.open_view is None:
                raise BladeError("Writing an open table needs the open tables.")
            request["ipc"] = base64.b64encode(await self.open_view(body["from_table"])).decode("ascii")
            count = f"every row of {body['from_table']}"
        elif body.get("rows") is not None:
            request["records"] = body["rows"]
            count = f"{len(body['rows']):,} row{'' if len(body['rows']) == 1 else 's'}"
        if who == "agent" and not dry_run:
            if self.approvals is None or not await self.approvals.ask(
                blade.name, "write_connection", f"Write {count} to {table} on {blade.name} ({mode})"
            ):
                raise Refused(f"The user declined (or did not answer): nothing was written to {table}.")
        return await self._blades.write(blade, request)

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
            # Its connection kept with it: the project reads it again through the connection (its path
            # from the connection's own code, a ${NAME} in it resolved on each computer), not this path.
            where = (place["database"], place["schema"], place["table"])
            return await self._tables.load_file(dataset, path, sheet, who, blade.name, where)
        if not place["table"]:
            raise ValueError("Name the table to open.")
        read = await self.read_table(blade, kind, place, every, body)
        named = body.get("as") if isinstance(body, dict) else None  # a caller's own name for the grid
        stored = await self._tables.store(
            named.strip() if isinstance(named, str) and named.strip() else read.dataset,
            read.table, who, read.opened, read.connection, read.sql, read.dax, read.code,
            read.place,
        )  # fmt: skip
        return stored | {"shown": read.shown, "total": read.total}

    async def read_table(
        self, blade: Blade, kind: str, place: dict[str, str], every: bool, body: Any
    ) -> TableRead:
        """A database connection's table read (its first Rows to open rows, or every row), not yet a grid:
        its rows, how many the source holds, the name it opens under and how a notebook reads it again."""
        # Every row: asked for once (the grid's Load all rows) or always (the connection's Load all rows: 0).
        limit = None if every or blade.row_limit == 0 else (blade.row_limit or rules.DEFAULT_OPEN_ROWS)
        # Dataverse saved for its Web API reads through it; a Dataverse on its SQL endpoint (the default
        # since 2026-11-17, the owner: "Dataverse tds is the only method I like here") is a database.
        reads = _web_api(blade) or lakes.is_kind(blade.dialect)
        where = (place["database"], place["schema"], place["table"])
        if kind == "python" or reads:
            # The user's own Python reads it (Read a table), or Dataverse's own read: the first rows,
            # and the count it gave.
            answer = await self._blades.read(blade, place, limit, body)
            table, total = answer["table"], answer.get("total")
            shown = int(table.num_rows)
            opened = (
                Opened(blade.name, place["database"], place["schema"], place["table"], shown, int(total))
                if limit is not None and isinstance(total, int) and total > shown
                else None
            )
            schema = "" if _web_api(blade) else place["schema"]  # Dataverse's one schema needs no naming
            again = python_connections.read_call(blade.name, schema, place["table"])
            # A sheet of a workbook (Budget.xlsx/Summary) opens under its own name.
            dataset = self._grid_name(rules.dataset_name(place["table"].rsplit("/", 1)[-1]), blade.name)
            return TableRead(dataset, table, opened, shown, total, blade.name, code=again, place=where,
                             how=str(answer.get("read_with") or ""))  # fmt: skip
        sql = select_sql(blade.dialect, place["database"], place["schema"], place["table"], [], limit)
        count = (
            None
            if every
            # SQL Server: the rows sys.partitions holds, not a COUNT(*) over the table (domain/sql_server.py)
            else sql_server.count_sql(place["schema"], place["table"])
            if blade.dialect == sql_server.DIALECT and not place["database"]
            else count_sql(blade.dialect, place["database"], place["schema"], place["table"])
        )
        dax = blade.dialect == powerbi.DIALECT
        within = place["schema"] if dax else ""  # a Power BI workspace: the table's dataset
        try:
            read = _adapter_read(blade, place, limit, count is not None)
            answer = await self._blades.rows(blade, sql, count, body, within, read)
        except Exception as error:
            if not dax or within or "name the one to read" not in str(error):
                raise
            # The connection's own words name its code's argument; say how to name it here.
            raise type(error)(
                f"{blade.name} is a Power BI workspace with several datasets: name the one that holds "
                f"{place['table']} as dataset (or schema). connections_datasets lists them. {error}"
            ) from None
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
        dataset = self._grid_name(dataset, blade.name)
        origin = powerbi.joined_name(blade.name, within)  # a notebook reads it again: sab.dax(origin, sql)
        # The table came whole: the notebook reads it whole again (no LIMIT), so a run next month, with
        # more rows than Rows to open, is not cut without a word. A table that was cut keeps its LIMIT,
        # as the grid shows it.
        whole = limit is not None and isinstance(total, int) and total <= shown
        again = select_sql(blade.dialect, place["database"], place["schema"], place["table"], [], None)
        query = again if whole else sql
        return TableRead(dataset, table, opened, shown, total, origin, query, dax, place=where)

    async def read_query(self, name: str, sql: str, body: Any = None) -> TableRead:
        """A query of the user's run on a connection (in its own SQL; DAX on a Power BI workspace's
        dataset, named by `body`'s "dataset"), every row it answers: a table's connection swapped
        (services/connection_swap.py)."""
        blade = self._blades.get(name)
        kind = rules.connection_kind(blade.kind, blade.template)
        if kind != "database" or _web_api(blade):
            raise BladeError(f"{blade.name} does not run SQL: pick one of its tables instead.")
        dax = blade.dialect == powerbi.DIALECT
        given = body if isinstance(body, dict) else {}
        within = str(given.get("dataset") or "") if dax else ""
        if dax and not within:
            raise ValueError("Name the Power BI dataset the query runs on: dataset.")
        answer = await self._blades.rows(blade, sql, None, given, within)
        table = answer["table"]
        if table.num_columns == 0:
            raise BladeError("The query answered no columns, so there is nothing to show.")
        origin = powerbi.joined_name(blade.name, within) if dax else blade.name
        shown = int(table.num_rows)
        return TableRead("", table, None, shown, shown, origin, sql, dax)

    async def use_sql_endpoint(self, name: str, who: str) -> dict[str, Any]:
        """A Dataverse connection saved for its Web API moved to its SQL endpoint: its tables listed by the
        endpoint's catalog and read with T-SQL from now on (the card's "Web API (switch to the SQL
        endpoint)"). Its code, sign-in and passwords stay as they are."""
        blade = self._blades.get(name)
        if not dataverse.is_dataverse(blade.dialect):
            raise BladeError(f"{blade.name} is not a Dataverse connection.")
        if not _web_api(blade):
            return {"name": blade.name, "changed": False}
        body = blade.to_json() | {"catalog": {"language": "sql", "command": dataverse.SQL_CATALOG}}
        saved = await self.save(body, blade.name, who)
        return {"name": saved["name"], "changed": True}

    async def update_driver(self, name: str, who: str) -> dict[str, Any]:
        """A SQL Server or Azure SQL connection whose code is the app's earlier one (pyodbc and an ODBC
        driver) made again on Microsoft's mssql-python with the same settings (the card's Update to the
        new driver; domain/sql_server.py upgraded). Its sign-in, settings and password sources stay; a
        connection of the user's own code is never rewritten (refused)."""
        blade = self._blades.get(name)
        if not sql_server.is_old(blade.code):
            if sql_server.is_robust(blade.code):
                return {"name": blade.name, "changed": False}
            raise BladeError(
                f"{blade.name}'s code is not the SQL Server code the app made, so it is left as it is: "
                "change its driver in its file."
            )
        body = blade.to_json() | {"code": sql_server.upgraded(blade.code)}
        saved = await self.save(body, blade.name, who)
        return {"name": saved["name"], "changed": True, "driver": "mssql-python"}

    async def read_for_query(
        self, name: str, place: dict[str, str], pushed: table_rules.Pushed, most: int
    ) -> TableRead:
        """A connection's table read for a DuckDB query (services/connection_tables.py): every row the
        query needs, never the connection's Rows to open. The columns and filters `pushed` are sent to a
        SQL source; the source's count (with them) is asked first, and more than `most` rows is refused
        with how to narrow it. DAX reads the table whole; a Python connection and Dataverse's Web API read
        at most `most` + 1 rows, refused past `most`; a file is read whole."""
        blade, kind, full = self._target(name, place)
        if kind == "file":
            return await self.read_place(name, place)
        table_name = full["table"]
        if not table_name:
            raise ValueError("Name the table to read.")
        own = lakes.is_kind(blade.dialect)
        if kind == "python" or _web_api(blade) or own:
            asked = pushed.limit if pushed.limit is not None else most + 1
            # A lake's or SharePoint's own read takes the query's columns and filters (DuckDB's pushdown,
            # Graph's $select and $filter); DuckDB applies the filters again.
            sent = (pushed.columns, pushed.filters) if own else ((), ())
            answer = await self._blades.read(blade, full, asked, {}, *sent)
            table, total = answer["table"], answer.get("total")
            seen = max(int(table.num_rows), total if isinstance(total, int) else 0)
            if pushed.limit is None and seen > most:
                raise BladeError(
                    table_rules.too_many(blade.name, table_name, seen, most, bool(pushed.filters))
                )
            again = python_connections.read_call(
                blade.name, "" if _web_api(blade) else full["schema"], table_name
            )
            shown = int(table.num_rows)
            how = str(answer.get("read_with") or "")
            return TableRead(table_name, table, None, shown, shown, blade.name, code=again, how=how)
        dax = blade.dialect == powerbi.DIALECT
        within = full["schema"] if dax else ""
        where = (full["database"], full["schema"], table_name)
        if dax:  # the whole table, as DAX reads it
            select = select_sql(blade.dialect, *where, [], None)
            count: str | None = count_sql(blade.dialect, *where)
        else:
            picked = list(pushed.columns)
            select = table_rules.with_filter(
                select_sql(blade.dialect, *where, picked, pushed.limit), pushed.where
            )
            count = (
                None
                if pushed.limit is not None
                else table_rules.with_filter(count_sql(blade.dialect, *where), pushed.where)
            )
        if count is not None:
            counted = (await self._blades.rows(blade, count, None, {}, within))["table"]
            values = counted.to_pylist()
            n = int(next(iter(values[0].values()))) if values and values[0] else 0
            if n > most:
                raise BladeError(table_rules.too_many(blade.name, table_name, n, most, bool(pushed.where)))
        parts = (("filters", pushed.where), ("columns", pushed.columns), ("limit", pushed.limit is not None))
        folded = [] if dax else [part for part, on in parts if on]  # what the SELECT sent to the source
        read = await self._blades.rows(blade, select, None, {}, within, target=table_name, folded=folded)
        table = read["table"]
        shown = int(table.num_rows)
        origin = powerbi.joined_name(blade.name, within)
        return TableRead(table_name, table, None, shown, shown, origin, select, dax, place=where)

    async def read_place(self, name: str, place: dict[str, str], every: bool = False) -> TableRead:
        """One of a connection's tables read, not kept (the tables contract's read, services/
        connection_tables.py): a database's (Power BI's, Dataverse's) or a Python connection's first Rows
        to open rows (every row with `every`), a file connection's file or sheet whole."""
        if self._tables is None:
            raise BladeError("Reading a table needs the datasets.")
        blade, kind, _ = self._target(name, place)
        if kind == "file":
            reached = await self._blades.rows(blade, None, None, {})
            path, sheet = rules.file_to_open(blade.template, str(reached["path"]), place.get("table", ""))
            if blade.template == "excel" and sheet is None:
                sheets = await self._tables.sheets(path)
                sheet = sheets[0] if sheets else None
            table = await self._tables.read_file(path, sheet)
            shown = int(table.num_rows)
            where = ("", place.get("schema", ""), place.get("table", ""))
            return TableRead(rules.dataset_name(place.get("table") or blade.name), table, None, shown, shown,
                             blade.name, place=where)  # fmt: skip
        full = {k: str(place.get(k) or "") for k in ("database", "schema", "table")}
        return await self.read_table(blade, kind, full, every, {})

    def blade(self, name: str) -> tuple[Blade, str]:
        """A saved connection and its kind (database, file, python, vault)."""
        blade = self._blades.get(name)
        return blade, str(rules.connection_kind(blade.kind, blade.template) or "")

    def _grid_name(self, name: str, connection: str) -> str:
        """Its own name, or the connection's before it when that name is open from elsewhere."""
        opened_from = self._tables.opened_from(name) if self._tables is not None else None
        return rules.table_grid_name(name, connection, opened_from)

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
        if kind == "python" or _web_api(blade) or lakes.is_kind(blade.dialect):
            read = (await self._blades.read(blade, place, rules.PREVIEW_ROWS, body))["table"]
            return {"columns": list(read.column_names), "rows": [list(r.values()) for r in read.to_pylist()]}
        sql = select_sql(
            blade.dialect, place["database"], place["schema"], place["table"], [], rules.PREVIEW_ROWS
        )
        within = place["schema"] if blade.dialect == powerbi.DIALECT else ""
        table = (await self._blades.rows(blade, sql, None, body, within))["table"]
        return {"columns": list(table.column_names), "rows": [list(r.values()) for r in table.to_pylist()]}

    async def tables(self, name: str, body: Any, who: str) -> dict[str, Any]:
        """A connection from the user's own Python: run its List the tables now, load the catalog it
        returns, and answer the tables it named, each with its columns."""
        blade = self._blades.get(name)
        if rules.connection_kind(blade.kind, blade.template) != "python":
            raise BladeError(
                f"{blade.name} is not a connection from your own Python: its tables are in its catalog."
            )
        if not blade.has_catalog:
            raise BladeError(f"{blade.name} has no List the tables: open the connection and fill it in.")
        answer = await self._blades.listed(blade, body, who)
        return {
            "catalog": answer["catalog"],
            "tables": python_connections.tables_json(answer["columns"], answer["rows"]),
        }

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

    async def _foreign_keys(self, name: str, body: Any, who: str) -> dict[str, Any]:
        """A SQL Server or Azure SQL database's foreign keys (sys.foreign_keys; a composite key whole)
        merged into the current model, as a Power BI dataset's relationships are."""
        if self._models is None:
            raise BladeError("Importing relationships needs the relationship model.")
        blade = self._blades.get(name)
        answer = await self._blades.queries(blade, sql_server.RELATIONSHIP_QUERIES, body)
        try:
            model = sql_server.relationships_model(blade.name, list(answer["results"]))
        except sql_server.SqlServerError as error:
            raise BladeError(str(error)) from None
        if not model.relationships:
            raise BladeError(f"{blade.name} has no foreign keys to import.")
        merged = await self._models.apply(model, who)
        return {
            "dataset": "",
            "model": {k: v for k, v in merged.items() if k != "changed"},
            "changed": merged.get("changed", []),
            "imported": [r.to_json() for r in model.relationships],
            "tables": sorted(model.tables()),
            "skipped": 0,
            "skipped_why": "",
        }

    async def import_relationships(self, name: str, body: Any, who: str) -> dict[str, Any]:
        """Read one dataset's relationships (DAX's INFO functions, on the connection) and merge them
        into the current model, the tables named as they open as grids: the ERD and the Key
        Finder's known joins then show them. `{"dataset"}` names it; a workspace with one dataset
        needs none. Answers the model, what the merge changed, and what came."""
        if self._models is None:
            raise BladeError("Importing relationships needs the relationship model.")
        if self._blades.get(name).dialect == sql_server.DIALECT:
            return await self._foreign_keys(name, body, who)
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
            "skipped_why": (
                "Relationships to the date tables Power BI makes by itself (LocalDateTable_..., "
                "DateTableTemplate_...) for its automatic date hierarchies; they are not the model's own."
                if skipped
                else ""
            ),
        }


class Colours(Protocol):
    def check(self, colour: Any) -> str | None: ...

    def saved(self, name: str, previous: str | None, sent: str | None) -> None: ...

    def colour_of(self, name: str) -> str | None: ...


class LoadedCatalogs(Protocol):
    """The loaded catalogs (services/catalogs.py): a Power BI workspace's datasets are its schemas."""

    async def shared_tables(self, name: str) -> set[str]: ...

    async def schema_names(self, name: str) -> list[dict[str, Any]] | None: ...


@dataclass(frozen=True)
class TableRead:
    """A connection's table read, before it is a grid."""

    dataset: str  # the name it opens under
    table: Any
    opened: Opened | None  # its first rows only: how many the source holds
    shown: int
    total: int | None
    connection: str  # the connection's name (a Power BI workspace's with its dataset: Finance/Sales)
    sql: str = ""
    dax: bool = False
    code: str = ""  # the Python that reads it again (a connection with no SQL)
    place: tuple[str, str, str] | None = None
    how: str = ""  # how the connection's own code read it (a lake's: delta_scan, deltalake, its log...)


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
        code: str = "",
        place: tuple[str, str, str] | None = None,
    ) -> dict[str, Any]: ...

    async def load_file(
        self,
        name: str,
        path: str,
        sheet: str | None,
        who: str,
        connection: str = "",
        place: tuple[str, str, str] | None = None,
    ) -> dict[str, Any]: ...

    def opened_from(self, name: str) -> str | None:
        """Where the open table of this name came from: its connection ("" when not a connection's;
        None when no table of that name is open)."""
        ...

    async def sheets(self, path: str) -> list[str]: ...

    async def peek(self, path: str, sheet: str | None, rows: int) -> dict[str, Any]: ...

    async def read_file(self, path: str, sheet: str | None) -> Any: ...


class CodeCheck(Protocol):
    def check_code(self, code: str, where: str) -> None: ...


# The connections the adapter reads itself (Plans/adapter.plan.md): DuckDB, and each SQL dialect it folds a
# plan into (adapter.DIALECTS). Sybase speaks T-SQL without OFFSET ... FETCH, so it keeps its own SQL.
ADAPTER_DIALECTS = ("duckdb", "postgres", "mysql", "sqlserver", "oracle", "sqlite", "snowflake", "trino")
NOT_ADAPTED = ("sybase",)  # starters whose dialect is shared but whose SQL is older


def _adapter_read(
    blade: Blade, place: dict[str, str], limit: int | None, counted: bool
) -> dict[str, Any] | None:
    """What the adapter reads for Open as grid ({"table", "dialect", "plan", "count"}), for a connection whose
    dialect it reads; None for the others (and a table named with its database), which send their SQL."""
    if blade.dialect not in ADAPTER_DIALECTS or blade.template in NOT_ADAPTED or place.get("database"):
        return None
    schema = place["schema"]
    plain = schema == "" or (blade.dialect == "duckdb" and schema == "main")
    table = place["table"] if plain else f"{schema}.{place['table']}"
    return {"table": table, "dialect": blade.dialect, "plan": {"limit": limit}, "count": counted}


def _web_api(blade: Blade) -> bool:
    """A Dataverse connection saved for its Web API (its catalog from the metadata), not its SQL endpoint."""
    return dataverse.is_dataverse(blade.dialect) and not dataverse.on_sql_endpoint(blade.catalog_language)


def _plain(value: Any) -> Any:
    """A cell as JSON holds it: text for what JSON has no word for, nothing for a missing number."""
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return value if value == value and abs(value) != float("inf") else None
    return str(value)
