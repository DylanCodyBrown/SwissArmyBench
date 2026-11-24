"""Every Swiss Army Bench action an agent can take, as one registry of named commands.

The Tables page has buttons; this has commands. Each command is named for the part of the app it
works on, then the action: `tabs_new_query` (the + tab), `table_filter` (the ribbon's Table row),
`column_keep` (the Column row), `cell_exclude` (a cell's right-click menu), `steps_add` (the Table
Transformations panel), `compare_create`, `analyze_add`. The prefix is the area, so a flat tool
list sorts itself into the app's layout; AREAS below lists them in the order the app shows them.
Some commands are composites of several server handlers that match one button on the page
(`steps_apply_sql`, `steps_delete`, `table_matching`).

Two front ends share this file and nothing else:

* the MCP server (`swissarmybench.mcp.server`) registers one typed tool per command, with a lean
  description, so a command added here is a tool with no other change;
* the `sab` terminal command (`swissarmybench.cli.main`) runs the same commands by hand.

Think of the registry as an ASP.NET controller table: `Command` is the route attribute (name,
arguments, summary), the decorated function is the action method, and `execute` is the one
dispatcher that validates arguments against the attribute before it calls the action.

The commands live one module per area (craft review 2026-11-22): `cli/commands_<area>.py` holds that
area's commands in their order, registering into the one REGISTRY (`cli/command_kit.py`: Arg, Command,
the registrar and the helpers several areas share). This file holds the help commands, imports every
area's module, orders the registry by AREAS, and is the dispatcher; it re-exports the kit's names.

Values in a result (cells) are untrusted: they come back inside an `<untrusted-data>` block. The
rules (approvals, the SQL guard, the audit log) are the server's, not this file's.

Standard library only.
"""

from __future__ import annotations

import json
from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.api import CommandError
from swissarmybench.cli.command_kit import (
    _BLOCK_TAG as _BLOCK_TAG,
)
from swissarmybench.cli.command_kit import (
    DATA_NOTE as DATA_NOTE,
)
from swissarmybench.cli.command_kit import (
    REGISTRY as REGISTRY,
)
from swissarmybench.cli.command_kit import (
    SCOPE as SCOPE,
)

# What every command module shares, re-exported: the extensions and the doors import it from here.
from swissarmybench.cli.command_kit import (
    Arg as Arg,
)
from swissarmybench.cli.command_kit import (
    ArgType as ArgType,
)
from swissarmybench.cli.command_kit import (
    Command as Command,
)
from swissarmybench.cli.command_kit import (
    ImageResult as ImageResult,
)
from swissarmybench.cli.command_kit import (
    Registrar as Registrar,
)
from swissarmybench.cli.command_kit import (
    Run as Run,
)
from swissarmybench.cli.command_kit import (
    _csv as _csv,
)
from swissarmybench.cli.command_kit import (
    _defuse as _defuse,
)
from swissarmybench.cli.command_kit import (
    _insert_step as _insert_step,
)
from swissarmybench.cli.command_kit import (
    _post_steps as _post_steps,
)
from swissarmybench.cli.command_kit import (
    _q as _q,
)
from swissarmybench.cli.command_kit import (
    _row_count as _row_count,
)
from swissarmybench.cli.command_kit import (
    _step_op as _step_op,
)
from swissarmybench.cli.command_kit import (
    _summary as _summary,
)
from swissarmybench.cli.command_kit import (
    command as command,
)
from swissarmybench.cli.command_kit import (
    opt as opt,
)
from swissarmybench.cli.command_kit import (
    req as req,
)

