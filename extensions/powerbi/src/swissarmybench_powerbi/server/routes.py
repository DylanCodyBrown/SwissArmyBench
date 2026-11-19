"""Export to Power BI… (services/export.py), for the ERD page and the agent (`powerbi_export`).

POST /powerbi/plan    {"tables"?, "name"?, "include_rows"?}: what goes, what not and why, the relationships
POST /powerbi/export  the same body: written into the open project's powerbi/ (JSON), or with no project a
                      zip download (the agent's zip is saved in the export folder: JSON)
POST /powerbi/open    {"path"}: the .pbip opened in Power BI Desktop or its folder shown (the user's click:
                      403 for the agent)
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench_powerbi.services.export import PowerBIExport


def routes(export: PowerBIExport) -> list[BaseRoute]:
    async def plan(request: Request) -> Response:
        try:
            return json_response(await export.plan(await read_json(request)))
        except Exception as error:
            return error_response(error)

    async def run(request: Request) -> Response:
        try:
            done = await export.export(await read_json(request), actor(request))
        except Exception as error:
            return error_response(error)
        if "zip" in done:
            return Response(
                done.pop("zip"),
                media_type="application/zip",
                headers={"Content-Disposition": f'attachment; filename="{done["file"]}"'},
            )
        return json_response(done)

    async def open_it(request: Request) -> Response:
        try:
            return json_response(export.open(await read_json(request), actor(request)))
        except Exception as error:
            return error_response(error)

    return [
        Route("/powerbi/plan", plan, methods=["POST"]),
        Route("/powerbi/export", run, methods=["POST"]),
        Route("/powerbi/open", open_it, methods=["POST"]),
    ]
