"""Updates: versions compared as PEP 440 says, the release lists read, the check against a stand-in PyPI on
127.0.0.1 (newer, same, older, unreachable, malformed), the switch off sending nothing, and Update to X
(the question before it, the agent's Allow, the helper handed the version)."""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

import pytest

from swissarmybench.adapters.updates import HttpFeed, UpdateSwitchFile, take_failure_note
from swissarmybench.domain import updates as rules
from swissarmybench.domain.updates import UpdateError, parse_version
from swissarmybench.services.agent import Approvals
from swissarmybench.services.updates import Updates
from swissarmybench.services.workspace import Conflict, Refused
from tests.conftest import AGENT, AUTH, make_client

# ===== versions =====


@pytest.mark.parametrize(
    ("lower", "higher"),
    [
        ("0.0.1", "0.0.2"),
        ("0.0.9", "0.0.10"),  # numbers, not text
        ("1.0", "1.0.1"),
        ("1.0.0a1", "1.0.0a2"),
        ("1.0.0a2", "1.0.0b1"),
        ("1.0.0b1", "1.0.0rc1"),
        ("1.0.0rc1", "1.0.0"),  # a final release after its candidates
        ("1.0.0.dev1", "1.0.0a1"),  # a dev release before the pre-releases
        ("1.0.0", "1.0.0.post1"),
        ("1.0.0.post1.dev1", "1.0.0.post1"),
        ("1.9", "1!0.1"),  # an epoch outranks everything
        ("1.7.0b1", "1.7.0"),
    ],
)
def test_versions_are_ordered_as_pep_440_orders_them(lower: str, higher: str) -> None:
    assert parse_version(lower) < parse_version(higher)
    assert parse_version(higher) > parse_version(lower)


def test_versions_that_differ_only_in_how_they_are_written_are_equal() -> None:
    assert parse_version("1.0") == parse_version("1.0.0")
    assert parse_version("v1.0.0") == parse_version("1.0.0")
    assert parse_version("1.0.0-rc.1") == parse_version("1.0.0rc1")
    assert parse_version("1.0.0+local.7") == parse_version("1.0.0")
    assert str(parse_version("1.0.0-RC.1")) == "1.0.0rc1"
    assert parse_version("1.7.0b1").is_prerelease and parse_version("1.0.dev3").is_prerelease
    assert not parse_version("1.0.post2").is_prerelease


@pytest.mark.parametrize("text", ["", "one", "1..0", "1.0-final", None, 12, "x" * 100])
def test_what_is_not_a_version_is_refused(text: object) -> None:
    with pytest.raises(UpdateError):
        parse_version(text)


def pypi(*versions: str, yanked: tuple[str, ...] = ()) -> dict[str, Any]:
    """PyPI's JSON in its real shape, cut down: each release's files."""
    return {
        "info": {"name": "swissarmybench", "version": versions[-1] if versions else "0.0.1"},
        "releases": {v: [{"filename": f"swissarmybench-{v}.whl", "yanked": v in yanked}] for v in versions},
    }


def offered(current: str, document: Any) -> str | None:
    found = rules.offered(parse_version(current), rules.releases_from(rules.PYPI_URL, document))
    return str(found.version) if found else None


def test_the_newest_release_is_offered_and_a_pre_release_only_to_someone_on_one() -> None:
    listed = pypi("0.0.1", "0.0.2", "0.0.3rc1")
    assert offered("0.0.1", listed) == "0.0.2"
    assert offered("0.0.2", listed) is None  # the same: nothing
    assert offered("0.0.9", listed) is None  # older than what runs: nothing
    assert offered("0.0.2rc1", listed) == "0.0.3rc1"  # on a pre-release: the newest, pre-release or not
    assert offered("0.0.3rc1", pypi("0.0.3rc1", "0.0.3")) == "0.0.3"


