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
    opt("dry_run", "true: only say what would go (with report: the mapping it proposes).", "bool"),
    opt("report", "Use this report's pages: a .pbix, .pbit or .pbip path on this computer."),
    opt("mapping", 'The report\'s fields: {"Table.Field": "Table.Field" or null to leave it}.', "json"),
    opt("bring_measures", "false: leave the report's model measures out (default true).", "bool"),
)
def powerbi_export(a: dict[str, Any]) -> Any:
    body: dict[str, Any] = {k: a[k] for k in ("tables", "name", "include_rows", "mapping") if a.get(k)}
    if a.get("report"):
        body["report"] = {"path": a["report"]}
    if a.get("bring_measures") is False:
        body["bring_measures"] = False
    return api.call("POST", "/powerbi/plan" if a.get("dry_run") else "/powerbi/export", body)


def _quoted(name: str) -> str:
    from urllib.parse import quote

    return quote(name, safe="")


@command(
    "powerbi_import_project",
    "A .pbix as a Power BI project: its connections, variables, tables as Source and In Power BI grids, "
    "relationships, data.ipynb, measures (dry_run: the plan only; the real one asks the user)",
    opt("path", "The .pbix on this computer."),
    opt("name", "The project's name (default: the file's)."),
    opt("folder", "Where the project's folder goes (default: the projects folder)."),
    opt("dataset", 'The published dataset: {"connection", "dataset"}, or {"none": true}.', "json"),
    opt("dry_run", "true: only the plan.", "bool"),
)
def powerbi_import_project(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("path", "name", "folder", "dataset", "dry_run") if a.get(k) is not None}
    return api.call("POST", "/powerbi/import", body)


@command(
    "powerbi_file",
    "A Power BI file (.pbix) connection: add one (name and path), or its card (name only): tables, as of, "
    "read-only and why; relationships=true offers its relationships to the ERD",
    opt("name", "The connection's name."),
    opt("path", "Add: the .pbix's path (a variable allowed)."),
    opt("relationships", "true: the file's relationships into the model.", "bool"),
)
def powerbi_file(a: dict[str, Any]) -> Any:
    if a.get("path"):
        return api.call("POST", "/powerbi/file-connection", {"name": a.get("name"), "path": a["path"]})
    if a.get("relationships"):
        return api.call("POST", f"/powerbi/file-connection/{_quoted(str(a.get('name')))}/relationships", {})
    return api.call("GET", f"/powerbi/file-connection/{_quoted(str(a.get('name')))}")


@command(
    "powerbi_setup_status",
    "The Power BI project's To finish setting up, each row with its fix; with action, one fix (dataset with "
    "connection and dataset, not_published, registration); sign-ins and passwords are the user's",
    opt("action", "dataset, not_published or registration."),
    opt("connection", "dataset: the workspace connection."),
    opt("dataset", "dataset: the dataset's name."),
    opt("registration", "registration: its name, or none."),
)
def powerbi_setup_status(a: dict[str, Any]) -> Any:
    if not a.get("action"):
        return api.call("GET", "/powerbi/setup")
    body = {k: a[k] for k in ("action", "connection", "dataset", "registration") if a.get(k)}
    return api.call("POST", "/powerbi/setup", body)


@command(
    "powerbi_source",
    "Read Power BI from: published or local (Power BI Desktop); the file when neither answers. No source: "
    "what it reads now",
    opt("source", "published or local."),
)
def powerbi_source(a: dict[str, Any]) -> Any:
    if a.get("source"):
        return api.call("PUT", "/powerbi/source", {"source": a["source"]})
    return api.call("GET", "/powerbi/source")
