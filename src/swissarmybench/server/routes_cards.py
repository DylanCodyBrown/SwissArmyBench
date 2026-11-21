"""Side-panel cards: charts, notes and small result tables (plan section 11).

  GET    /cards                            every card of every open grid: the one Visualizations
  POST   /cards                            a card of no table: note, diagram, graphviz, plotly, echarts,
                                            image, or a table of its own {"columns", "rows"}; "key"
                                            replaces the card sent with that key before
  GET    /grids/{id}/cards                 every card for the grid, charts computed on its view
  POST   /grids/{id}/cards                 {"kind": "chart"|"note"|"table"|"diagram", "title",
                                            "spec"|"body"|"sql"}
  PATCH  /cards/{card}                     change title, spec, body, sql or pinned
  DELETE /cards/{card}                     remove a card
  POST   /cards/{card}/select              {"value": ...} cross-filter: add a filter step for it
  GET    /cards/{card}/code                Altair code for a chart card

  GET    /dashboards                       the saved dashboards: name, versions, last saved, cards
  POST   /dashboards                       {"name"}: save Visualizations as a new version of `name`
  GET    /dashboards/{name}                its versions: when, and each card's kind and title
  POST   /dashboards/{name}/open           {"version"?}: make that version what Visualizations shows
  DELETE /dashboards/{name}                delete it and its versions

  GET    /analyze/themes                   the themes the Analyze board can take, and its current one
  PUT    /analyze/theme                    {"theme": id or "app"}: the board's theme (not the grid's)
  POST   /analyze/themes                   a theme file {"name", "dark", "tokens"}: the user's is kept on
                                           disk; the agent's is proposed (in memory) until the user keeps it
  DELETE /analyze/themes/{id}            remove one of the user's themes
Saving writes to disk and opening replaces what the user is looking at: those three are the user's
click, so they refuse the agent, which may list and read them.

A card records its source (dataset, version, steps) and redraws whenever its grid's view
changes, because charts are computed on request from the grid's current steps. Agent-made
cards are tagged so the page can mark them.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.domain.charts import ChartError
from swissarmybench.server.http import actor, error_as, error_response, json_response, read_json, safely
from swissarmybench.services.charts import Cards


def routes(cards: Cards) -> list[BaseRoute]:
    ws = cards.ws

    async def list_cards(request: Request) -> Response:
        grid, _ = ws.grid_and_info(request.path_params["grid_id"])
        return json_response(await cards.for_grid(grid))

    async def all_cards(request: Request) -> Response:
        """Visualizations: one list for every table."""
        return json_response(await cards.everything())

    async def add_card(request: Request) -> Response:
        try:
            grid, info = ws.grid_and_info(request.path_params["grid_id"])
            return json_response(await cards.add(grid, info, await read_json(request), actor(request)))
        except ChartError as error:
            return error_as(error, 400)
        except Exception as error:
            return error_response(error)

    async def add_free(request: Request) -> Response:
        return json_response(await cards.add_free(await read_json(request), actor(request)))

    async def update_card(request: Request) -> Response:
        try:
            card = cards.get(request.path_params["card_id"])
            return json_response(await cards.update(card, await read_json(request), actor(request)))
        except ChartError as error:
            return error_as(error, 400)
        except Exception as error:
            return error_response(error)

    async def delete_card(request: Request) -> Response:
        removed = await cards.remove(request.path_params["card_id"], actor(request))
        if removed is None:
            return Response("No such card.", status_code=404)
        return json_response(removed)

    async def select(request: Request) -> Response:
        """Cross-filtering: a click on a chart adds a filter step for what was clicked."""
        card, grid, info = cards.chart(request.path_params["card_id"])
        return json_response(await cards.select(card, grid, info, await read_json(request), actor(request)))

    async def code(request: Request) -> Response:
        card, grid, info = cards.chart(request.path_params["card_id"])
        return json_response(await cards.code(card, grid, info))

    def users_only(request: Request) -> None:
        """The golden rule (2026-11-14): the agent saves, opens and deletes dashboards as the user does."""

    async def saved(request: Request) -> Response:
        return json_response(cards.saved())

    async def save(request: Request) -> Response:
        users_only(request)
        body = await read_json(request)
        return json_response(
            await cards.save(body.get("name") if isinstance(body, dict) else None, actor(request))
        )

    async def versions(request: Request) -> Response:
        return json_response(cards.versions(request.path_params["name"]))

    async def open_saved(request: Request) -> Response:
        users_only(request)
        body = await read_json(request)
        version = body.get("version") if isinstance(body, dict) else None
        return json_response(await cards.open(request.path_params["name"], version, actor(request)))

    async def delete_saved(request: Request) -> Response:
        users_only(request)
        return json_response(cards.delete_saved(request.path_params["name"], actor(request)))

    async def list_themes(request: Request) -> Response:
        return json_response(cards.themes())

    async def set_theme(request: Request) -> Response:
        body = await read_json(request)
        theme = body.get("theme") if isinstance(body, dict) else None
        return json_response(await cards.set_theme(theme, actor(request)))

    async def add_theme(request: Request) -> Response:
        return json_response(await cards.add_theme(await read_json(request), actor(request)))

    async def remove_theme(request: Request) -> Response:
        return json_response(await cards.remove_theme(request.path_params["theme_id"], actor(request)))

    return [
        Route("/analyze/themes", list_themes),
        Route("/analyze/theme", safely(set_theme), methods=["PUT"]),
        Route("/analyze/themes", safely(add_theme), methods=["POST"]),
        Route("/analyze/themes/{theme_id}", safely(remove_theme), methods=["DELETE"]),
        # The old addresses, one release (Visualizations is the Analyze page, 2026-11-19).
        Route("/dashboards", safely(saved)),
        Route("/dashboards", safely(save), methods=["POST"]),
        Route("/dashboards/{name}", safely(versions)),
        Route("/dashboards/{name}/open", safely(open_saved), methods=["POST"]),
        Route("/dashboards/{name}", safely(delete_saved), methods=["DELETE"]),
        Route("/cards", safely(all_cards)),
        Route("/cards", safely(add_free), methods=["POST"]),
        Route("/grids/{grid_id}/cards", safely(list_cards)),
        Route("/grids/{grid_id}/cards", add_card, methods=["POST"]),
        Route("/cards/{card_id}", update_card, methods=["PATCH"]),
        Route("/cards/{card_id}", delete_card, methods=["DELETE"]),
        Route("/cards/{card_id}/select", safely(select), methods=["POST"]),
        Route("/cards/{card_id}/code", safely(code)),
    ]
