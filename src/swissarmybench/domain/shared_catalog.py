"""The shared catalog (the owner, 2026-11-17: "a shared meta store on GitHub ... any connection made in a
project would save to a centralized catalog it would sync and prune in realtime"; "you point the app to a
GitHub meta store folder on your machine. You push and pull as projects are created").

  where       the library's catalog/ folder: one file per connection, catalog/<connection>.json (the
              connection's name made file-safe as a blade's file is). The library folder is the user's Git
              working copy: the app writes files and reads what the user's pulls bring; it never runs git
  what        names, types, keys and usage: each table's database, schema and name, its columns (name, type,
              nullable, key), its primary key, the relationships whose ends are its tables, `used_by` (the
              project folders' names that use it) and its state (present, or gone since a date). Never a
              number or value from the data (no row counts, no profiles, no relationship evidence or note),
              never a secret, password, token or row
  stable      sorted keys, one table per block, a column or relationship per line, no time that changes on
              every save (`gone_since` is a date, set when the table goes): the same catalog is the same
              bytes, so a save that changes nothing changes no byte and two people's additions merge
  listing     a successful listing marks what it lists present and what it does not gone (since today); a
              table gone for PRUNE_DAYS (settings.py) is removed. A failed listing changes nothing
  model       the relationships in use and primary keys, added to the tables they name; a relationship the
              user deleted taken out (a project closing takes nothing out: its relationships are still true)
  used_by     the open project's name added to the tables it uses and taken from the ones it no longer uses;
              other projects' names stay as they are (they are someone else's to change)
  a bad file  conflict markers or JSON that does not parse: said with the file's name, never written over

Pure rules: no I/O, no clock (today's date is given).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from swissarmybench.domain.blades import file_name as blade_file_name
from swissarmybench.domain.connections import dataset_name
from swissarmybench.domain.relationships import Model, Relationship, from_connection, named_in

FORMAT: int = 1
FOLDER: str = "catalog"
SUFFIX: str = ".json"
PRESENT: str = "present"
GONE: str = "gone"
MAX_TYPE: int = 120  # a column's type as the source says it, cut (a type is a name, never a value)
_MARKER = re.compile(r"^(<{7}|={7}|>{7}|\|{7})(\s|$)", re.MULTILINE)


class CatalogFileError(ValueError):
    """A catalog file that cannot be read (a merge left its markers, or the JSON is broken): said with the
    file's name, and never written over until it reads."""


@dataclass(frozen=True)
class Column:
    name: str
    type: str = ""
    nullable: bool | None = None

    def to_json(self, key: str) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            **({"nullable": self.nullable} if self.nullable is not None else {}),
            **({"key": key} if key else {}),
        }


@dataclass(frozen=True)
class Join:
    """A relationship as the catalog keeps it: its ends and kind (no note, no evidence: those can carry
    numbers from the data)."""

    from_table: str
    from_columns: tuple[str, ...]
    to_table: str
    to_columns: tuple[str, ...]
    kind: str = "many-to-one"
    active: bool = True

    @property
    def key(self) -> tuple[str, tuple[str, ...], str, tuple[str, ...]]:
        return (self.from_table.casefold(), self.from_columns, self.to_table.casefold(), self.to_columns)

    def to_json(self) -> dict[str, Any]:
        return {
            "from": self.from_table,
            "from_columns": list(self.from_columns),
            "to": self.to_table,
            "to_columns": list(self.to_columns),
            "kind": self.kind,
            **({"active": False} if not self.active else {}),
        }

    @staticmethod
    def of(r: Relationship) -> Join:
        return Join(r.from_table, r.from_columns, r.to_table, r.to_columns, r.kind, r.active)


@dataclass(frozen=True)
class Table:
    name: str
    schema: str = ""
    database: str = ""
    kind: str = "table"
    columns: tuple[Column, ...] = ()
    primary_key: tuple[str, ...] = ()
    relationships: tuple[Join, ...] = ()
    used_by: tuple[str, ...] = ()
    state: str = PRESENT
    gone_since: str = ""

    @property
    def key(self) -> str:
        return table_key(self.database, self.schema, self.name)

    def names(self) -> set[str]:
        """What a model, a grid or a document may call it: its name, as a grid (Order_Lines), with its schema
        before it (dbo_Orders), in any case."""
        found = {self.name, dataset_name(self.name)}
        if self.schema:
            found |= {f"{self.schema}.{self.name}", dataset_name(f"{self.schema}_{self.name}")}
        return {n.casefold() for n in found}

    def to_json(self) -> dict[str, Any]:
        foreign = {c for j in self.relationships if _same(j.from_table, self) for c in j.from_columns}
        primary = set(self.primary_key)
        return {
            "name": self.name,
            "schema": self.schema,
            "database": self.database,
            "kind": self.kind,
            "columns": [
                c.to_json("primary" if c.name in primary else "foreign" if c.name in foreign else "")
                for c in self.columns
            ],
            "primary_key": list(self.primary_key),
            "relationships": [j.to_json() for j in self.relationships],
            "used_by": list(self.used_by),
            "state": self.state,
            **({"gone_since": self.gone_since} if self.gone_since else {}),
        }


