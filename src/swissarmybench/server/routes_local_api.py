"""The project's local sandbox API (services/local_api.py): API.py read, run, called.

GET   /local-api             API.py's settings, endpoints (each one's data words), models, problems, OpenAPI,
                             whether it runs                                                      api(state)
POST  /local-api/new         API.py made when the project has none; its settings                  api(new)
PUT   /local-api/settings    {name, description, target, base_path}: its header
api(settings)
POST  /local-api/run         hosted on 127.0.0.1 (started again when API.py changes)              api(run)
POST  /local-api/stop                                                                             api(stop)
POST  /local-api/call        {method, path, query, body}: one request (the agent's writes on Allow) api(call)
POST  /local-api/agent-writes  {allow}: the agent's writes for the rest of this session (one Allow; the
                             sandbox only); allow false stops them                         api(agent_writes)
GET   /local-api/log         its requests: method, path, status, ms, rows                         api(log)
GET   /local-api/address     where it runs and its key (this computer's own callers)              api(address)
GET   /local-api/openapi.json  its OpenAPI document
GET   /local-api/targets     the framework targets (the base's three, each extension's)        api(targets)
POST  /local-api/scaffold    {table, key?}: New endpoint from a table (the CRUD set, appended)   api(scaffold)
POST  /local-api/check       Will this work for real? each endpoint's SQL against its connection's loaded
                             catalog (never a query, never a load)                              api(check)
POST  /local-api/example     {endpoint, body}: Try it's body kept as the endpoint's example, beside
                             API.py in .sab/api_examples.json (body null: forgotten)      api(example)
GET   /local-api/shapes      Payload shapes: each canvas widget using an endpoint, what it expects beside
                             what the endpoint answers, each mismatch                           api(shapes)
POST  /local-api/export      {target?, folder?, rows?, replace?}: a ready-to-deploy folder        api(export)
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import error_response, json_response, with_actor, with_body
from swissarmybench.services.api_export import ApiExport
from swissarmybench.services.local_api import LocalApi


async def _answered(value: Any) -> Any:
    return value


def routes(api: LocalApi, export: ApiExport) -> list[BaseRoute]:
    async def openapi(request: Request) -> Response:
        try:
            state = await api.state()
            return json_response(state.get("openapi") or {})
        except Exception as error:
            return error_response(error)

    return [
        Route("/local-api", with_actor(lambda who: api.state(None, who))),
        Route("/local-api/new", with_body(api.new), methods=["POST"]),
        Route("/local-api/settings", with_body(api.set_settings), methods=["PUT"]),
        Route("/local-api/run", with_body(api.run), methods=["POST"]),
        Route("/local-api/stop", with_body(api.stop), methods=["POST"]),
        Route("/local-api/call", with_body(api.call), methods=["POST"]),
        Route("/local-api/agent-writes", with_body(api.set_agent_writes), methods=["POST"]),
        Route("/local-api/log", with_actor(lambda who: api.log(None, who))),
        Route("/local-api/address", with_actor(lambda who: api.address(None, who))),
        Route("/local-api/openapi.json", openapi),
        Route("/local-api/targets", with_actor(lambda who: _answered(export.targets(None, who)))),
        Route("/local-api/export", with_body(export.export), methods=["POST"]),
        Route("/local-api/scaffold", with_body(api.scaffold), methods=["POST"]),
        Route("/local-api/check", with_body(api.check), methods=["POST"]),
        Route("/local-api/example", with_body(api.keep_example), methods=["POST"]),
        Route("/local-api/shapes", with_actor(lambda who: api.shapes(None, who))),
    ]
