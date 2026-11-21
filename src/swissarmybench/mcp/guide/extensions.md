# Making an extension

An extension adds to Swiss Army Bench without changing it: a project type, a page on the rail, commands, routes,
starter blades, a deploy target. It is backend and data only: Python and its manifest. The front end draws what
the manifest says; an extension never ships `.ts`, `.tsx`, `.css` or `.html`. Usually an extension adds three
things: blades, language support (a cell kind, its completion, a runtime) and a canvas; the data and the APIs
underneath stay the same (design principles 1.0 and 13a).

Read the existing ones before writing one: `extensions/copilot/` is the smallest (a panel, three commands),
`extensions/powerbi/` adds a project type and a rail page, `extensions/streamlit/` a canvas.

## How it is found
Today an extension is a package (folders in the library are planned: see the end).
- Its `pyproject.toml` names the base at the same version and registers one entry point:
  `[project.entry-points."swissarmybench.extensions"]` with `<id> = "<package>.extension"`.
- The base reads the installed entry points once at start (`src/swissarmybench/adapters/extensions.py`). One that
  fails to import is left out and the app starts anyway.
- In a checkout, `SWISSARMYBENCH_EXTENSIONS=<id>` turns one on without installing it (its `src/` on the path);
  `-<id>` turns an installed one off. Tests do this in `tests/conftest.py`.
- `extensions_list` shows what is on; `extensions_install` and `extensions_remove` wait for the user's Allow.

## The layout
Arranged like the base (Cosmic Python, REFACTOR.md): imports point inwards, one file per feature in each layer.

```
extensions/<id>/
  pyproject.toml            the package, its entry point, `swissarmybench[server]==<the base's version>`
  README.md
  src/<package>/
    __init__.py             __version__
    extension.py            the manifest and the composition root (below)
    commands.py             the agent's commands
    domain/                 rules: standard library (and sqlglot) only, no input or output, no clock
    services/               use cases, given their ports
    adapters/               files, processes, the network
    server/routes.py        Starlette routes under /<id>/...
    starters/               read-only .blade.py starters (optional)
  tests/ in the repository's tests/: test_<id>_*.py
```

## extension.py: the manifest
Plain module values the base reads; leave out what you do not use.

| Name | What it is |
|---|---|
| `ID`, `NAME`, `VERSION`, `DESCRIPTION`, `ADDS` | who it is; `ADDS` is the Extensions card's list of what it adds |
| `describe()` | `{"id", "name", "description", "version", "adds"}` |
| `MODE` | its project type as data (copy the exact keys from `extensions/powerbi`'s): `type`, `name`, `deliverable`, `canvases`, `families`, `languages`, its extra cell kinds, `tools` (its command prefix), `export`, `areas` (the features open in it), `title`, `for_whom`, `explain`, `example`, `first_open`, `tour` |
| `scaffold(name, data_names)` | a new project's own files: `{"app", "files", "requirements"}` |
| `AREAS` | `((area, words),)`: its command prefix and what it covers |
| `RAIL` | `[{"area", "name", "icon", "panel"}]`: a rail page drawn from the `panel` route's data |
| `PANEL` | a route whose data draws its card on the Extensions page and in Settings |
| `PAGE_ACTIONS` | buttons it adds to a base page: `{"page", "id", "label", "icon", "title"}` |
| `INLINE_COMPLETION` | the editors' ghost-text routes |
| `OPENS` | `{".ext": "/<id>/opened"}`: files it opens when one is dropped on the app |
| `STARTERS` | its starter folder's path |
| `API_TARGETS` | more deploy targets for a local sandbox API |
| `SECRET_PATHS` | route prefixes that carry their own secret (a live page's) |
| `SESSION_RULES` | `{audit action: (detail, extra) -> (words, area, place)}`: the Session page's words |
| `BASE_MODE_ADDS` | what it adds to the base's BI project type |
| `routes(services)` | the composition root: build its adapters and services from the base's `services`, return its routes |
| `stop(services)` | async: end its processes when the app stops |
| `commands()` | its `COMMANDS` dictionary (below) |

Rules for `routes(services)`:
- take what you need from `services` (`settings.state_dir`, `ws.audit`, `agent.approvals`, `live`,
  `sab_projects`, `connections`, `connection_tables`, `variables`); keep your service on it
  (`services.<id> = service`) only for `stop` and tests;
- reach data only through the base's tools (connections and their tables, the sandbox, the local sandbox API,
  the widget contract): never your own reader, writer or client for something a shared tool does. If one is
  missing, it is added to the shared tool for every extension.

## commands.py: the golden rule
Every action a user can take in it is a command the agent can run, in the same change.

```python
from swissarmybench.cli import api
from swissarmybench.cli.commands import Command, Registrar, req

