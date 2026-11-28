"""The agent's workbench_* commands: workbench: notebooks, scripts, kernels, environments.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

import re
from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.api import CommandError
from swissarmybench.cli.command_kit import _q, command, opt, req


@command("workbench_home", "Where the Workbench saves by default, and the recent files")
def workbench_home(a: dict[str, Any]) -> Any:
    return api.call("GET", "/workbench/home")


@command(
    "workbench_open",
    "A notebook's cells (with their outputs) or a script's text, and its remembered Python",
    req("path", "An .ipynb, .py, .sql or .pq file."),
    values=True,
)
def workbench_open(a: dict[str, Any]) -> Any:
    return api.call("POST", "/workbench/open", {"path": a["path"]})


@command(
    "workbench_fine_tune",
    "Fine-tune as a script: an open table's transformations (its load and its steps as one DuckDB query) as "
    "a new script in the project's scripts/, opened on the Scripts page",
    req("table", "The open table's name."),
)
def workbench_fine_tune(a: dict[str, Any]) -> Any:
    return api.call("POST", "/scripts/fine-tune", {"table": a["table"]})


@command(
    "workbench_outline",
    "A module's outline as typed: its classes, methods, functions and constants with their lines",
    req("text", "The module's text."),
)
def workbench_outline(a: dict[str, Any]) -> Any:
    return api.call("POST", "/project/module-outline", {"text": a["text"]})


def _at(a: dict[str, Any]) -> dict[str, Any]:
    keys = ("text", "line", "column", "path")
    return {k: a[k] for k in keys if a.get(k) is not None}


@command(
    "workbench_definition",
    "Go to definition (F12): where the name at line/column is defined (project or libraries)",
    req("text", "The script's text."),
    req("line", "The line, from 1.", "int"),
    req("column", "The column, from 1.", "int"),
    opt("path", "The script's file."),
    opt("source", "A library's text too.", "bool"),
)
def workbench_definition(a: dict[str, Any]) -> Any:
    return api.call("POST", "/scripts/definition", _at(a) | ({"source": True} if a.get("source") else {}))


@command(
    "workbench_references",
    "Find all references (Shift+F12): every use of the name at line/column across the project's scripts",
    req("text", "The script's text."),
    req("line", "The line, from 1.", "int"),
    req("column", "The column, from 1.", "int"),
    opt("path", "The script's file."),
)
def workbench_references(a: dict[str, Any]) -> Any:
    return api.call("POST", "/scripts/references", _at(a))


@command(
    "workbench_rename",
    "Rename a symbol across the project's scripts (F2): the plan (each change, the made files skipped), "
    "or written with apply (said in the Session log)",
    req("text", "The script's text."),
    req("line", "The line, from 1.", "int"),
    req("column", "The column, from 1.", "int"),
    req("to", "The new name."),
    opt("path", "The script's file."),
    opt("apply", "Write the changes.", "bool"),
)
def workbench_rename(a: dict[str, Any]) -> Any:
    return api.call("POST", "/scripts/rename", _at(a) | {"to": a["to"], "apply": bool(a.get("apply"))})


@command(
    "workbench_debug",
    "Debug a script in its kernel; action: start, state, breakpoints, over, into, out, continue, "
    "variables, evaluate, stop",
    req("action", "What to do."),
    req("document", "The script's file."),
    opt("code", "start: its text."),
    opt("breakpoints", "[{line, condition?, log?}]", "json"),
    opt("expression", "evaluate this."),
)
def workbench_debug(a: dict[str, Any]) -> Any:
    act = a["action"]
    body = {"document": a["document"]} | {
        k: a[k] for k in ("code", "breakpoints", "expression") if a.get(k) is not None
    }
    if act == "state":
        return api.call("GET", "/workbench/debug", params={"document": a["document"]})
    if act in ("over", "into", "out", "continue"):
        return api.call("POST", "/workbench/debug/step", body | {"action": act})
    routes = {
        "start": "/workbench/debug/start",
        "breakpoints": "/workbench/debug/breakpoints",
        "variables": "/workbench/debug/variables",
        "evaluate": "/workbench/debug/evaluate",
        "stop": "/workbench/debug/stop",
    }
    if act not in routes:
        return {
            "error": "action: start, state, breakpoints, over, into, out, continue, variables, evaluate, stop."
        }
    return api.call("POST", routes[act], body)


def _scripts_window(command_id: str, path: Any) -> Any:
    """A command of the Scripts page's window on a file's tab (its tab brought forward first)."""
    body = {"command": command_id, "args": {"path": path} if path else {}, "page": "scripts"}
    return api.call("POST", "/workbench/window", body)["result"]


@command(
    "workbench_file",
    "Files. new: a named file with its type's starter (types: the list, by the project's type; no project: "
    "path is a whole folder). blocks, edit_block: a Markdown file's blocks, one replaced, added or its task "
    "ticked. view, export: a Scripts tab's preview, split or source; its diagram saved as svg or png. "
    "Modules: move (a plan until apply), package, duplicate. rename: in its folder",
    req("action", "new, types, blocks, edit_block, view, export, move, package, duplicate or rename."),
    opt("path", "The file (new: its folder; package: its parent)."),
    opt("to", "The new name; edit_block: the block's text; view: preview, split or source."),
    opt("apply", "move: do it.", "bool"),
    opt("type", "new: a type's id (default python)."),
    opt("connection", "new sql: where it runs (none: DuckDB)."),
    opt("variant", "new diagram: flowchart, class, sequence, state, er, gantt."),
    opt("block", "edit_block: the block's index.", "int"),
    opt("task", "edit_block: tick this task box (from 0).", "int"),
    opt("done", "With task: ticked or cleared (none: switched).", "bool"),
    opt("after", "edit_block: add `to` after the block (-1: top).", "bool"),
    opt("format", "export: svg or png."),
)
def workbench_file(a: dict[str, Any]) -> Any:
    act = a["action"]
    if act == "types":
        return api.call("GET", "/scripts/files/new")
    if act == "new":
        if not str(a.get("to") or "").strip():
            return {"error": "Give the file a name (to): a new file is made only once it is named."}
        body = {"type": a.get("type"), "name": a.get("to"), "folder": a.get("path")}
        more = {k: a[k] for k in ("variant",) if a.get(k)}
        return api.call("POST", "/scripts/files/new", body | {"connection": a.get("connection")} | more)
    if act == "blocks":
        found = api.call("POST", "/workbench/markdown", {"path": a.get("path")})
        return {"title": found["title"], "blocks": found["blocks"]}
    if act == "edit_block":
        keys = ("path", "block", "to", "task", "done", "after")
        done = api.call("POST", "/workbench/markdown", {k: a[k] for k in keys if a.get(k) is not None})
        return {k: done[k] for k in ("changed", "written", "blocks")}
    if act == "view":
        return _scripts_window("view." + str(a.get("to") or "preview"), a.get("path"))
    if act == "export":
        name = "preview.savePng" if a.get("format") == "png" else "preview.saveSvg"
        return _scripts_window(name, a.get("path"))
    if act == "rename":
        return api.call("POST", "/workbench/rename", {"path": a.get("path"), "to": a.get("to")})
    if act == "package":
        return api.call("POST", "/scripts/files/package", {"name": a.get("to"), "parent": a.get("path")})
    body = {"path": a.get("path"), "to": a.get("to"), "apply": bool(a.get("apply"))}
    if act == "move":
        return api.call("POST", "/scripts/files/move", body)
    if act == "duplicate":
        return api.call("POST", "/scripts/files/duplicate", body)
    return {
        "error": "action: new, types, blocks, edit_block, view, export, move, package, duplicate or rename."
    }


@command(
    "workbench_sql",
    "A .sql file (the Scripts page's SQL): run builds the open table named after the file (orders_by_month.sql: "
    "orders_by_month; run again replaces it, its steps kept) on the file's `-- connection: <name>` (none: DuckDB "
    "over the open tables and [Conn].table names); a failure names its line. for_table: a table a query made "
    "as its file (Edit in Scripts), its path. A Power Query file (path ending .pq or .m): run builds each query "
    "that is a table as the open table of its name, from its original sources; problems: what cannot run "
    "(line, column), nothing read; sql: the DuckDB SQL composed",
    req("action", "run or for_table; a .pq file: run, problems or sql."),
    opt("path", "The .sql or .pq file (its text read when text is not sent)."),
    opt("text", "run: the SQL or M (unsaved text wins over the file's)."),
    opt("connection", 'run: where it runs ("" the open tables), else the file\'s header.'),
    opt("line", "run: the statement (a .pq file: the query) at this line; none: Run file.", "int"),
    opt("table", "run: the table's name (default: the file's name); for_table: the table."),
    opt("query", "A .pq file: one query by its name."),
)
def workbench_sql(a: dict[str, Any]) -> Any:
    if a["action"] == "for_table":
        return api.call("POST", "/scripts/sql/for-table", {"table": a.get("table")})
    if str(a.get("path") or "").lower().endswith((".pq", ".m")):
        paths = {"run": "/scripts/pq/run", "problems": "/scripts/pq/problems", "sql": "/scripts/pq/sql"}
        if a["action"] not in paths:
            return {"error": "action: run, problems or sql."}
        body = {k: a[k] for k in ("path", "text", "query", "line") if a.get(k) is not None}
        return api.call("POST", paths[a["action"]], body)
    if a["action"] != "run":
        return {"error": "action: run or for_table (problems and sql: a .pq file's)."}
    body = {k: a[k] for k in ("path", "text", "connection", "line", "table") if a.get(k) is not None}
    return api.call("POST", "/scripts/sql/run", body)


@command(
    "workbench_search",
    "Search across the project's scripts (regex, case, whole word); with to: replace's plan, or applied",
    req("query", "The text (or a regular expression with regex)."),
    opt("to", "Replace with this (the plan; apply writes it)."),
    opt("regex", "A regular expression.", "bool"),
    opt("case", "Match case.", "bool"),
    opt("word", "Whole word.", "bool"),
    opt("apply", "With to: write the replacements.", "bool"),
)
def workbench_search(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("query", "to", "regex", "case", "word", "apply") if a.get(k) is not None}
    return api.call("POST", "/scripts/replace" if "to" in body else "/scripts/search", body)


@command(
    "workbench_format",
    "Format a script's text with Ruff in its own Python (said when Ruff is not there)",
    req("text", "The script's text."),
    opt("python", "The script's Python."),
)
def workbench_format(a: dict[str, Any]) -> Any:
    return api.call("POST", "/scripts/format", {k: a[k] for k in ("text", "python") if a.get(k)})


@command(
    "workbench_save",
    "Save a notebook's cells or a script's text (refused if changed on disk since modified, unless force)",
    req("path", "An .ipynb, .py, .sql or .pq file."),
    opt(
        "cells",
        '[{"kind": "code" | "sql" | "dax" | "html" | "markdown", "source", "connection"?, "outputs"?, "height"?}]',
        "json",
    ),
    opt("text", "A script's text."),
    opt("modified", "The modified time workbench_open gave.", "any"),
    opt("force", "Replace it even if it changed on disk.", "bool"),
    opt("next_cell", "A notebook's next cell number, as workbench_open gave it.", "int"),
)
def workbench_save(a: dict[str, Any]) -> Any:
    keys = ("path", "cells", "text", "modified", "force", "pages", "next_cell")
    body = {k: a[k] for k in keys if a.get(k) is not None}
    return api.call("POST", "/workbench/save", body)


@command(
    "workbench_export_script",
    "Export a notebook or script as ONE .py that runs with plain python anywhere (an Azure Function too), "
    "or as one linear .ipynb: its connections, vault lookups and table steps written out, no passwords, no rows",
    req("path", "The notebook (.ipynb) or script (.py)."),
    opt("format", "script (one .py, the default) or notebook (one self-contained .ipynb)."),
    opt("to", "Where it goes (default: beside it, <name>_automation.py or .ipynb)."),
    opt("stub", "Export the rest when a cell cannot be: each such cell a stub that raises FILL IN.", "bool"),
    opt("check", "Write nothing: the text, and what would stop it.", "bool"),
)
def workbench_export_script(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("path", "format", "to", "stub", "check") if a.get(k) is not None}
    return api.call("POST", "/workbench/export-script", body)


@command("workbench_pythons", "The Pythons a kernel can run in: version, ipykernel, the package")
def workbench_pythons(a: dict[str, Any]) -> Any:
    return api.call("GET", "/workbench/pythons")


@command(
    "workbench_kernel_start",
    "Start a kernel (every connection is a variable by its name in it); its id. With a project open it is "
    "the project's ONE Python session, shared by every notebook and script of the project (session.shared)",
    opt("python", "The Python (default: the app's own). A project's session runs in the project's own."),
    opt(
        "path", "The document it runs (its folder is the working folder; a loose file: a kernel of its own)."
    ),
    opt("own", "true: a kernel of its own even while a project is open (no document only).", "bool"),
)
def workbench_kernel_start(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("python", "path") if a.get(k)}
    # No document: the open project's one session (the Environment's variables are that session's).
    return api.call("POST", "/workbench/kernels", body | {"project": not a.get("own")})


def _outputs(lines: list[Any]) -> dict[str, Any]:
    """A run's outputs, made readable: text joined, pictures named not sent, tracebacks without colour."""
    shown: list[Any] = []
    done: Any = None
    for item in lines:
        if "done" in item:
            done = item["done"]
        elif item.get("output_type") == "stream":
            if shown and shown[-1].get("stream") == item["name"]:
                shown[-1]["text"] += item["text"]
            else:
                shown.append({"stream": item["name"], "text": item["text"]})
        elif item.get("output_type") == "error":
            shown.append(
                {
                    "error": f"{item.get('ename')}: {item.get('evalue')}",
                    "traceback": re.sub(r"\x1b\[[0-9;]*m", "", "\n".join(item.get("traceback", [])))[-4000:],
                }
            )
        elif item.get("output_type") in ("execute_result", "display_data"):
            data = item.get("data", {})
            cell = data.get("application/vnd.swissarmybench.html-cell+json")
            if isinstance(cell, dict):
                # An HTML cell's run: the design with its names filled, and what filled it (the values
                # go back to workbench_html_fill as they are; the marks to workbench_html_marks).
                shown.append(
                    {
                        "design": str(data.get("text/html", ""))[:200_000],
                        "missing": cell.get("missing", []),
                        "notes": cell.get("notes", []),
                        "marks": cell.get("marks", {}),
                        "values": cell.get("values", {}),
                    }
                )
                continue
            shown.append({"result": data.get("text/plain", ""), "kinds": sorted(data)})
        elif "input_request" in item:
            shown.append(
                {"waiting_for_input": item["input_request"]["prompt"], "answer_with": "workbench_input"}
            )
        elif "error_detail" in item:
            # The error panel's reading: where in the user's code, what it means, the fixes, and the
            # failing expression's values (each a short preview).
            detail = item["error_detail"]
            last = (detail.get("chain") or [{}])[-1]
            frames = last.get("frames") or []
            yours = last.get("your_frame")
            frame = frames[yours] if isinstance(yours, int) and 0 <= yours < len(frames) else {}
            shown.append(
                {
                    "error_explained": last.get("explanation", ""),
                    "where": detail.get("where"),
                    "fixes": [f.get("title") for f in last.get("fixes", [])],
                    "values": frame.get("values", []),
                    "chain": [f"{e.get('type')}: {e.get('message')}" for e in detail.get("chain", [])],
                    # A package missing from the kernel's Python: what the user's prompt says.
                    **({"missing": detail["missing"]} if detail.get("missing") else {}),
                }
            )
    for part in shown:
        if "text" in part and len(part["text"]) > 20_000:
            part["text"] = part["text"][:10_000] + "\n… (cut) …\n" + part["text"][-10_000:]
    return {"outputs": shown, "done": done}


