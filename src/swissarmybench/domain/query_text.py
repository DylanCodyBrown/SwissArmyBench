"""A query's SQL formatted for reading (the Queries window, the user's only): one clause a line, indented,
keywords in capitals, in the query's own dialect (sqlglot's pretty printer); DAX and text that does not
parse as written; `${NAME}` never resolved."""

from __future__ import annotations

import re

import sqlglot

_SQLGLOT_DIALECTS: dict[str, str] = {
    "sqlserver": "tsql",
    "dataverse": "tsql",
    "postgres": "postgres",
    "mysql": "mysql",
    "sqlite": "sqlite",
    "duckdb": "duckdb",
    "snowflake": "snowflake",
    "oracle": "oracle",
    "trino": "trino",
    "onelake": "duckdb",
    "datalake": "duckdb",
    "delta": "duckdb",
    "": "duckdb",
}
_VARIABLE = re.compile(r"\$\$?\{[^}\n]*\}")


def format_sql(text: str, dialect: str = "") -> str:
    """The SQL as one clause a line, indented, keywords in capitals (sqlglot's pretty printer in the query's
    own dialect). DAX, an unknown dialect, and text that does not parse come back as written; `${NAME}`
    stays as written, never resolved."""
    key = (dialect or "").strip().lower()
    if key in ("dax", "other", "sharepoint", "sharepoint_docs") or not text.strip():
        return text
    target = _SQLGLOT_DIALECTS.get(key)
    if target is None:
        return text
    found: list[str] = []

    def hide(match: re.Match[str]) -> str:
        found.append(match.group(0))
        return f"__sab_variable_{len(found) - 1}__"

    hidden = _VARIABLE.sub(hide, text)
    try:
        statements = sqlglot.parse(hidden, read=target)
        if not statements or any(s is None for s in statements):
            return text
        pretty = ";\n\n".join(s.sql(dialect=target, pretty=True) for s in statements if s is not None)
    except Exception:  # a query sqlglot cannot read is shown as it came
        return text
    for number, original in enumerate(found):
        marker = f"__sab_variable_{number}__"
        if marker not in pretty:
            return text
        pretty = pretty.replace(marker, original)
    return pretty