# The agent's guide: a short index (mcp/index.md, read first) and one page per topic (mcp/guide/<topic>.md).
# The MCP server also serves each as a resource: swissarmybench://index, swissarmybench://guide/<topic>.
GUIDE_TOPICS: dict[str, str] = {
    "grids": "Tables and steps: data in, reading, the ribbon, steps, SQL, the page",
    "analyze": "The Analyze page: the analyses, their cards on the board, dashboards, themes",
    "relationships": "Keys and relationships: the finder, saved sets, the ERD, compare and tie-out",
    "connections": "Connections and catalogs: databases, files, Power BI, your own Python; key vaults, variables",
    "apis": "APIs: the library's API and web call blades, the explorer, calls, Return as table, Refresh",
    "structures": "Structures: JSON, YAML, XML and TOML as documents, their steps, lineage, tables, saving",
    "environment": "The Environment: tables, variables, structures, settings and secrets, libraries; Used in",
    "sandbox": "Local sandbox APIs: the project's sandbox, API.py, mock clients, Run, Try it, Export",
    "blades": "Blades and starters: saved code, the starter pack",
    "workbench": "The Workbench: notebooks, scripts, kernels, SQL, DAX, HTML and table cells, windows",
    "streamlit": "Streamlit: the Canvas and widgets (the extension's)",
    "projects": "Projects as folders: open, save, the recent ones, tables that need a fix",
    "library": "The library: connections, APIs, vaults, blades, relationship sets, variables as a Git repo's files",
    "accounting": "Accounting (an extension): the Excel canvas, Play, workbook.py, templates, statements",
    "writing": "Writing data: which connections write, the Write starters, a dry run first",
    "privacy": "Approvals and privacy: what waits for the user, passwords, untrusted data, the beta log",
    "powerapps": "Power Apps (an extension): code apps with pa and pac, sources, connectors, Run live, Push",
    "powerbi": "Power BI (an extension): the model exported as a Power BI Project from the ERD",
    "git": "Git (an extension): GitHub sync of the team library and shared projects, Source Control, the graph",
    "extensions": "Making an extension: the manifest, commands, routes, the rules, tests; folders planned",
}


def guide_text(topic: str | None = None) -> str:
    """The index with no topic; a topic's page; for a topic that is not one, the list of topics."""
    from importlib.resources import files  # only the guide needs it

    folder = files("swissarmybench.mcp")
    if not topic:
        return folder.joinpath("index.md").read_text(encoding="utf-8")
    name = topic.strip().lower()
    if name not in GUIDE_TOPICS:
        listed = "\n".join(f"- {key}: {title}" for key, title in GUIDE_TOPICS.items())
        return f"No guide topic {topic!r}. The topics:\n{listed}\n"
    return folder.joinpath("guide", f"{name}.md").read_text(encoding="utf-8")


@command(
    "guide",
    "Read first: the index of the app and its tools; topic gives one topic's detail.",
    opt("topic", "One of: " + ", ".join(GUIDE_TOPICS) + "; or context: the live context.md."),
)
def guide(a: dict[str, Any]) -> Any:
    if str(a.get("topic") or "").strip().lower() == "context":
        return api.call("GET", "/claude/context")
    return guide_text(a.get("topic"))


@command(
    "commands",
    "The catalog: every command with its arguments. `match` filters by words in the name or summary.",
    opt("match", "Only commands whose name or summary contains this text."),
)
def commands(a: dict[str, Any]) -> Any:
    return catalog(a.get("match"))


@command("health", "Is the server up, which version.")
def health(a: dict[str, Any]) -> Any:
    return api.call("GET", "/health")


# Every area's commands, each module registering its own (the tool list is ordered by AREAS below).
from swissarmybench.cli import (  # noqa: E402, F401 (each registers its commands on import)
    commands_actions,
    commands_agent,
    commands_analyze,
    commands_api,
    commands_apis,
    commands_app,
    commands_blades,
    commands_catalog,
    commands_cell,
    commands_changes,
    commands_column,
    commands_compare,
    commands_connections,
    commands_datasets,
    commands_desktop,
    commands_environment,
    commands_erd,
    commands_explorer,
    commands_extensions,
    commands_files,
    commands_key_finder,
    commands_library,
    commands_project,
    commands_projects,
    commands_relationships,
    commands_row,
    commands_sandbox,
    commands_sharing,
    commands_stats,
    commands_steps,
    commands_structures,
    commands_table,
    commands_tabs,
    commands_team,
    commands_variables,
    commands_workbench,
)
from swissarmybench.cli.commands_environment import _ENVIRONMENT as _ENVIRONMENT  # noqa: E402

