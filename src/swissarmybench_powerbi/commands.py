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
    "The model as a Power BI Project in powerbi/. "
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
    "Import a .pbix as a Power BI project. "
    "A .pbix as a Power BI project: its connections, variables, tables as Source and In Power BI tabs, "
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
    "A .pbix file connection: add one, or its card. "
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
    "To finish setting up: each row, or one fix. "
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
    "Read Power BI from: published or local. "
    "Read Power BI from: published or local (Power BI Desktop); the file when neither answers. No source: "
    "what it reads now",
    opt("source", "published or local."),
)
def powerbi_source(a: dict[str, Any]) -> Any:
    if a.get("source"):
        return api.call("PUT", "/powerbi/source", {"source": a["source"]})
    return api.call("GET", "/powerbi/source")


@command(
    "powerbi_app_registration",
    "The Power BI project's app registration; set it. "
    "The Power BI project's app registration: none sent, what it is; registration (a name or none) re-points "
    "its Microsoft sources after a dry run (dry_run=true: only the list), then checks its access",
    opt("registration", "An app registration's name, or none (sign in as you)."),
    opt("dry_run", "true: only what would change.", "bool"),
)
def powerbi_app_registration(a: dict[str, Any]) -> Any:
    if not a.get("registration"):
        return api.call("GET", "/powerbi/registration")
    body = {"registration": a["registration"], "dry_run": bool(a.get("dry_run"))}
    return api.call("PUT", "/powerbi/registration", body, timeout=200)


@command(
    "powerbi_edit_files",
    "The running Power BI Desktops and their files. "
    "Edit in Power BI Desktop (Windows): the running Desktops and their open files; Live or Not open for the "
    "project's .pbix",
)
def powerbi_edit_files(a: dict[str, Any]) -> Any:
    return api.call("GET", "/powerbi/live?asked=1")


@command(
    "powerbi_edit_model",
    "The model open in Power BI Desktop (no rows). "
    "The model open in Power BI Desktop: tables, columns, measures, relationships (no rows)",
)
def powerbi_edit_model(a: dict[str, Any]) -> Any:
    return api.call("GET", "/powerbi/live/model")


@command(
    "powerbi_edit_plan",
    "Dry run of changes to the model in Power BI Desktop. "
    "The dry run of changes to the model open in Power BI Desktop, each in words and whether it can go (no "
    "changes: our relationships and measures)",
    opt(
        "changes",
        "[{kind, table, name, expression, ...}] (guide: powerbi). "
        "[{kind: measure_add|measure_change|measure_delete|relationship_add|relationship_delete|"
        "calculated_column|calculated_table|calculation_group, table, name, expression, ...}]",
        "json",
    ),
)
def powerbi_edit_plan(a: dict[str, Any]) -> Any:
    return api.call("POST", "/powerbi/live/plan", {"changes": a.get("changes") or []})


@command(
    "powerbi_edit_apply",
    "Apply changes to the model in Power BI Desktop (on Allow). "
    "Make the changes in the model open in Power BI Desktop (asks the user first; each change audited)",
    opt("changes", "As powerbi_edit_plan's (none: our relationships and measures).", "json"),
)
def powerbi_edit_apply(a: dict[str, Any]) -> Any:
    return api.call("POST", "/powerbi/live/apply", {"changes": a.get("changes") or []}, timeout=200)
