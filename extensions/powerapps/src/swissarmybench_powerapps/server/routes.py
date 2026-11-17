# ruff: noqa: E501 (the routes' table)
"""The Power Apps extension's HTTP door (services/powerapps.py). Every route serves the agent too: each
one's command is named after the route (cli: swissarmybench_powerapps/commands.py).

GET    /powerapps                    the page's picture                        powerapps_state
GET    /powerapps/tools              the tools, versions, install commands      powerapps_tools
POST   /powerapps/tools/install      {tool} (the agent's waits for Allow)       powerapps_tools install=
GET    /powerapps/account            pa auth status                             powerapps_auth
POST   /powerapps/account/sign-in    {account?}: pa auth login (the browser)    powerapps_auth sign_in=
POST   /powerapps/account/switch     {account}: pa auth switch                  powerapps_auth switch=
GET    /powerapps/environments       pac env list                               powerapps_environments
GET    /powerapps/profiles           pac auth list                              powerapps_profiles
POST   /powerapps/profiles           {environment?}: pac auth create            powerapps_profiles create=
PUT    /powerapps/profiles           {index}: pac auth select                   powerapps_profiles select=
GET    /powerapps/project            the open code app                          powerapps_project
POST   /powerapps/project/new        {name, environment_id, parent}             powerapps_new
POST   /powerapps/project/open       {folder}                                   powerapps_open
POST   /powerapps/project/close                                                 powerapps_open close=
GET    /powerapps/project/files      the file tree                              powerapps_files
GET    /powerapps/project/file       ?path=: a file and its language            powerapps_files path=
PUT    /powerapps/project/file       {path, text}: saved                        powerapps_files text=
POST   /powerapps/sources            pa app add data-source                     powerapps_add_source
POST   /powerapps/sources/remove     pa app remove data-source                  powerapps_remove_source
GET    /powerapps/connectors         ?q=&refresh=1: pa connector list           powerapps_connectors
GET    /powerapps/connectors/{name}  the explorer's model of one                powerapps_connector
GET    /powerapps/connections        ?connector=: pa connection list            powerapps_connections
GET    /powerapps/live               Run live's state                           powerapps_run_live state=
POST   /powerapps/live               start the dev server                       powerapps_run_live
DELETE /powerapps/live               stop it                                    powerapps_run_live stop=
POST   /powerapps/push               build, pa app push (Allow)                 powerapps_push
GET    /powerapps/versions           pa app list, this session's pushes         powerapps_versions
POST   /powerapps/custom-connector   the files, pac connector create (Allow)    powerapps_custom_connector
GET    /powerapps/runs[/{run}]       this session's runs, their output          powerapps_runs
       /powerapps/live/<key>/...     the dev server's pages and its socket (the live proxy)

The data notebook (phase 2: services/notebook.py):
GET    /powerapps/notebook                 its kernels, Deno, the data notebook's path   powerapps_notebook
GET    /powerapps/notebook/types           the kernel's `sab` for the editor (text)       (the editor's)
POST   /powerapps/notebook/open            the data notebook (made the first time)       powerapps_notebook open=
POST   /powerapps/notebook/run             {path, kind, code, cell, stream?}             powerapps_ts_run
POST   /powerapps/notebook/complete        {path, code, offset}: Deno's completions      (the editor's)
POST   /powerapps/notebook/interrupt       {path}                                        powerapps_notebook interrupt=
POST   /powerapps/notebook/restart         {path}                                        powerapps_notebook restart=
POST   /powerapps/notebook/stop            {path}: the kernel ends, its folder goes      powerapps_notebook stop=
POST   /powerapps/notebook/grid            {path, id, name}: a table result as a grid    powerapps_ts_grid
POST   /powerapps/notebook/data-ts         {path?, cells?}: data.ts as it would be       powerapps_data_ts
POST   /powerapps/notebook/use-in-app      {path?, cells?}: data.ts into src/            powerapps_data_ts use_in_app=
POST   /powerapps/notebook/preview         {path?, source, cell}: a TSX cell's page      powerapps_tsx_preview
POST   /powerapps/dataverse/grid           {source}: a Dataverse source as a grid        powerapps_dataverse_grid
POST   /powerapps/notebook/prepare/<key>   the kernel's own route (its key, no token): a connection's tables
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import BaseRoute, Route

from swissarmybench.server import streamlit_proxy
from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench_powerapps.domain import ts_notebook as ts_rules
from swissarmybench_powerapps.services.notebook import TsNotebooks
from swissarmybench_powerapps.services.powerapps import PowerApps

LIVE_PREFIX = "/powerapps/live/"
PREPARE_PREFIX = "/powerapps/notebook/prepare/"


def _origin(request: Request) -> str:
    """This server's own address as the kernel reaches it (127.0.0.1 and the port it listens on)."""
    port = request.url.port
    return f"http://127.0.0.1:{port}" if port else ""


