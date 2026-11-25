"""The Collaboration panel through the app (services/collaboration.py, server/routes_collaboration.py): a
thread posted with an `@cell` reference, its files on disk, a reply, reactions and resolves as their own small
files, the agent's limits (Claude for <name>, edits its own, deletes none), the activity heard from the change
log, a reply to a change, search, unread with mentions, pictures, a second author's files on disk noticed by
the look, the profile, and the panel opened by the agent. Made-up people and data only."""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pyarrow as pa
from starlette.testclient import TestClient

from swissarmybench.adapters.atomic_files import JsonFile
from swissarmybench.adapters.collaboration import CollaborationFiles
from swissarmybench.domain import collaboration as rules
from swissarmybench.domain import sab_files
from swissarmybench.services.collaboration import Collaboration
from tests.conftest import AGENT, AUTH, push


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def _notebook(path: Path, numbers: list[int]) -> None:
    cells = [
        {
            "cell_type": "code",
            "metadata": {"swissarmybench": {"number": n}},
            "source": [f"total_{n} = {n}\n"],
            "outputs": [],
            "execution_count": None,
        }
        for n in numbers
    ]
    path.write_text(
        json.dumps({"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}), encoding="utf-8"
    )


def _project(client: TestClient, tmp_path: Path) -> Path:
    project = tmp_path / "shop"
    ok(client.post("/project/new", json={"path": str(project)}, headers=AUTH))
    ok(client.put("/collaboration/profile", json={"name": "Avery Lin"}, headers=AUTH))
    return project


def test_no_project_says_so(client: TestClient) -> None:
    timeline = ok(client.get("/collaboration", headers=AUTH))
    assert timeline["project"] is None and timeline["items"] == []
    refused = client.post("/collaboration/post", json={"body": "Hello"}, headers=AUTH)
    assert refused.status_code == 409 and "Open a project first" in refused.json()["error"]


def test_a_thread_with_a_cell_reference_its_reply_reactions_and_resolve(
    client: TestClient, tmp_path: Path
) -> None:
    project = _project(client, tmp_path)
    _notebook(project / "data.ipynb", [3, 7])
    body = "Look at [@data.ipynb cell 7](sab:cell/data.ipynb#7): **returns** are double counted."
    thread = ok(client.post("/collaboration/post", json={"body": body}, headers=AUTH))
    ident = thread["id"]
    assert thread["where"] == "#general" and thread["title"].startswith("Look at data.ipynb cell 7")
    ref = thread["messages"][0]["references"][0]
    assert ref["kind"] == "cell" and ref["id"] == "7" and not ref["gone"]
    assert ref["href"].startswith("notebooks?path=") and ref["href"].endswith("&cell=7")
    folder = project / ".sab" / "collaboration" / ident
    assert (folder / "thread.toml").is_file()
    first = [p.name for p in folder.glob("*.md")]
    assert len(first) == 1 and first[0].endswith(".md") and "-avery-lin-" in first[0]
    # The reply is a file of its own; the first message's bytes are untouched.
    before = (folder / first[0]).read_bytes()
    ok(client.post("/collaboration/reply", json={"thread": ident, "body": "Fixed in cell 7."}, headers=AUTH))
    assert len(list(folder.glob("*.md"))) == 2 and (folder / first[0]).read_bytes() == before
    message = thread["messages"][0]["id"]
    # A reaction on, then off: two small event files, folded to nothing.
    on = ok(
        client.post(
            "/collaboration/react", json={"thread": ident, "message": message, "emoji": "👍"}, headers=AUTH
        )
    )
    assert on["messages"][0]["reactions"] == [{"emoji": "👍", "people": ["avery-lin"], "mine": True}]
    off = ok(
        client.post(
            "/collaboration/react", json={"thread": ident, "message": message, "emoji": "👍"}, headers=AUTH
        )
    )
    assert off["messages"][0]["reactions"] == []
    assert len(list((folder / "_events").glob("*.toml"))) == 2
    resolved = ok(client.post("/collaboration/resolve", json={"thread": ident}, headers=AUTH))
    assert resolved["resolved"]["by"] == "avery-lin"
    assert (
        ok(client.post("/collaboration/resolve", json={"thread": ident, "resolved": False}, headers=AUTH))[
            "resolved"
        ]
        is None
    )
    assert ok(client.post("/collaboration/pin", json={"thread": ident}, headers=AUTH))["pinned"] is True
    # The cell goes: the reference shows as gone, said in words by the page.
    _notebook(project / "data.ipynb", [3])
    gone = ok(client.get("/collaboration/thread", params={"id": ident}, headers=AUTH))
    assert gone["messages"][0]["references"][0]["gone"] is True
    # The folder is shared in Git: neither .gitignore leaves it out.
    assert "collaboration" not in sab_files.GITIGNORE and "collaboration" not in sab_files.APP_GITIGNORE


def test_the_agent_posts_as_itself_edits_its_own_and_deletes_none(client: TestClient, tmp_path: Path) -> None:
    _project(client, tmp_path)
    mine = ok(client.post("/collaboration/post", json={"body": "A note of mine"}, headers=AUTH))
    ident, message = mine["id"], mine["messages"][0]["id"]
    said = ok(
        client.post("/collaboration/reply", json={"thread": ident, "body": "Checked it."}, headers=AGENT)
    )
    agents = said["messages"][1]
    assert agents["author"] == {
        "name": "Claude for Avery Lin",
        "login": "claude-for-avery-lin",
        "agent": True,
    }
    edit = {"thread": ident, "message": message, "body": "Changed by the agent"}
    assert client.post("/collaboration/edit", json=edit, headers=AGENT).status_code == 403
    own = {"thread": ident, "message": agents["id"], "body": "Checked it twice."}
    edited = ok(client.post("/collaboration/edit", json=own, headers=AGENT))["messages"][1]
    assert edited["body"] == "Checked it twice." and edited["edited"]
    # Deleting is the user's own, even of the agent's own message.
    gone = {"thread": ident, "message": agents["id"]}
    assert client.post("/collaboration/delete", json=gone, headers=AGENT).status_code == 403
    assert client.post("/collaboration/delete", json=gone, headers=AUTH).status_code == 403  # not hers
    deleted = ok(
        client.post("/collaboration/delete", json={"thread": ident, "message": message}, headers=AUTH)
    )
    assert deleted["messages"][0]["deleted"] is True and deleted["messages"][0]["body"] == ""


def test_the_activity_a_reply_to_a_change_and_search(client: TestClient, tmp_path: Path) -> None:
    project = _project(client, tmp_path)
    push(client, "orders", pa.table({"id": [1, 2], "region": ["North", "South"]}))
    activity = ok(client.get("/collaboration/activity", headers=AGENT))["activity"]
    assert activity and activity[0]["author"]["login"] == "avery-lin"
    files = list((project / ".sab" / "collaboration" / "_activity").glob("*.jsonl"))
    assert [f.name for f in files] == ["avery-lin.jsonl"]
    assert "North" not in files[0].read_text(encoding="utf-8")  # names and words, never a value
    line = activity[0]
    thread = ok(
        client.post("/collaboration/reply", json={"activity": line["id"], "body": "Why this?"}, headers=AUTH)
    )
    assert thread["anchor"]["kind"] == "change"
    again = ok(
        client.post(
            "/collaboration/reply", json={"activity": line["id"], "body": "Asked again"}, headers=AUTH
        )
    )
    assert again["id"] == thread["id"] and len(again["messages"]) == 2  # one thread a change
    found = ok(client.get("/collaboration/search", params={"words": "why"}, headers=AGENT))["found"]
    assert any(f.get("thread") == thread["id"] for f in found)
    timeline = ok(client.get("/collaboration", params={"filter": "activity"}, headers=AUTH))
    assert all(i["type"] == "activity" for i in timeline["items"])
    shown = next(i for i in timeline["items"] if i["id"] == line["id"])
    assert shown["threads"] == [thread["id"]] and shown["replies"] == 2


def test_objects_pictures_channels_and_the_panel_shown(client: TestClient, tmp_path: Path) -> None:
    project = _project(client, tmp_path)
    _notebook(project / "data.ipynb", [1])
    (project / "load.py").write_text("def clean(rows):\n    return rows\n", encoding="utf-8")
    push(client, "orders", pa.table({"amount": [1.5]}))
    objects = ok(client.get("/collaboration/objects", params={"words": "clean"}, headers=AGENT))["objects"]
    assert objects == [
        {
            "kind": "function",
            "path": "load.py",
            "id": "clean",
            "text": "load.py clean()",
            "link": "[@load.py clean()](sab:function/load.py#clean)",
        }
    ]
    columns = ok(client.get("/collaboration/objects", params={"words": "amount"}, headers=AUTH))["objects"]
    assert (
        columns[0]["kind"] == "column" and columns[0]["link"] == "[@orders.amount](sab:column/orders#amount)"
    )
    picture = base64.b64encode(b"\x89PNG\r\n\x1a\nmade-up").decode()
    sent = {"body": "The chart ![chart](sab-image:new-1)", "images": [{"type": "image/png", "data": picture}]}
    thread = ok(client.post("/collaboration/post", json=sent, headers=AUTH))
    name = thread["messages"][0]["body"].split("sab-image:")[1].rstrip(")")
    image = client.get("/collaboration/image", params={"thread": thread["id"], "name": name}, headers=AUTH)
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    big = base64.b64encode(b"0" * (rules.MAX_IMAGE_BYTES + 1)).decode()
    refused = {"body": "Big ![x](sab-image:new-1)", "images": [{"type": "image/png", "data": big}]}
    assert client.post("/collaboration/post", json=refused, headers=AUTH).status_code == 400
    made = ok(client.post("/collaboration/channel", json={"name": "Month end"}, headers=AGENT))
    assert made["key"] == "#month-end"
    channels = [c["name"] for c in ok(client.get("/collaboration", headers=AUTH))["channels"]]
    assert channels == ["general", "month-end"]
    anchor = {"kind": "table", "path": "orders", "text": "orders"}
    assert (
        ok(client.post("/collaboration/show", json={"anchor": anchor}, headers=AGENT))["where"]
        == "table:orders"
    )


class _Live:
    def __init__(self) -> None:
        self.said: list[dict[str, Any]] = []

    async def broadcast(self, notice: dict[str, Any]) -> None:
        self.said.append(notice)


def _service(project: Path, state: Path, login: str, live: _Live) -> Collaboration:
    ws: Any = SimpleNamespace(live=live, audit=SimpleNamespace(write=lambda *a, **k: None))
    objects: Any = SimpleNamespace(present=lambda folder, ref: (True, None), candidates=lambda folder: [])
    profile = JsonFile(state / f"profile-{login}.json")
    profile.write({"name": login.replace("-", " ").title()})
    return Collaboration(
        ws,
        CollaborationFiles(),
        objects,
        lambda: str(project),
        profile,
        JsonFile(state / f"read-{login}.json"),
        system_name=login,
    )


def test_a_second_author_on_disk_is_noticed_with_unread_and_mentions(tmp_path: Path) -> None:
    """Two people's computers over one project folder (as a Pull brings it): the look every few seconds
    says the thread changed, and the unread count and the mention follow."""
    project, state = tmp_path / "shop", tmp_path / "state"
    project.mkdir()
    state.mkdir()
    avery_live, sam_live = _Live(), _Live()
    avery = _service(project, state, "avery-lin", avery_live)
    sam = _service(project, state, "sam-ortiz", sam_live)

    async def run() -> None:
        await avery.look()  # the first look: nothing to say
        thread = await sam.post({"body": "First"}, "user")
        await avery.post({"body": "Second note"}, "user")  # Avery is now someone Sam can mention
        await avery.look()
        avery_live.said.clear()
        await sam.reply({"thread": thread["id"], "body": "@avery-lin please check"}, "user")
        changed = await avery.look()
        assert changed == [thread["id"]]
        notice = next(n for n in avery_live.said if n["type"] == "collaboration_changed")
        assert notice["threads"] == [thread["id"]]
        unread = avery.unread()
        assert unread["total"] == 2 and unread["mentions"] == 1
        await avery.mark_read({"thread": thread["id"]}, "user")
        assert avery.unread()["total"] == 0
        assert await avery.look() == []  # nothing new since
        # A window whose first look comes after the files arrived (a project just opened) still says them.
        late = _service(project, state, "avery-lin", _Live())
        assert thread["id"] in await late.look()

    asyncio.run(run())
    # Each message its own file: two authors never touch the same one.
    names = sorted(p.name for p in project.glob(".sab/collaboration/t-*/*.md"))
    assert len(names) == 3 and len(set(names)) == 3