AREAS: tuple[tuple[str, str], ...] = (
    ("help", "Help"),
    ("tabs", "Tab bar: the open tables and the + query tab"),
    ("datasets", "Datasets: loading, closing, Python sessions"),
    ("table", "Ribbon, Table row"),
    ("column", "Ribbon, Column row"),
    ("cell", "A cell's right-click menu"),
    ("analyze", "The Analyze page: every analysis (analyze_run), its cards on the board, dashboards, themes"),
    ("row", "Rows"),
    ("steps", "Table Transformations panel and SQL box"),
    ("key_finder", "Key Finder"),
    ("relationships", "Relationships dialog"),
    ("erd", "ERD tab"),
    ("blades", "Blades: the user's saved code that loads from outside Python"),
    ("connections", "Connections: the user's databases and files (Application row's Connections)"),
    ("variables", "Settings and secrets (the Environment's tab): this computer's variables, sources, uses"),
    (
        "library",
        "The library: the folder of connections, APIs, vaults, blades and variables (a Git repository)",
    ),
    ("team", "Settings' Team box: join, start or leave a team (one GitHub repository, its projects/)"),
    ("sharing", "Share a running app with your organization (Microsoft Dev Tunnels)"),
    ("api", "The project's local sandbox API (API.py): run it, call it, export it for its target"),
    ("actions", "Every API's actions through api_adapter: list, run, shapes and drift, discover, build"),
    ("sandbox", "The project's sandbox: the tables a local sandbox API reads and writes, Reset, checkpoints"),
    ("environment", "The Environment: everything the project holds, where each is used, its libraries"),
    ("apis", "APIs: each API added with Add API, its operations' inputs and outputs, Try it, Refresh"),
    ("structures", "Structures: JSON, YAML, XML and TOML as documents, their steps, Open as table, Save"),
    ("files", "Folders and files on this computer (the file chooser)"),
    ("workbench", "Workbench: notebooks, scripts, kernels, environments"),
    ("project", "Projects: a folder (its files, and .sab/: tables, steps, Analyze, relationships)"),
    ("projects", "The Project Explorer: every project as a card, sorted; the project types explained"),
    ("catalog", "Catalog explorer: a source database's tables and columns"),
    ("explorer", "Data Explorer: one search over connections, catalogs, open tables, variables, blades"),
    ("compare", "Compare (two tables side by side)"),
    ("stats", "Every call's statistics: times, sizes and outcomes per table, connection and endpoint; hints"),
    ("changes", "The open project's change log: the last change to an object, its history, since a time"),
    ("app", "The page itself: snapshots"),
    ("desktop", "The desktop app: its windows, a page opened in one"),
    ("extensions", "Extensions: what plugs into the base (Streamlit, Accounting, Power Apps)"),
    ("agent", "What only the agent has: the table in front, the inbox, approvals, live events"),
)
HELP_COMMANDS = frozenset({"guide", "commands", "health"})


def area_of(name: str) -> str:
    """The area a command belongs to: its name's prefix, or help for the three unprefixed ones."""
    if name in HELP_COMMANDS:
        return "help"
    for area, _ in AREAS:
        if name == area or name.startswith(area + "_"):
            return area
    raise ValueError(f"{name} belongs to no area; add its prefix to AREAS.")


def _arrange() -> None:
    """Order the registry as the app is laid out, keeping definition order inside each area."""
    order = {area: i for i, (area, _) in enumerate(AREAS)}
    arranged = sorted(REGISTRY.items(), key=lambda item: order[area_of(item[0])])  # sorted() is stable
    REGISTRY.clear()
    REGISTRY.update(arranged)


_arrange()