async def _body(request: Request) -> Any:
    return await read_json(request) if await request.body() else {}


def routes(service: PowerApps, notebook: TsNotebooks | None = None) -> list[BaseRoute]:
    def door(work: Callable[[Request], Awaitable[Any]]) -> Callable[[Request], Awaitable[Response]]:
        async def answer(request: Request) -> Response:
            try:
                return json_response(await work(request))
            except Exception as error:
                return error_response(error)

        return answer

    async def state(r: Request) -> Any:
        return await service.state()

    async def tools(r: Request) -> Any:
        return await service.tools_state(refresh=r.query_params.get("refresh") == "1")

    async def install(r: Request) -> Any:
        return await service.install_tool((await _body(r)).get("tool"), actor(r))

    async def account(r: Request) -> Any:
        return await service.account()

    async def sign_in(r: Request) -> Any:
        return await service.sign_in((await _body(r)).get("account"), actor(r))

    async def switch(r: Request) -> Any:
        return await service.switch_account((await _body(r)).get("account"), actor(r))

    async def environments(r: Request) -> Any:
        return await service.environments(actor(r))

    async def profiles(r: Request) -> Any:
        return await service.profiles(actor(r))

    async def create_profile(r: Request) -> Any:
        return await service.create_profile((await _body(r)).get("environment"), actor(r))

    async def select_profile(r: Request) -> Any:
        return await service.select_profile((await _body(r)).get("index"), actor(r))

    async def project(r: Request) -> Any:
        return service.project_state()

    async def new(r: Request) -> Any:
        return await service.new_app(await _body(r), actor(r))

    async def open_app(r: Request) -> Any:
        return await service.open_app((await _body(r)).get("folder"), actor(r))

    async def close(r: Request) -> Any:
        return await service.close_app(actor(r))

    async def files(r: Request) -> Any:
        return service.files_tree()

    async def file(r: Request) -> Any:
        return service.read_file(r.query_params.get("path"))

    async def save(r: Request) -> Any:
        body = await _body(r)
        return await service.write_file(body.get("path"), body.get("text"), actor(r))

    async def add_source(r: Request) -> Any:
        return await service.add_source(await _body(r), actor(r))

    async def remove_source(r: Request) -> Any:
        return await service.remove_source(await _body(r), actor(r))

    async def connector_list(r: Request) -> Any:
        q = r.query_params
        return await service.connector_list(q.get("q"), q.get("refresh") == "1", actor(r))

    async def connector(r: Request) -> Any:
        return await service.connector(r.path_params["name"], actor(r))

    async def connection_list(r: Request) -> Any:
        return await service.connection_list(r.query_params.get("connector"), actor(r))

    async def live(r: Request) -> Any:
        return service.live_state()

    async def start(r: Request) -> Any:
        return await service.start_live(actor(r))

    async def stop(r: Request) -> Any:
        return await service.stop_live(actor(r))

    async def push(r: Request) -> Any:
        return await service.push(await _body(r), actor(r))

    async def versions(r: Request) -> Any:
        return await service.versions(actor(r))

    async def custom(r: Request) -> Any:
        return await service.custom_connector(await _body(r), actor(r))

    async def runs(r: Request) -> Any:
        return service.runs(r.path_params.get("run"))

    extra = notebook_routes(notebook, door) if notebook is not None else []
    return [
        *extra,
        Route("/powerapps", door(state)),
        Route("/powerapps/tools", door(tools)),
        Route("/powerapps/tools/install", door(install), methods=["POST"]),
        Route("/powerapps/account", door(account)),
        Route("/powerapps/account/sign-in", door(sign_in), methods=["POST"]),
        Route("/powerapps/account/switch", door(switch), methods=["POST"]),
        Route("/powerapps/environments", door(environments)),
        Route("/powerapps/profiles", door(profiles)),
        Route("/powerapps/profiles", door(create_profile), methods=["POST"]),
        Route("/powerapps/profiles", door(select_profile), methods=["PUT"]),
        Route("/powerapps/project", door(project)),
        Route("/powerapps/project/new", door(new), methods=["POST"]),
        Route("/powerapps/project/open", door(open_app), methods=["POST"]),
        Route("/powerapps/project/close", door(close), methods=["POST"]),
        Route("/powerapps/project/files", door(files)),
        Route("/powerapps/project/file", door(file)),
        Route("/powerapps/project/file", door(save), methods=["PUT"]),
        Route("/powerapps/sources", door(add_source), methods=["POST"]),
        Route("/powerapps/sources/remove", door(remove_source), methods=["POST"]),
        Route("/powerapps/connectors", door(connector_list)),
        Route("/powerapps/connectors/{name}", door(connector)),
        Route("/powerapps/connections", door(connection_list)),
        Route("/powerapps/live", door(live)),
        Route("/powerapps/live", door(start), methods=["POST"]),
        Route("/powerapps/live", door(stop), methods=["DELETE"]),
        Route("/powerapps/push", door(push), methods=["POST"]),
        Route("/powerapps/versions", door(versions)),
        Route("/powerapps/custom-connector", door(custom), methods=["POST"]),
        Route("/powerapps/runs", door(runs)),
        Route("/powerapps/runs/{run}", door(runs)),
        # The app's dev server, passed through under its run's key (the same pattern as Streamlit's).
        *streamlit_proxy.routes(service.live_port_of, prefix=LIVE_PREFIX, what="The code app's dev server"),
    ]


