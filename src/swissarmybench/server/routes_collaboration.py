"""The Collaboration panel (services/collaboration.py): the team's notes, threads and activity in the open
project's folder.

GET   /collaboration  ?where=#general|<object key>&filter=all|mentions|page|unresolved|activity|notes
      &page=<the page's file or table>: the timeline  (collaboration_list)
GET   /collaboration/thread  ?id=: one thread, folded  (collaboration_thread)
POST  /collaboration/post  {channel? | anchor?, title?, body, images?}: a new thread  (collaboration_post)
POST  /collaboration/reply  {thread | activity, body, images?}  (collaboration_reply)
POST  /collaboration/edit  {thread, message, body}: your own message  (collaboration_edit)
POST  /collaboration/delete  {thread, message}: your own message (the user's only: 403 for the agent)
POST  /collaboration/react  {thread, message, emoji}: on, or off when it is there  (collaboration_react)
POST  /collaboration/resolve  {thread, resolved?}  (collaboration_resolve)
POST  /collaboration/pin  {thread, pinned?}  (collaboration_pin)
POST  /collaboration/channel  {name}: a channel  (collaboration_channel)
POST  /collaboration/show  {anchor? | where?}: every window opens the panel there  (collaboration_show)
POST  /collaboration/read  {thread}: read up to its last message (this computer's, the panel's)
GET   /collaboration/search  ?words=  (collaboration_search)
GET   /collaboration/activity  ?n=&who=  (collaboration_activity)
GET   /collaboration/unread  the counts  (collaboration_unread)
GET   /collaboration/objects  ?words=: the `@` picker (people, the project's objects)  (collaboration_objects)
GET   /collaboration/image  ?thread=&name=: a pasted picture's bytes (the panel's)
GET   /collaboration/profile  this computer's name and login  (collaboration_profile)
PUT   /collaboration/profile  {name}: Settings' name ("" goes back to the GitHub login or the system's)
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, with_body
from swissarmybench.services.collaboration import Collaboration


def routes(collaboration: Collaboration) -> list[BaseRoute]:
    async def timeline(request: Request) -> Response:
        return json_response(await collaboration.timeline(dict(request.query_params), actor(request)))

    async def thread(request: Request) -> Response:
        return json_response(collaboration.thread(request.query_params.get("id"), actor(request)))

    async def search(request: Request) -> Response:
        return json_response(collaboration.search(request.query_params.get("words"), actor(request)))

    async def activity(request: Request) -> Response:
        return json_response(collaboration.activity(dict(request.query_params)))

    async def unread(_: Request) -> Response:
        return json_response(collaboration.unread())

    async def objects(request: Request) -> Response:
        return json_response(collaboration.objects(request.query_params.get("words", "")))

    async def image(request: Request) -> Response:
        data, mime = collaboration.image(request.query_params.get("thread"), request.query_params.get("name"))
        return Response(data, media_type=mime, headers={"Cache-Control": "private, max-age=3600"})

    async def profile(_: Request) -> Response:
        return json_response(collaboration.profile())

    return [
        Route("/collaboration", timeline),
        Route("/collaboration/thread", thread),
        Route("/collaboration/post", with_body(collaboration.post), methods=["POST"]),
        Route("/collaboration/reply", with_body(collaboration.reply), methods=["POST"]),
        Route("/collaboration/edit", with_body(collaboration.edit), methods=["POST"]),
        Route("/collaboration/delete", with_body(collaboration.delete), methods=["POST"]),
        Route("/collaboration/react", with_body(collaboration.react), methods=["POST"]),
        Route("/collaboration/resolve", with_body(collaboration.resolve), methods=["POST"]),
        Route("/collaboration/pin", with_body(collaboration.pin), methods=["POST"]),
        Route("/collaboration/channel", with_body(collaboration.channel), methods=["POST"]),
        Route("/collaboration/show", with_body(collaboration.show), methods=["POST"]),
        Route("/collaboration/read", with_body(collaboration.mark_read), methods=["POST"]),
        Route("/collaboration/search", search),
        Route("/collaboration/activity", activity),
        Route("/collaboration/unread", unread),
        Route("/collaboration/objects", objects),
        Route("/collaboration/image", image),
        Route("/collaboration/profile", profile),
        Route("/collaboration/profile", with_body(collaboration.set_profile), methods=["PUT"]),
    ]