# The old names, one release: a tang became a relationship set (the owner, 2026-11-17), so
# relationships_*_tang is relationships_*_set. Accepted by the dispatcher (the `sab` command and an MCP call by
# name) but not listed: the tool list carries the new names only.
OLD_NAMES: dict[str, str] = {
    "relationships_save_tang": "relationships_save_set",
    "relationships_export_tang": "relationships_export_set",
    "relationships_import_tang": "relationships_import_set",
    "projects_folder_set": "projects_folders",  # 2026-11-18: the local and shared projects folders
}


# An old argument's name, one release: (command, old) -> new. A tang became a relationship set.
OLD_ARGS: dict[tuple[str, str], str] = {("relationships_check", "tang"): "set"}


# Commands that went, one release: an old call says why instead of "unknown".
GONE_NAMES: dict[str, str] = {
    "analyze_shape": "analyze_shape went (2026-11-19): analyze_check(table, analysis) says whether a table suits "
    "an analysis, from its contract: what fits each slot, what is missing, the fixes.",
    "analyze_defaults": "analyze_defaults went (2026-11-19): analyze_plan(analysis, table) gives the columns a "
    "form starts on (never an identifier), and analyze_check each column's fit.",
    "app_autostart": "app_autostart went (2026-11-18): there is no tray and no start at sign-in any more; the "
    "server runs while the app is open (app_lifecycle says when it stops).",
    "app_frontend": "app_frontend went (2026-11-23): the Blazor front end is the only one, nothing to choose.",
}


def current_name(name: str) -> str:
    """A command's name as it is now: an old one (relationships_save_tang) is its new one."""
    return OLD_NAMES.get(name, name)


# ===== the catalog and the dispatcher =====


def catalog(match: str | None = None) -> dict[str, Any]:
    """Every command, with its arguments. Built live from the registry."""
    words = (match or "").lower().split()
    listed: list[dict[str, Any]] = []
    for cmd in REGISTRY.values():
        title = dict(AREAS)[area_of(cmd.name)]
        text = f"{cmd.name} {cmd.summary} {title}".lower()
        if words and not all(w in text for w in words):
            continue
        entry: dict[str, Any] = {
            "command": cmd.name,
            "group": title,
            "summary": cmd.summary,
            "args": [x.to_json() for x in cmd.args],
        }
        if cmd.values:
            entry["returns_cell_values"] = True
        if cmd.image:
            entry["returns_image"] = True
        listed.append(entry)
    return {"count": len(listed), "commands": listed}


_TRUE = {"1", "true", "yes", "y", "on", ""}


