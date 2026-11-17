"""Extensions (the owner, 2026-11-17): the catalog's statuses, discovery by entry points, the install plan
(the exact uv command, the wheel on this version's GitHub release, the installed extensions kept on an
update), a development checkout refusing, and the agent's Install and Remove waiting for the user's Allow.
The extensions "ledger" and "maps" are made up."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from swissarmybench import __version__
from swissarmybench.adapters.extensions import discover
from swissarmybench.domain import extensions as rules
from swissarmybench.domain.extensions import Extension, Found
from swissarmybench.server.updater import Helper
from swissarmybench.services.extensions import Extensions
from swissarmybench.services.workspace import Conflict, NotFound, Refused
from tests.conftest import AGENT, AUTH, make_client

PY = f"{sys.version_info.major}.{sys.version_info.minor}"
LEDGER = Extension("ledger", "Ledger", "A made-up ledger.", ("Ledger pages",), "available", "sab-ledger")
CATALOG = (*rules.CATALOG, LEDGER)


# ===== the catalog and discovery =====


def test_the_base_catalog_has_streamlit_preinstalled_and_two_available() -> None:
    listed = {e["id"]: e for e in rules.listed(rules.CATALOG, {}, "1.2.3")}
    assert list(listed) == ["streamlit", "accounting", "powerapps"]
    assert listed["streamlit"]["status"] == "preinstalled" and listed["streamlit"]["version"] == "1.2.3"
    assert listed["accounting"]["status"] == listed["powerapps"]["status"] == "available"
    assert listed["powerapps"]["version"] == "1.2.3" and listed["accounting"]["description"]
    assert all(e["status"] in rules.STATUSES for e in listed.values())


def test_a_found_extension_is_installed_and_a_preinstalled_one_stays_preinstalled() -> None:
    found = {
        "ledger": Found("ledger", "1.2.3"),
        "streamlit": Found("streamlit"),
        "maps": Found("maps", "0.1"),
    }
    listed = {e["id"]: e for e in rules.listed(CATALOG, found, "1.2.3")}
    assert listed["ledger"]["status"] == "installed" and listed["streamlit"]["status"] == "preinstalled"
    # One the catalog does not list is shown all the same (its package said where it came from).
    assert listed["maps"]["status"] == "installed" and listed["maps"]["version"] == "0.1"
    assert rules.listed(CATALOG, {}, "1.2.3")[-1]["status"] == "available"


class Point:
    """A made-up entry point (importlib.metadata.EntryPoint's shape)."""

    def __init__(self, name: str, value: Any, dist: str = "sab-ledger", version: str = "9.9.9") -> None:
        self.name, self._value = name, value
        self.dist = type("Dist", (), {"name": dist, "version": version})()

    def load(self) -> Any:
        if isinstance(self._value, Exception):
            raise self._value
        return self._value


def test_installed_extensions_are_found_by_their_entry_points() -> None:
    points = [
        Point("ledger", lambda: {"id": "ledger", "name": "Ledger", "adds": ["Ledger pages"]}),
        Point("maps", {"name": "Maps"}, "sab-maps", "0.2"),
        Point("broken", ImportError("no such module")),  # left out: the app starts anyway
        Point("bad id!", {}),
    ]
    found = discover({}, lambda: points)
    assert set(found) == {"ledger", "maps"}
    assert found["ledger"] == Found("ledger", "9.9.9", "Ledger", "", ("Ledger pages",), "sab-ledger")
    assert found["maps"].version == "0.2" and found["maps"].package == "sab-maps"
    # The environment variable (tests and development only) treats more as installed.
    more = discover({rules.ENV: "ledger, extra,, BAD ID"}, lambda: [])
    assert set(more) == {"ledger", "extra"}
    assert discover({}, lambda: (_ for _ in ()).throw(RuntimeError("metadata"))) == {}


# ===== the install plan =====


def test_the_wheel_comes_from_the_github_release_of_this_version() -> None:
    assert rules.wheel_url("swissarmybench-streamlit", "0.0.14") == (
        "https://github.com/DylanCodyBrown/SwissArmyBench/releases/download/v0.0.14/"
        "swissarmybench_streamlit-0.0.14-py3-none-any.whl"
    )


def test_install_is_this_version_with_each_kept_extensions_wheel() -> None:
    wheels = rules.kept_wheels(CATALOG, ["ledger", "streamlit"], "1.2.3")
    plan = rules.plan_change(
        current="1.2.3",
        uv="/bin/uv",
        tool_python="/tool/python",
        python_version="3.12",
        wheels=wheels[:1],
        before=[],
        wait_pids=[7, 0],
        info_file="info.json",
        note_file="note.json",
    )
    ledger = "https://github.com/DylanCodyBrown/SwissArmyBench/releases/download/v1.2.3/sab_ledger-1.2.3-py3-none-any.whl"
    assert plan.install == (
        "/bin/uv", "tool", "install", "--force", "--python", "3.12", "swissarmybench[server]==1.2.3",
        "--with", ledger,
    )  # fmt: skip
    assert plan.restore == (
        "/bin/uv",
        "tool",
        "install",
        "--force",
        "--python",
        "3.12",
        "swissarmybench[server]==1.2.3",
    )
    assert plan.version == plan.current == "1.2.3" and plan.wait_pids == (7,)
    assert plan.start == ("/tool/python", "-m", "swissarmybench.server", "start")


def _tool(tmp_path: Path) -> Path:
    prefix = tmp_path / "tools" / "swissarmybench"
    prefix.mkdir(parents=True)
    (prefix / "uv-receipt.toml").write_text("[tool]\n")
    return prefix


def test_an_update_of_the_base_keeps_the_installed_extensions(tmp_path: Path) -> None:
    spawned: list[list[str]] = []
    helper = Helper(
        tmp_path / "server.json",
        tmp_path / "note.json",
        prefix=_tool(tmp_path),
        spawn=spawned.append,
        uv=lambda: "/bin/uv",
        kept=lambda version: rules.kept_wheels(CATALOG, ["ledger"], version),
    )
    helper.launch("99.0.0", "pypi")
    handed = json.loads(Path(spawned[0][-1]).read_text())
    assert handed["install"][-3:] == [
        "swissarmybench[server]==99.0.0",
        "--with",
        rules.wheel_url("sab-ledger", "99.0.0"),
    ]
    assert handed["restore"][-1] == rules.wheel_url(
        "sab-ledger", __version__
    )  # the old set, at the old version
    shutil.rmtree(Path(spawned[0][-1]).parent)


def test_the_helper_hands_over_an_extension_change(tmp_path: Path) -> None:
    spawned: list[list[str]] = []
    helper = Helper(
        tmp_path / "server.json",
        tmp_path / "note.json",
        prefix=_tool(tmp_path),
        spawn=spawned.append,
        uv=lambda: "/bin/uv",
    )
    assert helper.installable()
    helper.launch_change(["https://example.invalid/ledger.whl"], [])
    handed = json.loads(Path(spawned[0][-1]).read_text())
    assert handed["install"] == [
        "/bin/uv", "tool", "install", "--force", "--python", PY, f"swissarmybench[server]=={__version__}",
        "--with", "https://example.invalid/ledger.whl",
    ]  # fmt: skip
    assert handed["version"] == __version__ and handed["wait_pids"][0] == os.getpid()
    shutil.rmtree(Path(spawned[0][-1]).parent)
    # A development checkout (no uv receipt) is not installable.
    assert not Helper(tmp_path / "s.json", tmp_path / "n.json", prefix=tmp_path).installable()


# ===== the service =====


class Fakes:
    def __init__(self, installable: bool = True, yes: bool = True) -> None:
        self.ok, self.yes = installable, yes
        self.changes: list[tuple[list[str], list[str]]] = []
        self.asked: list[tuple[str, str, str]] = []
        self.notices: list[dict[str, Any]] = []
        self.stopped: list[bool] = []

    def installable(self) -> bool:
        return self.ok

    def launch_change(self, wheels: list[str], before: list[str]) -> None:
        self.changes.append((wheels, before))

    async def ask(self, dataset: str, action: str, detail: str) -> bool:
        self.asked.append((dataset, action, detail))
        return self.yes

    async def broadcast(self, message: dict[str, Any]) -> None:
        self.notices.append(message)

    def write(self, who: str, action: str, dataset: str | None, **details: Any) -> None:
        pass


def made(fakes: Fakes, found: dict[str, Found] | None = None) -> Extensions:
    return Extensions(
        current="1.2.3",
        found=found or {},
        helper=fakes,
        approvals=cast(Any, fakes),
        audit=cast(Any, fakes),
        live=cast(Any, fakes),
        stop=lambda: fakes.stopped.append(True),
        catalog=CATALOG,
    )


def test_install_hands_over_and_stops_the_app() -> None:
    fakes = Fakes()

    async def go() -> dict[str, Any]:
        said = await made(fakes).install({"id": "ledger"}, "user")
        await asyncio.sleep(0.6)
        return said

    assert asyncio.run(go()) == {"changing": {"id": "ledger", "action": "install"}}
    assert fakes.changes == [([rules.wheel_url("sab-ledger", "1.2.3")], [])]
    assert fakes.asked == [] and fakes.stopped == [True]
    assert fakes.notices[-1] == {"type": "extensions_changing", "id": "ledger", "action": "install"}


def test_what_cannot_be_installed_or_removed_is_said_plainly() -> None:
    service = made(Fakes(), {"ledger": Found("ledger", "1.2.3")})
    for body, words in (
        ({"id": "streamlit"}, "comes with every install"),
        ({"id": "ledger"}, "installed already"),
    ):
        with pytest.raises(Conflict, match=words):
            asyncio.run(service.install(body, "user"))
    with pytest.raises(NotFound):
        asyncio.run(service.install({"id": "nothing"}, "user"))
    with pytest.raises(ValueError):
        asyncio.run(service.install({}, "user"))
    with pytest.raises(Conflict, match="not installed"):
        asyncio.run(made(Fakes()).remove({"id": "ledger"}, "user"))


def test_a_development_checkout_says_what_to_run_and_does_nothing() -> None:
    fakes = Fakes(installable=False)
    with pytest.raises(Conflict, match=r"development checkout.*uv pip install -e extensions/ledger"):
        asyncio.run(made(fakes).install({"id": "ledger"}, "user"))
    assert fakes.changes == [] and fakes.stopped == []
    assert made(fakes).state()["installable"] is False


def test_remove_asks_the_user_first_and_keeps_the_others() -> None:
    fakes = Fakes()
    found = {"ledger": Found("ledger"), "maps": Found("maps", package="sab-maps")}
    service = made(fakes, found)
    asked = asyncio.run(service.remove({"id": "ledger"}, "user"))
    assert asked["id"] == "ledger" and "removes Ledger" in asked["confirm"] and fakes.changes == []

    async def go() -> dict[str, Any]:
        return await service.remove({"id": "ledger", "confirmed": True}, "user")

    assert asyncio.run(go())["changing"] == {"id": "ledger", "action": "remove"}
    assert fakes.changes == [([], [rules.wheel_url("sab-ledger", "1.2.3")])]
    # One the catalog does not know was not installed from here.
    with pytest.raises(Conflict, match="not installed from here"):
        asyncio.run(made(Fakes(), found).remove({"id": "maps"}, "user"))


def test_the_agents_install_and_remove_wait_for_the_users_allow() -> None:
    no = Fakes(yes=False)
    with pytest.raises(Refused, match="declined"):
        asyncio.run(made(no).install({"id": "ledger"}, "agent"))
    assert no.changes == [] and no.asked[0][:2] == ("ledger", "install the extension")
    with pytest.raises(Refused, match="not removed"):
        asyncio.run(made(no, {"ledger": Found("ledger")}).remove({"id": "ledger"}, "agent"))
    yes = Fakes()

    async def go() -> dict[str, Any]:
        return await made(yes, {"ledger": Found("ledger")}).remove({"id": "ledger"}, "agent")

    assert asyncio.run(go())["changing"]["action"] == "remove" and len(yes.asked) == 1


# ===== the routes =====


def test_the_routes_list_and_refuse_in_a_development_checkout(tmp_path: Path) -> None:
    with make_client(tmp_path, update_feeds=()) as client:
        said = client.get("/extensions", headers=AUTH).json()
        assert [e["status"] for e in said["extensions"]] == ["preinstalled", "available", "available"]
        assert said["installable"] is False and said["changing"] is None
        refused = client.post("/extensions/install", headers=AGENT, json={"id": "accounting"})
        assert refused.status_code == 409 and "development checkout" in refused.text
        assert "uv pip install -e extensions/accounting" in refused.text
        assert client.post("/extensions/remove", headers=AUTH, json={"id": "nope"}).status_code == 404
        assert client.get("/extensions").status_code == 401  # the token, as on every route


def test_every_extension_package_is_on_the_bases_version() -> None:
    """Released together: each extension's pyproject, its dependency on the base and its __version__."""
    import re
    import tomllib

    root = Path(__file__).resolve().parents[1]
    base = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    folders = sorted(p.parent for p in (root / "extensions").glob("*/pyproject.toml"))
    assert [f.name for f in folders] == ["accounting", "powerapps"]
    for folder in folders:
        own = tomllib.loads((folder / "pyproject.toml").read_text())["project"]
        assert own["version"] == base, folder.name
        assert f"swissarmybench[server]=={base}" in own["dependencies"], folder.name
        init = next((folder / "src").glob("*/__init__.py")).read_text()
        assert re.search(rf'__version__(: str)? = "{re.escape(base)}"', init), folder.name
        package = own["name"]
        assert package in {e.package for e in rules.CATALOG}, package
