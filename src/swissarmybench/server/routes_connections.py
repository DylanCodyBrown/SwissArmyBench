"""Connections (Plans/workbench-and-connections.plan.md): the databases and files the user reaches, kept
in the blade store and seen apart from blades. The agent may do all of it too (the golden rule); no
answer holds a password's value:

  GET    /connections                 every connection: databases, then files
  GET    /connections/types           the starters, each as the Add connection form
  GET    /connections/{name}          a saved one as the form shows it to change
  POST   /connections                 save a new one        PUT /connections/{name}   change or rename it
  POST   /connections/test            run the form's code (not saved) with the passwords typed into it
  GET    /connections/vaults          the vault blades a password can come from, with their entries
  POST   /connections/vaults/secrets  the secrets' names in a vault (saved, or the form's draft)
  POST   /connections/source          point a password at the keyring, an environment variable or a vault
  POST   /connections/{name}/catalog  load its catalog in the background now (first use: a SQL cell asks)
  POST   /connections/{name}/open     a table as a grid {database, schema, table, all} (a file: its file)
  POST   /connections/{name}/preview  a table's first rows {database, schema, table} (nothing kept)
  GET    /connections/{name}/datasets a Power BI workspace's datasets: from its loaded catalog, or
                                      (?live=1, or no catalog yet) from Power BI itself, with their ids;
                                      ?live=0 never asks Power BI (none until the catalog is loaded)
  POST   /connections/{name}/relationships   {dataset}: one of a Power BI workspace's datasets' own
                                      relationships, merged into the current model (the ERD, the
                                      Key Finder's known joins)
  POST   /connections/variables       your own Python: the environment variables its three boxes read
                                      {code, tables, read} (names only; nothing runs)
  POST   /connections/{name}/tables   your own Python: run List the tables now; the tables it named
  GET    /connections/usage           the Connections page's cards: each one's type, status word (a cheap
                                      check, never a run) and calls this session
  GET    /connections/{name}/usage    one connection: where it is used (cells, canvas blocks, open grids),
                                      its configuration (never a password's value), its calls this session
  POST   /connections/{name}/used     {kind}: a Workbench kernel's call (client/connection_use.py)

Removing, secrets, Refresh, favourites and export are the blade routes' (routes_blades.py).
The use cases are services/connections.py.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.domain.blades import VaultUnavailableError
from swissarmybench.server.blade_runner import RefreshError
from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench.services.blades import BladeService, NeedsValues
from swissarmybench.services.catalog_loading import CatalogLoading
from swissarmybench.services.connection_usage import ConnectionUsage
from swissarmybench.services.connections import ConnectionService


def routes(
    connections: ConnectionService, blades: BladeService, loading: CatalogLoading, usage: ConnectionUsage
) -> list[BaseRoute]:
    async def overview(request: Request) -> Response:
        try:
            return json_response(usage.overview())
        except Exception as error:
            return error_response(error)

    async def used_by(request: Request) -> Response:
        try:
            return json_response(usage.usage(request.path_params["name"]))
        except Exception as error:
            return error_response(error)

    async def report(request: Request) -> Response:
        try:
            return json_response(usage.report(request.path_params["name"], await read_json(request)))
        except Exception as error:
            return error_response(error)

    async def listing(request: Request) -> Response:
        try:
            return json_response(connections.listing())
        except Exception as error:
            return error_response(error)

    async def types(request: Request) -> Response:
        try:
            return json_response(connections.types())
        except Exception as error:
            return error_response(error)

    async def details(request: Request) -> Response:
        try:
            return json_response(connections.details(request.path_params["name"]))
        except Exception as error:
            return error_response(error)

    async def save(request: Request) -> Response:
        try:
            previous = request.path_params.get("name")
            return json_response(await connections.save(await read_json(request), previous, actor(request)))
        except VaultUnavailableError as error:
            return Response(str(error), status_code=409)
        except Exception as error:
            return error_response(error)

    async def vaults(request: Request) -> Response:
        try:
            return json_response(connections.vaults())
        except Exception as error:
            return error_response(error)

    async def vault_names(request: Request) -> Response:
        try:
            return json_response(await connections.vault_names(await read_json(request)))
        except NeedsValues as error:
            return json_response({"needs": error.missing, "message": str(error)}, status_code=409)
        except RefreshError as error:
            failed = blades.run_failure(str(error), error.missing_module, request.path_params.get("name"))
            return json_response(failed, status_code=422)
        except Exception as error:
            return error_response(error)

    async def load_catalog(request: Request) -> Response:
        try:
            return json_response(loading.load(request.path_params["name"], actor(request)))
        except Exception as error:
            return error_response(error)

    async def open_table(request: Request) -> Response:
        try:
            body = await read_json(request)
            return json_response(
                await connections.open_table(request.path_params["name"], body, actor(request))
            )
        except NeedsValues as error:
            return json_response({"needs": error.missing, "message": str(error)}, status_code=409)
        except RefreshError as error:
            failed = blades.run_failure(str(error), error.missing_module, request.path_params.get("name"))
            return json_response(failed, status_code=422)
        except Exception as error:
            return error_response(error)

    async def preview(request: Request) -> Response:
        try:
            body = await read_json(request)
            return json_response(await connections.preview(request.path_params["name"], body))
        except NeedsValues as error:
            return json_response({"needs": error.missing, "message": str(error)}, status_code=409)
        except RefreshError as error:
            failed = blades.run_failure(str(error), error.missing_module, request.path_params.get("name"))
            return json_response(failed, status_code=422)
        except Exception as error:
            return error_response(error)

    async def import_relationships(request: Request) -> Response:
        try:
            body = await read_json(request)
            name = request.path_params["name"]
            return json_response(await connections.import_relationships(name, body, actor(request)))
        except NeedsValues as error:
            return json_response({"needs": error.missing, "message": str(error)}, status_code=409)
        except RefreshError as error:
            failed = blades.run_failure(str(error), error.missing_module, request.path_params.get("name"))
            return json_response(failed, status_code=422)
        except Exception as error:
            return error_response(error)

    async def datasets(request: Request) -> Response:
        try:
            name = request.path_params["name"]
            asked = request.query_params.get("live")
            live = None if asked is None else asked in ("1", "true")
            return json_response(await connections.datasets(name, {}, live))
        except NeedsValues as error:
            return json_response({"needs": error.missing, "message": str(error)}, status_code=409)
        except RefreshError as error:
            failed = blades.run_failure(str(error), error.missing_module, request.path_params.get("name"))
            return json_response(failed, status_code=422)
        except Exception as error:
            return error_response(error)

    async def variables(request: Request) -> Response:
        try:
            return json_response(connections.variables(await read_json(request)))
        except Exception as error:
            return error_response(error)

    async def tables(request: Request) -> Response:
        try:
            body = await read_json(request)
            return json_response(await connections.tables(request.path_params["name"], body, actor(request)))
        except NeedsValues as error:
            return json_response({"needs": error.missing, "message": str(error)}, status_code=409)
        except RefreshError as error:
            failed = blades.run_failure(str(error), error.missing_module, request.path_params.get("name"))
            return json_response(failed, status_code=422)
        except Exception as error:
            return error_response(error)

    async def source(request: Request) -> Response:
        try:
            return json_response(await connections.source(await read_json(request)))
        except Exception as error:
            return error_response(error)

    async def test(request: Request) -> Response:
        body: Any = None
        try:
            body = await read_json(request)
            return json_response(await connections.test(body))
        except NeedsValues as error:
            return json_response({"needs": error.missing, "message": str(error)}, status_code=409)
        except RefreshError as error:
            said = body if isinstance(body, dict) else {}
            name = said.get("name") if isinstance(said.get("name"), str) else None
            failed = blades.run_failure(str(error), error.missing_module, name or None, said.get("template"))
            return json_response(failed, status_code=422)
        except Exception as error:
            return error_response(error)

    return [
        Route("/connections", listing),
        Route("/connections", save, methods=["POST"]),
        Route("/connections/types", types),
        Route("/connections/usage", overview),
        Route("/connections/{name}/usage", used_by),
        Route("/connections/{name}/used", report, methods=["POST"]),
        Route("/connections/test", test, methods=["POST"]),
        Route("/connections/vaults", vaults),
        Route("/connections/vaults/secrets", vault_names, methods=["POST"]),
        Route("/connections/source", source, methods=["POST"]),
        Route("/connections/variables", variables, methods=["POST"]),
        Route("/connections/{name}/tables", tables, methods=["POST"]),
        Route("/connections/{name}/catalog", load_catalog, methods=["POST"]),
        Route("/connections/{name}/open", open_table, methods=["POST"]),
        Route("/connections/{name}/preview", preview, methods=["POST"]),
        Route("/connections/{name}/relationships", import_relationships, methods=["POST"]),
        Route("/connections/{name}/datasets", datasets),
        Route("/connections/{name}", details),
        Route("/connections/{name}", save, methods=["PUT"]),
    ]
