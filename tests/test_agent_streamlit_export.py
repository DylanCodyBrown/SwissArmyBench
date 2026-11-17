# ruff: noqa: F811
"""The agent's Streamlit Export waits for the user's Allow, as the grid's export does (the owner,
2026-11-15): the same approval request and the same prompt in the page, worded for this export (the
app, the folder, the tables whose rows are copied). Declined or unanswered, nothing is written; the
folder written is the one the user allowed. The user's own Export click asks nothing.

The same holds for the other agent commands that would write the user's rows to disk: New project and
Save as, when the project's data.ipynb would hold a pasted table's rows (its read-only cell writes a
small paste out). Code only asks nothing. Made-up data only."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest
from starlette.testclient import TestClient

from swissarmybench.cli.commands import CommandError
from swissarmybench.services import agent
from swissarmybench_streamlit.adapters.streamlit_files import AppFiles
from tests.conftest import AGENT, AUTH
from tests.test_cli import Live, live  # noqa: F401 (the running server)
from tests.test_cli import run as command
from tests.test_streamlit_apps import (
    ORDERS,
    FakeRunner,
    _canvas,
    _notebook,
    _ok,
    allowing,
    answering,
    served,  # noqa: F401 (the server with made-up orders and customers)
)

PASTED = "order_id\tregion\tamount\n1\tEast\t100\n2\tWest\t250\n"


def _answering(client: TestClient, approve: bool = True) -> Any:
    """The user at the page, answering each approval request (as the TestClient's user)."""
    return answering(
        lambda: client.get("/agent/approvals", headers=AUTH).json()["pending"],
        lambda request, yes: client.post(f"/agent/approvals/{request}", headers=AUTH, json={"approve": yes}),
        approve,
    )


def _app_with_orders(client: TestClient, tmp_path: Path) -> str:
    """A canvas with one page whose blocks read the orders table."""
    path = str(_notebook(tmp_path))
    app = str(_canvas(client)["app"])
    page = {"name": "Sales overview", "document": path, "cell": 4, "w": 12}
    _ok(client.post(f"/streamlit/apps/{app}/pages", headers=AUTH, json=page))
    _ok(
        client.post(
            f"/streamlit/apps/{app}/pages/p1/blocks", headers=AUTH, json={"document": path, "cell": 3}
        )
    )
    return app


def _export(client: TestClient, app: str, folder: Path | str, who: dict[str, str]) -> Any:
    return client.post(f"/streamlit/apps/{app}/export", headers=who, json={"folder": str(folder)})


# ===== the export =====


def test_the_agents_export_waits_for_the_users_allow_and_writes_the_folder_allowed(
    served: tuple[TestClient, FakeRunner], tmp_path: Path
) -> None:
    client, _ = served
    app = _app_with_orders(client, tmp_path)
    (tmp_path / "elsewhere").mkdir()
    # Sent with a detour: the prompt names the folder the export really writes, and it is that one.
    asked_for = tmp_path / "elsewhere" / ".." / "out"
    with _answering(client) as asked:
        done = _ok(_export(client, app, asked_for, AGENT))
    out = tmp_path / "out"
    assert done["folder"] == str(out) and done["tables"] == ["orders"]
    assert pq.read_table(out / "data" / "orders.parquet").to_pydict() == ORDERS.to_pydict()
    assert len(asked) == 1
    prompt = asked[0]
    assert prompt["action"] == "export the Streamlit app" and prompt["dataset"] == '"sales" (not saved yet)'
    assert f"  {out}\n" in prompt["detail"] and "Pages: Sales overview" in prompt["detail"]
    assert "  orders (6 rows as loaded)" in prompt["detail"] and "Parquet" in prompt["detail"]
    assert "customers" not in prompt["detail"]  # only the tables the pages read
    # The audit log says who: the user's Allow, then the agent's export.
    log = [json.loads(line) for line in (tmp_path / "state" / "audit.log").read_text().splitlines()]
    said = [(e["actor"], e["action"]) for e in log if e["action"] in ("approval", "export_streamlit_app")]
    assert said == [("user", "approval"), ("agent", "export_streamlit_app")]


def test_a_declined_export_writes_nothing(served: tuple[TestClient, FakeRunner], tmp_path: Path) -> None:
    client, _ = served
    app = _app_with_orders(client, tmp_path)
    with _answering(client, approve=False) as asked:
        refused = _export(client, app, tmp_path / "out", AGENT)
    assert refused.status_code == 403 and "declined" in refused.text and len(asked) == 1
    assert not (tmp_path / "out").exists()


def test_an_export_nobody_allows_is_refused(
    served: tuple[TestClient, FakeRunner], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = served
    app = _app_with_orders(client, tmp_path)
    monkeypatch.setattr(agent, "APPROVAL_TIMEOUT_SECONDS", 0.3)
    refused = _export(client, app, tmp_path / "out", AGENT)
    assert refused.status_code == 403 and "did not answer" in refused.text
    assert not (tmp_path / "out").exists()
    assert client.get("/agent/approvals", headers=AUTH).json()["pending"] == []


def test_the_agent_cannot_allow_its_own_export(served: tuple[TestClient, FakeRunner], tmp_path: Path) -> None:
    client, _ = served
    app = _app_with_orders(client, tmp_path)
    answers: list[int] = []
    waiting = threading.Thread(
        target=lambda: answers.append(_export(client, app, tmp_path / "out", AGENT).status_code)
    )
    waiting.start()
    pending: list[dict[str, Any]] = []
    for _ in range(250):
        pending = client.get("/agent/approvals", headers=AGENT).json()["pending"]
        if pending:
            break
        time.sleep(0.02)
    assert pending
    # The agent answering its own request is refused; the user's Deny then ends it.
    own = client.post(f"/agent/approvals/{pending[0]['id']}", headers=AGENT, json={"approve": True})
    assert own.status_code == 403
    client.post(f"/agent/approvals/{pending[0]['id']}", headers=AUTH, json={"approve": False})
    waiting.join(30)
    assert answers == [403] and not (tmp_path / "out").exists()


def test_the_users_own_export_asks_nothing(served: tuple[TestClient, FakeRunner], tmp_path: Path) -> None:
    client, _ = served
    app = _app_with_orders(client, tmp_path)
    with _answering(client) as asked:
        done = _ok(_export(client, app, tmp_path / "mine", AUTH))
    assert asked == [] and done["tables"] == ["orders"] and (tmp_path / "mine" / "app.py").is_file()


def test_an_export_writes_only_where_it_was_allowed(tmp_path: Path) -> None:
    """A folder that no longer resolves to the path chosen (a link put in its place since) is refused
    before anything is written."""
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real, target_is_directory=True)
    files = AppFiles()
    assert files.export_target(str(tmp_path / "link")) == str(real)
    with pytest.raises(PermissionError, match="changed since"):
        files.export(str(tmp_path / "link"), {"app.py": "x = 1\n"}, {"orders": b"PAR1"})
    assert list(real.iterdir()) == []
    target, written = files.export(str(real), {"app.py": "x = 1\n"}, {})
    assert target == str(real) and written == ["app.py"]


# ===== New project and Save as: only when data.ipynb would hold a pasted table's rows =====


def test_a_new_project_with_a_pasted_tables_rows_waits_for_the_users_allow(
    live: Live, tmp_path: Path
) -> None:
    command("datasets_paste", name="orders", text=PASTED)
    with allowing(live, approve=False) as asked:
        with pytest.raises(CommandError, match="declined"):
            command("project_new", folder=str(tmp_path), name="shop", app=False)
    assert not (tmp_path / "shop").exists()
    assert asked[0]["action"] == "make the project" and asked[0]["dataset"] == "shop"
    assert f"  {tmp_path / 'shop'}\n" in asked[0]["detail"] and "  orders (2 rows)" in asked[0]["detail"]
    with allowing(live) as asked:
        made = command("project_new", folder=str(tmp_path), name="shop", app=False)
    assert len(asked) == 1 and made["folder"] == str(tmp_path / "shop")
    assert "AS pasted(" in (tmp_path / "shop" / "data.ipynb").read_text()  # the rows, as allowed
    # The user's own New project asks nothing.
    with allowing(live) as asked:
        live.user("POST", "/projects", {"folder": str(tmp_path), "name": "mine", "app": False})
    assert asked == [] and (tmp_path / "mine" / "data.ipynb").is_file()


def test_a_project_of_code_only_asks_nothing(live: Live, tmp_path: Path) -> None:
    csv = tmp_path / "orders.csv"
    csv.write_text("order_id,region,amount\n1,East,100\n2,West,250\n")
    command("datasets_load", name="orders", path=str(csv))
    with allowing(live) as asked:
        made = command("project_new", folder=str(tmp_path), name="shop", app=False)
        assert command("project_export_data", folder=made["folder"])["names"] == ["orders"]
    assert asked == []  # a file's load is code: data.ipynb reads the file again


def test_save_as_that_would_write_a_pasted_tables_rows_waits_for_the_users_allow(
    live: Live, tmp_path: Path
) -> None:
    command("datasets_paste", name="orders", text=PASTED)
    path = str(_notebook(tmp_path))
    app = command("streamlit_open")["app"]
    page = command("streamlit_page_add", app=app, name="Sales")["page"]
    command("streamlit_block_place", app=app, page=page, document=path, cell=4, w=12)
    command("streamlit_save", app=app, path=str(tmp_path / "sales"))
    with allowing(live, approve=False) as asked:
        with pytest.raises(CommandError, match="declined"):
            command("streamlit_save_as", app=app, path=str(tmp_path / "done.zip"))
    assert asked[0]["action"] == "zip the Streamlit app" and asked[0]["dataset"] == "sales.stapp.json"
    assert f"  {tmp_path / 'data.ipynb'}\n" in asked[0]["detail"] and "  orders (2 rows" in asked[0]["detail"]
    assert not (tmp_path / "data.ipynb").exists() and not (tmp_path / "done.zip").exists()
    with allowing(live) as asked:
        zipped = command("streamlit_save_as", app=app, path=str(tmp_path / "done.zip"))
    assert len(asked) == 1 and (tmp_path / "data.ipynb").is_file() and Path(zipped["path"]).is_file()
    # Now the project has its data.ipynb: Save as again writes no rows, and asks nothing.
    with allowing(live) as asked:
        command("streamlit_save_as", app=app, path=str(tmp_path / "again.zip"))
    assert asked == []
