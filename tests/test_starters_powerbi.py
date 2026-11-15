"""The starter pack's Power BI actions (docs/ideas.md, the starter pack), against the stand-in on this
computer (tests/powerbi_standin.py): each blade signs in through the workspace connection, never a copy
of its secret, and answers in plain words."""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from swissarmybench.adapters.blade_run import run_code
from swissarmybench.domain.blades import read_blade
from swissarmybench.server.blade_templates import POWERBI_VAULT
from tests import powerbi_standin as made_up

STARTERS = Path(__file__).resolve().parents[1] / "src" / "swissarmybench" / "starters"
SECRETS = {"tenant id": made_up.TENANT, "client id": made_up.CLIENT, "client secret": made_up.SECRET}


@pytest.fixture
def standin(monkeypatch: pytest.MonkeyPatch) -> Iterator[made_up.StandIn]:
    running = made_up.StandIn().start()
    for name, value in running.environment().items():
        monkeypatch.setenv(name, value)
    running.refresh_polls = 1
    yield running
    running.stop()


@pytest.fixture
def workspace(standin: made_up.StandIn) -> Any:
    """The Power BI workspace connection, as sab.connection("Finance") makes it."""
    conn, _ = run_code(
        POWERBI_VAULT.replace("my-workspace-id", made_up.WORKSPACE), "conn", SECRETS, "Finance"
    )
    return conn


def action(file: str, monkeypatch: pytest.MonkeyPatch | None = None, conn: Any = None) -> Any:
    """A starter's function, as sab.blade gives it; `conn` stands in for sab.connection("Finance")."""
    blade = read_blade((STARTERS / f"{file}.blade.py").read_text(encoding="utf-8"))
    made, names = run_code(blade["code"], blade["variable"], {}, blade["name"])
    if conn is not None:
        asked: list[Any] = []

        def connection(name: str) -> Any:
            asked.append(name)
            return conn

        names["sab"] = type("sab", (), {"connection": staticmethod(connection)})
        made.asked = asked
    return made


def test_a_refresh_starts_through_the_connections_own_sign_in(
    standin: made_up.StandIn, workspace: Any
) -> None:
    refresh = action("power_bi_refresh_dataset", conn=workspace)
    started = refresh("Sales model")
    assert started["dataset"] == "Sales model" and started["status"] == "started"
    assert started["request_id"].startswith("made-up-request-")
    assert refresh.asked == ["Finance"]  # the WORKSPACE setting names the connection
    sent = standin.actions()[-1]
    assert sent["method"] == "POST" and sent["path"].endswith(f"/datasets/{made_up.DATASET}/refreshes")
    assert sent["body"] == {"notifyOption": "NoNotification"}
    # The token is the connection's: one sign-in, carrying the app registration from its vault.
    assert len([r for r in standin.requests if r["what"] == "token"]) == 1
    assert all(made_up.SECRET not in str(r) for r in standin.actions())


def test_a_dataset_named_with_its_connection_needs_no_setting(workspace: Any) -> None:
    refresh = action("power_bi_refresh_dataset", conn=workspace)
    assert refresh("Team/Budget model")["dataset"] == "Budget model"
    assert refresh.asked == ["Team"]


def test_a_refusal_is_said_in_plain_words(workspace: Any) -> None:
    refresh = action("power_bi_refresh_dataset", conn=workspace)
    with pytest.raises(Exception, match=r"Power BI refused \(400\): Invalid NotifyOption"):
        refresh("Sales model", notify="MailOnFailure")
    with pytest.raises(Exception, match="notify is one of NoNotification"):
        refresh("Sales model", notify="Loudly")
    with pytest.raises(Exception, match=r"no dataset .Nothing.\. It has: Sales model, Budget model"):
        refresh("Nothing")


def test_the_status_and_the_history(standin: made_up.StandIn, workspace: Any) -> None:
    status = action("power_bi_refresh_status", conn=workspace)
    assert status("Sales model") == {"dataset": "Sales model", "status": "never"}
    action("power_bi_refresh_dataset", conn=workspace)("Sales model")
    assert status("Sales model")["status"] == "running"  # Power BI's Unknown
    latest = status("Sales model")
    assert latest["status"] == "completed" and latest["seconds"] is not None and latest["error"] is None
    history = action("power_bi_refresh_history", conn=workspace)("Sales model", top=5)
    assert isinstance(history, pd.DataFrame)
    assert list(history.columns) == ["status", "started", "ended", "seconds", "type", "error", "request_id"]
    assert history["status"].tolist() == ["completed"]


def test_refresh_and_wait_waits_and_says_why_one_failed(standin: made_up.StandIn, workspace: Any) -> None:
    wait = action("power_bi_refresh_and_wait", conn=workspace)
    done = wait("Sales model", every=0.01)
    assert done["status"] == "completed" and done["dataset"] == "Sales model"
    with pytest.raises(Exception, match="The refresh of Broken model failed: The dataset is being refreshed"):
        wait("Broken model", every=0.01)
    standin.refresh_polls = 10_000
    with pytest.raises(Exception, match=r"still running after 0\.05 seconds"):
        wait("Sales model", timeout=0.05, every=0.01)


