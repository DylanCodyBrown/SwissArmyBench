# duckpq

Power Query (M) compiled to DuckDB SQL, in one Python file.

**duckpq is not a Microsoft product.** "Power Query" and "Power BI" are Microsoft's names. This is an
independent reading of the published M language specification and function reference, with no Microsoft code
in it. It runs the common part of M; it is not a full implementation, and it says so, in one sentence with a
line and a column, whenever it meets something it cannot run.

- One file, `duckpq.py`. The standard library and `duckdb`, nothing else (`parse`, `check` and `compile` need
  not even duckdb).
- A table is lazy: every `Table.*` step composes one DuckDB query, which runs once at the end. Nothing is
  pulled into Python row by row.
- Sources are plugged in by the caller. Files and `#table` literals work with no set-up.
- It reads one `let ... in` query, or a section document of many `shared` queries (the shape a Power BI
  dataset keeps its queries in). Queries name each other and run in dependency order.

## Example: a CSV and a DuckDB file

```python
import duckpq

M = """
section Sales;

shared MinimumAmount = 20 meta [IsParameterQuery = true];

shared Orders = let
    Source = Csv.Document(File.Contents("orders.csv"), [Delimiter = ","]),
    Promoted = Table.PromoteHeaders(Source),
    Typed = Table.TransformColumnTypes(Promoted, {{"amount", type number}, {"day", type date}}),
    Kept = Table.SelectRows(Typed, each [amount] >= MinimumAmount and [status] <> "cancelled")
in
    Kept;

shared Customers = Sql.Database("warehouse.example", "crm"){[Schema = "main", Item = "customers"]}[Data];

shared ByRegion = let
    Joined = Table.NestedJoin(Orders, {"customer_id"}, Customers, {"id"}, "c", JoinKind.LeftOuter),
    Expanded = Table.ExpandTableColumn(Joined, "c", {"region"}),
    Grouped = Table.Group(Expanded, {"region"}, {{"total", each List.Sum([amount]), type number}})
in
    Table.Sort(Grouped, {{"total", Order.Descending}});
"""


def resolver(source: duckpq.Source):
    # Any database function reaches here with its arguments and its navigation.
    if source.function == "Sql.Database" and source.arguments[0] == "warehouse.example":
        return "warehouse.duckdb"  # a DuckDB file: attached, the navigation picks its table
    return None  # not mine: files are read by duckpq itself


tables = duckpq.run(M, resolver=resolver, parameters={"MinimumAmount": 50})
print(tables["ByRegion"].fetchall())  # a DuckDB relation: .df(), .arrow(), .pl(), .fetchall()
print(duckpq.to_sql(M, resolver=resolver)["ByRegion"])  # the DuckDB SQL it composed
print(duckpq.check('Table.Nope(#table({"a"}, {{1}}))'))  # problems, before anything runs
```

## The API

| Function | What it gives |
| --- | --- |
| `parse(text, name="Query")` | The tree (`Document`). `PowerQueryError` carries `.line` and `.column`; `EvaluationError` is the kind a `try` in the M catches. |
| `check(text, ...)` | `list[Problem]`: what cannot run, found without reading anything. |
| `compile(text, name, context)` | `Compiled`: each query's SQL, columns, dependencies and sources. No I/O. |
| `to_sql(text, ...)` | `dict[str, str]`: each table query's DuckDB SQL. |
| `run(text, ...)` | `dict[str, DuckDBPyRelation]`: every table query, in dependency order. |
| `run_query(text, query, ...)` | One query's relation. |
| `functions()` | The M functions this version runs. |

`run`'s options: `resolver`, `tables` (tables a query names by their name: a relation, an Arrow table, a
DataFrame), `parameters` (values for the file's parameter queries), `variables` (values for `${NAME}` inside a
text), `connection` (your DuckDB connection), `folder` (what a relative path is relative to), `name`.

The contract changes only by adding.

## Sources

A resolver is a function of one `Source`:

| Field | |
| --- | --- |
| `function` | The M function: `Sql.Database`, `PostgreSQL.Database`, `Snowflake.Databases`, `Web.Contents`, any other. |
| `arguments` | Its plain arguments. |
| `navigation` | The records picked after it: `{[Schema = "dbo", Item = "Orders"]}`. |
| `query` | A native query (`Value.NativeQuery`, or the `Query` option). |
| `path`, `sheet`, `options` | A file's path, a workbook's sheet, the function's options record. |

It returns a path (CSV, Parquet, JSON, a workbook; a `.duckdb` file is attached read-only and the navigation
picks its table, a native query runs in it), a DuckDB relation, an Arrow table or a DataFrame; `None` means
"not mine". With no resolver: `Csv.Document`, `Parquet.Document`, `Json.Document` and `Excel.Workbook` over
`File.Contents`, and `#table`. A workbook is read by DuckDB's `excel` extension (`INSTALL excel` once).

A file's table is read with its first row as the header, so `Table.PromoteHeaders` is expected after
`Csv.Document` or a sheet, as Power Query writes it; a file never promoted is refused, not guessed.

### A caller with its own engine

