"""The agent's collaboration_* commands: the Collaboration panel's notes, threads and activity, kept in the open
project's folder (guide topic `collaboration` says the rest).

The agent posts as itself, marked as the user's ("Claude for <name>"); it edits its own messages and deletes
none (deleting is the user's own). Registered into cli/commands.py's REGISTRY when it imports this module (the
tool list's order is the areas', then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import command, opt, req

_BODY = "Markdown; an object as its link (collaboration_objects), a person as @login."
_THREAD = "The thread's id."
_ANCHOR = 'An object {"kind", "path", "id", "text"} (collaboration_objects).'


def _some(a: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {k: a[k] for k in keys if a.get(k) is not None}


@command(
    "collaboration_list",
    "The Collaboration panel's timeline (threads and activity), channels, objects with threads, unread, shared",
    opt("where", "#general, #<channel> or an object's key (cell:data.ipynb#7)."),
    opt("filter", "all, mentions, page, unresolved, activity or notes."),
    opt("page", "For filter page: the file or table in front."),
)
def collaboration_list(a: dict[str, Any]) -> Any:
    return api.call("GET", "/collaboration", params=_some(a, "where", "filter", "page"))


@command(
    "collaboration_thread",
    "One thread: its messages, reactions, references (where each opens, gone or not), resolved, pinned",
    req("thread", _THREAD),
)
def collaboration_thread(a: dict[str, Any]) -> Any:
    return api.call("GET", "/collaboration/thread", params={"id": a["thread"]})


@command(
    "collaboration_post",
    "Start a thread in a channel (default #general) or on an object; posted as Claude for the user",
    req("body", _BODY),
    opt("channel", "A channel."),
    opt("anchor", _ANCHOR, "json"),
    opt("title", "Default: the first line."),
)
def collaboration_post(a: dict[str, Any]) -> Any:
    return api.call("POST", "/collaboration/post", _some(a, "body", "channel", "anchor", "title"))


@command(
    "collaboration_reply",
    "Reply in a thread, or to an activity line (a change)",
    req("body", _BODY),
    opt("thread", _THREAD),
    opt("activity", "An activity line's id."),
)
def collaboration_reply(a: dict[str, Any]) -> Any:
    return api.call("POST", "/collaboration/reply", _some(a, "body", "thread", "activity"))


@command(
    "collaboration_edit",
    "Edit one of your own messages (the agent never deletes one)",
    req("thread", _THREAD),
    req("message", "The message's id."),
    req("body", _BODY),
)
def collaboration_edit(a: dict[str, Any]) -> Any:
    return api.call("POST", "/collaboration/edit", _some(a, "thread", "message", "body"))


@command(
    "collaboration_react",
    "A reaction on a message: on, or off when it is yours",
    req("thread", _THREAD),
    req("message", "The message's id."),
    req("emoji", "One emoji."),
)
def collaboration_react(a: dict[str, Any]) -> Any:
    return api.call("POST", "/collaboration/react", _some(a, "thread", "message", "emoji"))


@command(
    "collaboration_resolve",
    "Resolve a thread, or open it again",
    req("thread", _THREAD),
    opt("resolved", "false: open it again.", "bool"),
)
def collaboration_resolve(a: dict[str, Any]) -> Any:
    body = {"thread": a["thread"], "resolved": a.get("resolved") is not False}
    return api.call("POST", "/collaboration/resolve", body)


@command(
    "collaboration_pin",
    "Pin a thread, or unpin it",
    req("thread", _THREAD),
    opt("pinned", "false: unpin it.", "bool"),
)
def collaboration_pin(a: dict[str, Any]) -> Any:
    body = {"thread": a["thread"], "pinned": a.get("pinned") is not False}
    return api.call("POST", "/collaboration/pin", body)


@command("collaboration_channel", "Make a channel", req("name", "Its name."))
def collaboration_channel(a: dict[str, Any]) -> Any:
    return api.call("POST", "/collaboration/channel", {"name": a["name"]})


@command(
    "collaboration_show",
    "Open the Collaboration panel in the user's windows on an object or a channel",
    opt("anchor", _ANCHOR, "json"),
    opt("where", "#<channel> or an object's key."),
)
def collaboration_show(a: dict[str, Any]) -> Any:
    return api.call("POST", "/collaboration/show", _some(a, "anchor", "where"))


@command("collaboration_search", "Search the notes and the activity", req("words", "Words."))
def collaboration_search(a: dict[str, Any]) -> Any:
    return api.call("GET", "/collaboration/search", params={"words": a["words"]})


@command(
    "collaboration_activity",
    "The project's activity, newest first: each person's changes in words",
    opt("n", "How many (50).", "int"),
    opt("who", "A login."),
)
def collaboration_activity(a: dict[str, Any]) -> Any:
    return api.call("GET", "/collaboration/activity", params=_some(a, "n", "who"))


@command("collaboration_unread", "The user's unread counts: total, mentions, each channel's and object's")
def collaboration_unread(a: dict[str, Any]) -> Any:
    return api.call("GET", "/collaboration/unread")


@command(
    "collaboration_objects",
    "What @ points at: people and the project's objects, each with its link",
    opt("words", "Words to match."),
)
def collaboration_objects(a: dict[str, Any]) -> Any:
    return api.call("GET", "/collaboration/objects", params={"words": a.get("words") or ""})


@command(
    "collaboration_profile",
    "This computer's name in the panel; with name, set it",
    opt("name", '"" goes back to the default.'),
)
def collaboration_profile(a: dict[str, Any]) -> Any:
    if a.get("name") is None:
        return api.call("GET", "/collaboration/profile")
    return api.call("PUT", "/collaboration/profile", {"name": a["name"]})