def test_a_yanked_release_or_one_with_no_files_is_never_offered() -> None:
    listed = pypi("0.0.1", "0.0.2", yanked=("0.0.2",))
    listed["releases"]["0.0.3"] = []
    listed["releases"]["not a version"] = [{"yanked": False}]
    assert offered("0.0.1", listed) is None


def test_githubs_latest_release_is_read_by_its_tag() -> None:
    document = {"tag_name": "v0.0.2", "prerelease": False, "draft": False, "html_url": "https://github.com/x"}
    releases = rules.releases_from(rules.GITHUB_URL, document)
    assert [(str(r.version), r.source) for r in releases] == [("0.0.2", "github")]
    assert rules.releases_from(rules.GITHUB_URL, {"tag_name": "v9", "draft": True}) == []
    with pytest.raises(UpdateError):
        rules.releases_from(rules.GITHUB_URL, {"tag_name": "latest"})


@pytest.mark.parametrize("document", [[], "text", {"info": {}}, {"info": {"version": "soon"}}])
def test_a_malformed_release_list_is_an_error(document: Any) -> None:
    with pytest.raises(UpdateError):
        rules.releases_from(rules.PYPI_URL, document)


def test_the_install_is_uv_tool_install_force_on_the_python_the_app_runs_on() -> None:
    assert rules.install_command("uv", "0.0.2", "pypi", "3.12") == [
        "uv",
        "tool",
        "install",
        "--force",
        "--refresh-package",
        "swissarmybench",
        "--python",
        "3.12",
        "swissarmybench[server]==0.0.2",
    ]
    # Only GitHub answered: its release's wheel.
    assert rules.install_command("uv", "0.0.2", "github", "3.12")[-1] == (
        "swissarmybench[server] @ https://github.com/DylanCodyBrown/SwissArmyBench/releases/download/"
        "v0.0.2/swissarmybench-0.0.2-py3-none-any.whl"
    )
    local = rules.install_command("uv", "0.0.2", "pypi", "3.12", find_links="/wheels")
    assert local[-3:] == ["--find-links", "/wheels", "swissarmybench[server]==0.0.2"]
    with pytest.raises(UpdateError):
        rules.install_command("uv", "0.0.2; rm -rf", "pypi", "3.12")


def test_the_plan_waits_installs_checks_and_starts_in_that_order() -> None:
    plan = rules.plan_update(
        version="0.0.2",
        current="0.0.1",
        source="pypi",
        uv="/home/u/.local/bin/uv",
        tool_python="/tools/swissarmybench/bin/python",
        python_version="3.12",
        wait_pids=[4321, 0],
        info_file="/state/server.json",
        note_file="/state/update_failed.json",
    )
    said = plan.to_json()
    assert said["steps"] == ["wait", "install", "check", "start"]
    assert said["wait_pids"] == [4321]  # no tray: nothing to wait for
    assert said["install"][-1] == "swissarmybench[server]==0.0.2"
    assert said["restore"][-1] == "swissarmybench[server]==0.0.1"  # the old version, should the new one fail
    assert said["start"] == ["/tools/swissarmybench/bin/python", "-m", "swissarmybench.server", "start"]
    with pytest.raises(UpdateError):
        rules.plan_update(**{**_plan_args(), "version": "0.0.1"})


def _plan_args() -> dict[str, Any]:
    return {
        "version": "0.0.2",
        "current": "0.0.1",
        "source": "pypi",
        "uv": "uv",
        "tool_python": "python",
        "python_version": "3.12",
        "wait_pids": [],
        "info_file": "i",
        "note_file": "n",
    }


def test_the_question_before_an_update_says_what_would_be_lost() -> None:
    text = rules.update_question("0.0.2", {"unsaved": ["sales.ipynb", "load.py"], "kernels": 1})
    assert "sales.ipynb, load.py" in text and "1 running kernel stops." in text
    assert "2 running kernels stop." in rules.update_question("0.0.2", {"unsaved": [], "kernels": 2})


# ===== the check, against a stand-in PyPI on 127.0.0.1 =====