`compile()` does no I/O. What it needs from outside it asks of its `Context` by key: `("source", name)`,
`("json", path)`, `("variable", NAME)`, `("probe", sql)`. A key not in `context.resolved` is listed in
`context.missing`; fill them in (a `Resolved(columns, sql)` names a source your own way in the SQL, a
`Failure(message)` refuses it at its line; `Failure(message, raised=True)` says M's own read would raise
too, a file that is not there, so a `try` around the source takes its otherwise) and compile again until
`complete`. `run()` is that loop over a
DuckDB connection.

## Where M differs from SQL

duckpq writes M's meaning:

| M | The SQL it writes |
| --- | --- |
| `null = null` is true, `null <> 1` is true | `IS NOT DISTINCT FROM`, `IS DISTINCT FROM` |
| Text compares by code point and by case | DuckDB's own binary comparison, no collation |
| `Text.Contains` is case-sensitive | `contains()`; `Comparer.OrdinalIgnoreCase` lowers both |
| `7 / 2` is 3.5, `1 / 0` is infinity | `/` (DuckDB's float division) |
| `Number.Round` rounds halves to even | `round_even()`; `RoundingMode.AwayFromZero` is `round()` |
| Positions count from 0 (`Text.Middle`, `{0}`) | `substr(x, n + 1)`, `OFFSET n` |
| A sort puts null first going up | `ASC NULLS FIRST`, `DESC NULLS LAST` |
| A join's keys match null with null | `ON l.k IS NOT DISTINCT FROM r.k` |
| `List.Count` counts nulls, `List.Sum` skips them | `count(*)`, `sum()` |
| `try Number.From([c]) otherwise y`: y on an error, null kept | `CASE WHEN c IS NULL THEN NULL ELSE COALESCE(TRY_CAST(c AS DOUBLE), y) END` |
| `try x otherwise y`, any other x | `CASE WHEN g IS NULL THEN y ELSE list_extract(g, 1) END`, g being `TRY(list_transform([0], lambda duckpq_tried: x))` |

Known differences, stated rather than hidden:

- `try x otherwise y` per row (1.1.0) catches what DuckDB raises for that row (a conversion, a cast out of
  range, a text that is no date): the otherwise value where it raises, x's own value where it does not, and a
  null that is no error stays null, as in M. What is left different:
  - **Only DuckDB's errors are errors.** Where M would raise and DuckDB answers a value or a null, the row
    keeps DuckDB's answer and the otherwise value is not taken.
  - **One type.** x and the otherwise value must fit one DuckDB type, as any column does:
    `try Number.From([t]) otherwise "bad"` keeps numbers and a text in one column in M; here DuckDB refuses it
    when it runs. Write `otherwise null`, or a value of x's type.
  - **`try x` alone** per row is M's record of the error (`[HasError, Value, Error]`): refused with its line.
  - An `error "..."` of the query's own inside the tried expression, or another table's values (a subquery),
    is refused with its line: DuckDB's TRY takes neither.
- **A `try` never hides what duckpq cannot compile (1.1.1).** There are two kinds of failure. An
  `EvaluationError` (a `PowerQueryError`) is M's own error, known while compiling: a constant that does not
  convert (`Number.From("x")`), an operator between the wrong kinds, a column, field or item that is not
  there, an `error "..."`, a file that is not there. `try` takes its otherwise for these, as M does. Every
  other `PowerQueryError` is a refusal: a function duckpq does not run, a step it cannot map, a source
  nothing resolves. M has the function and might have run it, so the otherwise value would be a guess: it is
  refused with its line, column and name through every `try`, per row or around a whole query, nested or
  not. (1.1.0 gave `try Some.Unknown([a]) otherwise 0` as 0 on every row.) Per row, the otherwise value is
  taken only where DuckDB raises for that row.
- `Text.From` of a fractional number is DuckDB's text of it (`1.0`, where M writes `1`).
- `Table.TransformColumnTypes` ignores its culture argument: a cast is DuckDB's.
- `Date.AddDays` and its kind answer a date.
- Row order: a step that depends on "the row above" (`Table.FillDown`, `Table.Distinct` by columns,
  `Table.AddIndexColumn`) numbers the rows as DuckDB hands them, which for a file or a registered table is
  their order; `Table.Group`'s groups come in no promised order (sort them).
- `Table.Pivot` without an aggregate takes the largest value where M raises an error on two.

## What is refused

A function it does not know (`functions()` lists what runs), a source nothing resolves, a step whose columns
would depend on the rows (`Table.PromoteHeaders` on anything but a file or a literal, `Table.SplitColumn`
without its new names), a group's rows kept as a nested table, a custom function that needs rows where only
SQL is. Each with its line, its column, its name and one sentence. A refusal is never caught by a `try` in
the M: only M's own errors (`EvaluationError`) are.

## Licence and credits

The grammar follows Microsoft's published M language specification
(learn.microsoft.com/powerquery-m/power-query-m-language-specification) and each function its reference page.
No code was taken from Microsoft's powerquery-parser, from pqtools or from pbi_parsers; pqtools (MIT) was read
as a cross-check of a few traps.
