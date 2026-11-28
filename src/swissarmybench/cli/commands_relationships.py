"""The agent's relationships_* commands: relationships dialog.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.api import CommandError
from swissarmybench.cli.command_kit import SCOPE, _q, command, opt, req

MODEL_SHAPE = (
    '{"name": "my_model", "description": "...", "tables": {"<dataset>": {"primary_key": ["col"], "source": "..."}}, '
    '"relationships": [{"from": "<dataset>", "from_columns": [...], "to": "<dataset>", "to_columns": [...], '
    '"kind": "one-to-one|one-to-many|many-to-one|many-to-many", "note": "optional caveat"}]}'
)


@command(
    "relationships_get",
    "The relationship model: primary keys and joins. "
    "The current relationship model: primary keys and joins, as model JSON.",
)
def get_relationships(a: dict[str, Any]) -> Any:
    return api.call("GET", "/relationships")


@command(
    "relationships_set",
    "Set primary keys and joins. Merges into the current model. Verify keys first (count(*) = count(DISTINCT key)). "
    "Model shape: " + MODEL_SHAPE,
    req("model", "The model.", "json"),
    opt("replace", "Start over instead of merging.", "bool"),
)
def set_relationships(a: dict[str, Any]) -> Any:
    return api.call("POST", "/relationships", {"model": a["model"], "replace": bool(a.get("replace"))})


@command(
    "relationships_library",
    "The saved relationship sets. "
    "The saved relationship sets (the user's and the team's shared ones) and which of their tables are open",
)
def library(a: dict[str, Any]) -> Any:
    return api.call("GET", "/relationships/library")


@command(
    "relationships_apply_library",
    "Apply a saved relationship set (merges). Apply a saved relationship set by name (merges)",
    req("name", "Its name."),
)
def apply_library(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/relationships/library/{_q(a['name'])}")


JOINS_SHAPE = '[{"from": "<dataset>", "from_columns": [...], "to": "<dataset>", "to_columns": [...]}, ...]'


@command(
    "relationships_delete",
    "Delete joins in use (relationships_undo restores). Joins: " + JOINS_SHAPE,
    req("joins", "The joins to delete.", "json"),
)
def relationships_delete(a: dict[str, Any]) -> Any:
    return api.call("POST", "/relationships/delete", {"joins": a["joins"]})


@command(
    "relationships_update",
    "Change joins in use: their kind, or active. "
    "Change joins in use: their kind and/or Run (active: whether a join is used). Undo with relationships_undo",
    req(
        "joins", '[{"from", "from_columns", "to", "to_columns"}]. The joins to change: ' + JOINS_SHAPE, "json"
    ),
    opt("kind", "one-to-one, one-to-many, many-to-one or many-to-many."),
    opt("active", "Run: true to use the joins, false to keep them but not use them.", "bool"),
)
def relationships_update(a: dict[str, Any]) -> Any:
    body: dict[str, Any] = {"joins": a["joins"]}
    if a.get("kind"):
        body["kind"] = a["kind"]
    if a.get("active") is not None:
        body["active"] = bool(a["active"])
    return api.call("POST", "/relationships/update", body)


@command(
    "relationships_undo",
    "Undo the last delete or change of joins. Undo the last delete or change of the joins in use",
)
def relationships_undo(a: dict[str, Any]) -> Any:
    return api.call("POST", "/relationships/undo")


@command(
    "relationships_find",
    "Suggest how the open tables join, with evidence. "
    "Find how the open tables join: suggestions with evidence (match share, orphans, why); best first",
    opt("tables", "Dataset names to look at (default every open one).", "list"),
)
def find_relationships(a: dict[str, Any]) -> Any:
    return api.call("POST", "/relationships/find", {"tables": a.get("tables")} if a.get("tables") else {})


@command(
    "relationships_check",
    "Test the relationships against the open tables. "
    "Run the current relationships (or a saved set) against the open tables: holds, orphans or broken",
    opt("set", "A saved set's name (default the current relationships)."),
    values=True,
)
def check_relationships(a: dict[str, Any]) -> Any:
    return api.call("POST", "/relationships/check", {"set": a["set"]} if a.get("set") else {})


@command(
    "relationships_path",
    "The chain of joins linking two tables. "
    "The chain of joins that links two tables through the current relationships",
    req("start", "Dataset name to start from."),
    req("end", "Dataset name to reach."),
)
def relationship_path(a: dict[str, Any]) -> Any:
    return api.call("GET", "/relationships/path", params={"from": a["start"], "to": a["end"]})


@command(
    "relationships_scope",
    "Which model tables the open project uses. "
    "Which of the model's tables the open project uses (drawn on the ERD) and which not, by connection",
    SCOPE,
)
def relationships_scope(a: dict[str, Any]) -> Any:
    return api.call("GET", "/relationships/scope", params={"scope": a.get("scope")})


@command(
    "relationships_save_set",
    "Save the relationships as a relationship set. "
    "Save the current relationships as a relationship set (a shared .relationships.json file)",
    req("name", "The set's name."),
    opt("description", "What it joins."),
    opt("tags", "Words to find it by.", "list"),
    opt("author", "Who made it."),
    opt("folder", "A blade folder to save it in (default: the user's own sets, in the library)."),
)
def relationships_save_set(a: dict[str, Any]) -> Any:
    return api.call(
        "POST",
        "/relationships/sets",
        {k: a[k] for k in ("name", "description", "tags", "author", "folder") if a.get(k) is not None},
    )


@command(
    "relationships_export_set",
    "A relationship set as .relationships.json text. "
    "A saved relationship set, or the current relationships, as .relationships.json text",
    opt("name", "A saved set's name (default the current relationships)."),
)
def relationships_export_set(a: dict[str, Any]) -> Any:
    path = f"/relationships/sets/{_q(a['name'])}" if a.get("name") else "/relationships/set"
    data, _ = api.fetch_bytes("GET", path)
    return {"text": data.decode("utf-8", "replace")}


@command(
    "relationships_rename_set",
    "Rename a saved relationship set. Its file too",
    req("name", "Its name now."),
    req("new_name", "Its new name."),
)
def relationships_rename_set(a: dict[str, Any]) -> Any:
    return api.call("PATCH", f"/relationships/sets/{_q(a['name'])}", {"name": a["new_name"]})


@command(
    "relationships_delete_set",
    "Delete a saved relationship set (on Allow). "
    "Delete a saved relationship set's file (waits for the user's Allow)",
    req("name", "Its name."),
)
def relationships_delete_set(a: dict[str, Any]) -> Any:
    return api.call("DELETE", f"/relationships/sets/{_q(a['name'])}")


@command(
    "relationships_import_set",
    "Import a relationship set's text; apply uses it. "
    "Import a relationship set's text: without apply, what it would change; apply and save to use and keep it",
    req("text", "The .relationships.json file's text."),
    opt("apply", "Apply it to the current relationships.", "bool"),
    opt("save", "Keep it with the saved sets.", "bool"),
    opt("folder", "Where to keep it."),
)
def relationships_import_set(a: dict[str, Any]) -> Any:
    return api.call(
        "POST",
        "/relationships/import",
        {k: a[k] for k in ("text", "apply", "save", "folder") if a.get(k) is not None},
    )


@command(
    "relationships_reject",
    "Stop the finder offering a suggestion. Undo brings it back",
    req(
        "suggestion",
        "The suggestion, as relationships_find gave it. "
        "The suggestion as relationships_find gave it (from, to, columns).",
        "json",
    ),
    opt("undo", "Offer it again.", "bool"),
)
def relationships_reject(a: dict[str, Any]) -> Any:
    if not isinstance(a["suggestion"], dict):
        raise CommandError(
            'suggestion is one of relationships_find\'s suggestions: {"from", "to", "columns"}.'
        )
    body = a["suggestion"] | ({"undo": True} if a.get("undo") else {})
    return api.call("POST", "/relationships/reject", body)
