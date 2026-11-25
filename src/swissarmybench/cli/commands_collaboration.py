"""The agent's collaboration_* commands: the Collaboration panel's notes and threads, kept in the open project's
folder (guide topic `collaboration` says the rest).

The agent writes with ONE command, collaboration_post (a new thread, or a reply with `thread`), always marked as
its own ("Claude for <name>"); every other write (edit, delete, react, resolve, pin, a channel, showing the
panel, the name) is the user's alone (the owner, 2026-11-25: "the agent can post but only with a specific
tool"). The rest reads. Registered into cli/commands.py's REGISTRY when it imports this module. Standard
library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import command, opt, req

_BODY = "Markdown; an object as its link (collaboration_objects), a person as @login."
_PAGE = "The page in front: a file or table, or a JSON list of them."


def _some(a: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {k: a[k] for k in keys if a.get(k) is not None}


@command(
    "collaboration_list",
    "The Collaboration panel's threads, channels, objects with threads, unread, shared",
    opt("where", "#general, #<channel> or an object's key (cell:data.ipynb#7)."),
    opt("filter", "all, mentions, page or unresolved."),
    opt("page", _PAGE),
)
def collaboration_list(a: dict[str, Any]) -> Any:
    return api.call("GET", "/collaboration", params=_some(a, "where", "filter", "page"))


@command(
    "collaboration_thread",
    "One thread: its messages, reactions, references (where each opens, gone or not), resolved, pinned",
    req("thread", "The thread's id."),
)
def collaboration_thread(a: dict[str, Any]) -> Any:
    return api.call("GET", "/collaboration/thread", params={"id": a["thread"]})


@command(
    "collaboration_post",
    "Post as Claude for the user: a new thread (a channel or an object), or a reply with thread. "
    "The agent's only way to write here",
    req("body", _BODY),
    opt("thread", "Reply in this thread."),
    opt("channel", "A channel (default general)."),
    opt("anchor", 'An object {"kind", "path", "id", "text"} (collaboration_objects).', "json"),
    opt("title", "Default: the first line."),
)
def collaboration_post(a: dict[str, Any]) -> Any:
    return api.call("POST", "/collaboration/post", _some(a, "body", "thread", "channel", "anchor", "title"))


@command("collaboration_search", "Search the notes", req("words", "Words."))
def collaboration_search(a: dict[str, Any]) -> Any:
    return api.call("GET", "/collaboration/search", params={"words": a["words"]})


@command("collaboration_unread", "The user's unread counts and what is new since they last read")
def collaboration_unread(a: dict[str, Any]) -> Any:
    return api.call("GET", "/collaboration/unread") | {"news": api.call("GET", "/collaboration/news")}


@command(
    "collaboration_objects",
    "What @ points at: the page's objects first, then people, then the project's, each with its link",
    opt("words", "Words to match."),
    opt("page", _PAGE),
)
def collaboration_objects(a: dict[str, Any]) -> Any:
    return api.call(
        "GET", "/collaboration/objects", params={"words": a.get("words") or ""} | _some(a, "page")
    )


@command("collaboration_profile", "This computer's name in the panel (set in Settings, by the user)")
def collaboration_profile(a: dict[str, Any]) -> Any:
    return api.call("GET", "/collaboration/profile")
