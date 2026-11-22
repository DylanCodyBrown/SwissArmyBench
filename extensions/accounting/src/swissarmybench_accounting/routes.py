"""The Accounting extension's HTTP door (service.py has the use cases). Every route serves the page and the
agent alike (the golden rule), behind the base's guard (the token, 127.0.0.1).

GET    /accounting                                  the extension: its mode, block kinds, formats, charts
POST   /accounting/designs                          open {"path"} or new {"title"}: a design on the server
GET    /accounting/designs/{id}                     its state
PUT    /accounting/designs/{id}                     {"design"}: replaced whole (Undo, the agent's design)
DELETE /accounting/designs/{id}                     closed
POST   /accounting/designs/{id}/save                {"path"?}: the file written
POST   /accounting/designs/{id}/sheets              {"name"?}: a sheet added
PATCH  /accounting/designs/{id}/sheets/{sheet}      {name, freeze, tab_colour, print, index}
DELETE /accounting/designs/{id}/sheets/{sheet}
POST   /accounting/designs/{id}/sheets/{sheet}/blocks   a block placed
PATCH  /accounting/designs/{id}/blocks/{block}      a block changed, moved (cell, sheet), sized (w, h)
DELETE /accounting/designs/{id}/blocks/{block}
POST   /accounting/designs/{id}/play                the workbook built: its preview
GET    /accounting/designs/{id}/preview             the last Play's preview
GET    /accounting/designs/{id}/download            the last Play's .xlsx
POST   /accounting/designs/{id}/export              workbook.py written beside the design
POST   /accounting/templates                        {"folder"?}: the project's templates
POST   /accounting/templates/import                 {"source", "name"?}: an existing workbook as a template
POST   /accounting/templates/show                   {"name"}: its preview, bindings, what they need
POST   /accounting/templates/bind                   {"name", "binding"} or {"name", "unbind"}
POST   /accounting/build                            statements and invoices (dry_run true by default)
POST   /accounting/register                         what was built ({"open": true}: as a grid)
GET    /accounting/functions                        the Excel functions offered (the Excel starters)
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench import sab_excel
from swissarmybench.server.http import actor, json_response, read_json, safely, with_body
from swissarmybench_accounting import design as rules
from swissarmybench_accounting.service import Accounting

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def routes(accounting: Accounting, mode: dict[str, Any], functions: Any) -> list[BaseRoute]:
    live = accounting.ws.live

    async def changed(design_id: str, request: Request) -> None:
        """Every window showing the design draws it again (an agent's edit shows at once)."""
        await live.broadcast({"type": "workbook_changed", "id": design_id, "by": actor(request)})

    def p(request: Request, name: str) -> str:
        return str(request.path_params[name])

    async def about(request: Request) -> Response:
        return json_response(
            {
                "on": True,
                "mode": mode,
                "kinds": list(rules.KINDS),
                "charts": list(rules.CHARTS),
                "aggregates": list(rules.AGGREGATES),
                "operators": list(rules.OPERATORS),
                "formats": sab_excel.FORMATS,
            }
        )

    async def get(request: Request) -> Response:
        return json_response(accounting.state(p(request, "id")))

    async def put(request: Request) -> Response:
        done = accounting.put(p(request, "id"), await read_json(request), actor(request))
        await changed(p(request, "id"), request)
        return json_response(done)

    async def close(request: Request) -> Response:
        return json_response(accounting.close(p(request, "id")))

    async def save(request: Request) -> Response:
        return json_response(
            await accounting.save(p(request, "id"), await read_json(request), actor(request))
        )

    async def add_sheet(request: Request) -> Response:
        done = accounting.add_sheet(p(request, "id"), await read_json(request), actor(request))
        await changed(p(request, "id"), request)
        return json_response(done)

    async def change_sheet(request: Request) -> Response:
        done = accounting.change_sheet(
            p(request, "id"), p(request, "sheet"), await read_json(request), actor(request)
        )
        await changed(p(request, "id"), request)
        return json_response(done)

    async def remove_sheet(request: Request) -> Response:
        done = accounting.remove_sheet(p(request, "id"), p(request, "sheet"), actor(request))
        await changed(p(request, "id"), request)
        return json_response(done)

    async def add_block(request: Request) -> Response:
        done = accounting.add_block(
            p(request, "id"), p(request, "sheet"), await read_json(request), actor(request)
        )
        await changed(p(request, "id"), request)
        return json_response(done)

    async def change_block(request: Request) -> Response:
        done = accounting.change_block(
            p(request, "id"), p(request, "block"), await read_json(request), actor(request)
        )
        await changed(p(request, "id"), request)
        return json_response(done)

    async def remove_block(request: Request) -> Response:
        done = accounting.remove_block(p(request, "id"), p(request, "block"), actor(request))
        await changed(p(request, "id"), request)
        return json_response(done)

    async def play(request: Request) -> Response:
        done = await accounting.play(p(request, "id"), actor(request))
        await changed(p(request, "id"), request)
        return json_response(done)

    async def preview(request: Request) -> Response:
        return json_response(accounting.preview(p(request, "id")))

    async def download(request: Request) -> Response:
        data, name = accounting.download(p(request, "id"))
        safe = name.encode("ascii", "replace").decode().replace('"', "'")
        return Response(
            data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{safe}"'}
        )

    async def export(request: Request) -> Response:
        return json_response(
            await accounting.export(p(request, "id"), await read_json(request), actor(request))
        )

    async def templates(request: Request) -> Response:
        return json_response(accounting.templates(await read_json(request)))

    async def show_template(request: Request) -> Response:
        return json_response(await accounting.template(await read_json(request)))

    async def bind(request: Request) -> Response:
        done = await accounting.bind(await read_json(request), actor(request))
        await live.broadcast({"type": "template_changed", "name": done["name"], "by": actor(request)})
        return json_response(done)

    async def listed_functions(request: Request) -> Response:
        return json_response(functions())

    base = "/accounting/designs/{id}"
    return [
        Route("/accounting", safely(about)),
        Route("/accounting/designs", with_body(accounting.open), methods=["POST"]),
        Route(base, safely(get), methods=["GET"]),
        Route(base, safely(put), methods=["PUT"]),
        Route(base, safely(close), methods=["DELETE"]),
        Route(f"{base}/save", safely(save), methods=["POST"]),
        Route(f"{base}/sheets", safely(add_sheet), methods=["POST"]),
        Route(base + "/sheets/{sheet}", safely(change_sheet), methods=["PATCH"]),
        Route(base + "/sheets/{sheet}", safely(remove_sheet), methods=["DELETE"]),
        Route(base + "/sheets/{sheet}/blocks", safely(add_block), methods=["POST"]),
        Route(base + "/blocks/{block}", safely(change_block), methods=["PATCH"]),
        Route(base + "/blocks/{block}", safely(remove_block), methods=["DELETE"]),
        Route(f"{base}/play", safely(play), methods=["POST"]),
        Route(f"{base}/preview", safely(preview)),
        Route(f"{base}/download", safely(download)),
        Route(f"{base}/export", safely(export), methods=["POST"]),
        Route("/accounting/templates", safely(templates), methods=["POST"]),
        Route("/accounting/templates/import", with_body(accounting.import_template), methods=["POST"]),
        Route("/accounting/templates/show", safely(show_template), methods=["POST"]),
        Route("/accounting/templates/bind", safely(bind), methods=["POST"]),
        Route("/accounting/build", with_body(accounting.build), methods=["POST"]),
        Route("/accounting/register", with_body(accounting.register), methods=["POST"]),
        Route("/accounting/functions", safely(listed_functions)),
    ]