@dataclass(frozen=True)
class Catalog:
    connection: str
    kind: str = ""  # how it lists its tables: database, powerbi, file... (connection_tables.tables_kind)
    template: str = ""  # its starter (postgres, sqlserver, ...)
    tables: dict[str, Table] = field(default_factory=dict)  # by table_key

    def to_json(self) -> dict[str, Any]:
        return {
            "format": FORMAT,
            "connection": self.connection,
            "kind": self.kind,
            "template": self.template,
            "tables": {k: self.tables[k].to_json() for k in sorted(self.tables)},
        }

    def summary(self) -> dict[str, Any]:
        present = [t for t in self.tables.values() if t.state == PRESENT]
        return {
            "connection": self.connection,
            "kind": self.kind,
            "template": self.template,
            "tables": len(present),
            "gone": len(self.tables) - len(present),
            "relationships": sum(len(t.relationships) for t in self.tables.values()),
            "used_by": sorted({p for t in self.tables.values() for p in t.used_by}),
        }


def table_key(database: str, schema: str, name: str) -> str:
    return ".".join(p for p in (database, schema, name) if p)


def file_name(connection: str) -> str:
    """catalog/<this>: the connection's name made file-safe as its blade file is (warehouse.json)."""
    return blade_file_name(connection).removesuffix(".blade.py") + SUFFIX


def _same(name: str, table: Table) -> bool:
    return name.casefold() in table.names()


# ===== the file =====


def _line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def render(catalog: Catalog) -> str:
    """The file's text: sorted keys, one table per block, one column and one relationship per line."""
    data = catalog.to_json()
    out = ["{"]
    head = [k for k in sorted(data) if k != "tables"]
    for k in head:
        out.append(f"  {_line(k)}: {_line(data[k])},")
    tables = data["tables"]
    if not tables:
        out.append('  "tables": {}')
    else:
        out.append('  "tables": {')
        keys = list(tables)
        for i, key in enumerate(keys):
            table = tables[key]
            out.append(f"    {_line(key)}: {{")
            fields = sorted(table)
            for j, name in enumerate(fields):
                value = table[name]
                comma = "," if j < len(fields) - 1 else ""
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    out.append(f"      {_line(name)}: [")
                    out += [
                        f"        {_line(v)}{',' if n < len(value) - 1 else ''}" for n, v in enumerate(value)
                    ]
                    out.append(f"      ]{comma}")
                else:
                    out.append(f"      {_line(name)}: {_line(value)}{comma}")
            out.append("    }" + ("," if i < len(keys) - 1 else ""))
        out.append("  }")
    out.append("}")
    return "\n".join(out) + "\n"