class StandIn:
    """A made-up release list on 127.0.0.1: what it answers, and every request it was sent."""

    def __init__(self) -> None:
        self.answer: Any = pypi("0.0.1")
        self.status = 200
        self.requests: list[dict[str, Any]] = []
        stand_in = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                stand_in.requests.append({"path": self.path, "headers": dict(self.headers)})
                body = (
                    stand_in.answer
                    if isinstance(stand_in.answer, bytes)
                    else json.dumps(stand_in.answer).encode()
                )
                self.send_response(stand_in.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: Any) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/pypi/swissarmybench/json"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def stand_in() -> Iterator[StandIn]:
    found = StandIn()
    yield found
    found.close()


class Told:
    def __init__(self) -> None:
        self.notices: list[dict[str, Any]] = []

    async def broadcast(self, message: dict[str, Any]) -> None:
        self.notices.append(message)


class Audit:
    def __init__(self) -> None:
        self.lines: list[tuple[Any, ...]] = []

    def write(self, who: str, action: str, dataset: str | None, **details: Any) -> None:
        self.lines.append((who, action, details))


class Helper:
    def __init__(self) -> None:
        self.launched: list[tuple[str, str]] = []

    def launch(self, version: str, source: str) -> None:
        self.launched.append((version, source))


def service(
    feeds: tuple[str, ...],
    current: str = "0.0.1",
    switch: UpdateSwitchFile | None = None,
    work: dict[str, Any] | None = None,
    approvals: Any = None,
    changing: Any = None,
) -> tuple[Updates, Helper, Told, list[bool]]:
    helper, told, stopped = Helper(), Told(), []

    async def open_work() -> dict[str, Any]:
        return work or {"tables": [], "documents": [], "unsaved": [], "kernels": 0}

    updates = Updates(
        current=current,
        feeds=feeds,
        feed=HttpFeed(),
        switch=switch or UpdateSwitchFile(None),
        helper=helper,
        open_work=open_work,
        approvals=approvals or Approvals(cast(Any, told)),
        audit=cast(Any, Audit()),
        live=cast(Any, told),
        stop=lambda: stopped.append(True),
        changing=changing or (lambda: None),
    )
    return updates, helper, told, stopped


def test_a_newer_release_on_the_stand_in_is_available(stand_in: StandIn) -> None:
    stand_in.answer = pypi("0.0.1", "0.0.2")
    updates, _, told, _ = service((stand_in.url,))
    state = asyncio.run(updates.check())
    assert state["available"] is True and state["version"] == "0.0.2" and state["latest"] == "0.0.2"
    assert state["url"] == "https://github.com/DylanCodyBrown/SwissArmyBench/releases/tag/v0.0.2"
    assert told.notices[-1]["type"] == "update_changed" and told.notices[-1]["version"] == "0.0.2"


@pytest.mark.parametrize("listed", [("0.0.1",), ("0.0.1", "0.0.0")])
def test_the_same_or_an_older_release_is_not(stand_in: StandIn, listed: tuple[str, ...]) -> None:
    stand_in.answer = pypi(*listed)
    updates, _, told, _ = service((stand_in.url,))
    state = asyncio.run(updates.check())
    assert state["available"] is False and state["version"] is None and "error" not in state
    assert told.notices == []  # nothing to say


def test_an_unreachable_or_malformed_list_says_so_and_offers_nothing(stand_in: StandIn) -> None:
    stand_in.answer = b"<html>not json</html>"
    updates, _, _, _ = service((stand_in.url,))
    assert asyncio.run(updates.check())["error"] and not updates.state()["available"]
    stand_in.answer, stand_in.status = {"error": "busy"}, 503
    assert asyncio.run(updates.check())["error"]
    gone = service(("http://127.0.0.1:9/pypi/swissarmybench/json",))[0]
    state = asyncio.run(gone.check())
    assert state["error"] == "No release list could be reached." and state["available"] is False