def notebook_routes(
    notebook: TsNotebooks, door: Callable[[Callable[[Request], Awaitable[Any]]], Any]
) -> list[BaseRoute]:
    async def state(r: Request) -> Any:
        return notebook.state()

    async def types(r: Request) -> Response:
        return Response(ts_rules.DECLARATIONS, media_type="text/plain; charset=utf-8")

    async def open_data(r: Request) -> Any:
        return await notebook.open_data_notebook(actor(r))

    async def run(r: Request) -> Response:
        body = await _body(r)
        if not (isinstance(body, dict) and body.get("stream")):
            try:
                return json_response(await notebook.run_all(body, actor(r), _origin(r)))
            except Exception as error:
                return error_response(error)
        outputs = notebook.run(body, actor(r), _origin(r))
        try:  # the kernel started (or Deno missing, said as the usual answer) before the stream begins
            first: dict[str, Any] | None = await outputs.__anext__()
        except StopAsyncIteration:
            first = None
        except Exception as error:
            return error_response(error)

        async def lines() -> AsyncIterator[bytes]:
            try:
                if first is not None:
                    yield (json.dumps(first) + "\n").encode()
                async for output in outputs:
                    yield (json.dumps(output) + "\n").encode()
            except Exception as error:  # the kernel went away mid-run
                yield (json.dumps({"done": {"ok": False, "error": str(error)}}) + "\n").encode()

        return StreamingResponse(
            lines(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"}
        )

    async def complete(r: Request) -> Any:
        return await notebook.complete(await _body(r))

    async def interrupt(r: Request) -> Any:
        return await notebook.interrupt((await _body(r)).get("path"))

    async def restart(r: Request) -> Any:
        return await notebook.restart((await _body(r)).get("path"), actor(r))

    async def stop(r: Request) -> Any:
        return await notebook.stop((await _body(r)).get("path"))

    async def grid(r: Request) -> Any:
        return await notebook.grid(await _body(r), actor(r))

    async def data_ts(r: Request) -> Any:
        return await notebook.data_ts(await _body(r))

    async def use_in_app(r: Request) -> Any:
        return await notebook.use_in_app(await _body(r), actor(r))

    async def preview(r: Request) -> Any:
        return await notebook.preview(await _body(r), actor(r), _origin(r))

    async def dataverse(r: Request) -> Any:
        return await notebook.dataverse_grid(await _body(r), actor(r))

    async def prepare(r: Request) -> Any:
        return await notebook.prepare(r.path_params["key"], await _body(r))

    return [
        Route("/powerapps/notebook", door(state)),
        Route("/powerapps/notebook/types", types),
        Route("/powerapps/notebook/open", door(open_data), methods=["POST"]),
        Route("/powerapps/notebook/run", run, methods=["POST"]),
        Route("/powerapps/notebook/complete", door(complete), methods=["POST"]),
        Route("/powerapps/notebook/interrupt", door(interrupt), methods=["POST"]),
        Route("/powerapps/notebook/restart", door(restart), methods=["POST"]),
        Route("/powerapps/notebook/stop", door(stop), methods=["POST"]),
        Route("/powerapps/notebook/grid", door(grid), methods=["POST"]),
        Route("/powerapps/notebook/data-ts", door(data_ts), methods=["POST"]),
        Route("/powerapps/notebook/use-in-app", door(use_in_app), methods=["POST"]),
        Route("/powerapps/notebook/preview", door(preview), methods=["POST"]),
        Route("/powerapps/dataverse/grid", door(dataverse), methods=["POST"]),
        Route(PREPARE_PREFIX + "{key}", door(prepare), methods=["POST"]),
    ]