def parse(text: str, file: str = "") -> Catalog:
    """A catalog file read back; CatalogFileError (with the file's name) when it cannot be."""
    where = file or "a catalog file"
    if _MARKER.search(text):
        raise CatalogFileError(f"{where} has merge conflict markers in it: finish the merge, then save it.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise CatalogFileError(f"{where} does not read as JSON ({error.msg}, line {error.lineno}).") from None
    if not isinstance(data, dict) or not isinstance(data.get("connection"), str):
        raise CatalogFileError(f"{where} is not a catalog file (no connection named in it).")
    tables: dict[str, Table] = {}
    raw = data.get("tables")
    for entry in raw.values() if isinstance(raw, dict) else []:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            continue
        table = Table(
            name=entry["name"],
            schema=str(entry.get("schema") or ""),
            database=str(entry.get("database") or ""),
            kind=str(entry.get("kind") or "table"),
            columns=tuple(
                Column(
                    str(c["name"]),
                    str(c.get("type") or ""),
                    c["nullable"] if isinstance(c.get("nullable"), bool) else None,
                )
                for c in entry.get("columns") or []
                if isinstance(c, dict) and "name" in c
            ),
            primary_key=tuple(str(c) for c in entry.get("primary_key") or []),
            relationships=_sorted_joins(
                Join(
                    str(r["from"]),
                    tuple(str(c) for c in r.get("from_columns") or []),
                    str(r["to"]),
                    tuple(str(c) for c in r.get("to_columns") or []),
                    str(r.get("kind") or "many-to-one"),
                    r.get("active") is not False,
                )
                for r in entry.get("relationships") or []
                if isinstance(r, dict) and "from" in r and "to" in r
            ),
            used_by=tuple(sorted({str(p) for p in entry.get("used_by") or []}, key=str.casefold)),
            state=GONE if entry.get("state") == GONE else PRESENT,
            gone_since=str(entry.get("gone_since") or "") if entry.get("state") == GONE else "",
        )
        tables[table.key] = table
    return Catalog(data["connection"], str(data.get("kind") or ""), str(data.get("template") or ""), tables)


def _sorted_joins(joins: Iterable[Join]) -> tuple[Join, ...]:
    unique = {j.key: j for j in joins}
    return tuple(unique[k] for k in sorted(unique))


# ===== a listing =====


@dataclass(frozen=True)
class Listed:
    """One row a connection's listing gave: a table's column (column "" for a table with none listed)."""

    database: str
    schema: str
    table: str
    column: str = ""
    type: str = ""
    nullable: bool | None = None
    kind: str = "table"


def listed(catalog: Catalog, rows: Sequence[Listed], today: str, prune_days: int) -> Catalog:
    """A successful listing: what it lists is present (its columns as listed now), what it does not list is
    gone since today (kept as it was otherwise), and what has been gone `prune_days` is removed."""
    found: dict[str, tuple[Listed, list[Column]]] = {}
    for row in rows:
        if not row.table:
            continue
        key = table_key(row.database, row.schema, row.table)
        _, columns = found.setdefault(key, (row, []))
        if row.column and all(c.name != row.column for c in columns):
            columns.append(Column(row.column, str(row.type or "")[:MAX_TYPE], row.nullable))
    tables: dict[str, Table] = {}
    for key, (row, columns) in found.items():
        was = catalog.tables.get(key) or _by_name(catalog, row.table)
        base = was or Table(name=row.table)
        tables[key] = replace(
            base,
            name=row.table,
            schema=row.schema,
            database=row.database,
            kind=row.kind or "table",
            columns=tuple(columns),
            primary_key=tuple(c for c in base.primary_key if any(col.name == c for col in columns))
            or base.primary_key,
            state=PRESENT,
            gone_since="",
        )
    matched = {t.name.casefold() for t in tables.values()}
    for key, was in catalog.tables.items():
        if key in tables or (not was.schema and not was.database and was.name.casefold() in matched):
            continue  # listed now (a table the model named before a listing found its place)
        tables[key] = was if was.state == GONE else replace(was, state=GONE, gone_since=today)
    return prune(replace(catalog, tables=tables), today, prune_days)


def _by_name(catalog: Catalog, name: str) -> Table | None:
    """A table the model named before any listing (no schema, no database) that this listed one is."""
    for table in catalog.tables.values():
        if not table.schema and not table.database and table.name.casefold() == name.casefold():
            return table
    return None


def prune(catalog: Catalog, today: str, days: int) -> Catalog:
    """Without the tables gone `days` days or more."""
    now = date.fromisoformat(today)

    def stale(t: Table) -> bool:
        if t.state != GONE or not t.gone_since:
            return False
        try:
            return (now - date.fromisoformat(t.gone_since)).days >= days
        except ValueError:
            return False

    kept = {k: t for k, t in catalog.tables.items() if not stale(t)}
    return catalog if len(kept) == len(catalog.tables) else replace(catalog, tables=kept)


# ===== the model: keys and relationships =====


def _owner(catalog: Catalog, name: str, model: Model) -> Table | None:
    """This connection's table a model's table name is, when it is: by the model's recorded source (another
    connection's is never this one's), else by name."""
    said = model.sources.get(name, "")
    if said and not from_connection(said, catalog.connection):
        return None
    for table in sorted(catalog.tables.values(), key=lambda t: (t.state != PRESENT, t.key)):
        if _same(name, table):
            return table
    return None


def with_model(catalog: Catalog, model: Model) -> Catalog:
    """The model's primary keys and relationships added to this connection's tables (a table its source
    names that no listing has found yet is added by name). A relationship goes in its from-table's block,
    else its to-table's; the ones already kept stay."""
    tables = dict(catalog.tables)
    for name, said in sorted(model.sources.items()):
        if (
            from_connection(said, catalog.connection)
            and _owner(replace(catalog, tables=tables), name, model) is None
        ):
            made = Table(name=name)
            tables[made.key] = made
    current = replace(catalog, tables=tables)
    for name, key in sorted(model.keys.items()):
        owner = _owner(current, name, model)
        if owner is not None and key:
            tables[owner.key] = replace(tables[owner.key], primary_key=tuple(key))
    for r in model.relationships:
        owner = _owner(current, r.from_table, model) or _owner(current, r.to_table, model)
        if owner is None:
            continue
        held = tables[owner.key]
        tables[owner.key] = replace(held, relationships=_sorted_joins([*held.relationships, Join.of(r)]))
    return replace(catalog, tables=tables)


def without_joins(catalog: Catalog, removed: Iterable[Join]) -> Catalog:
    """The catalog without the relationships the user deleted."""
    gone = {j.key for j in removed}
    if not gone:
        return catalog
    tables = {
        k: replace(t, relationships=tuple(j for j in t.relationships if j.key not in gone))
        for k, t in catalog.tables.items()
    }
    return replace(catalog, tables=tables)


# ===== used_by: which projects use which tables =====


def candidate_names(catalog: Catalog) -> set[str]:
    """Every name a document may call one of its tables by (to look for as words)."""
    return {n for t in catalog.tables.values() for n in t.names()}


def used_names(catalog: Catalog, names: Iterable[str], texts: Iterable[str]) -> set[str]:
    """The names, of the ones a project uses (its tables, open ones) and of the ones its documents' code
    names as words (relationship_scope's rule), that are this connection's tables."""
    own = candidate_names(catalog)
    said = {n.casefold() for n in names} | {n.casefold() for n in named_in(list(texts), own)}
    return said & own


def with_usage(catalog: Catalog, project: str, used: set[str]) -> Catalog:
    """`project` (a folder's name) in each table's used_by that it uses (`used`: names, casefolded), and out
    of the ones it no longer uses; every other project's name kept."""
    if not project:
        return catalog
    tables = {}
    for key, table in catalog.tables.items():
        others = [p for p in table.used_by if p.casefold() != project.casefold()]
        uses = bool(table.names() & used)
        tables[key] = replace(
            table, used_by=tuple(sorted({*others, *([project] if uses else [])}, key=str.casefold))
        )
    return replace(catalog, tables=tables)


# ===== reading it: the agent's and the pages' =====


def table_json(catalog: Catalog, table: Table) -> dict[str, Any]:
    return {"connection": catalog.connection, "key": table.key} | table.to_json()


def listing(catalogs: Mapping[str, Catalog], here: set[str]) -> list[dict[str, Any]]:
    """Each connection's catalog in short (its tables' names, state and used_by), and whether this computer
    has the connection (`here`: casefolded names)."""
    out = []
    for name in sorted(catalogs, key=str.casefold):
        c = catalogs[name]
        out.append(
            c.summary()
            | {
                "here": c.connection.casefold() in here,
                "tables_list": [
                    {
                        "key": t.key,
                        "name": t.name,
                        "schema": t.schema,
                        "database": t.database,
                        "state": t.state,
                        **({"gone_since": t.gone_since} if t.gone_since else {}),
                        "used_by": list(t.used_by),
                        "columns": len(t.columns),
                    }
                    for t in sorted(c.tables.values(), key=lambda t: t.key.casefold())
                ],
            }
        )
    return out


def find_table(catalogs: Mapping[str, Catalog], connection: str, table: str) -> tuple[Catalog, Table]:
    """One table by its connection and its key or name (in any case); LookupError when there is none."""
    found = next((c for n, c in catalogs.items() if n.casefold() == connection.casefold()), None)
    if found is None:
        raise LookupError(f"The shared catalog has no connection {connection!r}.")
    wanted = table.casefold()
    for t in sorted(found.tables.values(), key=lambda t: t.key):
        if t.key.casefold() == wanted:
            return found, t
    for t in sorted(found.tables.values(), key=lambda t: (t.state != PRESENT, t.key)):
        if wanted in t.names():
            return found, t
    raise LookupError(f"{found.connection}'s shared catalog has no table {table!r}.")


def changed_words(count: int) -> str:
    """What the page says once when the user's pull brought catalog files in."""
    return f"Catalog updated from the library: {count} connection{'' if count == 1 else 's'} changed"


def model_of(catalogs: Iterable[Catalog]) -> Model:
    """The shared catalog as a model (keys, sources, columns, relationships of the present tables): what the
    ERD's All tables adds to the relationships in use."""
    keys: dict[str, tuple[str, ...]] = {}
    sources: dict[str, str] = {}
    columns: dict[str, tuple[tuple[str, str], ...]] = {}
    joins: dict[Any, Relationship] = {}
    for c in catalogs:
        for t in c.tables.values():
            if t.state != PRESENT:
                continue
            name = dataset_name(t.name)
            sources.setdefault(name, f"connection:{c.connection}")
            if t.primary_key:
                keys.setdefault(name, t.primary_key)
            if t.columns:
                columns.setdefault(name, tuple((col.name, col.type) for col in t.columns))
            for j in t.relationships:
                joins.setdefault(
                    j.key,
                    Relationship(
                        j.from_table, j.from_columns, j.to_table, j.to_columns, j.kind, active=j.active
                    ),
                )
    return Model(
        name="shared catalog",
        keys=keys,
        sources=sources,
        columns=columns,
        relationships=tuple(joins[k] for k in sorted(joins)),
    )
