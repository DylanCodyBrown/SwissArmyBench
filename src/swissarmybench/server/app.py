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
  routes_found_connections.py  Find connections on this computer: the known tools and the hint scan, import
  routes_connection_tables.py  a connection's tables: the tree, Open all, DuckDB SQL naming them
  routes_connection_slots.py  each connection's slots (queries at once, the agent's share, the line), the
                           Queries window, a kernel's leased slot
  routes_connection_swap.py  a table's connection swapped (its steps kept), every table of a deleted
                           one moved, the code that named it pointed at the new one
  routes_apis.py           Add API: an OpenAPI document or a form made into API_<name>.py and a connection
  routes_api_explorer.py   the APIs page: the library's APIs, their operations, search, send, save a web call
  routes_actions.py        every API's actions through api_adapter: list, describe, run, discover, build
  routes_structures.py     Structures: JSON, YAML, XML and TOML as documents, their steps, Open as grid, Save
  routes_folders.py        the page's own file picker: a folder's contents, its quick places, New folder
  routes_file_dialogs.py   the system's own file dialog, on the user's click (403 for the agent)
  routes_workbench.py      the Workbench: notebooks, scripts and their kernels, the user's alone
  routes_table_cells.py    every table's read-only cell in a Workbench document, and its Tables group
  routes_lineage.py        a cell's or a canvas block's lineage, back to the data, with each step's value
  routes_projects.py       projects: a new one, its files, Export data.py
  routes_sab_projects.py   a project is a folder: new, open, save, copy, close, a fix
  routes_project_explorer.py  the Project Explorer: every project as a card, sorted, the types explained
  routes_project_scope.py  what belongs to the open project: its documents, and importing into it
  routes_project_outline.py  the project's outline: ARCHITECTURE.md, read or written
  routes_script_export.py  Export as one Python script: a notebook or script as one .py
  routes_modes.py          project modes: the open project's type and its working set (canvases, families)
  (each extension's)       an extension that is on brings its own routes (swissarmybench/extensions.py)
  routes_explorer.py       the Data Explorer's search: connections, catalogs, open tables, variables, blades
  routes_navigation.py     app_navigate: a window sent Home, Back, Forward or to a view (the page moves)
  frontend_pages.py        the swap: a classic page's address answers with its Blazor page (ClassicToBlazor)
  routes_library.py        the library: its folder (Settings), what is in it, the move's notice
  routes_app_registrations.py  app registrations (a library item) and their access reports
  routes_team.py           Settings' Team box: join, start or leave a team (one GitHub repository)
  routes_local_api.py      the project's local sandbox API: API.py, Run, Stop, calls, its log
  routes_sandbox.py        the project's sandbox: tables, Reset, checkpoints, an API's data calls
  routes_scaffold.py       the project scaffold's made files: their state, a refresh, Take the new one
  routes_sharing.py        Share a running app with your organization (Microsoft Dev Tunnels)
  routes_shared_catalog.py the shared catalog: the library's catalog/ (tables, keys, used_by), refreshed
  routes_connection_colours.py   each connection's colour (kept in its record), the cells' connections
  routes_session_log.py    the Session page: this session's log of what was made, Follow the agent
  routes_call_stats.py     every call's statistics: the agent's views, the pages' figures
  routes_changes.py        the open project's change log: last, history, since, search
  routes_variables.py      the Variables page: this computer's variables, their sources and uses
  routes_environment.py    the Environment: everything the project holds, where each is used, its libraries
  routes_script_runs.py    a script's run settings
  routes_beta_log.py       beta mode, the beta log and the beta notes (beta_requests.py times requests)
  routes_updates.py        the update check, its Settings switch, Update to X
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
from typing import Any
from urllib.parse import urlencode

from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import BaseRoute, Mount, Route, WebSocketRoute
from starlette.staticfiles import NotModifiedResponse, StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from swissarmybench import __version__
from swissarmybench.bootstrap import bootstrap
from swissarmybench.domain import session_log as session_log_rules
from swissarmybench.domain import workbench_pages
from swissarmybench.extensions import manifest
from swissarmybench.server import (
    routes_actions,
    routes_agent,
    routes_analysis,
    routes_analyze,
    routes_api_explorer,
    routes_apis,
    routes_app_registrations,
    routes_beta_log,
    routes_blades,
    routes_call_stats,
    routes_cards,
    routes_catalog,
    routes_changes,
    routes_claude,
    routes_connection_colours,
    routes_connection_slots,
    routes_connection_swap,
    routes_connection_tables,
    routes_connections,
    routes_datasets,
    routes_debugger,
    routes_desktop,
    routes_environment,
    routes_explorer,
    routes_extensions,
    routes_file_dialogs,
    routes_folders,
    routes_found_connections,
    routes_grids,
    routes_intellisense,
    routes_library,
    routes_lifecycle,
    routes_lineage,
    routes_local_api,
    routes_modes,
    routes_navigation,
    routes_processes,
    routes_project_explorer,
    routes_project_outline,
    routes_project_scope,
    routes_projects,
    routes_regression,
    routes_relationships,
    routes_sab_projects,
    routes_sandbox,
    routes_scaffold,
    routes_script_export,
    routes_script_ide,
    routes_script_runs,
    routes_session_log,
    routes_shared_catalog,
    routes_sharing,
    routes_snapshots,
    routes_structures,
    routes_table_cells,
    routes_team,
    routes_tieout,
    routes_timeseries,
    routes_updates,
    routes_variables,
    routes_workbench,
)
from swissarmybench.server.beta_requests import BetaRequests
from swissarmybench.server.frontend_pages import ClassicToBlazor, chosen_by
from swissarmybench.server.http import guarded
from swissarmybench.server.routes_connection_slots import CallerAtTheDoor
from swissarmybench.server.security import (
    WEBSOCKET_SUBPROTOCOL,
    LocalOnlyGuard,
    cookie_name,
)
from swissarmybench.settings import Settings

# How often the server looks for Python sessions that stopped reporting.
PRUNE_EVERY_SECONDS: float = 10.0
ANY = ["GET", "POST", "PUT", "PATCH", "DELETE"]


async def _no_such_address(request: Request, error: Exception) -> Response:
    """Starlette's own 404 and 405 (an address no route has, a method it does not take) in the one shape."""
    status = getattr(error, "status_code", 404)
    words = "No such address." if status == 404 else f"{request.method} is not taken at this address."
    return JSONResponse({"error": words, "where": request.url.path}, status_code=status)


def not_installed(name: str, ident: str) -> Callable[[Request], Awaitable[Response]]:
    """The answer of an extension's door while it is not installed here: which one, and where to add it."""

    async def answer(request: Request) -> Response:
        words = f"This is the {name} extension's, and it is not installed here: install it on the Extensions "
        words += "page."
        return JSONResponse({"error": words, "extension": ident}, status_code=404)

    return answer


# A page's split parts are named for their content (web/build.mjs: build/chunks/<page>-<hash>.js): a saved
# copy is good for ever. Every other file is checked first (a 304 when it has not changed).
FOREVER = "public, max-age=31536000, immutable"


def cache_header(path: str) -> str:
    """The Cache-Control of a page's file (`path` under /static/): the hashed chunks kept for ever, the rest
    checked before a saved copy is used again."""
    return FOREVER if path.replace("\\", "/").startswith("build/chunks/") else "no-cache"


def versioned_etag(etag: str, version: str) -> str:
    """The file's ETag with the app's version in it: another version's saved copy never answers a 304, even
    when its file's time and size happen to be the same (an update's install sets both)."""
    inner = etag.strip().removeprefix("W/").strip('"')
    return f'"{inner}-{version}"'


class CheckedStaticFiles(StaticFiles):
    """The page's files, each checked before a saved copy is used again (`Cache-Control: no-cache`; a 304 when
    it has not changed and is this version's). Without it the desktop app's browser kept an update's old
    scripts (the owner, 2026-11-19: the {x} buttons still showing in 0.0.27). The hashed chunks are kept for
    ever (their names change with them)."""

    def file_response(self, full_path: Any, stat_result: Any, scope: Any, status_code: int = 200) -> Response:
        answer = FileResponse(full_path, status_code=status_code, stat_result=stat_result)
        answer.headers["etag"] = versioned_etag(answer.headers.get("etag", ""), __version__)
        # Only the ETag says whether a saved copy is good: an update's files may keep their old times.
        if "last-modified" in answer.headers:
            del answer.headers["last-modified"]
        answer.headers["Cache-Control"] = cache_header(self.get_path(scope))
        if self.is_not_modified(answer.headers, Headers(scope=scope)):
            return NotModifiedResponse(answer.headers)
        return answer


# Said at /blazor/ when the Blazor front end is not built here (blazor/README.md says how).
BLAZOR_MISSING: str = (
    "<!doctype html><html><head><meta charset='utf-8'><title>Swiss Army Bench</title></head><body "
    "style='font:15px system-ui,sans-serif;margin:48px'><p>The Blazor front end is not built here. "
    "<a href='/workspace'>Open the classic front end</a>.</p></body></html>"
)


class BlazorFiles(CheckedStaticFiles):
    """The Blazor front end's files at /blazor/. An address of one of its pages (/blazor/connections, no file
    by that name) answers its index.html: the app's own router draws the page (a reload, Back, a bookmark)."""

    async def get_response(self, path: str, scope: Any) -> Response:
        try:
            return await super().get_response(path, scope)
        except Exception as error:
            last = path.rsplit("/", 1)[-1]
            if getattr(error, "status_code", None) != 404 or "." in last:
                raise
            return await super().get_response("index.html", scope)


def blazor_routes(root: Any) -> list[BaseRoute]:
    """/blazor/ (the Blazor front end), or one line saying it is not built here."""
    if not (root / "index.html").is_file():

        async def missing(request: Request) -> Response:
            return HTMLResponse(BLAZOR_MISSING)

        return [Route("/blazor", missing), Route("/blazor/{rest:path}", missing)]
    return [
        Route("/blazor", lambda request: RedirectResponse("/blazor/", status_code=307)),
        Mount("/blazor", BlazorFiles(directory=root, html=True, check_dir=False)),
    ]


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
    secret_paths = (
        routes_sandbox.DATA_PREFIX,
        *(p for extension in ctx.switched_on for p in manifest(extension).SECRET_PATHS),
    )
    for extension in ctx.switched_on:
        session_log_rules.RULES.update(manifest(extension).SESSION_RULES or {})
    # The catalog's extensions that are not on: a call on their routes says which one it needs.
    on_ids = {manifest(extension).ID.lower() for extension in ctx.switched_on}
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
        ours = [p for p in (WEBSOCKET_SUBPROTOCOL,) if p in offered]
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
            code_page=websocket.query_params.get("page"),  # notebooks or scripts
            # The agent's event socket is not a window of the app (the server's life counts windows).
            page=websocket.query_params.get("agent") != "1",
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
        # The old blades page (the owner, 2026-11-21: blades move into the Scripts page): its Blades pane, and
        # ?blade=<name> that blade's tab there (an empty name: New blade). The #token goes with the redirect.
        query = urlencode({"pane": "blades"} | dict(request.query_params))  # ?blade= and a layer's open= kept
        return RedirectResponse(f"{workbench_pages.url_of('scripts')}?{query}", status_code=302)

    async def workbench_page(request: Request) -> Response:
        # The old address: notebooks and scripts are two pages now (the owner, 2026-11-21), /notebooks
        # and /scripts (the same page's code, each its own window); an old ?kind= goes to its page.
        # ?panel=explorer, the popped-out Data Explorer's old address: the Data page now (open=data). The
        # browser keeps the address's #token across the redirect.
        if request.query_params.get("panel") == "explorer":
            return RedirectResponse("/workspace?open=data", status_code=302)
        page, kept = workbench_pages.old_address(dict(request.query_params))
        query = f"?{urlencode(kept)}" if kept else ""
        return RedirectResponse(f"{workbench_pages.url_of(page)}{query}", status_code=302)

    async def code_page(request: Request) -> Response:
        # The Notebooks page and the Scripts page: one page's code, each window says which it is by its path.
        return FileResponse(settings.web_root / "workbench.html", headers={"Cache-Control": "no-store"})

    async def drop_silent_sessions() -> None:
        # A notebook that closes or crashes just stops reporting; the list notices within a few
        # seconds and tells the pages, so a dead session never lingers in the Open dialog.
        while True:
            await asyncio.sleep(PRUNE_EVERY_SECONDS)
            await ctx.sessions.drop_silent()
            # A Workbench window closed (or reloaded) a minute ago: its kernels stop.
            windows = ctx.live.workbench_windows()
            await ctx.workbench.stop_orphans(windows)

    @asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        pruner = asyncio.create_task(drop_silent_sessions())
        # The update check: at start, then every six hours (nothing with the switch off or no feeds).
        checker = asyncio.create_task(ctx.updates.run_forever())
        ctx.beta.started()  # the beta log: the version, OS and Python, and the crashes from here on
        ctx.variables.apply()  # the Variables page's values, in this server's environment
        # Every connection's catalog, in the background, once the first window is open (not racing it).
        catalogs = asyncio.create_task(
            ctx.catalog_loading.at_start_later(ctx.settings.catalogs_start_wait_seconds)
        )
        # A vault that loads every secret: its names read again, the same way (kept meanwhile).
        vault_names = asyncio.create_task(
            ctx.vault_names_at_start.at_start_later(ctx.settings.catalogs_start_wait_seconds)
        )
        ctx.extensions.bring_back()  # a preinstalled extension an update from a built-in version lacks
        autosave = asyncio.create_task(ctx.sab_projects.run_autosave())  # the open project's switch
        context_md = asyncio.create_task(ctx.context_md.run_forever())  # Launch Claude's folder's context.md
        shared = asyncio.create_task(ctx.shared_catalog.run_forever())  # what a pull brought
        watch = asyncio.create_task(ctx.file_watch.run_forever())  # a table's file changed on disk
        code_watch = asyncio.create_task(ctx.code_files.run_forever())  # a code file changed anywhere
        # The server's life follows the app's windows (services/lifecycle.py): only a server that can stop.
        life = asyncio.create_task(ctx.lifecycle.run_forever()) if on_shutdown is not None else None
        yield
        if life is not None:
            life.cancel()
        shared.cancel()
        catalogs.cancel()
        vault_names.cancel()
        watch.cancel()
        code_watch.cancel()
        context_md.cancel()
        autosave.cancel()
        pruner.cancel()
        checker.cancel()
        await ctx.local_api.stop_all()  # no local sandbox API outlives the server
        await ctx.sharing.stop_all()  # no share outlives the server (before the apps it tunnels to stop)
        await ctx.project_python.stop()  # a project's .venv being made is left as far as it got
        await ctx.workbench.stop_all()  # no kernel outlives the server
        await ctx.sab_projects.stop()
        for extension in ctx.switched_on:  # nor an extension's processes (a code app's dev server)
            stop = getattr(extension, "stop", None)
            if callable(stop):
                await stop(ctx.seams)
        ctx.variables.release()  # the environment as it was
        workers.close()
        ctx.beta.stopped()

    def connection_names() -> list[str]:
        return [str(c["name"]) for c in ctx.connections.listing()["connections"]]

    app = Starlette(
        # Every route's handler answers a crash in the one refusal shape (http.guarded): no route module
        # writes its own guard.
        routes=guarded(
            [
                *routes_datasets.routes(ctx.datasets),
                *routes_grids.routes(ctx.grids, ctx.profiles, ctx.sql, ctx.exports, ctx.codes),
                *routes_analysis.routes(ctx.grids, ctx.analysis),
                *routes_analyze.routes(ctx.analyze),
                *routes_regression.routes(ctx.grids, ctx.regression),
                *routes_timeseries.routes(ctx.grids, ctx.timeseries),
                *routes_agent.routes(ctx.agent, ctx.inbox),
                *routes_cards.routes(ctx.cards),
                *routes_catalog.routes(ctx.catalogs),
                *routes_blades.routes(ctx.blades),
                # Before the routes that read /connections/{name}: /connections/slots, /connections/queries.
                *routes_connection_slots.routes(
                    ctx.connection_slots,
                    lambda: [str(c["name"]) for c in ctx.connections.listing()["connections"]],
                ),
                *routes_connection_swap.routes(ctx.connection_swap),
                *routes_connection_tables.routes(ctx.connection_tables, ctx.blades, ctx.connections),
                *routes_found_connections.routes(ctx.found_connections),
                *routes_connections.routes(
                    ctx.connections, ctx.blades, ctx.catalog_loading, ctx.connection_usage
                ),
                *routes_apis.routes(ctx.apis),
                *routes_structures.routes(ctx.structures),
                *routes_api_explorer.routes(ctx.api_explorer),
                *routes_actions.routes(ctx.actions),
                *routes_folders.routes(ctx.folders),
                *routes_file_dialogs.routes(ctx.file_dialogs),
                *routes_intellisense.routes(ctx.intellisense),
                *routes_script_ide.routes(ctx.script_ide),
                *routes_debugger.routes(ctx.debugger),
                *routes_workbench.routes(ctx.workbench, ctx.workbench_window, ctx.code_files),
                *routes_table_cells.routes(ctx.table_cells),
                *routes_lineage.routes(ctx.lineage),
                *routes_projects.routes(ctx.projects),
                *routes_sab_projects.routes(ctx.sab_projects),
                *routes_project_explorer.routes(ctx.project_explorer),
                *routes_project_scope.routes(ctx.project_scope),
                *routes_project_outline.routes(ctx.project_outline),
                *routes_script_export.routes(ctx.script_exports),
                *routes_modes.routes(ctx.modes),
                # Each extension that is on: its routes, given the base's seams (services/hooks.py Seams,
                # never the whole Services record); its own services are built from them.
                # (a folder extension's are mounted below, so Remove and New extension change them at once).
                *(
                    route
                    for extension in ctx.switched_on
                    if not manifest(extension).FOLDER
                    for route in extension.routes(ctx.seams)
                ),
                # Each catalog extension that is not on here: its door answers which extension it is.
                *(Route(f"/{e.id}/{{rest:path}}", not_installed(e.name, e.id), methods=ANY) for e in missing),
                *routes_explorer.routes(ctx.explorer),
                *routes_navigation.routes(ctx.navigation),
                *routes_library.routes(ctx.library, ctx.library_setup),
                *routes_team.routes(ctx.team),
                *routes_sharing.routes(ctx.sharing),
                *routes_sandbox.routes(ctx.sandbox, ctx.local_api.data_keys),
                *routes_scaffold.routes(ctx.scaffold),
                *routes_local_api.routes(ctx.local_api, ctx.api_export),
                *routes_app_registrations.routes(ctx.app_registrations),
                *routes_shared_catalog.routes(ctx.shared_catalog),
                *routes_connection_colours.routes(ctx.connection_colours),
                *routes_session_log.routes(ctx.session_log),
                *routes_call_stats.routes(ctx.call_stats),
                *routes_changes.routes(ctx.changes),
                *routes_variables.routes(ctx.variables),
                *routes_environment.routes(ctx.environment),
                *routes_script_runs.routes(ctx.script_runs),
                *routes_beta_log.routes(ctx.beta),
                *routes_updates.routes(ctx.updates, ctx.extensions.names),
                *routes_lifecycle.routes(ctx.lifecycle),
                *routes_desktop.routes(ctx.desktop),
                *routes_extensions.routes(ctx.extensions),
                *routes_claude.routes(ctx.claude),
                *routes_relationships.routes(
                    ctx.models, ctx.finder, ctx.keys, ctx.compares, ctx.project_tables
                ),
                *routes_tieout.routes(ctx.tie_out),
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
                Route("/notebooks", code_page),
                Route("/scripts", code_page),
                Mount("/static", CheckedStaticFiles(directory=settings.web_root, check_dir=False)),
                *blazor_routes(settings.blazor_root),
            ]
        ),
        middleware=[
            Middleware(
                LocalOnlyGuard,
                port=port,
                token=token,
                session=session_secret,
                secret_paths=secret_paths,
                activity=ctx.lifecycle.request,
            ),
            # The swap: a classic page's address answers with its Blazor page while Blazor is the one opened.
            Middleware(
                ClassicToBlazor,
                chosen=chosen_by(ctx.navigation.frontend),
                built=(settings.blazor_root / "index.html").is_file(),
            ),
            Middleware(BetaRequests, beta=ctx.beta, slow_seconds=settings.beta_slow_seconds),
            Middleware(CallerAtTheDoor),  # who each request's connection calls are for (their slots)
        ],
        lifespan=lifespan,
        # No such address, or not that method: the one refusal shape too (design principle 9.5).
        exception_handlers={404: _no_such_address, 405: _no_such_address},
    )
    app.state.ctx = ctx
    _mount_folder_extensions(app, ctx)
    return app


def _mount_folder_extensions(app: Starlette, ctx: Any) -> None:
    """The library's folder extensions' routes, in the running app: each on one mounted now, and again on its
    Load again or New extension; unmounted on its Remove. A routes() that fails is said on its card (its
    error) and leaves the app as it was."""
    from swissarmybench import extensions as loader
    from swissarmybench.domain import extension_folders as folder_rules

    mounted: dict[str, list[BaseRoute]] = {}

    def unmount(ident: str) -> None:
        for route in mounted.pop(ident, []):
            if route in app.router.routes:
                app.router.routes.remove(route)

    def mount(ident: str) -> str:
        unmount(ident)
        found = loader.folders().get(ident)
        if found is None or found.module is None:
            return ""
        try:
            its_routes = getattr(found.module, "routes", None)
            made = guarded(list(its_routes(ctx.seams)) if callable(its_routes) else [])
        except Exception as error:  # its own code: said on its card, never the app's stop
            found.error, found.module = folder_rules.load_error(error, str(found.path)), None
            return found.error
        mounted[ident] = made
        app.router.routes[0:0] = made  # its own /<id>/ addresses (its id is never a base word)
        return ""

    ctx.extensions.mount, ctx.extensions.unmount = mount, unmount
    for extension in ctx.switched_on:
        if manifest(extension).FOLDER:
            mount(str(extension.ID))