def test_github_is_asked_when_pypi_cannot_be_read(stand_in: StandIn) -> None:
    github = StandIn()
    try:
        stand_in.status = 500
        github.answer = {"tag_name": "v0.0.2", "draft": False, "prerelease": False}
        updates, _, _, _ = service((stand_in.url, github.url))
        state = asyncio.run(updates.check())
        assert state["version"] == "0.0.2" and state["source"] == "github"
    finally:
        github.close()


def test_the_check_sends_nothing_but_its_request(stand_in: StandIn) -> None:
    stand_in.answer = pypi("0.0.2")
    asyncio.run(service((stand_in.url,))[0].check())
    [request] = stand_in.requests
    assert request["path"] == "/pypi/swissarmybench/json"  # no query: no identifiers
    sent = {k.lower() for k in request["headers"]}
    assert sent <= {"host", "accept", "accept-encoding", "user-agent", "connection"}
    assert request["headers"]["User-Agent"].startswith("Python-urllib/")


def test_with_the_switch_off_nothing_is_sent(stand_in: StandIn, tmp_path: Path) -> None:
    stand_in.answer = pypi("0.0.1", "0.0.2")
    switch = UpdateSwitchFile(tmp_path / "update.json")
    updates, _, told, _ = service((stand_in.url,), switch=switch)
    asyncio.run(updates.check())
    assert updates.state()["available"]
    asyncio.run(updates.set({"check": False}, "user"))
    assert updates.state()["available"] is False and told.notices[-1]["available"] is False
    stand_in.requests.clear()
    asyncio.run(updates.check())
    assert stand_in.requests == []
    # Kept across restarts: a new server reads the switch from its file and sends nothing either.
    assert json.loads((tmp_path / "update.json").read_text()) == {"check": False}
    again, _, _, _ = service((stand_in.url,), switch=UpdateSwitchFile(tmp_path / "update.json"))
    assert asyncio.run(again.check())["check"] is False and stand_in.requests == []
    with pytest.raises(ValueError, match="check"):
        asyncio.run(updates.set({"check": "yes"}, "user"))


def test_no_feeds_never_ask_anything() -> None:
    updates, _, _, _ = service(())
    asyncio.run(asyncio.wait_for(updates.run_forever(), 1))  # returns at once
    assert asyncio.run(updates.check())["checked"] is None


# ===== Update to X =====


def ready(stand_in: StandIn, **kwargs: Any) -> tuple[Updates, Helper, Told, list[bool]]:
    stand_in.answer = pypi("0.0.1", "0.0.2")
    made = service((stand_in.url,), **kwargs)
    asyncio.run(made[0].check())
    return made


def test_update_hands_the_version_to_the_helper_and_stops_the_app(stand_in: StandIn) -> None:
    updates, helper, told, stopped = ready(stand_in)

    async def go() -> dict[str, Any]:
        said = await updates.install({"version": "0.0.2", "confirmed": True}, "user")
        await asyncio.sleep(0.7)
        return said

    assert asyncio.run(go()) == {"updating": "0.0.2"}
    assert helper.launched == [("0.0.2", "pypi")] and stopped == [True]
    assert told.notices[-1] == {"type": "app_updating", "version": "0.0.2"}
    with pytest.raises(Conflict, match="already"):
        asyncio.run(updates.install({}, "user"))


def test_the_users_update_always_warns_of_the_restart_first(stand_in: StandIn) -> None:
    """The owner (2026-11-18): "warn that it will restart once updated": asked even with nothing at risk."""
    updates, helper, _, _ = ready(stand_in)
    asked = asyncio.run(updates.install({"version": "0.0.2"}, "user"))
    assert asked == {"confirm": {"unsaved": [], "kernels": 0}, "version": "0.0.2"}
    assert helper.launched == []


