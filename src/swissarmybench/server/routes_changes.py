"""The open project's change log (services/changes.py; Plans/changes.plan.md): names, types, fingerprints.

GET  /changes   ?action=last|history|since|search&object=table:orders&n=20&since=&kind=&who=&word=   changes
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import json_response
from swissarmybench.services.changes import ChangeLog


def routes(changes: ChangeLog) -> list[BaseRoute]:
    async def view(request: Request) -> Response:
        return json_response(changes.view(dict(request.query_params)))

    return [Route("/changes", view)]