@command(
    "workbench_run",
    "Run code in a kernel (kind sql: a SQL cell on its connection; kind dax: a DAX cell on a Power BI "
    "workspace's dataset; kind file: a script as python would; kind table: a table's cell; kind html: an "
    "HTML cell, its {{ names }} filled from the kernel)",
    req("kernel", "The kernel's id."),
    opt(
        "code",
        "Python; SQL with kind sql; DAX with kind dax; an unsaved script's text with kind file; HTML "
        "with kind html.",
    ),
    opt("kind", "code (default), sql, dax, file, table or html."),
    opt("connection", "A SQL cell's connection; a DAX cell's dataset: `Finance/Sales model`."),
    opt("table", "kind table: the table (its cell starts from the table as made, so a rerun is safe)."),
    opt("path", "kind file: a saved script to run (its __file__)."),
    opt("args", "kind file: its command-line arguments (sys.argv)."),
    opt("document", "The document the code runs for (a project's one session runs every document's)."),
    values=True,
)
def workbench_run(a: dict[str, Any]) -> Any:
    keys = ("code", "kind", "connection", "path", "args", "table", "document")
    body = {k: a[k] for k in keys if a.get(k) is not None}
    # This call waits for the run's end, so it could never answer input(): there input() raises instead.
    body["stdin"] = False
    return _outputs(api.call_lines("POST", f"/workbench/kernels/{_q(a['kernel'])}/execute", body))


