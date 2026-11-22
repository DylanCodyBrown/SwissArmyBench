"""The endpoint wizard of the project's local sandbox API (the owner, 2026-11-21; domain/api_patterns.py has
the patterns): a pattern over a sandbox table, appended to API.py. Split from services/local_api.py (craft
review 2026-11-22), which hosts the API and hands the wizard what it asks of API.py.

  pattern_list  the patterns as data: each one's question, its own steps, the widgets that pair with it
  plan          the one read (the agent's too): the sandbox's tables, the patterns ranked by a table's shape,
                a pattern's steps and the code as it would be added; nothing written
  scaffold      a pattern's endpoints appended to API.py (made first when there is none), or a dry run
  paired        each endpoint a pattern made, with the widgets that pair with it (the Canvas reads it)
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from swissarmybench.domain import api_patterns as pattern_rules
from swissarmybench.domain import api_scaffold as scaffold_rules
from swissarmybench.domain import local_api as rules
from swissarmybench.services.workspace import Conflict, NotFound


class ApiFile(Protocol):
    """What the wizard asks of the local sandbox API (services/local_api.py LocalApi)."""

    async def sandbox_tables(self) -> list[dict[str, Any]]: ...

    def text(self) -> str | None: ...

    async def new(self, body: Any = None, who: str = "user") -> dict[str, Any]: ...

    async def append(self, before: str, written: str, who: str, **facts: Any) -> None: ...

    async def set_key(self, body: Any, who: str = "user") -> dict[str, Any]: ...

    async def state(self, body: Any = None, who: str = "user", full: bool = False) -> dict[str, Any]: ...


def data_words(name: str, client: dict[str, Any] | None) -> str:
    """An endpoint's data in words: "Mock of Warehouse (sqlserver)", or why there is none yet."""
    if client is None:
        return f"{name}: no table of it in the sandbox yet (Add to sandbox)"
    if client.get("kind") == "duckdb":
        return "The sandbox (plain DuckDB)"
    what = client.get("template") or client.get("dialect") or client.get("kind")
    return f"Mock of {client.get('connection') or name} ({what})"


def _defined(text: str) -> list[str]:
    """The top-level names API.py defines (a CRUD set never takes one)."""
    return re.findall(r"^(?:def|class|async def)\s+([A-Za-z_]\w*)", text, re.M)


