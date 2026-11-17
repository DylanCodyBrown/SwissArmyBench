"""The Accounting extension's agent commands (the golden rule: everything the Excel canvas and the
statements dialog do, the agent does too). The base's registry (cli/commands.py) takes them when the
extension is on, so each is an MCP tool and a `sab` command. Standard library only.

  workbook_*    a workbook design: open or new, read, write whole, sheets, blocks, Play, save, export
  template_*    templates from existing workbooks: import, show, bind or unbind a place
  statements_*  build statements and invoices (a dry run unless dry_run is false: the real build is the
                same request after its dry run, and waits for the user's Allow), and the register
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from swissarmybench.cli import api
from swissarmybench.cli.commands import Arg, Command, opt, req

COMMANDS: dict[str, Command] = {}


Run = Callable[[dict[str, Any]], Any]


def command(name: str, summary: str, *args: Arg, values: bool = False) -> Callable[[Run], Run]:
    def register(run: Run) -> Run:
        COMMANDS[name] = Command(name, summary, args, run, values, False)
        return run

    return register


def _q(value: Any) -> str:
    return quote(str(value), safe="")


def _d(a: dict[str, Any]) -> str:
    return f"/accounting/designs/{_q(a['workbook'])}"


WORKBOOK = req("workbook", "The open design's id (workbook_open gives it).")


@command(
    "workbook_open",
    "Open a workbook design (workbook.design.json) or start a new one: its id, sheets, blocks, the tables it reads",
    opt("path", "A workbook.design.json to open."),
    opt("title", "A new workbook's title (no path)."),
)
def workbook_open(a: dict[str, Any]) -> Any:
    body = {"path": a["path"]} if a.get("path") else {"title": a.get("title") or ""}
    return api.call("POST", "/accounting/designs", body)


@command(
    "workbook_design",
    "A workbook design as it stands: sheets, blocks, the tables it reads, problems",
    WORKBOOK,
)
def workbook_design(a: dict[str, Any]) -> Any:
    return api.call("GET", _d(a))


@command(
    "workbook_set_design",
    "Replace a workbook's whole design: {title, sheets: [{name, freeze, print, blocks: [{kind: title|text|table|pivot|chart, cell, ...}]}]}",
    WORKBOOK,
    req("design", "The design (as workbook_design shows it).", "json"),
)
def workbook_set_design(a: dict[str, Any]) -> Any:
    return api.call("PUT", _d(a), {"design": a["design"]})


@command(
    "workbook_sheet",
    "Add, change or remove a sheet: action add (name), change (name, freeze, tab_colour, print, index), remove",
    WORKBOOK,
    req("action", "add, change or remove."),
    opt("sheet", "The sheet (its id or name): change, remove."),
    opt(
        "changes",
        '{"name": "Treaties", "freeze": "A2", "print": {"orientation": "landscape", "fit_width": true}}',
        "json",
    ),
)
def workbook_sheet(a: dict[str, Any]) -> Any:
    action = a["action"]
    if action == "add":
        return api.call("POST", f"{_d(a)}/sheets", {"name": (a.get("changes") or {}).get("name")})
    if not a.get("sheet"):
        raise api.CommandError("Name the sheet (its id or name).")
    path = f"{_d(a)}/sheets/{_q(a['sheet'])}"
    if action == "change":
        return api.call("PATCH", path, a.get("changes") or {})
    if action == "remove":
        return api.call("DELETE", path)
    raise api.CommandError("action is add, change or remove.")


@command(
    "workbook_block",
    "Place, change (move: cell or sheet; size: w, h) or remove a block. Kinds: title, text (text), table (source "
    "{table} or {query}, columns [{name, format, width, total}], total_row, conditional), pivot (source, rows, "
    "columns, values [{column, agg, format}], totals), chart (chart bar|column|line|pie|combo, from: a table or "
    "pivot block, category, series, line_series, title)",
    WORKBOOK,
    req("action", "add, change or remove."),
    opt("sheet", "add: the sheet (its id or name)."),
    opt("block", "change, remove: the block's id."),
    opt(
        "fields",
        '{"kind": "pivot", "cell": "H4", "source": {"table": "cessions"}, "rows": ["treaty"], ...}',
        "json",
    ),
)
def workbook_block(a: dict[str, Any]) -> Any:
    action = a["action"]
    if action == "add":
        if not a.get("sheet"):
            raise api.CommandError("Name the sheet the block goes on.")
        return api.call("POST", f"{_d(a)}/sheets/{_q(a['sheet'])}/blocks", a.get("fields") or {})
    if not a.get("block"):
        raise api.CommandError("Name the block (its id).")
    path = f"{_d(a)}/blocks/{_q(a['block'])}"
    if action == "change":
        return api.call("PATCH", path, a.get("fields") or {})
    if action == "remove":
        return api.call("DELETE", path)
    raise api.CommandError("action is add, change or remove.")


@command(
    "workbook_play",
    "Build the workbook from the open tables (each with its grid's steps) and show it: each sheet's cells as built",
    WORKBOOK,
    opt("rows", "Rows of each sheet to return (default 30).", "int"),
    values=True,
)
def workbook_play(a: dict[str, Any]) -> Any:
    done = api.call("POST", f"{_d(a)}/play")
    keep = int(a.get("rows") or 30)
    for sheet in (done.get("preview") or {}).get("sheets", []):
        sheet["rows"] = [[(c or {}).get("t", "") for c in row] for row in sheet["rows"][:keep]]
    return done


@command(
    "workbook_save",
    "Save a workbook's design (workbook.design.json: sheets, blocks, bindings; no data)",
    WORKBOOK,
    opt("path", "Where (Save as; needed for a new one)."),
)
def workbook_save(a: dict[str, Any]) -> Any:
    return api.call("POST", f"{_d(a)}/save", {"path": a["path"]} if a.get("path") else {})


@command(
    "workbook_export",
    "Export workbook.py beside the design: the automation that builds the same workbook from data.py, anywhere",
    WORKBOOK,
    opt("folder", "Another folder for workbook.py."),
)
def workbook_export(a: dict[str, Any]) -> Any:
    return api.call("POST", f"{_d(a)}/export", {"folder": a["folder"]} if a.get("folder") else {})


@command(
    "template_import",
    "Import an existing workbook (a statement, an invoice) as the project's template: templates/<name>.xlsx, its layout, formats, merged cells and named ranges kept",
    req("source", "The .xlsx to import."),
    opt("name", "The template's name (default: the file's)."),
    opt("folder", "The project's folder (default: the open project)."),
)
def template_import(a: dict[str, Any]) -> Any:
    return api.call(
        "POST", "/accounting/templates/import", {k: a[k] for k in ("source", "name", "folder") if a.get(k)}
    )


@command(
    "template_show",
    "A template: its sheets' cells, named ranges, bindings, the columns they need; without name, the project's templates",
    opt("name", "The template's name."),
    opt("folder", "The project's folder (default: the open project)."),
    values=True,
)
def template_show(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("name", "folder") if a.get(k)}
    if not a.get("name"):
        return api.call("POST", "/accounting/templates", body)
    done = api.call("POST", "/accounting/templates/show", body)
    for sheet in (done.get("preview") or {}).get("sheets", []):
        sheet["rows"] = [[(c or {}).get("t", "") for c in row] for row in sheet["rows"][:60]]
    return done


@command(
    "template_bind",
    "Bind a template's place to data: value {column}|{text}|{number: true}|{date: true} (format), or a table (columns, rows, grow); unbind frees one",
    req("name", "The template's name."),
    opt(
        "binding",
        '{"kind": "value", "place": "Cedant", "value": {"column": "cedant"}} or {"kind": "table", "place": "Statement!A12", "columns": [...]}',
        "json",
    ),
    opt("unbind", "A place to free."),
    opt("folder", "The project's folder (default: the open project)."),
)
def template_bind(a: dict[str, Any]) -> Any:
    return api.call(
        "POST",
        "/accounting/templates/bind",
        {k: a[k] for k in ("name", "binding", "unbind", "folder") if a.get(k)},
    )


@command(
    "statements_build",
    "Build statements or invoices from a template: one per group of data, lines joined on key, named, numbered, "
    "dated. A dry run (the files, rows, totals; nothing written) unless dry_run is false, which needs that dry run "
    "first and the user's Allow: only when the user said to build",
    req("template", "The template's name."),
    req("data", "An open table: one row per group (party, contract, period)."),
    opt("lines", "An open table of line items, joined on key."),
    opt("group_by", '["cedant", "period"]', "json"),
    opt("key", "The lines' join columns (default: group_by).", "json"),
    opt("name", "The file name pattern: {cedant} {period}.xlsx."),
    opt("number", '{"start": 1001, "pattern": "INV-{n:05d}"}', "json"),
    opt("date", "The statements' date, YYYY-MM-DD (default today)."),
    opt("one_workbook", "true: one workbook, a sheet per group.", "bool"),
    opt("out_folder", "Where (default: the project's statements/)."),
    opt("dry_run", "false: write the files (after the dry run, on the user's word).", "bool"),
)
def statements_build(a: dict[str, Any]) -> Any:
    keys = (
        "template",
        "data",
        "lines",
        "group_by",
        "key",
        "name",
        "number",
        "date",
        "one_workbook",
        "out_folder",
    )
    body: dict[str, Any] = {k: a[k] for k in keys if a.get(k) is not None}
    body["dry_run"] = a.get("dry_run") is not False
    return api.call("POST", "/accounting/build", body)


@command(
    "statements_register",
    "What was built in a folder (its register.csv: file, group, number, rows, totals, when); open: as a grid",
    opt("out_folder", "The folder (default: the project's statements/)."),
    opt("open", "true: open the register as a grid.", "bool"),
    values=True,
)
def statements_register(a: dict[str, Any]) -> Any:
    return api.call(
        "POST", "/accounting/register", {k: a[k] for k in ("out_folder", "open") if a.get(k) is not None}
    )