def _loose_json(value: Any) -> Any:
    """A value of any JSON type: from a terminal, `100` is a number and `east` stays text."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except ValueError:
        return value


def _coerce(cmd: Command, arg: Arg, value: Any) -> Any:
    """Typed values pass through (the MCP); text from a terminal is converted to the declared type."""
    try:
        if arg.type == "int":
            if isinstance(value, bool):
                raise ValueError("a bool is not a whole number")
            return int(value)
        if arg.type == "bool":
            return value if isinstance(value, bool) else str(value).lower() in _TRUE
        if arg.type == "json":
            return json.loads(value) if isinstance(value, str) else value
        if arg.type == "any":
            return _loose_json(value)
        if arg.type == "list":
            if isinstance(value, list):
                return value
            return [part.strip() for part in str(value).split(",") if part.strip()]
        return value if isinstance(value, str) else str(value)
    except (ValueError, TypeError) as error:
        raise CommandError(f"{cmd.name}: {arg.name} must be {arg.type} ({error}).") from error


def _wrap(source: str, payload: Any) -> str:
    # "<" as \u003c is the same JSON, and no value can then spell the block's closing tag.
    data = json.dumps(payload, default=str).replace("<", "\\u003c")
    return f"{DATA_NOTE}\n<untrusted-data source={json.dumps(source)}>\n{data}\n</untrusted-data>"


def execute_result(name: str, raw: dict[str, Any] | None = None) -> str | ImageResult:
    """Run one command from the registry. The result is text, or an ImageResult for a picture. Anything not in the
    registry, and any unknown or missing argument, is refused here with the reason, before the server
    is touched."""
    name = current_name(name)
    cmd = REGISTRY.get(name)
    if cmd is None and name in GONE_NAMES:
        raise CommandError(GONE_NAMES[name])
    if cmd is None:
        import difflib  # only a mistyped name needs it

        from swissarmybench.domain import extensions as catalog

        owner = catalog.owner_of(name)
        if owner is not None:
            raise CommandError(
                f"{name} is the {owner.name} extension's, and it is not installed here: install it on the "
                f"Extensions page (extensions_install id={owner.id})."
            )
        close = difflib.get_close_matches(name, list(REGISTRY), n=5)
        hint = f" Did you mean: {', '.join(close)}?" if close else ""
        raise CommandError(f"No command {name!r}.{hint} Call commands for the catalog.")
    given = {OLD_ARGS.get((name, k), k): v for k, v in (raw or {}).items()}
    known = {x.name: x for x in cmd.args}
    unknown = sorted(set(given) - set(known))
    if unknown:
        raise CommandError(
            f"{name}: unknown argument(s) {', '.join(unknown)}. It takes: {', '.join(known) or 'none'}."
        )
    # An empty id would address the collection instead (/grids/ for an open table): as good as missing.
    missing = [x.name for x in cmd.args if x.required and given.get(x.name) in (None, "")]
    if missing:
        raise CommandError(f"{name}: missing {', '.join(missing)}.")
    args = {k: _coerce(cmd, known[k], v) for k, v in given.items() if v is not None}
    result = cmd.run(args)
    if isinstance(result, str | ImageResult):
        return result
    if cmd.values:
        return _wrap(str(args.get("dataset") or args.get("grid") or args.get("compare") or name), result)
    return json.dumps(result, default=str)


def execute(name: str, raw: dict[str, Any] | None = None) -> str:
    """`execute_result` as text only: a picture comes back as its description (size, saved path)."""
    result = execute_result(name, raw)
    if isinstance(result, ImageResult):
        note = "The picture is returned as an image by the MCP tool, and saved to a file by the sab command."
        return json.dumps(result.meta | {"note": note})
    return result


def _add_extensions() -> None:
    """Each extension that is on (swissarmybench/extensions.py): its commands and their areas join the
    registry, so each is an MCP tool and a `sab` command like the base's."""
    global AREAS
    from swissarmybench import extensions

    for module in extensions.enabled():
        made = getattr(module, "commands", None)
        try:
            given = made() if callable(made) else {}
        except Exception:  # a folder extension's own code (the library's): its commands left out, never all
            given = {}
        declared = extensions.manifest(module)
        known = {area for area, _ in AREAS} | {a[0] for a in declared.AREAS}
        for name, cmd in (given if isinstance(given, dict) else {}).items():
            # A command in no area would leave the registry unordered: only one under an area is taken.
            if isinstance(cmd, Command) and any(name == a or name.startswith(a + "_") for a in known):
                REGISTRY.setdefault(name, cmd)
        # Its commands that went: an old call says why (as the base's GONE_NAMES).
        gone = getattr(module, "gone_commands", None)
        for name, said in (gone() if callable(gone) else {}).items():
            if name not in REGISTRY:
                GONE_NAMES.setdefault(name, said)
        # Its old names and arguments, one release (as the base's OLD_NAMES and OLD_ARGS).
        # (its commands' own metadata: extensions.COMMAND_NAMES, read here with its commands)
        OLD_NAMES.update(getattr(module, "OLD_NAMES", {}))
        OLD_ARGS.update(getattr(module, "OLD_ARGS", {}))
        known = {area for area, _ in AREAS}
        AREAS = AREAS + tuple(a for a in declared.AREAS if a[0] not in known)
    _arrange()  # an extension's commands in an area of the base's (workbench_canvas...) go with it


_add_extensions()


__all__ = [
    "GONE_NAMES",
    "OLD_NAMES",
    "REGISTRY",
    "Command",
    "CommandError",
    "ImageResult",
    "catalog",
    "current_name",
    "execute",
    "execute_result",
]
