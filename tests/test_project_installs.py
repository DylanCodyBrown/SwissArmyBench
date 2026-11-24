"""A project opens and everything it needs is found and installed at once (services/project_python.py
ProjectInstalls; the owner, 2026-11-23): the `project_installs` notice's states, ONE install with the stand-in
installer (tests/libraries_standin.py: nothing is downloaded), requirements.txt following, a failure with Try
again, SWISSARMYBENCH_PROJECT_VENV=off respected, and the agent's tool waiting for Allow. Made-up data
only."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.cli import commands
from swissarmybench.server import environments
from tests import libraries_standin
from tests.conftest import AGENT, AUTH, PORT, make_client


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def notebook(*cells: str) -> str:
    return json.dumps(
        {"cells": [{"cell_type": "code", "source": c, "metadata": {}, "outputs": []} for c in cells],
         "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    )  # fmt: skip


# What the app makes every project's Python with (the kernel, the Excel readers, the canvas's Streamlit).
MACHINERY = {"ipykernel": "6.29.5", "openpyxl": "3.1.5", "xlrd": "2.0.1", "streamlit": "1.50.0"}


def made_up_project(folder: Path, venv: bool = True) -> Path:
    """A project folder whose data.ipynb imports a made-up library and whose requirements.txt names another;
    its own .venv already made (with the kernel and the Excel readers) unless `venv` is False."""
    folder.mkdir(parents=True)
    (folder / "data.ipynb").write_text(
        notebook("%pip list\nimport tabulate_made_up as tm", "%%sql Sales\nSELECT 1"), encoding="utf-8"
    )
    (folder / "requirements.txt").write_text("rich_made_up==2.0.0\n", encoding="utf-8")
    (folder / "helpers.py").write_text("def double(x):\n    return 2 * x\n", encoding="utf-8")
    (folder / "scripts").mkdir()
    (folder / "scripts" / "load.py").write_text("import helpers\nimport os\n", encoding="utf-8")
    (folder / "builds").mkdir()
    (folder / "builds" / "old.py").write_text("import never_counted_made_up\n", encoding="utf-8")
    if venv:
        libraries_standin.make_venv(folder, MACHINERY)
    return folder


@pytest.fixture
def installing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv(environments.STANDIN, str(Path(libraries_standin.__file__)))
    with make_client(tmp_path, project_venv=True) as test_client:
        yield test_client


def settled(client: TestClient, *states: str) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for _ in range(300):
        state = ok(client.get("/project/installs", headers=AUTH))
        if state["state"] in states:
            return state
        time.sleep(0.05)
    raise AssertionError(f"never {states}: {state}")


def test_a_project_opened_gets_everything_it_needs_in_one_install(
    installing: TestClient, tmp_path: Path
) -> None:
    folder = made_up_project(tmp_path / "work" / "Sales Recon")
    heard: list[dict[str, Any]] = []
    with installing.websocket_connect(
        "/ws?catalog=1", headers=AUTH | {"Host": f"127.0.0.1:{PORT}"}
    ) as socket:
        ok(installing.post("/project/open", json={"path": str(folder), "make": True}, headers=AUTH))
        while not heard or heard[-1]["state"] not in ("done", "failed"):
            notice = socket.receive_json()
            if notice.get("type") == "project_installs" and notice.get("project") == "Sales Recon":
                heard.append(notice)
    states = [n["state"] for n in heard]
    assert states[0] == "checking" and "installing" in states and states[-1] == "done", json.dumps(heard[-1])
    installing_one = next(n for n in heard if n["state"] == "installing")
    assert installing_one["total"] == 2 and installing_one["words"].startswith(
        "Setting up Sales Recon: installing"
    )
    by = {p["name"]: p["why"] for p in heard[-1]["packages"]}
    assert by == {"rich_made_up": "requirements.txt", "tabulate_made_up": "data.ipynb"}
    assert {p["status"] for p in heard[-1]["packages"]} == {"installed"}
    done = heard[-1]
    assert done["done"] == 2 and done["words"] == "Installed 2 libraries · added to requirements.txt"
    # Installed into the project's own Python, the pin kept; what code imports added to requirements.txt.
    site = libraries_standin.site_packages(folder)
    assert (site / "rich_made_up-2.0.0.dist-info").is_dir() and list(site.glob("tabulate_made_up-*"))
    requirements = (folder / "requirements.txt").read_text(encoding="utf-8")
    assert requirements == "rich_made_up==2.0.0\ntabulate_made_up\n"
    # Neither the project's own module, the standard library nor a build's file is a library.
    assert not list(site.glob("helpers-*")) and not list(site.glob("never_counted_made_up-*"))
    # Looking again finds nothing missing.
    again = ok(installing.post("/project/installs/check", json={}, headers=AUTH))
    assert again["state"] == "none" and again["packages"] == []
    assert again["words"] == "Everything this project needs is installed."


def test_a_new_import_saved_later_is_installed_by_itself(installing: TestClient, tmp_path: Path) -> None:
    """The owner, 2026-11-24: "the app is still not auto detecting missing packages and installing them":
    not only as the project opens, but as its code is saved."""
    folder = made_up_project(tmp_path / "work" / "Pricing")
    ok(installing.post("/project/open", json={"path": str(folder), "make": True}, headers=AUTH))
    assert settled(installing, "done", "failed")["state"] == "done"
    script = folder / "scripts" / "price.py"
    saved = {"path": str(script), "text": "import pretty_made_up\n"}
    ok(installing.post("/workbench/save", json=saved, headers=AUTH))
    for _ in range(300):  # the saves settle (2 s), then the one install
        if list(libraries_standin.site_packages(folder).glob("pretty_made_up-*")):
            break
        time.sleep(0.05)
    assert list(libraries_standin.site_packages(folder).glob("pretty_made_up-*"))
    done = settled(installing, "done", "failed")
    assert done["state"] == "done" and [p["name"] for p in done["packages"]] == ["pretty_made_up"]
    assert "pretty_made_up" in (folder / "requirements.txt").read_text(encoding="utf-8")


def test_a_project_without_a_venv_has_it_made_first_then_its_needs_installed(
    installing: TestClient, tmp_path: Path
) -> None:
    folder = made_up_project(tmp_path / "work" / "Ledger", venv=False)
    ok(installing.post("/project/open", json={"path": str(folder), "make": True}, headers=AUTH))
    done = settled(installing, "done", "failed")
    # requirements.txt's line came with the .venv (it is made with it); the import is the one left.
    assert done["state"] == "done" and [p["name"] for p in done["packages"]] == ["tabulate_made_up"]
    assert "tabulate_made_up" in (folder / "requirements.txt").read_text(encoding="utf-8")


def test_a_failure_keeps_what_installed_says_which_failed_and_try_again_installs_the_rest(
    installing: TestClient, tmp_path: Path
) -> None:
    folder = made_up_project(tmp_path / "work" / "Broken")
    (folder / "report.py").write_text("import broken_widgets_made_up\n", encoding="utf-8")
    ok(installing.post("/project/open", json={"path": str(folder), "make": True}, headers=AUTH))
    failed = settled(installing, "done", "failed")
    assert failed["state"] == "failed"
    status = {p["name"]: p["status"] for p in failed["packages"]}
    assert status["broken_widgets_made_up"] == "failed" and status["tabulate_made_up"] == "installed"
    assert failed["words"].startswith("1 library could not be installed (broken_widgets_made_up)")
    problem = failed["problem"]
    assert problem["error"] == "These could not be installed: broken_widgets_made_up."
    assert problem["fixes"] == [{"label": "Try again", "action": "try_again"}]
    assert "No solution found" in problem["details"]
    # What installed was kept, and written to requirements.txt; the failed one was not.
    requirements = (folder / "requirements.txt").read_text(encoding="utf-8")
    assert "tabulate_made_up" in requirements and "broken" not in requirements
    # Try again: the broken import fixed, the rest installs.
    (folder / "report.py").write_text("import pretty_made_up\n", encoding="utf-8")
    ok(installing.post("/project/installs/run", json={}, headers=AUTH))
    again = settled(installing, "done", "failed")
    assert again["state"] == "done" and [p["name"] for p in again["packages"]] == ["pretty_made_up"]


def test_with_the_making_switched_off_nothing_happens_by_itself_but_check_and_run_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(environments.STANDIN, str(Path(libraries_standin.__file__)))
    with make_client(tmp_path, project_venv=False) as client:
        folder = made_up_project(tmp_path / "work" / "Quiet")
        ok(client.post("/project/open", json={"path": str(folder), "make": True}, headers=AUTH))
        time.sleep(0.3)
        quiet = ok(client.get("/project/installs", headers=AUTH))
        assert quiet["state"] == "none" and quiet["packages"] == [] and quiet["project"] == "Quiet"
        assert not list(libraries_standin.site_packages(folder).glob("tabulate_made_up-*"))
        # The agent's check looks (installs nothing): what is missing, and the words to install them.
        looked = ok(client.post("/project/installs/check", json={}, headers=AGENT))
        assert {p["name"] for p in looked["packages"]} == {"rich_made_up", "tabulate_made_up"}
        assert looked["words"] == "This project needs 2 libraries its Python does not have yet: Install them."
        assert {p["status"] for p in looked["packages"]} == {"waiting"}
        # The agent's install waits for the user's Allow.
        answer: dict[str, Any] = {}
        waiting = threading.Thread(
            target=lambda: answer.update(r=client.post("/project/installs/run", json={}, headers=AGENT))
        )
        waiting.start()
        pending: list[Any] = []
        for _ in range(100):
            pending = ok(client.get("/agent/approvals", headers=AUTH))["pending"]
            if pending:
                break
            time.sleep(0.05)
        assert pending and pending[0]["action"] == "install libraries"
        ok(client.post(f"/agent/approvals/{pending[0]['id']}", json={"approve": True}, headers=AUTH))
        waiting.join(10)
        assert answer["r"].status_code == 200
        assert settled(client, "done", "failed")["state"] == "done"


def test_no_project_open_is_said_and_a_project_without_its_own_python_installs_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(environments.STANDIN, str(Path(libraries_standin.__file__)))
    with make_client(tmp_path, project_venv=False) as client:
        refused = client.post("/project/installs/check", json={}, headers=AUTH)
        assert refused.status_code == 409 and "open or make one first" in refused.text
        folder = made_up_project(tmp_path / "work" / "Bare", venv=False)
        ok(client.post("/project/open", json={"path": str(folder), "make": True}, headers=AUTH))
        looked = ok(client.post("/project/installs/check", json={}, headers=AUTH))
        assert looked["own"] is False and "not made yet" in looked["words"]
        refused = client.post("/project/installs/run", json={}, headers=AUTH)
        assert refused.status_code == 409 and "no Python of its own yet" in refused.text


def test_the_agents_tool() -> None:
    tool = commands.REGISTRY["project_installs"]
    assert "Allow" in tool.summary
    with pytest.raises(commands.CommandError, match="action is one of"):
        tool.run({"action": "refresh"})
