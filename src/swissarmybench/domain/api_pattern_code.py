"""The endpoint wizard's patterns' code (domain/api_patterns.py has what a pattern is, the nine as data and
the registry): each pattern's ONE template, filled from its fields and the table's catalog, how well a table's
shape fits it and why, and the defaults its shape suggests.

Every template is written in the scaffold's one style: the adapter's `connection(name).read / .query /
.write` (adapters/adapter.py's Connection), never a per-source client, so the code runs on the sandbox here
and on the real connection in an export. The filters, the columns, the sort, the page and the keys go to the
source in the read's plan; no endpoint reads a whole large table a call. Summary folds its group and totals
into the plan; a summary by period and Reconcile are one statement in the source's own SQL through `query`
where the source has SQL, and where it has none (Dataverse's Web API, SharePoint, two different connections)
they read only the columns they need and DuckDB does the rest over the stream, said in the endpoint's words.

Pure text: standard library and sqlglot only.
"""

from __future__ import annotations

import keyword
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp

from swissarmybench.domain import api_scaffold as scaffold
from swissarmybench.domain import local_api as api_rules
from swissarmybench.domain import sandbox_dialects as dialects
from swissarmybench.domain.api_scaffold import ScaffoldError, Source, py

PERIODS = ("day", "month", "quarter", "year")
TOTALS = ("count", "sum", "avg", "min", "max", "count_distinct")
FORMATS = ("csv", "xlsx")
_KINDS = {"int": "number", "float": "number", "bool": "flag", "date": "date", "datetime": "date"}
# The sources whose own SQL takes a statement through `query` (the others: a plan through `read` only).
_SQL_KINDS = ("duckdb", "database")
_NO_FULL_JOIN = ("mysql",)


@dataclass(frozen=True)
class Target:
    """A sandbox table as the wizard has it: its columns (name, DuckDB type, key), how it is reached, its
    row count when known."""

    name: str
    columns: tuple[Mapping[str, Any], ...]
    source: Source = field(default_factory=lambda: Source("duckdb", "Sandbox"))
    rows: int | None = None

    @property
    def names(self) -> list[str]:
        return [str(c["name"]) for c in self.columns]

    @property
    def types(self) -> dict[str, str]:
        """Each column's Python annotation (int, float, bool, date, datetime, str)."""
        return api_rules.model_types(self.columns)

    @property
    def key(self) -> list[str]:
        return [str(c["name"]) for c in self.columns if c.get("key")]

    def kind(self, column: str) -> str:
        """A column's kind in the wizard's words: text, number, date or flag."""
        return _KINDS.get(self.types.get(column, "str"), "text")

    def of(self, what: str) -> list[str]:
        """The columns a step offers."""
        if what in ("any", "shared"):
            return self.names
        if what == "whole":
            return [n for n in self.names if self.types[n] == "int"]
        return [n for n in self.names if self.kind(n) == what]

    @property
    def place(self) -> str:
        return f"{self.source.schema}.{self.name}" if self.source.schema else self.name


@dataclass
class Made:
    """A pattern's code for a table: the block to append to API.py, the endpoints' function names, the key
    the sandbox should keep for the table (when the pattern writes by one), and whether DuckDB does part of
    the work over the stream (its source could not take it)."""

    text: str
    added: list[str]
    key: list[str] = field(default_factory=list)
    streams: bool = False
    words: str = ""


@dataclass(frozen=True)
class Taken:
    """What API.py has already: its function and class names, its paths (a block never answers one twice)."""

    names: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()

    def free(self, *wanted: str) -> None:
        clash = [n for n in wanted if n in self.names]
        if clash:
            raise ScaffoldError(f"API.py has {clash[0]} already: rename it, or write this one by hand.")

    def open(self, *wanted: str) -> None:
        clash = [p for p in wanted if p in self.paths]
        if clash:
            raise ScaffoldError(f"API.py answers {clash[0]} already.")


# ===== the small parts every template shares =====


def _fill(template: str, **values: Any) -> str:
    """A template's <<name>> places filled (its own braces left as they are)."""

    def one(found: re.Match[str]) -> str:
        return str(values[found.group(1)])

    return re.sub(r"<<(\w+)>>", one, template)


def _c(target: Target) -> str:
    return f"connection({py(target.source.connection)})"


def _path(table: str) -> str:
    return "/" + re.sub(r"[^A-Za-z0-9._~-]+", "-", table.lower()).strip("-")


