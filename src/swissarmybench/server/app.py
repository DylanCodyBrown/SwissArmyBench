"""The web app: asks the composition root (bootstrap.py) for the services and mounts every route
behind the guard.

Route modules, one per area, like ASP.NET controllers. Each is given its service (services/*.py)
and does nothing but read the request, call the use case and shape the answer:
  routes_datasets.py       push, list, close, load a file, paste, the "+" tab; health and shutdown
  routes_grids.py          rows, steps, profile, SQL, export, code for one grid
  routes_analysis.py       the Analyze menu's analyses on one grid's view
  routes_regression.py     regression and what-if predictions
  routes_timeseries.py     time series and forecast
  routes_tieout.py         the tie-out report on a compare
  routes_agent.py          the MCP door: the agent's reads, approvals, the current table
  routes_cards.py          side-panel charts and notes (plan section 11)
  routes_catalog.py        catalogs (a source's names and types)
  routes_blades.py         blades (saved code that loads): the user's alone
  routes_connections.py    connections (database and file blades, seen apart): the user's alone
  routes_connection_tables.py  a connection's tables: the tree, Open all, DuckDB SQL naming them
  routes_connection_swap.py  a table's connection swapped (its steps kept), every table of a deleted
                           one moved, the code that named it pointed at the new one
  routes_apis.py           Add API: an OpenAPI document or a form made into API_<name>.py and a connection
  routes_api_explorer.py   the APIs page: the library's APIs, their operations, search, send, save a web call
  routes_structures.py     Structures: JSON, YAML, XML and TOML as documents, their steps, Open as grid, Save
  routes_folders.py        the page's file chooser: a folder's contents, the user's alone
  routes_workbench.py      the Workbench: notebooks, scripts and their kernels, the user's alone
  routes_table_cells.py    every table's read-only cell in a Workbench document, and its Tables group
  routes_lineage.py        a cell's or a canvas block's lineage, back to the data, with each step's value
  routes_projects.py       projects: a new one, its files, Export data.py
  routes_sab_projects.py   a project is a folder: new, open, save, copy, an old .sab imported, close, a fix
  routes_project_explorer.py  the Project Explorer: every project as a card, sorted, the types explained
  routes_project_scope.py  what belongs to the open project: its documents, and importing into it
  routes_script_export.py  Export as one Python script: a notebook or script as one .py
  routes_panels.py         the panels' switches in Settings (memory only: all on at each start)
  routes_modes.py          project modes: the open project's type and its working set (canvases, families)
  (each extension's)       an extension that is on brings its own routes (swissarmybench/extensions.py)
  routes_explorer.py       the Data Explorer's search: connections, catalogs, open tables, variables, blades
  routes_navigation.py     app_navigate: a window sent Home, Back, Forward or to a view (the page moves)
  routes_kind_colours.py   the kind colours in Settings (kept across restarts)
  routes_library.py        the library: its folder (Settings), what is in it, the move's notice
  routes_connection_colours.py   each connection's colour (kept in its record), the cells' connections
  routes_session_log.py    the Session page: this session's log of what was made, Follow the agent
  routes_variables.py      the Variables page: this computer's variables, their sources and uses
  routes_script_runs.py    a script's run settings, Run as scheduled and its run history
  routes_beta_log.py       beta mode, the beta log and the beta notes (beta_requests.py times requests)
  routes_updates.py        the update check, its Settings switch, Update to X, the tray's menu
  routes_extensions.py     the Extensions page: the catalog, Install and Remove (the updater's helper)
  routes_claude.py         Launch Claude: Claude Code in a terminal, or Claude Desktop (the user's only)
  streamlit_proxy.py       live pages passed through under their own secret (the extensions' Streamlit and dev
                           servers mount it with their own prefix)
  routes_relationships.py  the relationship model, the Key Finder, comparing two grids
  routes_processes.py      Python sessions offering tables: the Open list
  routes_snapshots.py      a PNG of the page the user sees, drawn by the page, for an agent
plus here: the WebSocket for live updates, the grid page shell and its static files.

All DuckDB work runs on the priority worker pool (adapters/database.py), never on the event loop.
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from swissarmybench.bootstrap import bootstrap
from swissarmybench.domain import session_log as session_log_rules
from swissarmybench.server import (
    routes_agent,
    routes_analysis,
    routes_api_explorer,
    routes_apis,
    routes_beta_log,
    routes_blades,
    routes_cards,
    routes_catalog,
    routes_claude,
    routes_connection_colours,
    routes_connection_swap,
    routes_connection_tables,
    routes_connections,
    routes_datasets,
    routes_explorer,
    routes_extensions,
    routes_folders,
    routes_grids,
    routes_intellisense,
    routes_kind_colours,
    routes_library,
    routes_lineage,
    routes_modes,
    routes_navigation,
    routes_packs,
    routes_panels,
    routes_processes,
    routes_project_explorer,
    routes_project_scope,
    routes_projects,
    routes_regression,
    routes_relationships,
    routes_sab_projects,
    routes_script_export,
    routes_script_runs,
    routes_session_log,
    routes_snapshots,
    routes_structures,
    routes_table_cells,
    routes_tieout,
    routes_timeseries,
    routes_updates,
    routes_variables,
    routes_workbench,
)
from swissarmybench.server.beta_requests import BetaRequests
from swissarmybench.server.security import (
    OLD_WEBSOCKET_SUBPROTOCOL,
    WEBSOCKET_SUBPROTOCOL,
    LocalOnlyGuard,
    cookie_name,
)
from swissarmybench.settings import Settings

# How often the server looks for Python sessions that stopped reporting.
PRUNE_EVERY_SECONDS: float = 10.0
ANY = ["GET", "POST", "PUT", "PATCH", "DELETE"]


def not_installed(name: str, ident: str) -> Callable[[Request], Awaitable[Response]]:
    """The answer of an extension's door while it is not installed here: which one, and where to add it."""

    async def answer(request: Request) -> Response:
        words = f"This is the {name} extension's, and it is not installed here: install it on the Extensions "
        words += "page."
        return JSONResponse({"error": words, "extension": ident}, status_code=404)

    return answer