@command(
    "workbench_script_settings",
    "A script's run settings: arguments, the variables it needs and each one's source (never a value); "
    "with set, change them",
    req("path", "The script (.py)."),
    opt(
        "set",
        '{"arguments": "--region all", "variables": [{"name": "REPORT_FOLDER", "from": "env"}, '
        '{"name": "HOST", "from": "value", "value": "db1"}, {"name": "PASSWORD", "from": "vault", '
        '"vault": "Team vault", "secret": "warehouse-password"}]}',
        "json",
    ),
)
def workbench_script_settings(a: dict[str, Any]) -> Any:
    if a.get("set") is not None:
        if not isinstance(a["set"], dict):
            raise CommandError('set is {"arguments": "...", "variables": [...]}.')
        return api.call("PUT", "/workbench/scripts/settings", {"path": a["path"], **a["set"]})
    return api.call("GET", f"/workbench/scripts/settings?path={_q(a['path'])}")


@command(
    "workbench_input",
    "Answer a run the user started that waits at input(), getpass or pdb",
    req("kernel", "The kernel's id."),
    req("value", "The line to type."),
)
def workbench_input(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/workbench/kernels/{_q(a['kernel'])}/input", {"value": a["value"]})


@command(
    "workbench_is_complete",
    "Whether code is a whole statement yet (complete, incomplete with its indent, or invalid)",
    req("kernel", "The kernel's id."),
    req("code", "The code."),
)
def workbench_is_complete(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/workbench/kernels/{_q(a['kernel'])}/is-complete", {"code": a["code"]})


def _intel_body(a: dict[str, Any]) -> dict[str, Any]:
    body = {"text": a["code"], "line": a["line"], "column": a["column"]}
    for key in ("kernel", "path", "notebook"):
        if a.get(key) is not None:
            body[key] = a[key]
    return body


_INTEL_ARGS = (
    req("code", "The cell's or script's text."),
    req("line", "The cursor's line (1-based).", "int"),
    req("column", "The cursor's column (1-based).", "int"),
    opt("kernel", "The document's kernel: its live names (Jedi's Interpreter)."),
    opt("path", "The document's path (its project's modules)."),
    opt("notebook", "A notebook cell (IPython's lines allowed).", "bool"),
)


@command(
    "workbench_complete",
    "What the editor's member list offers at a place: names ranked, each with its kind, signature and "
    "docs; the app's names inside strings (connections, variables, blades); a project module's import",
    *_INTEL_ARGS,
)
def workbench_complete(a: dict[str, Any]) -> Any:
    return api.call("POST", "/workbench/intel/complete", _intel_body(a))


@command(
    "workbench_signature",
    "Parameter info for the call at a place (each signature, the active parameter, each one's words), "
    "or with hover the docs and type of the name there",
    *_INTEL_ARGS,
    opt("hover", "The name's docs and type instead.", "bool"),
)
def workbench_signature(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/workbench/intel/{'hover' if a.get('hover') else 'signature'}", _intel_body(a))


@command(
    "workbench_problems",
    "The problems the Workbench's editors show (syntax, undefined names, unused imports, Ruff's), each "
    "document's; with path, that file checked now",
    opt("path", "A .py or .ipynb file to check now."),
)
def workbench_problems(a: dict[str, Any]) -> Any:
    if a.get("path"):
        return api.call("GET", f"/workbench/intel/problems?path={_q(a['path'])}")
    return api.call("GET", "/workbench/intel/problems")


@command(
    "workbench_window",
    "Do what the user does in the open Workbench window: any command of its palette (Ctrl+Shift+P). "
    'command "documents" says what is open (its tab groups too); "commands" lists every command and its '
    'args; e.g. "cell.insertBelow" {"kind": "code", "source": "..."}, "run.cell", "view.focus", "doc.show", '
    '"group.splitRight", "group.moveTab" {"group": 1}, "data.goToTable" {"table": "orders"}',
    req("command", 'A command\'s id, such as "documents", "commands", "run.statement" or "cell.delete".'),
    opt("args", 'The command\'s arguments, as an object (see "commands").', "json"),
    opt("page", "notebooks or scripts (default: args.path's, else the window the user was last in)."),
)
def workbench_window(a: dict[str, Any]) -> Any:
    body = {"command": a["command"], "args": a.get("args") or {}}
    if a.get("page"):
        body["page"] = a["page"]
    return api.call("POST", "/workbench/window", body)["result"]


@command(
    "workbench_table_cells",
    "Every open table's read-only Workbench cell: its steps as one DuckDB query, its tab and kernel",
)
def workbench_table_cells(a: dict[str, Any]) -> Any:
    return api.call("GET", "/workbench/tables")


@command(
    "workbench_tables_arrange",
    "A notebook's cells or a script's text with its Tables group (the tables' cells, on top) as it should be",
    req("kind", "notebook or script."),
    opt("cells", "A notebook's cells.", "json"),
    opt("text", "A script's text."),
    opt("tables", "The document's open tables (names).", "json"),
    opt("next_cell", "A notebook's next cell number (workbench_open gave it).", "int"),
    opt("move", "false: move nothing.", "bool"),
)
def workbench_tables_arrange(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("kind", "cells", "text", "tables", "next_cell", "move") if a.get(k) is not None}
    return api.call("POST", "/workbench/tables/arrange", body)


def _window(command_id: str, args: dict[str, Any]) -> Any:
    return api.call("POST", "/workbench/window", {"command": command_id, "args": args})["result"]


@command(
    "workbench_tables",
    "The front Workbench document's tables: each one's cell, steps, and whether it is up to date",
)
def workbench_tables(a: dict[str, Any]) -> Any:
    return _window("tables.list", {})


@command(
    "workbench_table_run",
    "Run a table's cell in the front Workbench document (default: every one not up to date)",
    opt("table", "The table."),
)
def workbench_table_run(a: dict[str, Any]) -> Any:
    if a.get("table"):
        return _window("tables.run", {"table": a["table"]})
    return _window("tables.runOutOfDate", {})


@command(
    "workbench_cell_goto",
    "Go to a cell of the front Workbench document by its number (as @cell7 links to it)",
    req("number", "The cell's number.", "int"),
)
def workbench_cell_goto(a: dict[str, Any]) -> Any:
    return _window("cell.goTo", {"number": a["number"]})


@command(
    "workbench_html_add",
    "Add an HTML cell to the front Workbench document: a design drawn from its HTML; {{ name }} in it "
    "is filled from the kernel when the cell runs",
    opt("source", "The cell's HTML."),
    opt("height", "Its pane's height in pixels, 60 to 2000 (default: the design's own).", "int"),
)
def workbench_html_add(a: dict[str, Any]) -> Any:
    return _window("html.add", {k: a[k] for k in ("source", "height") if a.get(k) is not None})


@command(
    "workbench_dax_add",
    "Add a DAX cell to the front Workbench document, on one dataset of a Power BI workspace connection "
    "(a notebook: a cell of kind dax; a script: `# %% [dax]` over one sab.dax() call). Run it with "
    "workbench_window run.cell; connections_datasets lists a workspace's datasets",
    opt("dataset", "The dataset, as `Finance/Sales model` (default: the first one listed)."),
    opt("source", "The cell's DAX: EVALUATE ..."),
)
def workbench_dax_add(a: dict[str, Any]) -> Any:
    return _window("cell.addDax", {k: a[k] for k in ("dataset", "source") if a.get(k) is not None})


@command(
    "workbench_snippet_insert",
    "Insert a filled snippet into the front Workbench document: DAX, HTML or Markdown into a cell of its "
    "kind, a Streamlit piece as a named Python cell",
    req("name", "The snippet."),
    opt("values", '{"placeholder": "value"} (default: each one\'s own)', "json"),
    opt("number", "The cell's own number (default: a new cell, or the selected one).", "int"),
)
def workbench_snippet_insert(a: dict[str, Any]) -> Any:
    args = {k: a[k] for k in ("name", "values", "number") if a.get(k) is not None}
    return _window("snippet.insert", args)


@command(
    "workbench_html_cells",
    "The front Workbench document's HTML cells (and Markdown cells with names): number, text, names, "
    "height, and whether it needs a run",
)
def workbench_html_cells(a: dict[str, Any]) -> Any:
    return _window("html.list", {})


@command(
    "workbench_html_run",
    "Run an HTML cell (or a Markdown cell with names) in the front Workbench document: fill its names "
    "and draw it (default: every one "
    "that needs a run)",
    opt("number", "The cell's own number.", "int"),
)
def workbench_html_run(a: dict[str, Any]) -> Any:
    return _window("html.run", {"number": a["number"]} if a.get("number") is not None else {})


@command(
    "workbench_html_resize",
    "Size an HTML cell's pane in the front Workbench document (saved with the cell)",
    req("number", "The cell's own number.", "int"),
    opt("height", "Pixels, 60 to 2000 (without it: the design's own height).", "int"),
)
def workbench_html_resize(a: dict[str, Any]) -> Any:
    args = {"number": a["number"]} | ({"height": a["height"]} if a.get("height") is not None else {})
    return _window("html.resize", args)


@command(
    "workbench_html_fill",
    "An HTML cell's design as text: its HTML with each {{ name }} filled from a run's values (nothing runs)",
    req("html", "The cell's HTML (or a Markdown cell's text, with markdown)."),
    opt(
        "values", "{name: value} from a run's output (default: none, so every name shows as written).", "json"
    ),
    opt("markdown", "It is a Markdown cell's text: each value is written as text.", "bool"),
    values=True,
)
def workbench_html_fill(a: dict[str, Any]) -> Any:
    key = "markdown" if a.get("markdown") else "html"
    return api.call("POST", "/workbench/html/fill", {key: a["html"], "values": a.get("values") or {}})


@command(
    "workbench_html_marks",
    "A mark of what each name would draw in an HTML cell now (differs from a run's mark: out of date)",
    req("kernel", "The kernel's id."),
    req("names", 'The names, e.g. ["orders", "total"].', "json"),
)
def workbench_html_marks(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/workbench/kernels/{_q(a['kernel'])}/html-marks", {"names": a["names"]})


@command(
    "workbench_cell_copy",
    "Copy a cell of the front document (as C does)",
    opt("number", "The cell's own number (default: the selected cell).", "int"),
)
def workbench_cell_copy(a: dict[str, Any]) -> Any:
    return _window("cell.copy", {"number": a["number"]} if a.get("number") is not None else {})


@command(
    "workbench_cell_paste",
    "Paste the copied cell into the front notebook (as V does)",
)
def workbench_cell_paste(a: dict[str, Any]) -> Any:
    return _window("cell.paste", {})


@command(
    "workbench_cell_name",
    "Name a cell of the front document (its number stays its identity)",
    req("number", "The cell's own number.", "int"),
    opt("name", "One line (without it: no name)."),
)
def workbench_cell_name(a: dict[str, Any]) -> Any:
    return _window("cell.name", {"number": a["number"], "name": a.get("name") or ""})


@command(
    "workbench_lineage",
    "A cell's lineage back to the data: nodes, edges, Mermaid, each value summarised",
    opt("document", "The notebook or script (its path)."),
    opt("cell", "The cell's own number.", "int"),
    opt("values", "false: the graph alone.", "bool"),
    values=True,
)
def workbench_lineage(a: dict[str, Any]) -> Any:
    keys = ("document", "cell", "values")
    return api.call("POST", "/workbench/lineage", {k: a[k] for k in keys if a.get(k) is not None})


@command(
    "workbench_lineage_show",
    "Show the lineage overlay in the Workbench for a cell of the front document",
    opt("number", "The cell's own number (default: the selected cell).", "int"),
)
def workbench_lineage_show(a: dict[str, Any]) -> Any:
    return _window("lineage.open", {"number": a["number"]} if a.get("number") is not None else {})


@command(
    "workbench_pop_out",
    "Move the front document (unsaved text, kernel) into a Workbench window of its own",
)
def workbench_pop_out(a: dict[str, Any]) -> Any:
    return _window("doc.popOut", {})


@command("workbench_move_back", "Move the front document of a popped-out window back to the main window")
def workbench_move_back(a: dict[str, Any]) -> Any:
    return _window("doc.moveToMain", {})


@command(
    "workbench_project_open",
    "Open a project's folder in the Workbench window, its files as tabs",
    req("folder", "The project's folder."),
)
def workbench_project_open(a: dict[str, Any]) -> Any:
    return _window("project.open", {"folder": a["folder"]})


@command(
    "workbench_statement",
    "The whole statement at a script's line, as Ctrl+Enter runs it (first and last line, the next one)",
    req("code", "The script's code."),
    req("line", "A line in it (the first is 1).", "int"),
)
def workbench_statement(a: dict[str, Any]) -> Any:
    return api.call("POST", "/workbench/statement", {"code": a["code"], "line": a["line"]})


@command(
    "workbench_run_notebook",
    "Open a notebook, run every cell in a kernel (stops at an error), save it with the outputs",
    req("path", "An .ipynb file."),
    opt("kernel", "A running kernel (default: start one in the notebook's remembered Python)."),
    opt("save", "Save the outputs into the file (default true).", "bool"),
    values=True,
)
def workbench_run_notebook(a: dict[str, Any]) -> Any:
    opened = api.call("POST", "/workbench/open", {"path": a["path"]})
    kernel = (
        a.get("kernel")
        or api.call("POST", "/workbench/kernels", {"python": opened.get("python"), "path": opened["path"]})[
            "kernel"
        ]
    )
    results = []
    for cell in opened["cells"]:
        if cell["kind"] == "markdown" or not cell["source"].strip():
            continue
        lines = api.call_lines(
            "POST",
            f"/workbench/kernels/{_q(kernel)}/execute",
            {
                "code": cell["source"],
                "kind": cell["kind"],
                "connection": cell.get("connection"),
                "document": opened["path"],
            },
        )
        cell["outputs"] = [item for item in lines if "done" not in item and "clear" not in item]
        done: dict[str, Any] = next((item["done"] for item in lines if "done" in item), {})
        cell["execution_count"] = done.get("execution_count")
        results.append(_outputs(lines))
        if not done.get("ok"):
            break
    if a.get("save", True):
        api.call(
            "POST",
            "/workbench/save",
            {
                "path": opened["path"],
                "cells": opened["cells"],
                "modified": opened["modified"],
                "next_cell": opened.get("next_cell"),
            },
        )
    return {"kernel": kernel, "cells_run": len(results), "results": results}


@command(
    "workbench_inspect",
    "The signature and help of the name at a place in the code",
    req("kernel", "The kernel's id."),
    req("code", "The code."),
    req("offset", "The place: characters from the start.", "int"),
)
def workbench_inspect(a: dict[str, Any]) -> Any:
    return api.call(
        "POST", f"/workbench/kernels/{_q(a['kernel'])}/inspect", {"code": a["code"], "offset": a["offset"]}
    )


@command(
    "workbench_variables",
    "What a kernel holds: variables (type, size, a preview), connections, environment names",
    req("kernel", "The kernel's id."),
    values=True,
)
def workbench_variables(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/workbench/kernels/{_q(a['kernel'])}/variables")


@command(
    "workbench_to_grid",
    "Open a table from a kernel on the Tables page: a variable, or a cell's result (an output's Open as table); "
    "structure=true: a dict or list variable on the Structures page",
    req("kernel", "The kernel's id."),
    opt("name", "The variable; with output, the new table's name (else out_<n>)."),
    opt("output", "A result's number, as In [n] shows it: opens Out[n].", "int"),
    opt("structure", "Open the variable in Structures instead.", "bool"),
)
def workbench_to_grid(a: dict[str, Any]) -> Any:
    if a.get("structure"):
        return api.call("POST", f"/workbench/kernels/{_q(a['kernel'])}/structure", {"name": a.get("name")})
    body: dict[str, Any] = {k: a[k] for k in ("name", "output") if a.get(k) is not None}
    return api.call("POST", f"/workbench/kernels/{_q(a['kernel'])}/grid", body)


@command(
    "workbench_kernel",
    "Interrupt, restart or stop a kernel. A project's one Python session: interrupt and restart act on it "
    "for every document of the project, stop leaves it running for them, stop_session stops it",
    req("kernel", "The kernel's id."),
    req("action", "interrupt, restart, stop or stop_session."),
)
def workbench_kernel(a: dict[str, Any]) -> Any:
    kernel, action = _q(a["kernel"]), a["action"]
    if action == "stop":
        return api.call("DELETE", f"/workbench/kernels/{kernel}")
    if action == "stop_session":
        return api.call("DELETE", f"/workbench/kernels/{kernel}?session=1")
    if action == "interrupt":
        return api.call("POST", f"/workbench/kernels/{kernel}/interrupt")
    if action == "restart":
        return api.call("POST", f"/workbench/kernels/{kernel}/restart")
    raise CommandError("The action is interrupt, restart, stop or stop_session.")


@command(
    "workbench_environment_offer",
    "What a new environment can hold: libraries by group, presets, Python versions",
)
def workbench_environment_offer(a: dict[str, Any]) -> Any:
    return api.call("GET", "/workbench/environments")


@command(
    "workbench_environment_create",
    "Make a virtual environment (uv, else venv and pip) with ipykernel and the packages; remembered for a document",
    req("folder", "A new folder (a .venv beside the notebook)."),
    opt("python", "3.13, 3.12, 3.11 or 3.10 (default: the app's own version)."),
    opt("packages", "pip names, such as pandas.", "list"),
    opt("document", "The notebook or script that uses it."),
)
def workbench_environment_create(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("folder", "python", "packages", "document") if a.get(k) is not None}
    lines = api.call_lines("POST", "/workbench/environments", body)
    done = next((item["done"] for item in lines if "done" in item), None)
    return {"done": done, "log": [item["line"] for item in lines if "line" in item][-40:]}


@command(
    "workbench_environment_choose",
    "Remember the Python a document runs in",
    req("path", "The document."),
    req("python", "The Python."),
)
def workbench_environment_choose(a: dict[str, Any]) -> Any:
    return api.call("POST", "/workbench/environment", {"path": a["path"], "python": a["python"]})
