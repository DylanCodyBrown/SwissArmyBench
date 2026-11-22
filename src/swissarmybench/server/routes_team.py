"""Settings' Team box (services/team.py): one GitHub repository for the team library and its shared projects.

GET   /team               no team or joined (owner/repo, its sync words), the step kept over a restart, the
                          folders (?remote=1: GitHub asked, at most once a minute)               team_status
GET   /team/repositories  ?search=: the repositories the account can push to, newest first    team_status
GET   /team/owners        the account and its organisations (Start a team's owner)             team_status
POST  /team/join          {"repository"} (the agent's on Allow)                                  team_join
POST  /team/start         {"name", "owner"?, "private"?} (the agent's on Allow)                 team_start
POST  /team/leave         {"keep"?}: {} asks first (the agent's on Allow)                        team_leave
POST  /team/pull          the team library pulled (the agent's on Allow)                       github_pull
POST  /team/push          the team library pushed (the agent's on Allow)                       github_push
POST  /team/pending       {"action", "step"?} or {"action": null}: kept over Install's restart (the page's)
POST  /team/show          Show its folder (the user's only: 403 for the agent)
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, with_actor, with_body
from swissarmybench.services.team import Team


def routes(team: Team) -> list[BaseRoute]:
    async def status(request: Request) -> Response:
        remote = request.query_params.get("remote") in ("1", "true")
        return json_response(await team.status(remote, actor(request)))

    async def repositories(request: Request) -> Response:
        return json_response(await team.repositories(request.query_params.get("search", ""), actor(request)))

    return [
        Route("/team", status),
        Route("/team/repositories", repositories),
        Route("/team/owners", with_actor(team.owners)),
        Route("/team/join", with_body(team.join), methods=["POST"]),
        Route("/team/start", with_body(team.start), methods=["POST"]),
        Route("/team/leave", with_body(team.leave), methods=["POST"]),
        Route("/team/pull", with_actor(team.pull), methods=["POST"]),
        Route("/team/push", with_actor(team.push), methods=["POST"]),
        Route("/team/pending", with_body(team.set_pending), methods=["POST"]),
        Route("/team/show", with_actor(team.show), methods=["POST"]),
    ]
