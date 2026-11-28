"""The agent's structures_* commands: structures: JSON, YAML, XML and TOML as documents, their steps, Open as table, Save.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import _q, command, opt, req


@command(
    "structures_list",
    "The open structures and the project's structure files. "
    "The open structures (id, name, format, steps) and the project's structure files",
)
def structures_list(a: dict[str, Any]) -> Any:
    return api.call("GET", "/structures")


@command(
    "structures_open",
    "Open a structure: a file, pasted text or a new one. "
    "Open a structure: a .json/.yaml/.xml/.toml file (path), pasted text (text, format found), or a new "
    "one (kind object|list, or value: your JSON)",
    opt("path", "A file."),
    opt("text", "Text to paste instead."),
    opt("format", "json, yaml, xml or toml (pasted: found when not given; new: json)."),
    opt("kind", "New: object or list."),
    opt("value", "New: this JSON value.", "json"),
    opt("name", "Its name."),
)
def structures_open(a: dict[str, Any]) -> Any:
    if a.get("path"):
        return api.call("POST", "/structures/open", {"path": a["path"]})
    if a.get("text"):
        return api.call(
            "POST", "/structures/paste", {k: a[k] for k in ("text", "format", "name") if a.get(k)}
        )
    body = {k: a[k] for k in ("kind", "format", "name") if a.get(k)}
    if "value" in a:
        body["value"] = a["value"]
    return _structure_summary(api.call("POST", "/structures", body))


def _structure_summary(answer: Any) -> Any:
    """An open structure without its values (structures_show reads them, capped)."""
    if isinstance(answer, dict):
        return {k: v for k, v in answer.items() if k not in ("value", "text")}
    return answer


@command(
    "structures_show",
    "A structure's shape and the node at a path. "
    "A structure's shape (types, counts, keys), its record lists, and the node at path, capped like rows; "
    "search: where words stand (each match's path and Python code)",
    req("structure", "Its id or name."),
    opt("path", "$.orders[0] (default $)."),
    opt("search", "Words to find in its keys and values (the file's; through its steps with path=result)."),
    values=True,
)
def structures_show(a: dict[str, Any]) -> Any:
    sid = _q(a["structure"])
    if a.get("search"):
        view = "result" if a.get("path") == "result" else "file"
        return api.call("GET", f"/structures/{sid}/search?words={_q(a['search'])}&view={view}")
    query = f"?path={_q(a['path'])}" if a.get("path") else ""
    return api.call("GET", f"/structures/{sid}/describe" + query)


@command(
    "structures_step_add",
    "Add a step (guide: structures). "
    "Add a step: op pick|filter|rename|remove|set|add|sort|flatten; path ($.orders, [*] for each); "
    "filter: field, test (= != > >= < <= contains, starts with, exists, missing), value; rename: key, to; "
    "set/add: key, value; sort: field, descending",
    req("structure", "Its id or name."),
    req("step", '{"op": "filter", "path": "$.orders", "field": "status", "value": "open"}.', "json"),
)
def structures_step_add(a: dict[str, Any]) -> Any:
    return _structure_summary(api.call("POST", f"/structures/{_q(a['structure'])}/steps", a["step"]))


@command(
    "structures_step_remove",
    "Remove a step, or undo or redo the last change. "
    "Remove a step (index from 0; the last when not given), or undo / redo the last change",
    req("structure", "Its id or name."),
    opt("index", "The step's index.", "int"),
    opt("undo", "Undo the last step.", "bool"),
    opt("redo", "Redo what was undone.", "bool"),
)
def structures_step_remove(a: dict[str, Any]) -> Any:
    sid = _q(a["structure"])
    if a.get("undo"):
        return _structure_summary(api.call("POST", f"/structures/{sid}/undo", {}))
    if a.get("redo"):
        return _structure_summary(api.call("POST", f"/structures/{sid}/redo", {}))
    body = {"index": a["index"]} if a.get("index") is not None else {}
    return _structure_summary(api.call("POST", f"/structures/{sid}/steps/remove", body))


@command(
    "structures_edit",
    "Change a structure's file: its text or its tree. "
    "Change a structure's file (unsaved until structures_save): its text (kept as typed; text_error says "
    "where it does not parse), a node (edit), Format, the format it is written in, or its name",
    req("structure", "Its id or name."),
    opt("text", "The new text, in its format."),
    opt(
        "edit",
        '{"op": set|rename|remove|add|duplicate|move, "path", "value"|"key","to"|"to": index}.',
        "json",
    ),
    opt("format_text", "true: written again in its own format (JSON indented by 2).", "bool"),
    opt("format", "json, yaml, xml or toml."),
    opt("name", "A new name."),
)
def structures_edit(a: dict[str, Any]) -> Any:
    sid = _q(a["structure"])
    if a.get("edit") is not None:
        return _structure_summary(api.call("POST", f"/structures/{sid}/edit", a["edit"]))
    if a.get("format_text"):
        return _structure_summary(api.call("POST", f"/structures/{sid}/format", {}))
    body = {k: a[k] for k in ("text", "format", "name") if a.get(k) is not None}
    return _structure_summary(api.call("PUT", f"/structures/{sid}", body))


@command(
    "structures_open_as_grid",
    "Open the records at a path as a table. "
    "Open the list of records at path on the Tables page (a table: SQL and Analyze work on it)",
    req("structure", "Its id or name."),
    opt("path", "$.orders (default $)."),
    opt("name", "The table's name."),
)
def structures_open_as_grid(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("path", "name") if a.get(k)}
    return api.call("POST", f"/structures/{_q(a['structure'])}/grid", body)


@command(
    "structures_save",
    "Save a structure to its file. "
    "Save a structure to its file (as_text: its text as typed, only changed bytes, never over a file "
    "changed on disk); with name, format, folder or path: Save as; disk=reload|keep_mine after a change",
    req("structure", "Its id or name."),
    opt("as_text", "true: the file's text (a tab's Save), not the steps' result.", "bool"),
    opt("name", "Save as: its file's name."),
    opt("format", "Save as: json, yaml, xml or toml."),
    opt("folder", "Save as: the folder."),
    opt("path", "Save as: the whole path."),
    opt("disk", "reload (the file as it is now) or keep_mine (the next save writes over it)."),
)
def structures_save(a: dict[str, Any]) -> Any:
    sid = _q(a["structure"])
    if a.get("disk") in ("reload", "keep_mine"):
        route = {"reload": f"/structures/{sid}/reload", "keep_mine": f"/structures/{sid}/keep-mine"}[
            a["disk"]
        ]
        return _structure_summary(api.call("POST", route, {}))
    body = {k: a[k] for k in ("name", "format", "folder", "path", "as_text") if a.get(k)}
    if body.keys() - {"as_text"}:
        return api.call("POST", f"/structures/{sid}/save-as", body)
    if a.get("as_text"):
        # The text as the app holds it, over the file as it was read (a change on disk since refuses it).
        return _structure_summary(api.call("POST", f"/structures/{sid}/save", {"hash": None}))
    return api.call("POST", f"/structures/{sid}/save", {})


@command(
    "structures_lineage",
    "A structure's lineage: its source, steps, tables. "
    "A structure's lineage: the API call (inputs, body, when) or file, its steps, the tables made from it; "
    "run_again=true sends the same call again (the steps kept)",
    req("structure", "Its id or name."),
    opt("run_again", "Send its call again.", "bool"),
)
def structures_lineage(a: dict[str, Any]) -> Any:
    sid = _q(a["structure"])
    if a.get("run_again"):
        return _structure_summary(api.call("POST", f"/structures/{sid}/run-again", {}))
    return api.call("GET", f"/structures/{sid}/lineage")


@command(
    "structures_close",
    "Close a structure, or list where code uses it. "
    "Close an open structure (unsaved steps go), or with references=true: where code calls "
    "sab.structure(name)",
    req("structure", "Its id or name (references: the saved structure's name)."),
    opt("references", "Only list where it is used.", "bool"),
)
def structures_close(a: dict[str, Any]) -> Any:
    if a.get("references"):
        return api.call("GET", f"/structures/references?name={_q(a['structure'])}")
    return api.call("DELETE", f"/structures/{_q(a['structure'])}")