class EndpointWizard:
    def __init__(self, api: ApiFile, patterns: pattern_rules.Registry | None = None) -> None:
        self._api = api
        self.patterns = patterns or pattern_rules.Registry()

    @staticmethod
    def _target(table: dict[str, Any]) -> pattern_rules.Target:
        """A sandbox table as the patterns read it: its columns, its row count, how it is reached (the
        connection it is mocked as, its schema there)."""
        client = table.get("client") or {}
        place = (table.get("source") or {}).get("place") or {}
        kind = str(client.get("kind") or "duckdb")
        source = scaffold_rules.Source(
            kind if kind in ("duckdb", "dataverse", "sharepoint") else "database",
            str(client.get("connection") or "Sandbox") if kind != "duckdb" else "Sandbox",
            str(client.get("dialect") or "duckdb"),
            str(place.get("schema") or ""),
        )
        rows = table.get("rows")
        return pattern_rules.Target(
            str(table["name"]),
            tuple(table.get("columns") or ()),
            source,
            rows if isinstance(rows, int) else None,
        )

    @staticmethod
    def _named(listed: list[dict[str, Any]], wanted: Any) -> dict[str, Any] | None:
        name = str(wanted or "").strip().casefold()
        return next((t for t in listed if str(t["name"]).casefold() == name), None)

    def _taken(self, text: str) -> pattern_rules.Taken:
        api = rules.parse(text)
        names = [e.name for e in api.endpoints] + list(api.models) + _defined(text)
        return pattern_rules.Taken(tuple(names), tuple(e.path for e in api.endpoints))

    async def pattern_list(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        """The patterns as data: each one's question, its own steps, the widgets that pair with it."""
        return {"patterns": self.patterns.listed()}

    async def plan(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        """The wizard's one read (the agent's too): {"table"?, "pattern"?, "fields"?, "other"?}. With no
        table: the sandbox's tables. With a table: every pattern ranked by its shape, each with one sentence
        why. With a pattern too: that pattern's own steps (the columns each offers, its value: the one sent,
        else what the shape suggests), and the code as it would be added, or the one thing still missing.
        Nothing is written."""
        given = body if isinstance(body, dict) else {}
        listed = await self._api.sandbox_tables()
        tables = [
            {"name": t["name"], "rows": t.get("rows"), "columns": t.get("columns") or [],
             "data": data_words(str(t["name"]), t.get("client") or {"kind": "duckdb"})}
            for t in listed
        ]  # fmt: skip
        answer: dict[str, Any] = {"tables": tables, "patterns": self.patterns.listed()}
        if not str(given.get("table") or "").strip():
            return answer
        table = self._named(listed, given.get("table"))
        if table is None:
            raise NotFound(f"The sandbox has no table named {given.get('table')}: Add to sandbox first.")
        target = self._target(table)
        others = [self._target(t) for t in listed]
        answer |= {"table": target.name, "ranked": self.patterns.ranked(target, others)}
        if not str(given.get("pattern") or "").strip():
            return answer
        pattern = self.patterns.get(given.get("pattern"))
        other = None
        if pattern.tables == 2:
            second = self._named(listed, given.get("other"))
            other = self._target(second) if second is not None else pattern_rules.partner(target, others)
        elif given.get("other"):  # a second table a one-table pattern may take (an action's log)
            second = self._named(listed, given.get("other"))
            other = self._target(second) if second is not None else None
        fields = given.get("fields") if isinstance(given.get("fields"), dict) else {}
        answer["plan"] = self.patterns.planned(pattern.id, target, fields, other)
        answer["others"] = [t["name"] for t in tables if t["name"] != target.name]
        text = self._api.text() or rules.scaffold("api")
        try:
            made = self.patterns.make(pattern.id, target, fields, self._taken(text), other)
        except scaffold_rules.ScaffoldError as error:
            return answer | {"problem": str(error), "code": "", "added": []}
        made.text = scaffold_rules.fitted(text, made.text)
        needs = scaffold_rules.imports_missing(text, made.text)
        paired = [
            w | {"function": name} for name in made.added for w in self.patterns.pairings(pattern.id, name)
        ]
        code = {"problem": None, "code": made.text.lstrip("\n"), "imports": needs, "added": made.added}
        return answer | code | {"streams": made.streams, "words": made.words, "paired": paired}

    async def scaffold(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"table", "pattern"? (table), "fields"?, "other"? (Reconcile's second table), "dry_run"?}: a
        pattern's endpoints over a sandbox table appended to API.py (domain/api_patterns.py); API.py made
        first when the project has none. "dry_run": the code and its endpoints, nothing written. The older
        {"table", "key"} is the Table pattern with that key."""
        given = body if isinstance(body, dict) else {}
        wanted = str(given.get("table") or "").strip()
        listed = await self._api.sandbox_tables()
        table = self._named(listed, wanted)
        if table is None:
            raise NotFound(f"The sandbox has no table named {wanted}: Add to sandbox first.")
        pattern = self.patterns.get(given.get("pattern"))
        fields = dict(given.get("fields") or {}) if isinstance(given.get("fields"), dict) else {}
        if given.get("key") and "key" not in fields:
            fields["key"] = given["key"]
        target = self._target(table)
        other = None
        if pattern.tables == 2:
            second = self._named(listed, given.get("other"))
            if second is None:
                raise NotFound(f"{pattern.label} compares two sandbox tables: name the second one (other).")
            other = self._target(second)
        elif given.get("other"):  # a second table a one-table pattern may take (an action's log)
            second = self._named(listed, given.get("other"))
            if second is None:
                raise NotFound(f"The sandbox has no table {given.get('other')} for {pattern.label}.")
            other = self._target(second)
        dry = bool(given.get("dry_run"))
        if self._api.text() is None and not dry:
            await self._api.new(None, who)
        text = self._api.text() or rules.scaffold("api")
        made = self.patterns.make(pattern.id, target, fields, self._taken(text), other)
        block = scaffold_rules.fitted(text, made.text)
        needs = scaffold_rules.imports_missing(text, block)
        if dry:
            return {"dry_run": True, "pattern": pattern.id, "code": block.lstrip("\n"), "imports": needs,
                    "added": made.added, "streams": made.streams, "words": made.words}  # fmt: skip
        before = text
        text, needs = scaffold_rules.with_imports(text, needs)
        written = text.rstrip("\n") + "\n" + ("\n" + needs if needs else "") + block
        await self._api.append(before, written, who, table=table["name"], pattern=pattern.id)
        note = ""
        if made.key and not any(c.get("key") for c in table["columns"]):
            try:  # the endpoint's key: the sandbox keeps it too
                await self._api.set_key({"table": table["name"], "key": made.key}, who)
            except (ValueError, LookupError, Conflict) as error:
                note = f"{table['name']} has no primary key in the sandbox: {error}"
        state = await self._api.state()
        by = {e["name"]: e for e in state.get("endpoints") or []}
        paired = [
            w | {"endpoint": f"{by[name]['method']} {by[name]['path']}"}
            for name in made.added
            if name in by
            for w in self.patterns.pairings(pattern.id, name)
        ]
        line = text.count("\n") + 2 + (needs.count("\n") + 1 if needs else 0)
        done = state | {"added": [n for n in made.added if n in by], "line": line, "pattern": pattern.id,
                        "paired": paired}  # fmt: skip
        return done | ({"note": note} if note else {})

    def paired(self) -> list[dict[str, Any]]:
        """Each endpoint a pattern made, with the widgets that pair with it ("GET /orders": api_table's
        endpoint): what a widget dropped on the Canvas wires itself to (the Streamlit extension reads it)."""
        text = self._api.text()
        if text is None:
            return []
        try:
            api = rules.parse(text)
        except Exception:  # API.py's own trouble: nothing to pair
            return []
        found: list[dict[str, Any]] = []
        for e in api.endpoints:
            made_by, of = pattern_rules.pattern_at(text, e.line)
            answer = rules.answer_fields(e, api.models)
            for w in self.patterns.pairings(made_by, e.name) if made_by else []:
                # A property the pairing sets to a field of the answer (a select's column: the label).
                places = dict(w.get("sets") or {})
                sets = {p: answer[i] for p, i in places.items() if 0 <= int(i) < len(answer)}
                w = {k: v for k, v in w.items() if k != "sets"} | ({"sets": sets} if sets else {})
                found.append(w | {"endpoint": f"{e.method} {e.path}", "pattern": made_by, "of": of})
        return found
