"""The Git extension's HTTP door (services/sync.py and services/scm.py). Every route serves the agent too but the
sign-in's (the user's own): each one's command is named in the table (swissarmybench_git/commands.py).

GET   /git                       signed in (the login, never the token), each folder's link and status, the
                                 footer's mark (?remote=1: GitHub asked, at most once a minute)        github_status
POST  /git/sign-in/token         {"token"}: Use a token (the user's only: 403 for the agent)
POST  /git/sign-in/device        Sign in with GitHub: the device flow's code (the user's only)
POST  /git/sign-in/device/poll   has the code been typed? (the user's only)
POST  /git/sign-out              (the user's only)
GET   /git/repositories          the signed-in user's repositories                               github_repositories
POST  /git/clone                 {"which", "repository", "branch"?, "folder"?}  (on Allow)          github_clone
POST  /git/connect               {"which", "repository", "branch"?}  (on Allow)                   github_connect
POST  /git/disconnect            {"which"}                                                      github_disconnect
POST  /git/pull                  {"which", "path"?}  (on Allow)                                      github_pull
POST  /git/push                  {"which", "message"?, "path"?, "paths"?}  (on Allow)                github_push
POST  /git/sync                  {"which"}: Pull then Push (on Allow)                                 scm_sync
GET   /git/changes               ?which=: the Source Control page's repositories and groups          scm_changes
POST  /git/stage                 {"which", "paths", "unstage"?}                                       scm_stage
POST  /git/discard               {"which", "paths"}  (on Allow)                                     scm_discard
POST  /git/commit                {"which", "message", "paths"?, "sync"?}  (on Allow)                 scm_commit
GET   /git/history               ?which=&page=: the branch's commits and refs                        scm_history
GET   /git/commit-files          ?which=&commit=: one commit's files                            scm_commit_files
GET   /git/diff                  ?which=&path=&commit=&conflict=&unified=: the two sides (or text)      scm_diff
GET   /git/branches              ?which=                                                           scm_branches
POST  /git/checkout              {"which", "branch", "create"?}  (on Allow)                        scm_checkout
GET   /git/mark                  the footer's mark (none when up to date, not connected, no project open)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, safely, with_actor, with_body
from swissarmybench_git.services.scm import SourceControl

Handler = Callable[[Request], Awaitable[Response]]


def with_query(run: Callable[[Any, str], Awaitable[dict[str, Any]]]) -> Handler:
    """A route that runs `run(its query, who is asking)`: conflict and unified read as switches."""

    async def handle(request: Request) -> Response:
        query: dict[str, Any] = dict(request.query_params)
        for key in ("conflict", "unified"):
            query[key] = query.get(key) in ("1", "true")
        try:
            return json_response(await run(query, actor(request)))
        except Exception as error:
            return error_response(error)

    return handle


def routes(sync: SourceControl) -> list[BaseRoute]:
    async def status(request: Request) -> Response:
        remote = request.query_params.get("remote") in ("1", "true")
        try:
            return json_response(await sync.status(remote, actor(request)))
        except Exception as error:
            return error_response(error)

    async def mark(request: Request) -> Response:
        return json_response({"mark": (await sync.status(False, actor(request)))["footer"]})

    return [
        Route("/git", status),
        Route("/git/mark", safely(mark)),
        Route("/git/sign-in/token", with_body(sync.sign_in_token), methods=["POST"]),
        Route("/git/sign-in/device", with_actor(sync.device_start), methods=["POST"]),
        Route("/git/sign-in/device/poll", with_actor(sync.device_poll), methods=["POST"]),
        Route("/git/sign-out", with_actor(sync.sign_out), methods=["POST"]),
        Route("/git/repositories", with_actor(sync.repositories)),
        Route("/git/clone", with_body(sync.clone), methods=["POST"]),
        Route("/git/connect", with_body(sync.connect), methods=["POST"]),
        Route("/git/disconnect", with_body(sync.disconnect), methods=["POST"]),
        Route("/git/pull", with_body(sync.pull), methods=["POST"]),
        Route("/git/push", with_body(sync.push), methods=["POST"]),
        Route("/git/sync", with_body(sync.sync), methods=["POST"]),
        Route("/git/changes", with_query(sync.changes)),
        Route("/git/stage", with_body(sync.stage), methods=["POST"]),
        Route("/git/discard", with_body(sync.discard), methods=["POST"]),
        Route("/git/commit", with_body(sync.commit), methods=["POST"]),
        Route("/git/history", with_query(sync.history)),
        Route("/git/commit-files", with_query(sync.commit_files)),
        Route("/git/diff", with_query(sync.diff)),
        Route("/git/branches", with_query(sync.branches)),
        Route("/git/checkout", with_body(sync.checkout), methods=["POST"]),
    ]
