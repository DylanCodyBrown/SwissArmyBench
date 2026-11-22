"""The agent's blades_* commands: blades: the user's saved code that loads from outside Python.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import _q, command, opt, req


@command(
    "blades_list",
    "Every blade and connection: name, kind, description, tags, which secrets are saved (never values)",
)
def blades_list(a: dict[str, Any]) -> Any:
    return api.call("GET", "/blades")


@command(
    "blades_get",
    "One blade whole: code, the file's stamp, header fields, settings, packages",
    req("name", "The blade's name."),
)
def blades_get(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/blades/{_q(a['name'])}")


@command(
    "blades_templates",
    "Starter connections (databases, files, vaults) and analyses; give an id for one's full code",
    opt("id", "A starter's id, for its code and catalog query."),
)
def blades_templates(a: dict[str, Any]) -> Any:
    listed = api.call("GET", "/blades/templates")["templates"]
    if a.get("id"):
        return next((t for t in listed if t["id"] == a["id"]), None) or {"error": f"No starter {a['id']}."}
    return [{k: t[k] for k in ("id", "label", "group", "kind")} for t in listed]


@command(
    "blades_new",
    "New blade by name and kind: a blank working .blade.py (made-up rows), or from a template",
    opt("name", "Its name."),
    opt("kind", "table, code, analysis, connection, snippet, secret."),
    opt("template", "Or a template's id."),
    opt("table", "Its table's name."),
)
def blades_new(a: dict[str, Any]) -> Any:
    if not a.get("template") and not a.get("kind"):
        return api.call("GET", "/blades/new")
    body = {k: a[k] for k in ("template", "kind", "name", "table") if a.get(k) is not None}
    return api.call("POST", "/blades/new", body)


@command(
    "blades_header_set",
    "Set a blade's header fields (none given: its kind's fields and values)",
    req("name", "The blade."),
    opt("fields", '{"dialect": "duckdb", "queries.total": 4}', "json"),
)
def blades_header_set(a: dict[str, Any]) -> Any:
    if not a.get("fields"):
        return api.call("GET", f"/blades/{_q(a['name'])}/header")
    return api.call("PUT", f"/blades/{_q(a['name'])}/header", a["fields"])


@command(
    "blades_update",
    "Save a blade's code into its file (a starter's refused: blades_copy); its header: blades_header_set",
    req("name", "Its name."),
    req("code", "Its code (after the file's header)."),
    opt("stamp", "From blades_get: refused (409) if the file changed since."),
)
def blades_update(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("code", "stamp") if a.get(k) is not None}
    return api.call("PUT", f"/blades/{_q(a['name'])}", body)


@command(
    "blades_table_name_check",
    "Is a table name free for a blade's result? available, or why not",
    req("name", "The table name."),
    opt("blade", "The blade it is for (it may keep its own)."),
)
def blades_table_name_check(a: dict[str, Any]) -> Any:
    return api.call("GET", "/blades/table-name", params={"name": a["name"], "blade": a.get("blade")})


@command(
    "blades_delete", "Delete a blade or connection (its saved passwords go too)", req("name", "Its name.")
)
def blades_delete(a: dict[str, Any]) -> Any:
    return api.call("DELETE", f"/blades/{_q(a['name'])}")


@command(
    "blades_inspect",
    "What code makes, asks for (secrets), imports and needs (packages); its settings. Nothing runs",
    req("code", "The Python."),
    opt("template", "The starter it came from."),
)
def blades_inspect(a: dict[str, Any]) -> Any:
    return api.call("POST", "/blades/inspect", {"code": a["code"], "template": a.get("template")})


@command(
    "blades_fill",
    "Write values into code at its settings (ids from blades_inspect); the new code",
    req("code", "The Python."),
    req(
        "values",
        '{"<setting id>": "new value"}; a certificate or keystore file also takes {"value": path, '
        '"env": "TRINO_KEYSTORE_PATH"} (env null: a plain path)',
        "json",
    ),
)
def blades_fill(a: dict[str, Any]) -> Any:
    return api.call("POST", "/blades/fill", {"code": a["code"], "values": a["values"]})


@command(
    "blades_secrets",
    "Save or forget a blade's passwords in the system keyring (values are never read back)",
    req("name", "The blade."),
    req("values", '{"password": "value"} to save; {"password": null} to forget.', "json"),
)
def blades_secrets(a: dict[str, Any]) -> Any:
    return api.call("PUT", f"/blades/{_q(a['name'])}/secrets", a["values"])


@command(
    "blades_test",
    "Run a blade in a child process: does it work? What it made",
    req("name", "The blade."),
    opt("env", '{"VAR": "value"}: values a secret blade asks for, for this run only.', "json"),
)
def blades_test(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/blades/{_q(a['name'])}/test", {"env": a.get("env") or {}})


@command(
    "blades_refresh",
    "Run a blade's catalog command and load its source's tables and columns into the catalog",
    req("name", "The blade."),
    opt("env", '{"VAR": "value"}: values a secret blade asks for, for this run only.', "json"),
)
def blades_refresh(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/blades/{_q(a['name'])}/refresh", {"env": a.get("env") or {}})


@command(
    "blades_run",
    "Run a blade as the IDE's Run does (`code`: unsaved): output, result, error, problems",
    req("name", "The blade."),
    opt("code", "Code to run instead (nothing saved)."),
    opt("env", '{"VAR": "value"}: values a secret blade asks for, for this run only.', "json"),
    opt("open", "Then open its table result as a grid.", "bool"),
    opt("cancel", "A run id going now: stop it."),
)
def blades_run(a: dict[str, Any]) -> Any:
    name = _q(a["name"])
    if a.get("cancel"):
        return api.call("POST", f"/blades/runs/{_q(a['cancel'])}/cancel")
    body = {k: a[k] for k in ("code", "env") if a.get(k) is not None}
    ran = api.call("POST", f"/blades/{name}/run", body, timeout=900.0)
    if a.get("open") and isinstance(ran, dict) and (ran.get("result") or {}).get("kind") == "table":
        ran["opened"] = api.call("POST", f"/blades/{name}/result/open")
    return ran


@command(
    "blades_problems",
    "The lint's problems in a blade's code (or `code`): line, column, message, severity, fixes",
    req("name", "The blade."),
    opt("code", "Code to check instead of its saved code."),
)
def blades_problems(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/blades/{_q(a['name'])}/problems", {"code": a.get("code")})


@command(
    "blades_install",
    "Install packages into the app's own Python (where Test and Refresh run)",
    req("packages", "pip names, such as pyodbc.", "list"),
)
def blades_install(a: dict[str, Any]) -> Any:
    return api.call("POST", "/blades/install", {"packages": a["packages"]}, timeout=900.0)


@command(
    "blades_pin",
    "Make a blade a favourite (listed first), or not",
    req("name", "The blade."),
    opt("pinned", "true or false (default true).", "bool"),
)
def blades_pin(a: dict[str, Any]) -> Any:
    return api.call("PUT", f"/blades/{_q(a['name'])}/pin", {"pinned": a.get("pinned", True)})


@command(
    "blades_folders",
    "The blade folders searched for .blade.py files; give folders to set them",
    opt("folders", "The new list of folders.", "list"),
)
def blades_folders(a: dict[str, Any]) -> Any:
    if a.get("folders") is not None:
        return api.call("PUT", "/blades/folders", {"folders": a["folders"]})
    return api.call("GET", "/blades/folders")


@command(
    "blades_export",
    "A blade as its portable .blade.py text (no secret values in it)",
    req("name", "The blade."),
)
def blades_export(a: dict[str, Any]) -> Any:
    data, _ = api.fetch_bytes("GET", f"/blades/{_q(a['name'])}/export")
    return {"text": data.decode("utf-8", "replace")}


@command(
    "blades_import",
    "Import .blade.py texts: without apply, a review of what they hold; with apply, save the chosen ones",
    req("files", '[{"name": "file.blade.py", "text": "..."}]', "json"),
    opt("apply", 'Choices from the review: {"<file>": "save" | "rename" | "skip"}.', "json"),
)
def blades_import(a: dict[str, Any]) -> Any:
    body: dict[str, Any] = {"files": a["files"]}
    if a.get("apply") is not None:
        body["apply"] = a["apply"]
    return api.call("POST", "/blades/import", body)


@command(
    "blades_starters",
    "The built-in starter pack by family: read-only blades and snippets",
)
def blades_starters(a: dict[str, Any]) -> Any:
    return api.call("GET", "/blades/starters")


@command(
    "blades_copy",
    "Copy a starter (or a pack's blade) as the user's own; Save as with code",
    req("name", "The starter or blade."),
    opt("new_name", "The copy's name (default: <name> copy)."),
    opt("code", "The copy's code (default: its own)."),
)
def blades_copy(a: dict[str, Any]) -> Any:
    body = {k: v for k, v in (("name", a.get("new_name")), ("code", a.get("code"))) if v is not None}
    return api.call("POST", f"/blades/{_q(a['name'])}/copy", body)


@command(
    "blades_snippet",
    "A snippet's placeholders and their choices; with values, its filled text",
    req("name", "The snippet."),
    opt("values", '{"placeholder": "value"}', "json"),
    opt("dataset", "A DAX snippet's dataset (Finance/Sales model), for its choices."),
)
def blades_snippet(a: dict[str, Any]) -> Any:
    if a.get("values") is not None:
        return api.call("POST", f"/blades/{_q(a['name'])}/snippet", {"values": a["values"]})
    query = f"?dataset={_q(a['dataset'])}" if a.get("dataset") else ""
    return api.call("GET", f"/blades/{_q(a['name'])}/snippet{query}")


@command("blades_analyses", "The user's own analyses (analysis blades) the Analyze page offers")
def blades_analyses(a: dict[str, Any]) -> Any:
    return api.call("GET", "/blades/analyses")


@command(
    "blades_run_analysis",
    "Run an analysis blade on a grid's rows as shown; its result as Analyze cards",
    req("grid", "The grid's id."),
    req("name", "The analysis blade."),
    opt("columns", "The selected columns it gets.", "list"),
    values=True,
)
def blades_run_analysis(a: dict[str, Any]) -> Any:
    return api.call(
        "POST",
        f"/grids/{_q(a['grid'])}/blade-analysis",
        {"name": a["name"], "columns": a.get("columns") or [], "env": {}},
    )
