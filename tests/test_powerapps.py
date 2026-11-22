"""The Power Apps extension through its door, with the Power Platform tools stood in by recorded fakes on a
PATH of their own (tests/powerapps_fakes.py) and the environment's connectivity service by a made-up
stand-in on 127.0.0.1. Never a real tenant; made-up names only."""

from __future__ import annotations

import http.server
import json
import os
import shutil
import socketserver
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench import extensions
from swissarmybench.cli import api as cli_api
from swissarmybench.cli import commands as base_commands
from tests import powerapps_fakes as fakes
from tests.conftest import AGENT, AUTH, make_client
from tests.test_powerapps_rules import OPENAPI


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def tools_dir(tmp_path: Path) -> Path:
    return fakes.install(tmp_path / "fake-tools")


@pytest.fixture
def switched_on(monkeypatch: pytest.MonkeyPatch, tools_dir: Path) -> Iterator[None]:
    monkeypatch.setenv(extensions.VARIABLE, "powerapps")
    monkeypatch.setenv("PATH", str(tools_dir) + os.pathsep + os.environ.get("PATH", ""))
    yield


@pytest.fixture
def client(tmp_path: Path, switched_on: None) -> Iterator[TestClient]:
    with make_client(tmp_path) as test_client:
        yield test_client


def new_app(client: TestClient, tmp_path: Path, name: str = "Expense Tracker", headers: Any = AUTH) -> Any:
    parent = tmp_path / "apps"
    parent.mkdir(exist_ok=True)
    body = {"name": name, "environment_id": fakes.ENVIRONMENT_ID, "parent": str(parent)}
    return client.post("/powerapps/project/new", json=body, headers=headers)


def wait_for_approval(client: TestClient) -> dict[str, Any]:
    for _ in range(200):
        pending = ok(client.get("/agent/approvals", headers=AUTH))["pending"]
        if pending:
            return dict(pending[0])
        time.sleep(0.05)
    raise AssertionError("no approval was asked")


def answer_in_background(client: TestClient, approve: bool) -> threading.Thread:
    def answer() -> None:
        asked = wait_for_approval(client)
        client.post(f"/agent/approvals/{asked['id']}", json={"approve": approve}, headers=AUTH)

    thread = threading.Thread(target=answer)
    thread.start()
    return thread


# ===== off and on =====