def create_app(
    port: int,
    token: str,
    settings: Settings | None = None,
    on_shutdown: Callable[[], None] | None = None,
    audit_log: bool = True,
) -> Starlette:
    """Build the app for a server listening on 127.0.0.1:`port` that accepts `token`."""
    ctx = bootstrap(port, token, settings, on_shutdown, audit_log)
    settings, workers = ctx.settings, ctx.workers
    # The pages' cookie (security.py): a secret of this start's own, never the token, in memory only.
    session_secret = secrets.token_urlsafe(32)
    # Each extension that is on: its live pages' secret paths (the guard lets them through, the route checks
    # the secret) and its Session page words.
    secret_paths = tuple(p for extension in ctx.switched_on for p in getattr(extension, "SECRET_PATHS", ()))
    for extension in ctx.switched_on:
        session_log_rules.RULES.update(getattr(extension, "SESSION_RULES", None) or {})
    # The catalog's extensions that are not on: a call on their routes says which one it needs.
    on_ids = {str(getattr(extension, "ID", "")).lower() for extension in ctx.switched_on}
    missing = [e for e in ctx.extensions.catalog if e.id not in on_ids]

    async def session(request: Request) -> Response:
        # The guard let the request in (the token, or a good cookie). POST: the cookie for this start.
        answer = JSONResponse({"ok": True})
        if request.method == "POST":
            answer.set_cookie(
                cookie_name(port), session_secret, httponly=True, samesite="strict", path="/", secure=False
            )
        return answer

    async def live(websocket: WebSocket) -> None:
        # Echo our subprotocol only when the client offered it (browsers do; others may not).
        offered: list[str] = websocket.scope.get("subprotocols", [])
        ours = [p for p in (WEBSOCKET_SUBPROTOCOL, OLD_WEBSOCKET_SUBPROTOCOL) if p in offered]
        await websocket.accept(subprotocol=ours[0] if ours else None)
        ctx.live.add(
            websocket,
            websocket.query_params.get("grid"),
            workspace=websocket.query_params.get("workspace") == "1",
            # A VS Code window (the extension): it shows the workspace when a push needs it.
            opener=websocket.query_params.get("opener") == "1",
            # A Workbench window: the agent's workbench_window commands go to it.
            workbench=websocket.query_params.get("workbench") == "1",
            # The blades page: the agent's app_navigate to the catalog window goes to it.
            catalog=websocket.query_params.get("catalog") == "1",
            window=websocket.query_params.get("window"),
        )
        try:
            while True:
                # The only message a client sends: a VS Code or Workbench window saying it came to the front.
                if await websocket.receive_text() == '{"type":"focus"}':
                    ctx.live.focus(websocket)
        except WebSocketDisconnect:
            pass
        finally:
            ctx.live.discard(websocket)

    async def grid_page(request: Request) -> Response:
        return FileResponse(settings.web_root / "index.html", headers={"Cache-Control": "no-store"})

    async def workspace_page(request: Request) -> Response:
        # The same page as /g/<id>: it shows every open grid as a tab, opened on the last one.
        return FileResponse(settings.web_root / "index.html", headers={"Cache-Control": "no-store"})

    async def catalog_page(request: Request) -> Response:
        # Blades and the catalog explorer, in a tab of its own (plan decision 18).
        return FileResponse(settings.web_root / "catalog.html", headers={"Cache-Control": "no-store"})

    async def workbench_page(request: Request) -> Response:
        # Notebooks and scripts, always in a window of their own (the grid page's Workbench tab opens it).
        # ?panel=explorer: the Data Explorer popped out into a window of its own.
        page = "explorer.html" if request.query_params.get("panel") == "explorer" else "workbench.html"
        return FileResponse(settings.web_root / page, headers={"Cache-Control": "no-store"})

    async def drop_silent_sessions() -> None:
        # A notebook that closes or crashes just stops reporting; the list notices within a few
        # seconds and tells the pages, so a dead session never lingers in the Open dialog.
        while True:
            await asyncio.sleep(PRUNE_EVERY_SECONDS)
            await ctx.sessions.drop_silent()
            # A Workbench window closed (or reloaded) a minute ago: its kernels stop.
            windows = ctx.live.workbench_windows()
            await ctx.workbench.stop_orphans(windows)
            await ctx.hooks.stop_orphans(windows)  # and what they left running (an extension's)

    @asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        pruner = asyncio.create_task(drop_silent_sessions())
        # The update check: at start, then every six hours (nothing with the switch off or no feeds).
        checker = asyncio.create_task(ctx.updates.run_forever())
        ctx.beta.started()  # the beta log: the version, OS and Python, and the crashes from here on
        ctx.variables.apply()  # the Variables page's values, in this server's environment
        ctx.catalog_loading.at_start()  # every connection's catalog, in the background
        ctx.extensions.bring_back()  # a preinstalled extension an update from a built-in version lacks
        autosave = asyncio.create_task(ctx.sab_projects.run_autosave())  # the open project's switch
        context_md = asyncio.create_task(ctx.context_md.run_forever())  # Launch Claude's folder's context.md
        yield
        context_md.cancel()
        autosave.cancel()
        pruner.cancel()
        checker.cancel()
        await ctx.workbench.stop_all()  # no kernel outlives the server
        await ctx.sab_projects.stop()
        for extension in ctx.switched_on:  # nor an extension's processes (a code app's dev server)
            stop = getattr(extension, "stop", None)
            if callable(stop):
                await stop(ctx)
        ctx.variables.release()  # the environment as it was
        workers.close()
        ctx.beta.stopped()

    app = Starlette(
        routes=[
            *routes_datasets.routes(ctx.datasets),
            *routes_grids.routes(ctx.grids, ctx.profiles, ctx.sql, ctx.exports, ctx.codes),
            *routes_analysis.routes(ctx.grids, ctx.analysis),
            *routes_regression.routes(ctx.grids, ctx.regression),
            *routes_timeseries.routes(ctx.grids, ctx.timeseries),
            *routes_agent.routes(ctx.agent, ctx.inbox),
            *routes_cards.routes(ctx.cards),
            *routes_catalog.routes(ctx.catalogs),
            *routes_blades.routes(ctx.blades),
            *routes_connection_swap.routes(ctx.connection_swap),
            *routes_connection_tables.routes(ctx.connection_tables, ctx.blades, ctx.connections),
            *routes_connections.routes(
                ctx.connections, ctx.blades, ctx.catalog_loading, ctx.connection_usage
            ),
            *routes_apis.routes(ctx.apis),
            *routes_structures.routes(ctx.structures),
            *routes_api_explorer.routes(ctx.api_explorer),
            *routes_folders.routes(ctx.folders),
            *routes_intellisense.routes(ctx.intellisense),
            *routes_workbench.routes(ctx.workbench, ctx.workbench_window),
            *routes_table_cells.routes(ctx.table_cells),
            *routes_lineage.routes(ctx.lineage),
            *routes_projects.routes(ctx.projects),
            *routes_sab_projects.routes(ctx.sab_projects),
            *routes_project_explorer.routes(ctx.project_explorer),
            *routes_project_scope.routes(ctx.project_scope),
            *routes_script_export.routes(ctx.script_exports),
            *routes_panels.routes(ctx.panels),
            *routes_modes.routes(ctx.modes),
            # Each extension that is on: its routes, given the services (its own are built from them).
            *(route for extension in ctx.switched_on for route in extension.routes(ctx)),
            # Each catalog extension that is not on here: its door answers which extension it is.
            *(Route(f"/{e.id}/{{rest:path}}", not_installed(e.name, e.id), methods=ANY) for e in missing),
            *routes_explorer.routes(ctx.explorer),
            *routes_navigation.routes(ctx.navigation),
            *routes_kind_colours.routes(ctx.kind_colours),
            *routes_library.routes(ctx.library),
            *routes_connection_colours.routes(ctx.connection_colours),
            *routes_session_log.routes(ctx.session_log),
            *routes_variables.routes(ctx.variables),
            *routes_script_runs.routes(ctx.script_runs),
            *routes_beta_log.routes(ctx.beta),
            *routes_updates.routes(ctx.updates, ctx.extensions.names),
            *routes_extensions.routes(ctx.extensions),
            *routes_claude.routes(ctx.claude),
            *routes_relationships.routes(ctx.models, ctx.finder, ctx.keys, ctx.compares),
            *routes_tieout.routes(ctx.tie_out),
            *routes_packs.routes(ctx.packs),
            *routes_processes.routes(ctx.sessions),
            *routes_snapshots.routes(ctx.snapshots),
            WebSocketRoute("/ws", live),
            Route("/g/{grid_id}", grid_page),
            # The bare address goes to the app's page; the browser keeps the #token fragment across it.
            Route("/", lambda request: RedirectResponse("/workspace", status_code=307)),
            Route("/session", session, methods=["GET", "POST"]),
            Route("/workspace", workspace_page),
            Route("/catalog", catalog_page),
            Route("/workbench", workbench_page),
            Mount("/static", StaticFiles(directory=settings.web_root, check_dir=False)),
        ],
        middleware=[
            Middleware(
                LocalOnlyGuard, port=port, token=token, session=session_secret, secret_paths=secret_paths
            ),
            Middleware(BetaRequests, beta=ctx.beta, slow_seconds=settings.beta_slow_seconds),
        ],
        lifespan=lifespan,
    )
    app.state.ctx = ctx
    return app