def _camel(text: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[^A-Za-z0-9]+", text) if part)


def _style(target: Target) -> str:
    return f"{_c(target)} through the adapter"


def _head(pattern: str, label: str, target: Target, other: Target | None = None) -> str:
    """The block's banner and its one marker comment."""
    of = target.name if other is None else f"{target.name} and {other.name}"
    return f"\n\n# ===== {of}: {label} ({_style(target)}) =====\n# pattern: {pattern} of {of}\n\n\n"


def _column(target: Target, value: Any, what: str, required: bool = True) -> str:
    name = str(value or "").strip()
    if not name:
        if required:
            raise ScaffoldError(f"Pick {what}.")
        return ""
    found = next((n for n in target.names if n.casefold() == name.casefold()), None)
    if found is None:
        raise ScaffoldError(f"{target.name} has no column {name} to be {what}.")
    return found


def _columns(target: Target, value: Any, what: str, required: bool = True) -> list[str]:
    given = [value] if isinstance(value, str) else list(value or [])
    found = list(dict.fromkeys(_column(target, v, what) for v in given if str(v or "").strip()))
    if required and not found:
        raise ScaffoldError(f"Pick {what}.")
    return found


def _named(target: Target, columns: Sequence[str], what: str) -> None:
    """Columns that become Python names (a model's fields, a function's parameters)."""
    bad = next((n for n in columns if not n.isidentifier() or keyword.iskeyword(n)), None)
    if bad is not None:
        raise ScaffoldError(f"The column {py(bad)} is not a Python name, so it cannot be {what}.")


def _model(name: str, fields: Mapping[str, str], total: bool = False) -> str:
    lines = [f"class {name}(TypedDict{'' if total else ', total=False'}):"]
    lines += [f"    {n}: {t}" for n, t in fields.items()]
    return "\n".join(lines) + "\n"


def _words(names: Sequence[str]) -> str:
    listed = list(names)
    if len(listed) <= 1:
        return "".join(listed)
    return ", ".join(listed[:-1]) + " and " + listed[-1]


def _first(target: Target, what: str, *hints: str, skip: Sequence[str] = ()) -> str:
    """The first column of a kind, one whose name holds a hint before any other ("" when there is none)."""
    offered = [n for n in target.of(what) if n not in skip]
    for hint in hints:
        for n in offered:
            if hint in n.casefold():
                return n
    return offered[0] if offered else ""


def key_of(target: Target) -> str:
    return scaffold.chosen_key(target.columns)


def _literal(target: Target, column: str, text: Any) -> Any:
    """A typed value written into the code: text as its column holds it (a number, true or false, text)."""
    kind = target.types.get(column, "str")
    raw = str(text if text is not None else "").strip()
    try:
        if kind == "int":
            return int(raw)
        if kind == "float":
            return float(raw)
    except ValueError:
        raise ScaffoldError(f"{column} holds numbers: {py(raw)} is not one.") from None
    if kind == "bool":
        if raw.casefold() in ("true", "yes", "1", "on"):
            return True
        if raw.casefold() in ("false", "no", "0", "off"):
            return False
        raise ScaffoldError(f"{column} is true or false, not {py(raw)}.")
    return raw


# ===== table =====


def make_table(target: Target, fields: Mapping[str, Any], taken: Taken, other: Target | None) -> Made:
    key = _column(target, fields.get("key") or key_of(target), "its key")
    block = scaffold.crud(target.name, target.columns, target.source, key, taken.names, taken.paths)
    stem = scaffold.stem(target.name)
    added = [f"{verb}_{stem}" for verb in ("list", "get", "create", "update", "delete")]
    return Made(block, added, [key])


def fit_table(target: Target, others: Sequence[Target]) -> tuple[int, str]:
    key = target.key
    if key:
        return 90, f"{target.name} has a key ({_words(key)}): list, get, create, update and delete by it."
    return (
        89,
        f"The rows of {target.name} a page at a time, and one read, made, changed or deleted by a key.",
    )


# ===== choices =====

_CHOICES = '''<<head>><<model>>

@endpoint("GET", "<<path>>")
def <<fn>>(<<search>>limit: int = 200) -> list[<<model_name>>]:
    """<<table>>: <<words>>

    <<more>>"""
<<filters>><<body>>
'''


def make_choices(target: Target, fields: Mapping[str, Any], taken: Taken, other: Target | None) -> Made:
    value = _column(target, fields.get("value") or key_of(target), "the value")
    label = _column(target, fields.get("label") or value, "the label")
    picked = list(dict.fromkeys([value, label]))
    _named(target, picked, "a field of the choices")
    stem = scaffold.stem(target.name)
    whole = value in target.key or (not target.key and value == key_of(target) and label != value)
    fn = f"choices_{stem}" if whole else f"choices_{stem}_{scaffold.stem(value)}"
    path = _path(target.name) + "/choices" + ("" if whole else "/" + _path(value).strip("/"))
    model = _camel(target.name) + ("" if whole else _camel(value)) + "Choice"
    taken.free(fn, model)
    taken.open(path)
    types = target.types
    searched = types[label] == "str"
    shown = {n: types[n] for n in picked} | ({} if whole else {"rows": "int"})
    filters = (
        f'    filters = [[{py(label)}, "like", f"%{{search}}%"]] if search else []\n' if searched else ""
    )
    narrowed = '"filters": filters, ' if searched else ""
    if whole:
        plan = (
            f'    plan = {{"columns": {py(picked)}, {narrowed}"sort": [[{py(label)}, "asc"]], '
            f'"limit": limit}}\n'
        )
        body = plan + f"    return records({_c(target)}.read({py(target.place)}, plan))"
        words = f"its choices for a dropdown ({_words(picked)})"
        more = f"Sorted by {label}, `limit` at most"
    else:
        plan = (
            f'    plan = {{"group": {py(picked)}, "totals": [{{"fn": "count", "name": "rows"}}], '
            f'{narrowed}"sort": [[{py(label)}, "asc"]], "limit": limit}}\n'
        )
        body = plan + f"    return records({_c(target)}.read({py(target.place)}, plan))"
        words = f"each {_words(picked)} it holds, once, with how many rows have it"
        more = "The group and the count are the read's plan: the source does them where it can"
    if searched:
        more += f"; ?search= narrows by {label}"
    text = _fill(
        _CHOICES,
        head=_head("choices", "Choices", target),
        model=_model(model, shown),
        model_name=model,
        path=path,
        fn=fn,
        search='search: str = "", ' if searched else "",
        table=target.name,
        words=words + ".",
        more=more + ".",
        filters=filters,
        body=body,
    )
    return Made(text, [fn])


def fit_choices(target: Target, others: Sequence[Target]) -> tuple[int, str]:
    label = _first(target, "text", "name", "title", "label", "description")
    short = target.rows is not None and target.rows <= 2000
    if label and len(target.names) <= 6 and (short or target.rows is None):
        return 85, f"{target.name} is a short list with {label}: the choices of a dropdown."
    if label:
        return 55, f"The {label} values of {target.name}, each once, as a dropdown's choices."
    return 30, f"{target.name} has no text column: its choices would be its {key_of(target)} values."


def defaults_choices(target: Target, other: Target | None) -> dict[str, Any]:
    label = _first(target, "text", "name", "title", "label", "description")
    short = len(target.names) <= 6 and (target.rows is None or target.rows <= 2000)
    return {"value": key_of(target) if short or not label else label, "label": label or key_of(target)}


# ===== search =====

_SEARCH = '''<<head>><<model>>

@endpoint("GET", "<<path>>")
def <<fn>>(
<<params>>    sort: str = <<sort>>,
    descending: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[<<model_name>>]:
    """<<table>>: the rows that match, a page at a time.

    <<words>>The filters, the sort and the page go to the source."""
    columns = <<columns>>
    filters: list[list] = []
<<filters>>    if sort not in columns:
        raise ApiError(422, "sort is one of the columns it answers.")
    way = "desc" if descending else "asc"
    plan = {"columns": columns, "filters": filters, "sort": [[sort, way]], "limit": limit, "offset": offset}
    return records(<<c>>.read(<<t>>, plan))
'''


def make_search(target: Target, fields: Mapping[str, Any], taken: Taken, other: Target | None) -> Made:
    text_in = _column(target, fields.get("text"), "the column the text search looks in", required=False)
    by = _columns(target, fields.get("filters"), "the columns to filter by", required=False)
    columns = (
        _columns(target, fields.get("columns"), "the columns it answers", required=False) or target.names
    )
    sort = _column(target, fields.get("sort") or columns[0], "the column it sorts by")
    if not text_in and not by:
        raise ScaffoldError("Pick a column the text search looks in, or a column to filter by.")
    if text_in and target.types[text_in] != "str":
        raise ScaffoldError(f"{text_in} is not text: the text search looks in a text column.")
    if sort not in columns:
        raise ScaffoldError(f"It sorts by {sort}, so {sort} is one of the columns it answers.")
    _named(target, [*by, *columns], "a parameter or a field of the search")
    stem = scaffold.stem(target.name)
    fn, model, path = f"search_{stem}", _camel(target.name) + "Found", _path(target.name) + "/search"
    taken.free(fn, model)
    taken.open(path)
    types = target.types
    params, filters, said = [], [], []
    if text_in:
        params.append('    q: str = "",\n')
        filters.append(f'    if q:\n        filters.append([{py(text_in)}, "like", f"%{{q}}%"])\n')
        said.append(f"?q= looks in {text_in}")
    for name in by:
        kind = types[name]
        if kind in ("date", "datetime"):
            params.append(f"    from_{name}: {kind} | None = None,\n    to_{name}: {kind} | None = None,\n")
            filters.append(
                f"    if from_{name} is not None:\n"
                f'        filters.append([{py(name)}, ">=", from_{name}.isoformat()])\n'
                f"    if to_{name} is not None:\n"
                f'        filters.append([{py(name)}, "<=", to_{name}.isoformat()])\n'
            )
        else:
            params.append(f"    {name}: {kind} | None = None,\n")
            filters.append(f'    if {name} is not None:\n        filters.append([{py(name)}, "=", {name}])\n')
    if by:
        said.append(f"{_words(by)} narrow{'s' if len(by) == 1 else ''} it")
    made = _fill(
        _SEARCH,
        head=_head("search", "Search", target),
        model=_model(model, {n: types[n] for n in columns}),
        model_name=model,
        path=path,
        fn=fn,
        params="".join(params),
        sort=py(sort),
        table=target.name,
        words=("; ".join(said) + ". ") if said else "",
        filters="".join(filters),
        columns=py(columns, 4),
        c=_c(target),
        t=py(target.place),
    )
    return Made(made, [fn])


def fit_search(target: Target, others: Sequence[Target]) -> tuple[int, str]:
    texts = target.of("text")
    if texts:
        big = target.rows is not None and target.rows > 2000
        return (80 if big else 65), f"{target.name} has text to look in ({_words(texts[:3])})."
    return 40, f"{target.name} has no text column: a search of it is filters on its columns."


def defaults_search(target: Target, other: Target | None) -> dict[str, Any]:
    text = _first(target, "text", "name", "title", "description", "customer", "email")
    by = [n for n in target.names if n != text and n not in target.key and target.kind(n) != "number"][:3]
    return {"text": text, "filters": by, "columns": target.names, "sort": key_of(target)}


# ===== summary =====

_SUMMARY_PLAN = '''<<head>><<model>>

@endpoint("GET", "<<path>>")
def <<fn>>(
<<params>>    limit: int = 1000,
) -> list[<<model_name>>]:
    """<<table>>: <<words>>.

    The group and the totals are the read's plan: the source does them where it can."""
    filters: list[list] = []
<<filters>>    plan = {
        "group": <<group>>,
        "totals": <<totals>>,
        "filters": filters,
        "sort": <<sort>>,
        "limit": limit,
    }
    return records(<<c>>.read(<<t>>, plan))
'''

_SUMMARY_SQL = '''<<head>><<model>>

@endpoint("GET", "<<path>>")
def <<fn>>(since: date | None = None) -> list[<<model_name>>]:
    """<<table>>: <<words>>.

    One statement in the source's own SQL: it groups, only the totals come back (from `since` on)."""
    start = (since or date(1900, 1, 1)).isoformat()
    return records(
        <<c>>.query(
            f"""
<<sql>>
            """
        )
    )
'''

_SUMMARY_STREAM = '''<<head>><<model>>

@endpoint("GET", "<<path>>")
def <<fn>>(since: date | None = None) -> list[<<model_name>>]:
    """<<table>>: <<words>>.

    <<source>> cannot group by a period, so only the columns it needs are read (from `since` on) and
    DuckDB groups them over the stream."""
    import duckdb

    filters = [[<<date>>, ">=", since.isoformat()]] if since is not None else []
    rows = <<c>>.read(<<t>>, columns=<<needed>>, filters=filters)
    engine = duckdb.connect()
    engine.register("rows", rows)
    return records(
        engine.sql(
            """
<<sql>>
            """
        ).to_arrow_table()
    )
'''


def _totals(target: Target, value: Any) -> list[tuple[str, str, str]]:
    """The totals asked for as (fn, column, its name in the answer)."""
    out: list[tuple[str, str, str]] = []
    for item in value or []:
        raw = dict(item) if isinstance(item, Mapping) else {"fn": str(item)}
        fn = str(raw.get("fn") or "").strip().lower()
        if fn not in TOTALS:
            raise ScaffoldError(f"A total is one of {', '.join(TOTALS)}, not {fn or 'nothing'}.")
        column = _column(target, raw.get("column"), f"the column of the {fn}", required=fn != "count")
        if fn in ("sum", "avg") and target.kind(column) != "number":
            raise ScaffoldError(f"{column} is not a number: a {fn} takes a number column.")
        name = "rows" if fn == "count" and not column else f"{fn}_{scaffold.stem(column)}"
        if name not in [n for _, _, n in out]:
            out.append((fn, column, name))
    if not out:
        raise ScaffoldError("Pick at least one total (count is one).")
    return out


def _total_type(target: Target, fn: str, column: str) -> str:
    if fn in ("count", "count_distinct"):
        return "int"
    if fn == "avg":
        return "float"
    return target.types.get(column, "float")


_SQL_FN = {"count": "COUNT", "sum": "SUM", "avg": "AVG", "min": "MIN", "max": "MAX"}


def _total_sql(fn: str, column: str, name: str) -> exp.Expr:
    if fn == "count" and not column:
        made: exp.Expr = exp.Count(this=exp.Star())
    elif fn == "count_distinct":
        made = exp.Count(this=exp.Distinct(expressions=[exp.column(column, quoted=True)]))
    else:
        made = exp.func(_SQL_FN[fn], exp.column(column, quoted=True))
    return exp.alias_(made, name, quoted=True)


def _table_sql(place: str) -> exp.Table:
    parts = place.split(".")
    return exp.table_(parts[-1], db=parts[-2] if len(parts) > 1 else None, quoted=True)


def _dialect(source: Source) -> str:
    name = dialects.dialect_of(source.dialect)
    return {"sqlserver": "tsql"}.get(name, name)


def _in_dialect(tree: exp.Expr, source: Source) -> str:
    """A statement written in the source's own SQL (its quoting, its LIMIT, its date functions), indented
    for the code it is written into."""
    try:
        text = tree.sql(dialect=_dialect(source), pretty=True)
    except (sqlglot.errors.SqlglotError, ValueError) as error:
        raise ScaffoldError(f"That could not be written in {source.dialect} SQL: {error}") from None
    text = text.replace("{", "{{").replace("}", "}}")
    return "\n".join("            " + line for line in text.split("\n"))


def make_summary(target: Target, fields: Mapping[str, Any], taken: Taken, other: Target | None) -> Made:
    group = _columns(target, fields.get("group"), "the columns to group by", required=False)
    totals = _totals(target, fields.get("totals"))
    period = str(fields.get("period") or "").strip().lower()
    when = _column(target, fields.get("date"), "the date column", required=bool(period))
    if period and period not in PERIODS:
        raise ScaffoldError(f"A period is one of {', '.join(PERIODS)}.")
    if period and target.kind(when) != "date":
        raise ScaffoldError(f"{when} is not a date: a period groups a date column.")
    if not period:
        when = ""
    _named(target, group, "a parameter or a field of the summary")
    stem = scaffold.stem(target.name)
    tail = "_by_" + "_".join(scaffold.stem(g) for g in ([period] if period else []) + group) if (
        group or period
    ) else ""  # fmt: skip
    fn = f"summary_{stem}{tail}"
    path = _path(target.name) + "/summary" + "".join(_path(g) for g in ([period] if period else []) + group)
    model = _camel(target.name) + "".join(_camel(g) for g in ([period] if period else []) + group) + "Summary"
    taken.free(fn, model)
    taken.open(path)
    types = target.types
    shown = ({"period": "date"} if period else {}) | {g: types[g] for g in group}
    shown |= {name: _total_type(target, f, column) for f, column, name in totals}
    said = _words(
        [f"{f.replace('_', ' ')} of {column}" if column else "the row count" for f, column, _ in totals]
    )
    by = ([f"{period} of {when}"] if period else []) + group
    words = said + (f" by {_words(by)}" if by else "")
    common = {
        "head": _head("summary", "Summary", target),
        "model": _model(model, shown),
        "model_name": model,
        "path": path,
        "fn": fn,
        "table": target.name,
        "words": words,
        "c": _c(target),
        "t": py(target.place),
    }
    if not period:
        params, filters = [], []
        for name in group:
            params.append(f"    {name}: {types[name]} | None = None,\n")
            filters.append(f'    if {name} is not None:\n        filters.append([{py(name)}, "=", {name}])\n')
        plan_totals = [
            {"fn": f, "name": name} | ({"column": column} if column else {}) for f, column, name in totals
        ]
        text = _fill(
            _SUMMARY_PLAN,
            **common,
            params="".join(params),
            filters="".join(filters),
            group=py(group),
            totals=py(plan_totals),
            sort=py([[g, "asc"] for g in group]),
        )
        return Made(text, [fn])
    quoted = '"' + when.replace('"', '""') + '"'
    bucket = sqlglot.parse_one(f"CAST(DATE_TRUNC('{period}', {quoted}) AS DATE)", read="duckdb")
    picked: list[exp.Expr] = [exp.alias_(bucket, "period", quoted=True)]
    picked += [exp.column(g, quoted=True) for g in group]
    picked += [_total_sql(f, column, name) for f, column, name in totals]
    grouped: list[exp.Expr] = [bucket.copy(), *(exp.column(g, quoted=True) for g in group)]
    if target.source.kind in _SQL_KINDS:
        since = exp.column(when, quoted=True) >= exp.cast(exp.Literal.string("9999-12-31"), "date")
        tree = (
            exp.select(*picked)
            .from_(_table_sql(target.place))
            .where(since)
            .group_by(*grouped)
            .order_by(*[g.copy() for g in grouped])
        )
        sql = _in_dialect(tree, target.source).replace("9999-12-31", "{start}")
        return Made(_fill(_SUMMARY_SQL, **common, sql=sql), [fn])
    tree = (
        exp.select(*picked)
        .from_(exp.table_("rows"))
        .group_by(*grouped)
        .order_by(*[g.copy() for g in grouped])
    )
    sql = "\n".join("            " + line for line in tree.sql(dialect="duckdb", pretty=True).split("\n"))
    needed = list(dict.fromkeys([when, *group, *[column for _, column, _ in totals if column]]))
    text = _fill(
        _SUMMARY_STREAM,
        **common,
        sql=sql,
        source=target.source.connection,
        date=py(when),
        needed=py(needed),
    )
    return Made(text, [fn], streams=True, words="DuckDB groups it over the stream")


def fit_summary(target: Target, others: Sequence[Target]) -> tuple[int, str]:
    numbers = [n for n in target.of("number") if n not in target.key and not n.casefold().endswith("id")]
    groups = [n for n in target.names if target.kind(n) in ("text", "flag")]
    dates = target.of("date")
    if numbers and (groups or dates):
        by = _words([*(groups[:2]), *([f"month of {dates[0]}"] if dates else [])][:2])
        return 75, f"{target.name} has amounts ({_words(numbers[:2])}) to total by {by}."
    if groups or dates:
        return 50, f"{target.name}'s rows counted by {_words((groups or dates)[:2])}."
    return 20, f"{target.name} has nothing to group by: its summary would be one row of totals."


def defaults_summary(target: Target, other: Target | None) -> dict[str, Any]:
    numbers = [n for n in target.of("number") if n not in target.key and not n.casefold().endswith("id")]
    groups = [n for n in target.names if target.kind(n) in ("text", "flag")]
    group = _first(target, "text", "region", "status", "category", "type") or (groups[0] if groups else "")
    totals: list[dict[str, str]] = [{"fn": "sum", "column": n} for n in numbers[:1]]
    return {"group": [group] if group else [], "totals": [*totals, {"fn": "count", "column": ""}],
            "date": "", "period": ""}  # fmt: skip


# ===== bulk upload =====

_BULK = '''<<head>><<upper>>_COLUMNS = <<kinds>>  # each column and what it holds
<<upper>>_REQUIRED = <<required>>


class <<model_name>>(TypedDict):
    rows: int
    inserted: int
    updated: int
    written: bool
    problems: list[dict]


def _problem_<<stem>>(value: object, kind: str) -> str:
    """Why a value does not fit its column ("" when it does); a date arrives as 2026-01-15."""
    if kind == "int" and (isinstance(value, bool) or not isinstance(value, int)):
        return "is not a whole number"
    if kind == "float" and (isinstance(value, bool) or not isinstance(value, (int, float))):
        return "is not a number"
    if kind == "bool" and not isinstance(value, bool):
        return "is not true or false"
    if kind == "str" and not isinstance(value, str):
        return "is not text"
    if kind in ("date", "datetime"):
        try:
            (date if kind == "date" else datetime).fromisoformat(str(value))
        except ValueError:
            return "is not a date (2026-01-15)" if kind == "date" else "is not a date and time"
    return ""


@endpoint("POST", "<<path>>")
def <<fn>>(rows: list[dict], dry_run: bool = False) -> <<model_name>>:
    """<<table>>: many rows at once, checked first, then all written or none.

    Every row is checked (its columns, the required ones, each value's type, a <<key>> sent
    twice<<also>>); ?dry_run=true answers the problems and what would be written, and writes nothing. With
    no problem, one write: all of it or none. A column a row leaves out is written blank."""
    problems: list[dict] = []
    seen: dict[object, int] = {}
    clean: list[dict] = []
    for at, row in enumerate(rows, 1):
        for name in row:
            if name not in <<upper>>_COLUMNS:
                problems.append({"row": at, "column": name, "problem": "is not a column of <<table>>"})
        for name in <<upper>>_REQUIRED:
            if row.get(name) in (None, ""):
                problems.append({"row": at, "column": name, "problem": "is required"})
        kept: dict[str, object] = {}
        for name, kind in <<upper>>_COLUMNS.items():
            value = row.get(name)
            said = "" if value is None else _problem_<<stem>>(value, kind)
            if said:
                problems.append({"row": at, "column": name, "problem": said})
            elif value is not None and kind in ("date", "datetime"):
                value = (date if kind == "date" else datetime).fromisoformat(str(value))
            kept[name] = value
        key = row.get(<<key_r>>)
        if key is not None and key in seen:
            problems.append({"row": at, "column": <<key_r>>, "problem": f"repeats row {seen[key]}'s"})
        seen.setdefault(key, at)
        clean.append(kept)
    keys = [k for k in seen if k is not None]
    there: set[object] = set()
    for start in range(0, len(keys), 500):  # only the keys sent are looked up, 500 a read
        found = <<c>>.read(<<t>>, columns=[<<key_r>>], filters=[[<<key_r>>, "in", keys[start : start + 500]]])
        there.update(r[<<key_r>>] for r in records(found))
<<insert_only>>    answer: <<model_name>> = {
        "rows": len(rows),
        "inserted": len(keys) - len(there),
        "updated": <<updated>>,
        "written": False,
        "problems": problems[:200],
    }
    if dry_run or not rows:
        return answer
    if problems:
        first = problems[0]
        raise ApiError(
            422,
            f"Nothing was written: {len(problems)} problems, the first: row {first['row']} {first['column']} "
            f"{first['problem']}. Send dry_run=true for the list.",
        )
    done = <<c>>.write(<<t>>, clean, key=[<<key_r>>], mode=<<mode>>)  # one write: all of it or none
    return answer | {"inserted": done.inserted, "updated": done.updated, "written": True}
'''

_BULK_INSERT_ONLY = """    for at, row in enumerate(rows, 1):
        if row.get(<<key_r>>) in there:
            problems.append({"row": at, "column": <<key_r>>, "problem": "is already in <<table>>"})
"""


def make_bulk(target: Target, fields: Mapping[str, Any], taken: Taken, other: Target | None) -> Made:
    key = _column(target, fields.get("key") or key_of(target), "its key")
    mode = str(fields.get("mode") or "merge").strip().lower()
    if mode not in ("merge", "insert"):
        raise ScaffoldError(
            "A bulk upload adds new rows only (insert), or adds and updates by the key (merge)."
        )
    required = list(dict.fromkeys([key, *_columns(target, fields.get("required"), "the required", False)]))
    stem = scaffold.stem(target.name)
    fn, model, path = f"bulk_{stem}", _camel(target.name) + "BulkAnswer", _path(target.name) + "/bulk"
    upper = stem.upper()
    taken.free(fn, model, f"_problem_{stem}", f"{upper}_COLUMNS", f"{upper}_REQUIRED")
    taken.open(path)
    insert_only = _fill(_BULK_INSERT_ONLY, key_r=py(key), table=target.name) if mode == "insert" else ""
    text = _fill(
        _BULK,
        head=_head("bulk", "Bulk upload", target),
        upper=upper,
        kinds=py(target.types),
        required=py(required),
        model_name=model,
        stem=stem,
        path=path,
        fn=fn,
        table=target.name,
        key=key,
        key_r=py(key),
        also=f", a {key} already there" if mode == "insert" else "",
        insert_only=insert_only,
        updated="len(there)" if mode == "merge" else "0",
        c=_c(target),
        t=py(target.place),
        mode=py(mode),
    )
    return Made(text, [fn], [key])


def fit_bulk(target: Target, others: Sequence[Target]) -> tuple[int, str]:
    if target.key:
        return (
            60,
            f"{target.name} has a key ({_words(target.key)}): an upload adds new rows and updates the rest.",
        )
    return 45, f"An upload of {target.name} checked row by row, then written all or none."


def defaults_bulk(target: Target, other: Target | None) -> dict[str, Any]:
    return {"key": key_of(target), "mode": "merge", "required": [key_of(target)]}


# ===== action =====

_ACTION = '''<<head>>class <<body_name>>(TypedDict):
    keys: list[<<key_type>>]


class <<done_name>>(TypedDict):
    changed: int
    keys: list[<<key_type>>]


@endpoint("POST", "<<path>>")
def <<fn>>(sent: <<body_name>>) -> <<done_name>>:
    """<<table>>: <<words>>.

    Every key is checked first; then one write, all of the rows or none."""
    keys = list(dict.fromkeys(sent["keys"]))
    if not keys:
        raise ApiError(422, "Send at least one key.")
    if len(keys) > 1000:
        raise ApiError(422, "Send 1,000 keys at most in one call.")
    found = records(<<c>>.read(<<t>>, columns=<<read>>, filters=[[<<key_r>>, "in", keys]]))
    have = {row[<<key_r>>] for row in found}
    missing = [k for k in keys if k not in have]
    if missing:
        gone = f"{len(missing)} of {len(keys)} are not there"
        raise ApiError(404, f"No <<table>> row has <<key>> {missing[0]} ({gone}).")
<<only>>    changes = [{<<key_r>>: k, <<sets>>} for k in keys]
    done = <<c>>.write(<<t>>, changes, key=[<<key_r>>], mode="update")  # one write: all or none
    return {"changed": done.updated, "keys": keys}
'''

_ACTION_ONLY = """    wrong = [row[<<key_r>>] for row in found if row[<<only_r>>] != <<only_value>>]
    if wrong:
        others = f"{len(wrong)} of {len(keys)} are not"
        raise ApiError(409, f"<<key>> {wrong[0]} is not <<only>> <<only_said>> ({others}): nothing changed.")
"""


def make_action(target: Target, fields: Mapping[str, Any], taken: Taken, other: Target | None) -> Made:
    name = scaffold.stem(str(fields.get("name") or "").strip() or "change")
    if name in (
        "list",
        "get",
        "create",
        "update",
        "delete",
        "search",
        "summary",
        "bulk",
        "choices",
        "export",
    ):
        raise ScaffoldError(
            f"{name} is another pattern's word: name the action for what it does (approve, close)."
        )
    key = _column(target, fields.get("key") or key_of(target), "its key")
    sets: dict[str, Any] = {}
    for item in fields.get("sets") or []:
        raw = dict(item) if isinstance(item, Mapping) else {}
        column = _column(target, raw.get("column"), "a column it sets")
        if column == key:
            raise ScaffoldError(f"{key} is the key: an action sets other columns.")
        sets[column] = _literal(target, column, raw.get("value"))
    if not sets:
        raise ScaffoldError("Pick at least one column it sets, and the value.")
    only = _column(target, fields.get("only"), "the column it checks first", required=False)
    stem = scaffold.stem(target.name)
    fn, path = f"{name}_{stem}", f"{_path(target.name)}/{name.replace('_', '-')}"
    body, done = _camel(name) + _camel(target.name), _camel(name) + _camel(target.name) + "Done"
    taken.free(fn, body, done)
    taken.open(path)
    said = _words([f"{column} set to {py(value)}" for column, value in sets.items()])
    words = f"{name.replace('_', ' ')} the rows whose {key} is sent: {said}"
    only_text = ""
    if only:
        value = _literal(target, only, fields.get("only_value"))
        only_text = _fill(
            _ACTION_ONLY, key_r=py(key), key=key, only_r=py(only), only=only, only_value=py(value),
            only_said=str(value),
        )  # fmt: skip
        words += f", only while {only} is {py(value)}"
    text = _fill(
        _ACTION,
        head=_head("action", "Action", target),
        body_name=body,
        done_name=done,
        key_type=target.types[key],
        path=path,
        fn=fn,
        table=target.name,
        words=words,
        c=_c(target),
        t=py(target.place),
        read=py(list(dict.fromkeys([key, *([only] if only else [])]))),
        key=key,
        key_r=py(key),
        only=only_text,
        sets=", ".join(f"{py(column)}: {py(value)}" for column, value in sets.items()),
    )
    return Made(text, [fn], [key])


_STATUS = ("status", "state", "stage", "approved", "closed", "active", "done", "flag")


def _status(target: Target) -> str:
    return next(
        (n for n in target.names if any(h in n.casefold() for h in _STATUS) and n not in target.key), ""
    )


def fit_action(target: Target, others: Sequence[Target]) -> tuple[int, str]:
    status = _status(target)
    if status:
        return (
            72,
            f"{target.name} has {status}: an action sets it on the rows whose keys you send, all or none.",
        )
    return (
        35,
        f"{target.name} has no status column: an action would set a column you pick on the rows you send.",
    )


def defaults_action(target: Target, other: Target | None) -> dict[str, Any]:
    status = _status(target)
    flag = bool(status) and target.types[status] == "bool"
    return {
        "name": "approve" if status else "",
        "key": key_of(target),
        "sets": [{"column": status, "value": "true" if flag else "approved"}] if status else [],
        "only": "",
        "only_value": "",
    }


# ===== versions =====

_VERSIONS = '''<<head>><<model>>

@endpoint("GET", "<<path>>/{key}/versions")
def versions_<<stem>>(key: <<key_type>>, limit: int = 50, offset: int = 0) -> list[<<model_name>>]:
    """<<table>>: every version of one <<of>>, the newest first."""
    return records(
        <<c>>.read(
            <<t>>, filters=[[<<of_r>>, "=", key]], sort=[[<<version_r>>, "desc"]], limit=limit, offset=offset
        )
    )


@endpoint("GET", "<<path>>/{key}/current")
def current_<<stem>>(key: <<key_type>>) -> <<model_name>>:
    """<<table>>: the current version of one <<of>> (its highest <<version>>)."""
    latest = {"filters": [[<<of_r>>, "=", key]], "sort": [[<<version_r>>, "desc"]], "limit": 1}
    found = records(<<c>>.read(<<t>>, latest))
    if not found:
        raise ApiError(404, f"No <<table>> row has <<of>> {key}.")
    return found[0]


@endpoint("POST", "<<path>>/{key}/versions", status=201)
def new_version_<<stem>>(key: <<key_type>>, row: <<model_name>>) -> <<model_name>>:
    """<<table>>: a new version of one <<of>> from the body, numbered after its latest.

    Earlier versions are never changed."""
    newest = {"filters": [[<<of_r>>, "=", key]], "sort": [[<<version_r>>, "desc"]], "limit": 1}
    latest = records(<<c>>.read(<<t>>, newest | {"columns": [<<version_r>>]}))
    made = {name: value for name, value in row.items() if name in <<names>>}
    made |= {<<of_r>>: key, <<version_r>>: (latest[0][<<version_r>>] if latest else 0) + 1}
    <<c>>.write(<<t>>, [made])
    return made
'''

_VERSION = ("version", "revision", "rev", "edition", "sequence", "seq")


def _version(target: Target) -> str:
    return next((n for n in target.of("whole") if any(h in n.casefold() for h in _VERSION)), "")


def make_versions(target: Target, fields: Mapping[str, Any], taken: Taken, other: Target | None) -> Made:
    of = _column(target, fields.get("of"), "the column that says which thing a version is of")
    version = _column(target, fields.get("version") or _version(target), "the version number")
    if target.types[version] != "int":
        raise ScaffoldError(f"{version} is not a whole number: a version number counts 1, 2, 3.")
    if of == version:
        raise ScaffoldError("The thing and its version number are two columns.")
    _named(target, target.names, f"a field of {_camel(target.name)}Version")
    stem = scaffold.stem(target.name)
    model, path = _camel(target.name) + "Version", _path(target.name)
    added = [f"versions_{stem}", f"current_{stem}", f"new_version_{stem}"]
    taken.free(model, *added)
    taken.open(f"{path}/{{key}}/versions", f"{path}/{{key}}/current")
    text = _fill(
        _VERSIONS,
        head=_head("versions", "Versions", target),
        model=_model(model, target.types),
        model_name=model,
        path=path,
        stem=stem,
        key_type=target.types[of],
        table=target.name,
        of=of,
        of_r=py(of),
        version=version,
        version_r=py(version),
        names=py(target.names),
        c=_c(target),
        t=py(target.place),
    )
    return Made(text, added, [of, version])


def fit_versions(target: Target, others: Sequence[Target]) -> tuple[int, str]:
    version = _version(target)
    if version:
        return 92, f"{target.name} has {version}: every version kept, the current one read, a new one added."
    return (
        0,
        f"{target.name} has no version number column (a whole number such as version): Versions needs one.",
    )


def defaults_versions(target: Target, other: Target | None) -> dict[str, Any]:
    version = _version(target)
    of = next((n for n in [*target.key, *target.names] if n != version), "")
    return {"of": of, "version": version}


# ===== reconcile =====

_RECONCILE = '''<<head>><<upper>>_SHOWS = {
    "differences": <<differences>>,
    "all": <<all>>,
    "matched": ["matched"],
    "differing": ["differing"],
    "missing_in_<<left_stem>>": [<<missing_left>>],
    "missing_in_<<right_stem>>": [<<missing_right>>],
}
# Each compared row: the key, its result, both sides' values<<in_sql>>.
<<upper>>_COMPARED = """
<<compared>>
"""


class <<counts_name>>(TypedDict):
    matched: int
    differing: int
    missing_in_<<left_stem>>: int
    missing_in_<<right_stem>>: int


<<row_model>>

@endpoint("GET", "<<path>>")
def <<fn>>() -> <<counts_name>>:
    """<<left>> and <<right>> by <<keys>>: how many rows match, differ or are missing on each side.

    Compared: <<compare>>. <<how>>"""
<<counts_run>>
    counts = {"matched": 0, "differing": 0, <<missing_left>>: 0, <<missing_right>>: 0}
    for row in records(found):
        counts[row["result"]] = row["rows"]
    return {
        "matched": counts["matched"],
        "differing": counts["differing"],
        "missing_in_<<left_stem>>": counts[<<missing_left>>],
        "missing_in_<<right_stem>>": counts[<<missing_right>>],
    }


@endpoint("GET", "<<path>>/rows")
def <<fn>>_rows(show: str = "differences", limit: int = 50, offset: int = 0) -> list[<<row_name>>]:
    """<<left>> and <<right>> by <<keys>>: the compared rows, a page at a time.

    Each row has its result and both sides' values. ?show= is one of differences, all, matched, differing,
    missing_in_<<left_stem>>, missing_in_<<right_stem>>. <<how>>"""
    if show not in <<upper>>_SHOWS:
        raise ApiError(422, f"show is one of: {', '.join(<<upper>>_SHOWS)}.")
    shown = ", ".join(f"'{word}'" for word in <<upper>>_SHOWS[show])
<<rows_run>>
    return records(found)
'''

_RECONCILE_FOLDED = """    found = <<c>>.query(<<sql>>)"""

_RECONCILE_STREAMED = """    import duckdb

    engine = duckdb.connect()
    engine.register("left_rows", <<c>>.read(<<t>>, columns=<<needed>>))
    engine.register("right_rows", <<c2>>.read(<<t2>>, columns=<<needed>>))
    found = engine.sql(<<sql>>).to_arrow_table()"""


def _compared(left: exp.Table, right: exp.Table, keys: Sequence[str], compare: Sequence[str],
              names: tuple[str, str], labels: tuple[str, str]) -> exp.Select:  # fmt: skip
    """The compared rows as one SELECT: each key, the result, both sides' compared values."""

    def col(side: str, name: str) -> exp.Column:
        return exp.column(name, table=side, quoted=True)

    differs = [
        exp.or_(
            col("l", n).neq(col("r", n)),
            exp.and_(col("l", n).is_(exp.null()), exp.not_(col("r", n).is_(exp.null()))),
            exp.and_(exp.not_(col("l", n).is_(exp.null())), col("r", n).is_(exp.null())),
        )
        for n in compare
    ]
    result = exp.Case()
    result = result.when(col("r", keys[0]).is_(exp.null()), exp.Literal.string(labels[1]))
    result = result.when(col("l", keys[0]).is_(exp.null()), exp.Literal.string(labels[0]))
    if differs:
        result = result.when(exp.or_(*differs), exp.Literal.string("differing"))
    result = result.else_(exp.Literal.string("matched"))
    picked: list[exp.Expr] = [
        exp.alias_(exp.func("COALESCE", col("l", k), col("r", k)), k, quoted=True) for k in keys
    ]
    picked.append(exp.alias_(result, "result", quoted=True))
    for n in compare:
        picked.append(exp.alias_(col("l", n), f"{n}_{names[0]}", quoted=True))
        picked.append(exp.alias_(col("r", n), f"{n}_{names[1]}", quoted=True))
    joined = exp.and_(*[col("l", k).eq(col("r", k)) for k in keys])
    return (
        exp.select(*picked)
        .from_(exp.alias_(left, "l"))
        .join(exp.alias_(right, "r"), on=joined, join_type="full outer")
    )


def make_reconcile(target: Target, fields: Mapping[str, Any], taken: Taken, other: Target | None) -> Made:
    if other is None:
        raise ScaffoldError("Reconcile compares two tables: pick the second one.")
    if other.name.casefold() == target.name.casefold():
        raise ScaffoldError("Reconcile compares two different tables.")
    keys = _columns(target, fields.get("key"), "the key both tables share")
    compare = _columns(target, fields.get("compare"), "the columns to compare", required=False)
    for name in [*keys, *compare]:
        _column(other, name, f"compared ({target.name} has it)")
    compare = [n for n in compare if n not in keys]
    left_stem, right_stem = scaffold.stem(target.name), scaffold.stem(other.name)
    _named(target, [*keys, *[f"{n}_{left_stem}" for n in compare]], "a field of the compared rows")
    fn = f"reconcile_{left_stem}_{right_stem}"
    upper = fn.upper()
    path = f"/reconcile{_path(target.name)}-{_path(other.name).strip('/')}"
    counts_name = "Reconcile" + _camel(target.name) + _camel(other.name)
    row_name = counts_name + "Row"
    taken.free(fn, f"{fn}_rows", counts_name, row_name, f"{upper}_SHOWS", f"{upper}_COMPARED")
    taken.open(path, path + "/rows")
    labels = (f"missing in {target.name}", f"missing in {other.name}")
    same = target.source.connection == other.source.connection
    folded = same and target.source.kind in _SQL_KINDS and _dialect(target.source) not in _NO_FULL_JOIN
    if folded:
        compared = _compared(
            _table_sql(target.place), _table_sql(other.place), keys, compare, (left_stem, right_stem), labels
        )
        source = target.source
    else:
        compared = _compared(
            exp.table_("left_rows"), exp.table_("right_rows"), keys, compare, (left_stem, right_stem), labels
        )
        source = Source("duckdb", "Sandbox")
    result = exp.column("result", quoted=True)
    inner = exp.select(exp.alias_(exp.Literal.number(1), "sab_inner"))
    counts_tree = (
        exp.select(result, exp.alias_(exp.Count(this=exp.Star()), "rows", quoted=True))
        .from_("compared")
        .with_("compared", as_=inner)
        .group_by(result.copy())
    )
    rows_tree = (
        exp.select(exp.Star())
        .from_("compared")
        .with_("compared", as_=inner.copy())
        .where(result.copy().isin(exp.Literal.string("sab_shown")))
        .order_by(*[exp.column(k, quoted=True) for k in keys])
        .limit(987654321)
        .offset(123456789)
    )
    upper_compared = f"{upper}_COMPARED"

    def written(tree: exp.Expr, page: bool) -> str:
        """The statement around the compared rows, as an f-string of the endpoint."""
        text = _in_dialect(tree, source)
        swaps = [("'sab_shown'", "{shown}"), ("987654321", "{int(limit)}"), ("123456789", "{int(offset)}")]
        found = re.search(r"SELECT\s+1 AS \S*sab_inner\S*", text)
        if found is None or (page and any(old not in text for old, _ in swaps)):
            raise ScaffoldError(f"That could not be written in {source.dialect} SQL.")
        text = text.replace(found.group(0), "{" + upper_compared + "}")
        for old, new in swaps if page else []:
            text = text.replace(old, new)
        quotes = '"""'
        return f"\n        f{quotes}\n{text}\n        {quotes}\n    "

    types = target.types
    fields_of = {k: types[k] for k in keys} | {"result": "str"}
    for n in compare:
        fields_of |= {f"{n}_{left_stem}": types[n], f"{n}_{right_stem}": other.types[n]}
    needed = py([*keys, *compare])
    if folded:
        how = f"One statement in {target.source.connection}'s own SQL: the source joins the two tables."

        def run(sql: str) -> str:
            return _fill(_RECONCILE_FOLDED, c=_c(target), sql=sql)
    else:
        why = (
            f"{target.name} and {other.name} are on two connections"
            if not same
            else f"{target.source.connection} has no SQL that joins the two"
        )
        how = f"{why[0].upper()}{why[1:]}, so only the key and the compared columns are read and "
        how += "DuckDB joins the streams."

        def run(sql: str) -> str:
            return _fill(
                _RECONCILE_STREAMED, c=_c(target), t=py(target.place), c2=_c(other), t2=py(other.place),
                needed=needed, sql=sql,
            )  # fmt: skip

    text = _fill(
        _RECONCILE,
        head=_head("reconcile", "Reconcile", target, other),
        upper=upper,
        differences=py(["differing", *labels]),
        all=py(["matched", "differing", *labels]),
        left_stem=left_stem,
        right_stem=right_stem,
        missing_left=py(labels[0]),
        missing_right=py(labels[1]),
        in_sql=f", in {target.source.connection}'s own SQL"
        if folded
        else ", in DuckDB SQL over the two streams",
        compared=compared.sql(dialect=_dialect(source), pretty=True),
        counts_name=counts_name,
        row_model=_model(row_name, fields_of),
        row_name=row_name,
        path=path,
        fn=fn,
        left=target.name,
        right=other.name,
        keys=_words(keys),
        compare=_words(compare) or "the key only",
        how=how,
        counts_run=run(written(counts_tree, False)),
        rows_run=run(written(rows_tree, True)),
    )
    words = "" if folded else "DuckDB joins the two streams"
    return Made(text, [fn, f"{fn}_rows"], [], streams=not folded, words=words)


def columns_shared(target: Target, other: Target) -> list[str]:
    theirs = {n.casefold() for n in other.names}
    return [n for n in target.names if n.casefold() in theirs]


def fit_reconcile(target: Target, others: Sequence[Target]) -> tuple[int, str]:
    best: tuple[int, Target | None, list[str]] = (0, None, [])
    for other in others:
        if other.name.casefold() == target.name.casefold():
            continue
        both = columns_shared(target, other)
        if len(both) > best[0]:
            best = (len(both), other, both)
    if best[1] is None or not best[2]:
        return (
            0,
            f"No other sandbox table shares a column with {target.name}: Reconcile compares two by a key.",
        )
    return (
        58 + min(20, 4 * best[0]),
        f"{target.name} and {best[1].name} share {_words(best[2][:3])}: matched, missing, differing.",
    )


def partner(target: Target, others: Sequence[Target]) -> Target | None:
    """The table Reconcile would compare with by default: the one that shares the most columns."""
    found = [
        (len(columns_shared(target, o)), o) for o in others if o.name.casefold() != target.name.casefold()
    ]
    found = [f for f in found if f[0]]
    return max(found, key=lambda f: f[0])[1] if found else None


def defaults_reconcile(target: Target, other: Target | None) -> dict[str, Any]:
    if other is None:
        return {"key": [], "compare": []}
    both = columns_shared(target, other)
    key = [n for n in both if n in target.key] or [n for n in both if n.casefold().endswith("id")][:1]
    key = key or both[:1]
    return {"key": key, "compare": [n for n in both if n not in key and target.kind(n) != "text"][:6]}


# ===== export =====

_EXPORT = '''<<head>>@endpoint("GET", "<<path>>")
def <<fn>>(limit: int = 100000) -> Download:
    """<<table>> as <<what>> to save.

    It carries <<columns_said>>, sorted by <<sort>>: read from the source a batch at a time, `limit` rows at
    most."""
    columns = <<columns>>
    plan = {"columns": columns, "sort": [[<<sort_r>>, "asc"]], "limit": limit}
    return download(<<c>>.read(<<t>>, plan), <<file>>)
'''


def make_export(target: Target, fields: Mapping[str, Any], taken: Taken, other: Target | None) -> Made:
    kind = str(fields.get("format") or "csv").strip().lower()
    kind = {"excel": "xlsx"}.get(kind, kind)
    if kind not in FORMATS:
        raise ScaffoldError("An export is a CSV file (csv) or an Excel workbook (xlsx).")
    columns = (
        _columns(target, fields.get("columns"), "the columns it carries", required=False) or target.names
    )
    sort = _column(target, fields.get("sort") or key_of(target), "the column it sorts by")
    stem = scaffold.stem(target.name)
    fn = f"export_{stem}" + ("" if kind == "csv" else "_xlsx")
    path = f"{_path(target.name)}/export.{kind}"
    taken.free(fn)
    taken.open(path)
    every = columns == target.names
    text = _fill(
        _EXPORT,
        head=_head("export", "Export", target),
        path=path,
        fn=fn,
        table=target.name,
        what="a CSV file" if kind == "csv" else "an Excel workbook",
        columns_said="every column" if every else _words(columns),
        sort=sort,
        sort_r=py(sort),
        c=_c(target),
        t=py(target.place),
        columns=py(columns, 4),
        file=py(f"{target.name}.{kind}"),
    )
    return Made(text, [fn])


def fit_export(target: Target, others: Sequence[Target]) -> tuple[int, str]:
    return 42, f"{target.name} as a CSV file or an Excel workbook to save."


def defaults_export(target: Target, other: Target | None) -> dict[str, Any]:
    return {"columns": target.names, "format": "csv", "sort": key_of(target)}