def test_off_nothing_of_it_is_there(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(extensions.VARIABLE, raising=False)
    with make_client(tmp_path) as client:
        assert client.get("/powerapps", headers=AUTH).status_code == 404
        assert client.get("/powerapps/live/any/", headers=AUTH).status_code == 404
        mode = ok(client.get("/app/mode", headers=AUTH))
        assert mode["project_type"] == "bi" and mode["mode"]["languages"] == ["python"]
        assert [m["type"] for m in ok(client.get("/app/modes", headers=AUTH))["modes"]] == ["bi"]
        assert all(not n.startswith("powerapps_") for n in base_commands.REGISTRY)
        families = [f["family"] for f in ok(client.get("/blades/starters", headers=AUTH))["families"]]
        assert "TypeScript" not in families and "React" not in families


def test_on_its_project_type_and_mode_are_listed(client: TestClient) -> None:
    listed = ok(client.get("/app/modes", headers=AUTH))["modes"]
    assert [m["type"] for m in listed] == ["bi", "codeapp"]
    assert listed[1]["deliverable"] == "a Power Apps code app"
    families = [f["family"] for f in ok(client.get("/blades/starters", headers=AUTH))["families"]]
    assert {"TypeScript", "React", "Connectors"} <= set(families)


# ===== tools =====


def test_tools_are_found_with_their_versions(client: TestClient) -> None:
    found = {t["id"]: t for t in ok(client.get("/powerapps/tools", headers=AUTH))["tools"]}
    assert found["pa"]["version"] == "1.4.2" and found["pa"]["ok"]
    assert found["pac"]["version"] == "1.47.1" and found["node"]["version"] == "22.11.0"
    assert found["npm"]["version"] == "10.9.0"


def test_a_missing_tool_is_the_missing_package_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    only = fakes.install(tmp_path / "only-node", tools=("node", "npm", "npx"))
    monkeypatch.setenv(extensions.VARIABLE, "powerapps")
    monkeypatch.setenv("PATH", str(only))
    with make_client(tmp_path) as client:
        refused = new_app(client, tmp_path)
        assert refused.status_code == 422, refused.text
        missing = refused.json()["missing"]
        assert missing["packages"] == ["Power Apps CLI"] and missing["tool"] == "pa"
        assert missing["command"] == "npm install --global @microsoft/power-apps-cli"
        assert missing["feature"] == "A new code app"
        assert not (tmp_path / "apps" / "expense-tracker").exists()
        envs = client.get("/powerapps/environments", headers=AUTH)
        assert envs.status_code == 422 and envs.json()["missing"]["packages"] == ["Power Platform CLI"]
        # Installing needs the user's word; the agent's waits for Allow (declined here).
        thread = answer_in_background(client, approve=False)
        declined = client.post("/powerapps/tools/install", json={"tool": "pa"}, headers=AGENT)
        thread.join(10)
        assert declined.status_code == 403
        assert ["npm", "install", "--global", "@microsoft/power-apps-cli"] not in [
            c for c in fakes.calls(only) if c[0] == "npm"
        ]


# ===== signing in and environments =====


def test_sign_in_and_environments(client: TestClient, tools_dir: Path) -> None:
    account = ok(client.get("/powerapps/account", headers=AUTH))
    assert account == {
        "signed_in": True,
        "active": fakes.ACCOUNT,
        "accounts": [{"username": fakes.ACCOUNT, "active": True}],
    }
    fakes.sign_out(tools_dir)
    assert ok(client.get("/powerapps/account", headers=AUTH))["signed_in"] is False
    assert ok(client.post("/powerapps/account/sign-in", json={}, headers=AUTH))["signed_in"] is True
    envs = ok(client.get("/powerapps/environments", headers=AUTH))["environments"]
    assert [e["name"] for e in envs] == ["Contoso (default)", "Contoso Test"]
    profiles = ok(client.get("/powerapps/profiles", headers=AUTH))["profiles"]
    assert [p["environment"] for p in profiles] == ["Contoso (default)", "Contoso Test"]
    ok(client.put("/powerapps/profiles", json={"index": 2}, headers=AGENT))  # the agent may: no Allow
    assert ["pac", "auth", "select", "--index", "2"] in fakes.calls(tools_dir)
    assert client.put("/powerapps/profiles", json={"index": "two"}, headers=AUTH).status_code == 400


# ===== the project =====


def test_new_code_app_through_the_cli_and_its_mode(
    client: TestClient, tmp_path: Path, tools_dir: Path
) -> None:
    assert ok(client.get("/app/mode", headers=AUTH))["project_type"] == "bi"
    made = new_app(client, tmp_path)
    state = ok(made)
    folder = tmp_path / "apps" / "expense-tracker"
    assert state["folder"] == str(folder.resolve()) and state["app"]["name"] == "Expense Tracker"
    assert state["app"]["environment_id"] == fakes.ENVIRONMENT_ID and state["vite_plugin"] is True
    assert json.loads((folder / ".sab" / "project.json").read_text()) == {"type": "codeapp"}
    ran = [c for c in fakes.calls(tools_dir) if c[0] in ("npx", "npm", "pa") and c[1:2] != ["--version"]]
    assert ran[:3] == [
        ["npx", "--yes", "degit", "github:microsoft/PowerAppsCodeApps/templates/vite", "expense-tracker"],
        ["npm", "install"],
        ["pa", "app", "init", "--display-name", "Expense Tracker", "--environment-id", fakes.ENVIRONMENT_ID],
    ]
    # The open code app sets the mode: TypeScript for new files, its families, its coming cells.
    active = ok(client.get("/app/mode", headers=AUTH))
    assert active["project_type"] == "codeapp" and active["project"] == str(folder.resolve())
    assert active["mode"]["languages"][0] == "typescript"
    assert active["mode"]["families"] == ["TypeScript", "React", "Connectors"]
    # Its runs are this session's, each in words, and on the Session page.
    runs = ok(client.get("/powerapps/runs", headers=AUTH))["runs"]
    assert {"npx degit github:microsoft/PowerAppsCodeApps/templates/vite expense-tracker", "npm install",
            "pa app init"} <= {r["command"] for r in runs}  # fmt: skip
    one = ok(client.get(f"/powerapps/runs/{runs[0]['id']}", headers=AUTH))["run"]
    assert one["done"] and "output" in one
    log = ok(client.get("/session-log?who=both", headers=AUTH))["entries"]
    words = [e["what"] for e in log]
    assert "Made the code app Expense Tracker" in words and "Ran pa app init (done)" in words
    assert all(e["area"] == "codeapp" for e in log if e["action"].startswith("powerapps_"))
    # A folder that is there already is refused; closing goes back to the base's mode.
    assert new_app(client, tmp_path).status_code == 409
    ok(client.post("/powerapps/project/close", headers=AUTH))
    assert ok(client.get("/app/mode", headers=AUTH))["project_type"] == "bi"
    reopened = ok(client.post("/powerapps/project/open", json={"folder": str(folder)}, headers=AGENT))
    assert reopened["app"]["name"] == "Expense Tracker"
    not_an_app = client.post("/powerapps/project/open", json={"folder": str(tmp_path)}, headers=AUTH)
    assert not_an_app.status_code == 400 and "not a code app" in not_an_app.text


def test_code_apps_switched_off_in_an_environment_is_said_plainly(client: TestClient, tmp_path: Path) -> None:
    parent = tmp_path / "apps"
    parent.mkdir()
    body = {"name": "Off App", "environment_id": fakes.OTHER_ENVIRONMENT_ID, "parent": str(parent)}
    refused = client.post("/powerapps/project/new", json=body, headers=AUTH)
    assert refused.status_code == 409 and "Code apps are switched off" in refused.text
    assert "Enable code apps" in refused.text


def test_data_sources_added_listed_and_removed(client: TestClient, tmp_path: Path) -> None:
    ok(new_app(client, tmp_path))
    state = ok(
        client.post("/powerapps/sources", json={"kind": "dataverse", "table": "account"}, headers=AUTH)
    )
    assert [(s["name"], s["kind"]) for s in state["sources"]] == [("accounts", "dataverse")]
    assert [g["name"] for g in state["generated"]] == ["AccountsModel.ts", "AccountsService.ts"]
    body = {
        "kind": "connector",
        "connector": "shared_contosotasks",
        "connection_id": "c0ffee00000011112222333344445555",
    }
    state = ok(client.post("/powerapps/sources", json=body, headers=AGENT))
    assert ("Contosotasks", "connector") in [(s["name"], s["kind"]) for s in state["sources"]]
    no_connection = client.post(
        "/powerapps/sources", json={"kind": "connector", "connector": "shared_x"}, headers=AUTH
    )
    assert no_connection.status_code == 400 and "connection" in no_connection.text
    state = ok(client.post("/powerapps/sources/remove", json={"name": "accounts"}, headers=AUTH))
    assert "accounts" not in [s["name"] for s in state["sources"]]
    assert client.post("/powerapps/sources/remove", json={"name": "nothing"}, headers=AUTH).status_code == 404
    # The generated service opens in the editor, as TypeScript.
    read = ok(
        client.get("/powerapps/project/file?path=src/generated/services/AccountsService.ts", headers=AUTH)
    )
    assert read["language"] == "typescript" and read["generated"] and "AccountsService" in read["text"]
    tree = ok(client.get("/powerapps/project/files", headers=AUTH))["tree"]
    assert "node_modules" not in [c["name"] for c in tree["children"]]
    ok(
        client.put(
            "/powerapps/project/file",
            json={"path": "src/App.tsx", "text": "export default 1;\n"},
            headers=AUTH,
        )
    )
    assert (Path(read["full_path"]).parents[2] / "App.tsx").read_text() == "export default 1;\n"
    outside = client.get("/powerapps/project/file?path=../../secret.txt", headers=AUTH)
    assert outside.status_code == 403


# ===== connectors =====


@pytest.fixture
def connectivity(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[dict[str, str]]]:
    """The environment's connectivity service, stood in: Northwind Orders' made-up definition."""
    asked: list[dict[str, str]] = []
    swagger = fakes.tasks_swagger() | {"info": {"title": "Northwind Orders", "version": "1.0"}}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            asked.append({"path": self.path, "auth": self.headers.get("Authorization", "")})
            body = json.dumps(
                {
                    "name": "shared_northwindorders",
                    "properties": {"displayName": "Northwind Orders", "swagger": swagger},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:
            pass

    server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("SWISSARMYBENCH_POWERPLATFORM_API", f"http://127.0.0.1:{server.server_address[1]}")
    yield asked
    server.shutdown()


def test_connectors_listed_searched_and_read_into_the_explorer(
    client: TestClient, tmp_path: Path, connectivity: list[dict[str, str]]
) -> None:
    ok(new_app(client, tmp_path))
    listed = ok(client.get("/powerapps/connectors", headers=AUTH))
    assert listed["total"] == 3 and listed["connectors"][0]["display_name"] == "Contoso Tasks"
    assert [
        c["name"] for c in ok(client.get("/powerapps/connectors?q=tickets", headers=AUTH))["connectors"]
    ] == ["shared_fabrikamtickets"]
    linked = ok(client.get("/powerapps/connections?connector=shared_fabrikamtickets", headers=AUTH))[
        "connections"
    ]
    assert [c["id"] for c in linked] == ["beef0000000011112222333344445555"]
    # Added to the app: its definition comes from the app's own .power/schemas.
    body = {
        "kind": "connector",
        "connector": "shared_contosotasks",
        "connection_id": "c0ffee00000011112222333344445555",
    }
    ok(client.post("/powerapps/sources", json=body, headers=AUTH))
    tasks = ok(client.get("/powerapps/connectors/shared_contosotasks", headers=AUTH))
    assert tasks["read_only"] and tasks["from"].startswith("the code app's .power/schemas")
    assert {o["operation_id"] for o in tasks["operations"]} == {"ListTasks", "CreateTask"}
    assert ok(client.get("/powerapps/connectors", headers=AUTH))["connectors"][0]["in_app"] is True
    # Not in the app: the environment's service, with pac's sign-in (its token never shown or kept).
    orders = ok(client.get("/powerapps/connectors/shared_northwindorders", headers=AGENT))
    assert (
        orders["display_name"] == "Northwind Orders"
        and orders["from"] == "the environment's connectivity service"
    )
    assert connectivity[0]["auth"] == f"Bearer {fakes.TOKEN}"
    assert connectivity[0]["path"].startswith(
        "/connectivity/connectors/shared_northwindorders?api-version=1&$filter="
    )
    assert fakes.ENVIRONMENT_ID in connectivity[0]["path"]
    every = json.dumps(ok(client.get("/powerapps/runs", headers=AUTH))) + json.dumps(
        ok(client.get("/session-log?who=both", headers=AUTH))
    )
    assert fakes.TOKEN not in every and "pac auth token" not in every.replace("Ran pac auth token", "")


# ===== Run live =====


def test_run_live_through_this_servers_proxy(client: TestClient, tmp_path: Path) -> None:
    ok(new_app(client, tmp_path))
    live = ok(client.post("/powerapps/live", json={}, headers=AUTH))
    try:
        assert live["running"] and live["ready"] and live["pane"].startswith("/powerapps/live/")
        assert live["play_url"].startswith(
            f"https://make.powerapps.com/play/e/{fakes.ENVIRONMENT_ID}/app/local"
        )
        page = client.get(live["pane"])  # the frame's address: its own secret, no token
        assert page.status_code == 200 and "Expense Tracker" in page.text
        assert page.headers["referrer-policy"] == "no-referrer"
        wrong = client.get("/powerapps/live/not-the-key/")
        assert wrong.status_code == 404 and "dev server is not running" in wrong.text
        assert ok(client.get("/powerapps/live", headers=AUTH))["running"]
    finally:
        ok(client.delete("/powerapps/live", headers=AUTH))
    assert client.get(live["pane"]).status_code == 404
    log = [e["what"] for e in ok(client.get("/session-log?who=both", headers=AUTH))["entries"]]
    assert "Ran Expense Tracker live" in log and "Stopped Run live" in log


# ===== Push =====


def test_push_dry_run_then_the_agents_push_waits_for_allow(
    client: TestClient, tmp_path: Path, tools_dir: Path
) -> None:
    ok(new_app(client, tmp_path))
    plan = ok(client.post("/powerapps/push", json={"dry_run": True}, headers=AGENT))
    assert plan["dry_run"] and plan["commands"] == ["npm run build", "pa app push"]
    assert ["pa", "app", "push"] not in fakes.calls(tools_dir)
    thread = answer_in_background(client, approve=False)
    declined = client.post("/powerapps/push", json={}, headers=AGENT)
    thread.join(10)
    assert declined.status_code == 403 and ["pa", "app", "push"] not in fakes.calls(tools_dir)
    thread = answer_in_background(client, approve=True)
    pushed = ok(client.post("/powerapps/push", json={}, headers=AGENT))
    thread.join(10)
    assert pushed["link"] == f"https://apps.powerapps.com/play/e/{fakes.ENVIRONMENT_ID}/a/{fakes.APP_ID}"
    versions = ok(client.get("/powerapps/versions", headers=AUTH))
    assert [a["this"] for a in versions["apps"]] == [True, False] and versions["pushes"][0]["link"] == pushed[
        "link"
    ]
    # The user's own push asks nothing.
    assert ok(client.post("/powerapps/push", json={}, headers=AUTH))["pushed"]


# ===== custom connectors =====


def test_a_custom_connector_dry_run_then_made(client: TestClient, tmp_path: Path, tools_dir: Path) -> None:
    ok(new_app(client, tmp_path))
    auth = {"type": "api_key", "in": "header", "name": "X-Orders-Key"}
    client.app.state.ctx.extension["powerapps"].powerapps._api_documents = lambda name: (OPENAPI, auth)  # type: ignore[attr-defined]
    dry = ok(client.post("/powerapps/custom-connector", json={"api": "Made-up Orders"}, headers=AGENT))
    assert dry["dry_run"] and set(dry["files"]) == {"apiDefinition.swagger.json", "apiProperties.json"}
    folder = tmp_path / "apps" / "expense-tracker" / "connectors" / "made-up-orders"
    assert not folder.exists()
    thread = answer_in_background(client, approve=True)
    made = ok(
        client.post(
            "/powerapps/custom-connector", json={"api": "Made-up Orders", "dry_run": False}, headers=AGENT
        )
    )
    thread.join(10)
    assert made["made"] and (folder / "apiDefinition.swagger.json").exists()
    created = [c for c in fakes.calls(tools_dir) if c[:3] == ["pac", "connector", "create"]]
    assert created and created[0][3:5] == [
        "--api-definition-file",
        str(folder / "apiDefinition.swagger.json"),
    ]
    assert "X-Orders-Key" in (folder / "apiDefinition.swagger.json").read_text()


# ===== the agent's commands =====


def test_every_action_is_an_agent_command(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The commands register in the base's registry (an MCP tool each) and drive the same door."""
    before_registry = dict(base_commands.REGISTRY)
    before_areas = base_commands.AREAS
    try:
        from swissarmybench_powerapps import extension

        base_commands.REGISTRY.update(extension.commands())
        base_commands.AREAS = (*base_commands.AREAS, *extension.AREAS)
        names = {n for n in base_commands.REGISTRY if n.startswith("powerapps_")}
        assert names == {
            "powerapps_state", "powerapps_tools", "powerapps_auth", "powerapps_environments",
            "powerapps_profiles", "powerapps_project", "powerapps_new", "powerapps_open", "powerapps_files",
            "powerapps_add_source", "powerapps_remove_source", "powerapps_connectors", "powerapps_connector",
            "powerapps_connections", "powerapps_run_live", "powerapps_push", "powerapps_versions",
            "powerapps_custom_connector", "powerapps_runs",
            # phase 2: the data notebook (tests/test_powerapps_notebook.py drives these)
            "powerapps_notebook", "powerapps_ts_run", "powerapps_ts_grid", "powerapps_data_ts",
            "powerapps_tsx_preview", "powerapps_dataverse_grid",
            # pages (tests/test_powerapps_pages.py)
            "powerapps_pages", "powerapps_scaffold", "powerapps_lint",
        }  # fmt: skip
        assert base_commands.area_of("powerapps_push") == "powerapps"

        def through_client(
            method: str, path: str, body: Any = None, params: Any = None, timeout: float = 0
        ) -> Any:
            answer = client.request(
                method,
                path,
                json=body,
                params={k: v for k, v in (params or {}).items() if v is not None},
                headers=AGENT,
            )
            if answer.status_code >= 400:
                raise cli_api.CommandError(answer.text)
            return answer.json()

        monkeypatch.setattr(cli_api, "call", through_client)
        parent = tmp_path / "apps"
        parent.mkdir()
        made = json.loads(
            base_commands.execute(
                "powerapps_new",
                {"name": "Agent App", "environment_id": fakes.ENVIRONMENT_ID, "parent": str(parent)},
            )
        )
        assert made["app"]["name"] == "Agent App"
        json.loads(base_commands.execute("powerapps_add_source", {"table": "account"}))
        assert json.loads(base_commands.execute("powerapps_push", {"dry_run": True}))["dry_run"]
        mode = json.loads(base_commands.execute("app_mode"))
        assert mode["project_type"] == "codeapp" and mode["mode"]["tools"] == ["powerapps_"]
        thread = answer_in_background(client, approve=False)
        with pytest.raises(cli_api.CommandError, match="declined"):
            base_commands.execute("powerapps_push")
        thread.join(10)
    finally:
        base_commands.REGISTRY.clear()
        base_commands.REGISTRY.update(before_registry)
        base_commands.AREAS = before_areas


def test_node_and_npm_for_real_when_this_computer_has_them(tmp_path: Path) -> None:
    """The version reading against the real tools, where they are (skipped with the reason otherwise)."""
    import asyncio

    from swissarmybench_powerapps.adapters.runner import Runner
    from swissarmybench_powerapps.domain import tools

    if not (shutil.which("node") and shutil.which("npm")):
        pytest.skip("Node.js and npm are not on this computer's PATH")
    runner = Runner()
    ran = asyncio.run(runner.run(["node", "--version"], None, 30.0))
    version = tools.parse_version("node", ran.output)
    assert ran.code == 0 and version and tools.version_tuple(version) >= (1,)
    ran = asyncio.run(runner.run(["npm", "--version"], str(tmp_path), 60.0))
    assert ran.code == 0 and tools.parse_version("npm", ran.output)