def test_update_asks_first_and_lists_what_would_be_lost(stand_in: StandIn) -> None:
    work = {"tables": [], "documents": [], "unsaved": ["sales.ipynb"], "kernels": 1}
    updates, helper, _, _ = ready(stand_in, work=work)
    asked = asyncio.run(updates.install({"version": "0.0.2"}, "user"))
    assert asked == {"confirm": {"unsaved": ["sales.ipynb"], "kernels": 1}, "version": "0.0.2"}
    assert helper.launched == []  # nothing yet, and nothing saved for the user

    async def confirmed() -> dict[str, Any]:
        return await updates.install({"version": "0.0.2", "confirmed": True}, "user")

    assert asyncio.run(confirmed()) == {"updating": "0.0.2"} and helper.launched == [("0.0.2", "pypi")]


def test_update_refuses_what_is_not_the_offered_version(stand_in: StandIn) -> None:
    updates, helper, _, _ = ready(stand_in)
    with pytest.raises(Conflict, match=r"0\.0\.2"):
        asyncio.run(updates.install({"version": "9.9.9"}, "user"))
    nothing, _, _, _ = service(())
    with pytest.raises(Conflict, match="No update"):
        asyncio.run(nothing.install({}, "user"))
    assert helper.launched == []


class Answer:
    def __init__(self, yes: bool) -> None:
        self.yes = yes
        self.asked: list[tuple[str, str, str]] = []

    async def ask(self, dataset: str, action: str, detail: str) -> bool:
        self.asked.append((dataset, action, detail))
        return self.yes


def test_the_agents_update_waits_for_the_users_allow(stand_in: StandIn) -> None:
    no = Answer(False)
    updates, helper, _, _ = ready(stand_in, approvals=no, work={"unsaved": ["a.ipynb"], "kernels": 0})
    with pytest.raises(Refused, match="declined"):
        asyncio.run(updates.install({}, "agent"))
    assert helper.launched == [] and no.asked[0][:2] == ("0.0.2", "update the app to")
    assert "a.ipynb" in no.asked[0][2]
    yes = Answer(True)
    updates, helper, _, _ = ready(stand_in, approvals=yes)

    async def go() -> dict[str, Any]:
        return await updates.install({}, "agent")

    assert asyncio.run(go()) == {"updating": "0.0.2"} and len(yes.asked) == 1  # asked even with nothing open


def test_a_failed_updates_note_is_read_once(tmp_path: Path) -> None:
    note = tmp_path / "update_failed.json"
    note.write_text(json.dumps({"version": "0.0.2", "reason": "uv could not reach PyPI."}))
    assert take_failure_note(note) == {"version": "0.0.2", "reason": "uv could not reach PyPI."}
    assert not note.exists() and take_failure_note(note) is None


# ===== the routes, for the pages and the agent =====


def test_the_routes_read_switch_and_refuse_without_an_update(tmp_path: Path) -> None:
    with make_client(tmp_path, update_feeds=()) as client:
        state = client.get("/updates", headers=AUTH).json()
        assert state["current"] and state["available"] is False and state["check"] is True
        assert client.put("/updates", json={"check": False}, headers=AUTH).json()["check"] is False
        assert client.post("/updates/check", headers=AUTH).json()["check"] is False
        refused = client.post("/updates/install", json={}, headers=AGENT)
        assert refused.status_code == 409 and "No update" in refused.text
        # The tray is gone (2026-11-18): its route and start at sign-in's with it.
        assert client.get("/updates/tray", headers=AUTH).status_code == 404
        assert client.get("/autostart", headers=AUTH).status_code == 404
        assert client.get("/updates").status_code == 401  # the token, as on every route


def test_the_app_is_named_swiss_army_bench(tmp_path: Path) -> None:
    """The status bar's name (the owner, 2026-11-17: "It's not an edition now it's the streamlit extension.
    Preinstalled"): the backend says it, and the installed extensions with it."""
    from swissarmybench.server.routes_updates import APP_NAME

    assert APP_NAME == "Swiss Army Bench"
    with make_client(tmp_path, update_feeds=()) as client:
        said = client.get("/updates", headers=AUTH).json()
        assert said["name"] == "Swiss Army Bench" and "Streamlit" in said["extensions"]