def test_a_dataflow_refreshes_by_its_name(standin: made_up.StandIn, workspace: Any) -> None:
    assert action("power_bi_refresh_dataflow", conn=workspace)("Orders dataflow") == {
        "dataflow": "Orders dataflow",
        "status": "started",
    }
    history = action("power_bi_dataflow_history", conn=workspace)("Orders dataflow")
    assert history["status"].tolist() == ["inprogress"]
    with pytest.raises(Exception, match=r"no dataflow .Nothing.\. It has: Orders dataflow"):
        action("power_bi_refresh_dataflow", conn=workspace)("Nothing")


def test_the_workspace_lists(workspace: Any) -> None:
    datasets = action("power_bi_list_datasets", conn=workspace)()
    assert datasets["name"].tolist() == made_up.DATASET_NAMES
    reports = action("power_bi_list_reports", conn=workspace)()
    assert reports.to_dict("records")[0]["dataset_id"] == made_up.DATASET
    flows = action("power_bi_list_dataflows", conn=workspace)()
    assert flows["name"].tolist() == ["Orders dataflow"]


def test_parameters_are_read_and_changed_once_the_dataset_is_taken_over(workspace: Any) -> None:
    read = action("power_bi_read_parameters", conn=workspace)
    assert read("Sales model")[["name", "value"]].to_dict("records") == [
        {"name": "Region", "value": "North"},
        {"name": "Rows", "value": "1000"},
    ]
    update = action("power_bi_update_parameters", conn=workspace)
    with pytest.raises(Exception, match=r"refused \(403\): The user is not the owner"):
        update("Sales model", {"Region": "West"})
    assert action("power_bi_take_over_dataset", conn=workspace)("Sales model") == {
        "dataset": "Sales model",
        "status": "taken over",
    }
    assert update("Sales model", {"Region": "West", "Rows": 5000}) == {
        "dataset": "Sales model",
        "updated": ["Region", "Rows"],
    }
    assert read("Sales model")["value"].tolist() == ["West", "5000"]


def test_the_refresh_schedule(workspace: Any) -> None:
    assert action("power_bi_refresh_schedule", conn=workspace)("Sales model") == {
        "dataset": "Sales model",
        "enabled": True,
        "days": ["Monday", "Wednesday", "Friday"],
        "times": ["07:00", "13:30"],
        "time_zone": "UTC",
        "notify": "MailOnFailure",
    }


def test_a_connection_that_is_not_power_bi_is_refused_by_name(workspace: Any) -> None:
    refresh = action("power_bi_refresh_dataset", conn=object())
    with pytest.raises(Exception, match="Finance is not a Power BI workspace connection"):
        refresh("Sales model")


SIGNATURES = {
    "power_bi_refresh_dataset": "(dataset: str, notify: str = 'NoNotification', workspace: Any = None)",
    "power_bi_refresh_status": "(dataset: str, workspace: Any = None)",
    "power_bi_refresh_history": "(dataset: str, top: int = 20, workspace: Any = None)",
    "power_bi_refresh_and_wait": "(dataset: str, timeout: float = 1800, every: float = 15, "
    "notify: str = 'NoNotification', workspace: Any = None)",
    "power_bi_refresh_dataflow": "(dataflow: str, notify: str = 'NoNotification', workspace: Any = None)",
    "power_bi_dataflow_history": "(dataflow: str, workspace: Any = None)",
    "power_bi_list_datasets": "(workspace: Any = None)",
    "power_bi_list_reports": "(workspace: Any = None)",
    "power_bi_list_dataflows": "(workspace: Any = None)",
    "power_bi_read_parameters": "(dataset: str, workspace: Any = None)",
    "power_bi_update_parameters": "(dataset: str, values: dict[str, Any], workspace: Any = None)",
    "power_bi_take_over_dataset": "(dataset: str, workspace: Any = None)",
    "power_bi_refresh_schedule": "(dataset: str, workspace: Any = None)",
}


@pytest.mark.parametrize("file", sorted(SIGNATURES))
def test_each_action_is_a_function_as_its_first_lines_say(file: str) -> None:
    text = (STARTERS / f"{file}.blade.py").read_text(encoding="utf-8")
    made = action(file)
    shown = str(inspect.signature(made)).split(" ->")[0].replace("'", "")
    assert shown == SIGNATURES[file].replace("'", "")
    blade = read_blade(text)
    assert f'{made.__name__} = sab.blade("{blade["name"]}")' in text  # the docstring shows the use


def test_the_shared_part_is_the_same_in_every_power_bi_starter() -> None:
    def shared(text: str) -> str:
        start = text.index("# ===== the workspace and its sign-in")
        return text[start : text.index("# ===== this starter =====")]

    found = {shared(p.read_text(encoding="utf-8")) for p in STARTERS.glob("power_bi_*.blade.py")}
    assert len(found) == 1
