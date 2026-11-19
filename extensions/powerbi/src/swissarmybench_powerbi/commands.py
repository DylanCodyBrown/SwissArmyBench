"""The Power BI extension's agent commands (the golden rule). Opening the export in Power BI Desktop is the
user's click (it starts a program on their screen). Standard library only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.commands import Arg, Command, opt

COMMANDS: dict[str, Command] = {}
Run = Callable[[dict[str, Any]], Any]


def command(name: str, summary: str, *args: Arg) -> Callable[[Run], Run]:
    def register(run: Run) -> Run:
        COMMANDS[name] = Command(name, summary, args, run, False, False)
        return run

    return register


@command(
    "powerbi_export",
    "The model as a Power BI Project in the project's powerbi/ (none open: a zip); what went, what not, why",
    opt("tables", "Comma-separated tables (default: the ERD's)."),
    opt("name", "File name (default: the project's)."),
    opt("include_rows", "Comma-separated tables whose rows go as Parquet (asks the user)."),
    opt("dry_run", "true: only say what would go.", "bool"),
)
def powerbi_export(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("tables", "name", "include_rows") if a.get(k)}
    return api.call("POST", "/powerbi/plan" if a.get("dry_run") else "/powerbi/export", body)
