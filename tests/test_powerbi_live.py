"""Edit in Power BI Desktop (domain/live_link.py, services/live_link.py): the running Desktops found, the open
model's metadata, a dry run and Apply, and E's Local source, against tests/powerbi_live_fake.py at the
TomModel seam.
Made-up names only."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from swissarmybench_powerbi.domain import live_link as rules
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


def test_a_port_file_and_a_command_line_are_read() -> None:
    assert rules.port_of("51234".encode("utf-16-le")) == 51234
    assert rules.port_of(b"\xff\xfe" + "6000".encode("utf-16-le")) == 6000
    assert rules.port_of(b"not a port") is None
    line = r'"C:\Program Files\Microsoft Power BI Desktop\bin\PBIDesktop.exe" "C:\Reports\Sales model.pbix"'
    assert rules.file_of(line) == r"C:\Reports\Sales model.pbix"
    found = desktop.instances()
    assert rules.status_words(found, "Sales model.pbix")["words"] == "Live: Sales model.pbix"
    assert (
        rules.status_words([], "Sales model.pbix")["words"]
        == "Not open: open Sales model.pbix in Power BI Desktop"
    )
    assert rules.status_words([], "x.pbix", windows=False)["words"] == rules.WINDOWS_ONLY


def test_what_an_external_tool_may_not_change_points_to_the_export() -> None:
    with pytest.raises(rules.LiveError, match="Processing"):
        rules.change_from({"kind": "refresh"})
    with pytest.raises(rules.LiveError, match="export a Power BI Project"):
        rules.change_from({"kind": "partition"})
    with pytest.raises(rules.LiveError, match="Power BI's own date table"):
        rules.change_from({"kind": "calculated_column", "table": "LocalDateTable_0001", "name": "x"})


def test_the_dry_run_says_each_change_and_whether_it_can_go() -> None:
    model = desktop.FakeDesktop().model
    changes = rules.ours(
        [fake.MODEL.relationships[0].to_json(), fake.MODEL.relationships[1].to_json()],
        [m.to_json() for m in fake.MODEL.measures],
        model,
    )
    words = [c.words() for c in changes]
    assert words == [
        "Add the relationship Sales[ProductKey] to Product[ProductKey] (inactive)",
        "Add the measure Sales[Total Sales]",
    ]  # the relationship already there is left out
    checked = rules.check(model, [*changes, rules.Change("measure_delete", "Sales", "Nope")])
    assert [c["ok"] for c in checked] == [True, True, False]
    assert checked[2]["why"] == "the open model has no such measure"


def test_edit_in_power_bi_desktop_and_the_local_source(tmp_path: Path) -> None:
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

        status = ok(client.get("/powerbi/live?asked=1", headers=AGENT))
        assert status["live"] and status["words"] == "Live: Sales model.pbix"
        assert status["note"].startswith("Only works on your machine: Power BI Desktop runs only here.")
        model = ok(client.get("/powerbi/live/model", headers=AGENT))
        assert [t["name"] for t in model["tables"]] == [
            "Sales",
            "Customer",
            "Product",
        ]  # no rows, no date table

        planned = ok(client.post("/powerbi/live/plan", json={}, headers=AGENT))["changes"]
        assert [c["words"] for c in planned] == [
            "Add the relationship Sales[ProductKey] to Product[ProductKey] (inactive)",
            "Add the measure Sales[Total Sales]",
        ]
        assert not running.applied  # a dry run changes nothing
        refused = client.post("/powerbi/live/plan", json={"changes": [{"kind": "refresh"}]}, headers=AGENT)
        assert refused.status_code == 400 and "export a Power BI Project" in refused.text
        done = ok(client.post("/powerbi/live/apply", json={}, headers=AUTH))
        assert (
            len(done["applied"]) == 2
            and running.model.measures[("Sales", "Total Sales")] == "SUM(Sales[Amount])"
        )

        # E: Local reads DAX over the live link; the In Power BI grids read again.
        switched = ok(client.put("/powerbi/source", json={"source": "local"}, headers=AGENT))
        assert switched["effective"] == "local" and switched["words"] == "Sales model · Local"
        assert "EVALUATE 'Customer'" in running.queries
