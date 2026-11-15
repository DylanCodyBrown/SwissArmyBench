"""A Power BI workspace as a connection: how its datasets are named, how their tables are named as
grids, and what a dataset's relationships are in the app's model.

The connection is per workspace (the owner, 2026-11-15: "you designed the connection per dataset; it
should be per workspace"): one connection gives every dataset (semantic model) in the workspace, as a
database connection gives every schema. It is a starter (server/blade_templates.py POWERBI): code
that signs in, lists the workspace's datasets and sends DAX to any one of them through Power BI's
Execute Queries request; a dataset is shaped like a database connection, so the catalog, Open as grid
and DAX cells use it as they use one. Its dialect is `dax` (domain/catalogs.py quotes for it), and in
the catalog each dataset is a schema.

- A dataset is named with its connection: `Finance/Sales model` (split_name, joined_name). A DAX cell,
  `sag.dax()` and the agent's commands all say it that way.
- A table opens as a grid under its own name; when two of the workspace's datasets hold a table of
  that name, under the dataset's name and its own (grid_name: `Sales_model_Date`).

The rest is the rules for reading a dataset's own relationships (the owner, 2026-11-15: "an existing
Power BI model's joins arrive with its tables"):

- which DAX asks for them: `INFO.VIEW.RELATIONSHIPS()`, which names tables and columns; where a model
  does not know the VIEW form, `INFO.RELATIONSHIPS()` with `INFO.TABLES()` and `INFO.COLUMNS()`, whose
  rows hold ids and numbers that are resolved here;
- how each becomes a Relationship: tables named as they open as grids (grid_name), columns by
  their own names (as a grid's headers are), `Many` to `One` as
  `many-to-one` and the like, an inactive relationship kept inactive, a cross-filter in both
  directions said in its note.

Pure rules: the rows arrive already read (services/connections.py runs the DAX in a child process).
"""

from __future__ import annotations

import re
from collections.abc import Collection
from typing import Any

from swissarmygrid.domain.connections import dataset_name
from swissarmygrid.domain.relationships import Model, Relationship, parse_model

DIALECT: str = "dax"

# What to ask, in order: the first group whose every query the dataset answers is used.
RELATIONSHIP_QUERIES: tuple[tuple[str, ...], ...] = (
    ("EVALUATE INFO.VIEW.RELATIONSHIPS()",),
    ("EVALUATE INFO.RELATIONSHIPS()", "EVALUATE INFO.TABLES()", "EVALUATE INFO.COLUMNS()"),
)

# Tables Power BI makes by itself for each date column (Auto date/time): hidden, never opened.
_OWN_TABLES: tuple[str, ...] = ("LocalDateTable_", "DateTableTemplate_")


class PowerBIError(ValueError):
    """The dataset's answer cannot be read as relationships. The message says what was missing."""


def split_name(name: str) -> tuple[str, str]:
    """`Finance/Sales model`: the connection and the dataset in its workspace ("" when none is named).
    A connection's own name has no slash; a dataset's may."""
    connection, _, dataset = name.partition("/")
    return connection.strip(), dataset.strip()


def joined_name(connection: str, dataset: str) -> str:
    """A dataset with its connection, as a DAX cell names it: `Finance/Sales model`."""
    return f"{connection}/{dataset}" if dataset else connection


def grid_name(dataset: str, table: str, shared: Collection[str] = ()) -> str:
    """A dataset's table as a grid: its own name; the dataset's name before it when another of the
    workspace's datasets holds a table of that name (`shared`: those names, casefolded)."""
    if dataset and table.casefold() in shared:
        return dataset_name(f"{dataset} {table}")
    return dataset_name(table)


def model_name(connection: str, dataset: str) -> str:
    """The imported model's name: the connection and the dataset, in the letters a model's name takes."""
    return re.sub(r"[^A-Za-z0-9 _-]+", " ", f"{connection} {dataset}").strip()[:64] or "Power BI"


def source(connection: str, dataset: str) -> str:
    """Where a model's table came from, as the Diagram says it."""
    return f"{joined_name(connection, dataset)} (Power BI)"


def is_own_table(table: str) -> bool:
    """A table Power BI made by itself (Auto date/time), not one of the model's own."""
    return table.startswith(_OWN_TABLES)


