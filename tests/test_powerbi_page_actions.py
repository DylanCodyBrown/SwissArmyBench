"""The Power BI page's actions complete (the owner's F and D): Edit in Power BI Desktop answers an on-page dry
run (each change listed, Apply, Cancel; the agent's Apply waits for the user's Allow), and Use another
report's pages asks the page to open the report dialog right there. A running Power BI Desktop is stood in for
(tests/powerbi_live_fake.py), pbixray too. Made-up data only."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests import powerbi_live_fake as desktop
from tests import powerbi_pbix_fake as fake
from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring


@pytest.fixture(autouse=True)
def extension_on(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    with memory_keyring():
        yield


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def test_edit_shows_its_dry_run_on_the_page_and_pages_opens_the_report_dialog(tmp_path: Path) -> None:
    pbix = fake.fake_pbix(tmp_path)
    with make_client(tmp_path) as client:
        ctx: Any = client.app.state.ctx  # type: ignore[attr-defined]
        ctx.extension["powerbi"].project.reader = fake.reader
        running = desktop.FakeDesktop()
        live = ctx.extension["powerbi"].live
        live._discover, live._opener, live._windows = desktop.instances, lambda port: running, lambda: True
        live.stop()
        body = {"path": str(pbix), "folder": str(tmp_path / "projects"), "dataset": {"none": True}}
        ok(client.post("/powerbi/import", json=body, headers=AUTH))
        ok(client.get("/powerbi/live?asked=1", headers=AGENT))

        panel = ok(client.post("/powerbi/panel", json={"action": "edit"}, headers=AUTH))
        review = panel["review"]
        assert [i["text"] for i in review["items"]] == [
            "Add the relationship Sales[ProductKey] to Product[ProductKey] (inactive)",
            "Add the measure Sales[Total Sales]",
        ]
        assert review["apply"] == {"id": "edit:apply", "label": "Apply", "disabled": False}
        assert not running.applied  # the dry run changes nothing
        assert ok(client.get("/powerbi/panel", headers=AUTH))["review"] == review  # it stays until done

        # The agent's Apply waits for the user's Allow: declined, nothing changes.
        answer: dict[str, Any] = {}
        thread = threading.Thread(
            target=lambda: answer.update(
                r=client.post("/powerbi/panel", json={"action": "edit:apply"}, headers=AGENT)
            )
        )
        thread.start()
        pending = []
        for _ in range(100):
            pending = ok(client.get("/agent/approvals", headers=AUTH))["pending"]
            if pending:
                break
            threading.Event().wait(0.05)
        assert pending and "Total Sales" in pending[0]["detail"]
        ok(client.post(f"/agent/approvals/{pending[0]['id']}", json={"approve": False}, headers=AUTH))
        thread.join(10)
        said = answer["r"].json()
        assert "declined" in said["lines"][0]["text"] and not running.applied

        done = ok(client.post("/powerbi/panel", json={"action": "edit:apply"}, headers=AUTH))
        assert done["lines"][0]["text"] == "Applied 2 changes to the open model in Power BI Desktop."
        assert done["review"] is None and len(running.applied) == 2

        ok(client.post("/powerbi/panel", json={"action": "edit"}, headers=AUTH))
        assert (
            ok(client.post("/powerbi/panel", json={"action": "edit:cancel"}, headers=AUTH))["review"] is None
        )

        opened = ok(client.post("/powerbi/panel", json={"action": "pages"}, headers=AUTH))
        assert opened["open"] == {
            "plugin": "powerbi_report_pages",
            "context": ["Sales", "Customer", "Product"],
        }
        assert ok(client.get("/powerbi/panel", headers=AUTH))["open"] is None  # once, not on every draw
