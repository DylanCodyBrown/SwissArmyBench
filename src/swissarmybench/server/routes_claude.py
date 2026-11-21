"""Launch Claude (services/claude.py), for the pages and, reading only, the agent.

GET    /claude            what was found (Claude Code, Claude Desktop), the choices; ?refresh=1 looks again
                                                                                    app_claude
GET    /claude/context    context.md: the app's live picture (metadata only), its path    app_context (and
                          the MCP resource swissarmybench://context); the agent's read counts as seen
GET    /claude/context/prompt   the prompt hook's question: the sections changed since the agent's last
                          read, and the line it prints (plumbing)
PUT    /claude            Settings, Claude: which Claude, bypass permissions mode, a Desktop's config file
                          (the user's only: 403 for the agent)
POST   /claude/launch     the status bar's Launch Claude (the user's only: 403 for the agent)
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, read_json, safely
from swissarmybench.services.claude import Claude


def routes(claude: Claude) -> list[BaseRoute]:
    async def state(request: Request) -> Response:
        return json_response(await claude.state(refresh=request.query_params.get("refresh") == "1"))

    async def context(request: Request) -> Response:
        return json_response(await claude.summary(actor(request)))

    async def prompt(request: Request) -> Response:
        if claude.context_md is None:
            return json_response({"path": None, "first": False, "changed": [], "line": ""})
        try:
            return json_response(await claude.context_md.prompt())
        except Exception as error:
            return error_response(error)

    async def choose(request: Request) -> Response:
        return json_response(await claude.choose(await read_json(request), actor(request)))

    async def launch(request: Request) -> Response:
        body = await read_json(request) if await request.body() else {}
        return json_response(await claude.launch(body, actor(request)))

    return [
        Route("/claude", safely(state)),
        Route("/claude", safely(choose), methods=["PUT"]),
        Route("/claude/context", safely(context)),
        Route("/claude/context/prompt", prompt),
        Route("/claude/launch", safely(launch), methods=["POST"]),
    ]