def _key(name: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _rows(table: Any) -> list[dict[str, Any]]:
    """One query's answer ({"columns", "rows"}) as rows by column name, the names compared loosely
    (FromTable, [FromTable] and from table are the same column)."""
    if not isinstance(table, dict):
        return []
    names = [_key(c) for c in table.get("columns") or []]
    return [dict(zip(names, row, strict=False)) for row in table.get("rows") or []]


def _need(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if row.get(name) not in (None, ""):
            return row[name]
    gave = ", ".join(sorted(row)) or "nothing"
    raise PowerBIError(f"The dataset's relationships came back without {names[0]}: it gave {gave}.")


def _many(value: object) -> bool:
    """A relationship end's cardinality: Many (2 in the numbered form), else One (1)."""
    return _key(value) in ("many", "2")


def _both(value: object) -> bool:
    """Cross-filtering in both directions (2 in the numbered form)."""
    return _key(value) in ("bothdirections", "both", "2")


def _true(value: object) -> bool:
    return value is True or _key(value) in ("true", "1", "yes")


def relationship(
    from_table: str,
    from_column: str,
    to_table: str,
    to_column: str,
    from_cardinality: object,
    to_cardinality: object,
    cross_filter: object,
    active: object,
    dataset: str = "",
    shared: Collection[str] = (),
) -> Relationship:
    """One of the dataset's relationships as the app's: its tables named as they open as grids."""
    kind = f"{'many' if _many(from_cardinality) else 'one'}-to-{'many' if _many(to_cardinality) else 'one'}"
    return Relationship(
        grid_name(dataset, from_table, shared),
        (from_column,),
        grid_name(dataset, to_table, shared),
        (to_column,),
        kind,
        "filters both ways" if _both(cross_filter) else "",
        _true(active),
    )


def _named(results: list[Any]) -> list[tuple[str, str, str, str, dict[str, Any]]]:
    """INFO.VIEW.RELATIONSHIPS(): each row names its tables and columns."""
    found = []
    for row in _rows(results[0]):
        found.append(
            (
                str(_need(row, "fromtable")),
                str(_need(row, "fromcolumn")),
                str(_need(row, "totable")),
                str(_need(row, "tocolumn")),
                row,
            )
        )
    return found


def _by_id(results: list[Any]) -> list[tuple[str, str, str, str, dict[str, Any]]]:
    """INFO.RELATIONSHIPS() with INFO.TABLES() and INFO.COLUMNS(): ids resolved to names."""
    tables = {str(_need(t, "id")): str(_need(t, "name")) for t in _rows(results[1])}
    columns = {
        str(_need(c, "id")): str(_need(c, "explicitname", "inferredname", "name")) for c in _rows(results[2])
    }
    found = []
    for row in _rows(results[0]):
        ids = [
            (str(_need(row, "fromtableid")), tables),
            (str(_need(row, "fromcolumnid")), columns),
            (str(_need(row, "totableid")), tables),
            (str(_need(row, "tocolumnid")), columns),
        ]
        missing = [i for i, names in ids if i not in names]
        if missing:
            raise PowerBIError(
                f"The dataset's relationships name a table or column (id {missing[0]}) it did not list."
            )
        a, b, c, d = (names[i] for i, names in ids)
        found.append((a, b, c, d, row))
    return found


def relationships_model(
    connection: str, attempt: int, results: list[Any], dataset: str = "", shared: Collection[str] = ()
) -> tuple[Model, int]:
    """One dataset's relationships as a model to merge into the current one, and how many were left
    out (those of the date tables Power BI makes by itself). `attempt`: which of RELATIONSHIP_QUERIES
    answered; `results`: its answers, in order; `shared`: the table names several of the workspace's
    datasets hold, which open as grids under the dataset's name too."""
    rows = _named(results) if attempt == 0 else _by_id(results)
    kept: list[Relationship] = []
    skipped = 0
    for from_table, from_column, to_table, to_column, row in rows:
        if is_own_table(from_table) or is_own_table(to_table):
            skipped += 1
            continue
        kept.append(
            relationship(
                from_table,
                from_column,
                to_table,
                to_column,
                row.get("fromcardinality"),
                row.get("tocardinality"),
                row.get("crossfilteringbehavior"),
                row.get("isactive", True),
                dataset,
                shared,
            )
        )
    kept.sort(key=lambda r: not r.active)  # of two joins between the same tables, the active one first
    tables = {t for r in kept for t in (r.from_table, r.to_table)}
    model = Model(
        name=model_name(connection, dataset),
        sources={t: source(connection, dataset) for t in sorted(tables)},
        relationships=tuple(kept),
    )
    return parse_model(model.to_json()), skipped  # the model's own limits and name rules apply