COMMANDS: dict[str, Command] = {}
command = Registrar(COMMANDS)

@command("inventory_status", "The inventory page's state")
def inventory_status(a: dict[str, object]) -> object:
    return api.call("GET", "/inventory")

@command("inventory_sync", "Sync a store's counts (waits for the user's Allow)", req("store", "Its name."))
def inventory_sync(a: dict[str, object]) -> object:
    return api.call("POST", "/inventory/sync", {"store": a["store"]})
```

- Name every command `<prefix>_<verb>`, the prefix in `MODE["tools"]` and `AREAS`.
- A refusal is `CommandError` (from `swissarmybench.cli.commands`) with one plain sentence, never a bare exception.
- The agent's tools list has a size budget (`tests/test_cli.py`): group related actions behind one command with an
  `action` argument rather than many small ones.
- What changes something outside the app, writes a file the user did not ask for, or reads rows into the agent's
  answer waits for the user's Allow (`services.agent.approvals.ask`). The agent never answers its own approval.

## server/routes.py
Starlette routes under `/<id>/`. Shape answers with `swissarmybench.server.http`: `with_body` and `with_actor`
read the request and who is asking; every refusal is the one refusal shape (`error`, `where`, `fixes`, `details`).
Routes are behind the base's guard (127.0.0.1, the token): never open a port of your own to the outside.

## The rules that always hold
- **Data is sensitive:** made-up data only in tests, examples and screenshots; nothing on disk but what the user
  saves, the project's folder and the library; no secret, token or password in a file, a log or an answer
  (variables by name; values from the keyring or a vault).
- **Portable code:** what it generates runs unchanged on an Azure Function App or a hosted Streamlit app; anything
  that works only on this computer says so in amber ("Only works on your machine: ... use ... instead").
- **Simple:** the simplest thing for the task at hand; no layer, option or class with one user; code it writes
  reads top to bottom like a roadmap; nothing nested past two levels without a reason.
- **Typed:** type hints everywhere; `ruff check`, `ruff format --check` and `mypy` clean.

## Tests
- Rules first (its `domain/`), then its routes through the base's test client, then its commands.
- A stand-in for anything that cannot run here (see `tests/copilot_standin.py`, `tests/devtunnel_standin.py`).
- A browser test that builds one thing end to end in Chromium, with made-up data.
- The base's own tests keep the boundary: no extension's name in `web/`, no front-end file in an extension, each
  manifest against the shared shapes.

## Planned, not yet loadable
- **Folders in the library** (Plans/folder-extensions.plan.md): `library/extensions/<id>/` with the same
  `extension.py`, `commands.py`, `sources.py`, `starters/` and `README.md`, found at start, trusted like the
  library's blades, a missing package offered through the Install now prompt, and a New extension scaffold.
- **The project contract** (Plans/adapter.plan.md): a `project.json` at the extension's root (JSON; not a project's own `.sab/project.json`) listing the files the
  extension owns, made or yours, and what grows each; the base scaffolds, grows and exports a project from it.
- **Sources for the adapter:** `sources.py` with three calls (list tables, read a plan as Arrow, write Arrow),
  the only way an extension reaches data once the adapter exists.
