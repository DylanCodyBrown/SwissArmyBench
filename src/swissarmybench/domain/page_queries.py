"""A Streamlit page's SQL and DAX blocks (the canvas, 2026-11-19: "did we add DAX cells to the canvas?"):
the page values a query names (`{{ region }}`), read by the same text the page runs, and sab_queries.py,
the module beside the pages: the connections a script export would write out, then the page's own `sql`
and `dax` (each value bound, never pasted; cached by Streamlit). Pure rules, no I/O."""

from __future__ import annotations

import re
from dataclasses import dataclass

from swissarmybench.domain import script_export as exporter
from swissarmybench.domain import script_runtime as runtime

# The page values a query names (`{{ region }}`), read by the same text the page runs (sab_queries.py).
_PAGE: dict[str, object] = {"re": re, "Any": object}
exec(compile(runtime.PAGE_PARTS, "sab_queries.py", "exec"), _PAGE)  # noqa: S102 (our own text, read once)


def page_split(query: str, dax: bool = False) -> list[str | tuple[str]]:
    """A query as its text and its page values (`("region",)`), as sab_queries.py reads it."""
    found = _PAGE["page_parts"]
    return list(found(query, dax))  # type: ignore[operator]


def page_names(query: str, dax: bool = False) -> list[str]:
    """The page values a SQL or DAX query names: `{{ name }}` outside its strings and comments."""
    found = _PAGE["page_names"]
    return list(found(query, dax))  # type: ignore[operator]


# ===== a Streamlit page's SQL and DAX blocks: their connections as one module beside the pages =====

QUERY_MODULE: str = "sab_queries"
QUERY_FILE: str = f"{QUERY_MODULE}.py"


@dataclass(frozen=True)
class QueryModule:
    """sab_queries.py: what the pages' SQL and DAX blocks call (`sql`, `dax`), with each connection
    they name written out as this exporter writes it for a script (its own code, its settings read from
    the environment, a password never written). Its requirements, settings and what it could not take."""

    text: str
    requirements: tuple[str, ...]
    settings: tuple[dict[str, object], ...]
    problems: tuple[exporter.Problem, ...]


def query_module(made: exporter.Plan) -> QueryModule:
    """The plan of a page's SQL and DAX cells (`plan` over them) as sab_queries.py: the connections,
    vaults and helpers a script would hold, then the page's own `sql` and `dax` (the page's values bound,
    never pasted; cached by Streamlit). Settings are read from the environment when a query runs."""
    shared = exporter._shared(made)
    out = [
        '"""Written by Swiss Army Bench: the connections the SQL and DAX blocks of these pages query, each',
        "one's own code as saved in the app, and how a page's values go with a query (bound, never pasted",
        "into its text). No password is written here: each is read from the environment. Change the",
        'connections in the app, not this file."""',
        "",
        "from __future__ import annotations",
        "",
        runtime.IMPORTS,
        "",
        f"log = logging.getLogger({QUERY_MODULE!r})",
        "",
        shared.settings_text,
        "",
        "",
        shared.helpers,
    ]
    if made.pieces:
        out += ["", "", "\n\n\n".join(shared.pieces), "", "", shared.registry]
    out += ["", "", runtime.PAGE_PARTS.strip("\n"), "", "", runtime.PAGE_QUERIES.strip("\n"), ""]
    _, listed = runtime.settings_block(made.settings)
    requirements = dict(shared.requirements)
    requirements.pop("streamlit", None)  # the page's own
    return QueryModule("\n".join(out), tuple(requirements.values()), tuple(listed), made.problems)
