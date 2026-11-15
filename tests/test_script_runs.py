# ruff: noqa: F811
"""Script mode (the Workbench's modes, 2026-11-15): a script's run settings (arguments, and where each
variable comes from, never a value but a plain one's), Run as scheduled (a fresh process with no app)
and the run history (memory only). Made-up data only."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import script_runs as rules
from tests.conftest import AUTH, make_client
from tests.test_cli import Live, live  # noqa: F401 (the running server)
from tests.test_cli import run as command

SCRIPT = """\
import argparse
import os
import sys

import swissarmybench as sab

parser = argparse.ArgumentParser()
parser.add_argument("--region", default="all")
options = parser.parse_args()
orders = sab.read("Warehouse", "orders") if False else None
folder = os.environ["REPORT_FOLDER"]
host = os.getenv("WAREHOUSE_HOST", "none")
print(f"region {options.region} host {host} folder {folder}")
from swissarmybench.client import push_client
print("no app" if push_client._read_info() is None else "an app")
sys.exit(int(os.environ.get("EXIT_WITH", "0")))
"""


def test_settings_are_checked() -> None:
    settings = rules.check_settings(
        {
            "arguments": ' --region "East coast" ',
            "variables": [
                {"name": "WAREHOUSE_HOST", "from": "value", "value": "db1.example.test"},
                {
                    "name": "WAREHOUSE_PASSWORD",
                    "from": "vault",
                    "vault": "Team vault",
                    "secret": "warehouse-password",
                },
                {"name": "REPORT_FOLDER", "from": "env"},
            ],
        }
    )
    assert rules.split_arguments(settings.arguments) == ["--region", "East coast"]
    assert rules.source_words(settings.variables["WAREHOUSE_PASSWORD"]) == "Key vault · warehouse-password"
    assert rules.source_words(settings.variables["WAREHOUSE_HOST"]) == "Plain value"
    for bad, words in (
        ([], "Send"),
        ({"arguments": 'a "b'}, "cannot be read"),
        ({"arguments": "a\nb"}, "one line"),
        ({"variables": [{"name": "1X"}]}, "not an environment variable"),
        ({"variables": [{"name": "X", "from": "keyring"}]}, "comes"),
        ({"variables": [{"name": "API_TOKEN", "from": "value", "value": "x"}]}, "reads like a secret"),
        ({"variables": [{"name": "X", "from": "vault", "vault": "V"}]}, "Name the secret"),
        ({"variables": [{"name": "X"}, {"name": "X"}]}, "twice"),
    ):
        with pytest.raises(rules.ScriptRunError, match=words):
            rules.check_settings(bad)


def test_the_variables_a_script_needs() -> None:
    code = (
        'import os\nimport swissarmybench as sab\n\nrows = sab.read("Warehouse", "orders")\n'
        'fx = sab.blade("Daily FX rate")\nm = sab.dax("Finance/Sales model", "EVALUATE x")\n'
        'folder = os.environ["REPORT_FOLDER"]\n'
    )
    assert rules.named_connections(code) == ["Warehouse", "Daily FX rate", "Finance"]
    secrets = {"Warehouse": ["password"], "Daily FX rate": ["api_key"]}
    found = rules.needed(code, secrets.get)
    assert [(n.name, n.why, n.secret) for n in found] == [
        ("REPORT_FOLDER", "line 7", False),
        ("WAREHOUSE_PASSWORD", "Warehouse", True),
        ("DAILY_FX_RATE_API_KEY", "Daily FX rate", True),
    ]
    settings = rules.RunSettings("", {"EXTRA": {"from": "value", "value": "1"}})
    listed = rules.rows(settings, found)
    assert [r["name"] for r in listed] == [
        "REPORT_FOLDER",
        "WAREHOUSE_PASSWORD",
        "DAILY_FX_RATE_API_KEY",
        "EXTRA",
    ]
    assert listed[0]["words"] == "This computer" and listed[3]["why"] == "added"
    assert rules.plan(settings, found, lambda name: False).missing == ["REPORT_FOLDER"]
    planned = rules.plan(settings, found, lambda name: name == "REPORT_FOLDER")
    assert planned.values == {"EXTRA": "1"} and planned.missing == []


def test_a_logs_tail_and_the_command_line() -> None:
    assert rules.tail("a\r\nb\n") == ("a", "b")
    assert len(rules.tail("x\n" * 1000)) == rules.MAX_LOG_LINES
    assert rules.command_line("/home/me/daily sales.py", ["--date", "2026-11-14"]) == (
        "$ python 'daily sales.py' --date 2026-11-14"
    )


def _script(folder: Path) -> str:
    path = folder / "daily_sales.py"
    path.write_text(SCRIPT, encoding="utf-8")
    return str(path)


def _ok(response: object) -> dict[str, Any]:
    assert response.status_code == 200, response.text  # type: ignore[attr-defined]
    return dict(response.json())  # type: ignore[attr-defined]


def test_run_as_scheduled_with_no_app_and_the_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REPORT_FOLDER", str(tmp_path / "reports"))
    path = _script(tmp_path)
    with make_client(tmp_path) as client:
        settings = _ok(client.get("/workbench/scripts/settings", params={"path": path}, headers=AUTH))
        assert [(v["name"], v["words"]) for v in settings["variables"]] == [
            ("REPORT_FOLDER", "This computer"),
            ("WAREHOUSE_HOST", "This computer"),
            ("EXIT_WITH", "This computer"),
        ]
        body = {
            "path": path,
            "arguments": "--region East",
            "variables": [{"name": "WAREHOUSE_HOST", "from": "value", "value": "db1.example.test"}],
        }
        _ok(client.put("/workbench/scripts/settings", json=body, headers=AUTH))
        ran = _ok(
            client.post("/workbench/scripts/run", json={"path": path, "python": sys.executable}, headers=AUTH)
        )
        assert ran["exit_code"] == 0 and ran["how_words"] == "Run as scheduled"
        log = ran["log"]
        assert isinstance(log, list)
        assert log[0] == "$ python daily_sales.py --region East"
        assert f"region East host db1.example.test folder {tmp_path / 'reports'}" in log and "no app" in log
        assert {"name": "WAREHOUSE_HOST", "words": "Plain value"} in ran["sources"]
        # A Run file the window ran is kept beside it; a failing run says its exit code.
        _ok(
            client.post(
                "/workbench/scripts/history",
                json={"path": path, "seconds": 3.9, "exit_code": 1},
                headers=AUTH,
            )
        )
        runs = _ok(client.get("/workbench/scripts/history", params={"path": path}, headers=AUTH))["runs"]
        assert [(r["how"], r["exit_code"]) for r in runs] == [("file", 1), ("scheduled", 0)]
        assert (
            client.post(
                "/workbench/scripts/run", json={"path": str(tmp_path / "x.ipynb")}, headers=AUTH
            ).status_code
            == 400
        )
    # A new start: the settings are kept (no secret value in them), the history is not.
    with make_client(tmp_path) as client:
        kept = _ok(client.get("/workbench/scripts/settings", params={"path": path}, headers=AUTH))
        assert kept["arguments"] == "--region East"
        assert (
            _ok(client.get("/workbench/scripts/history", params={"path": path}, headers=AUTH))["runs"] == []
        )
    saved = (tmp_path / "state" / "run_settings.json").read_text()
    assert "db1.example.test" in saved and "password" not in saved.lower()


def test_a_failing_run_keeps_its_traceback(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REPORT_FOLDER", raising=False)
    path = _script(tmp_path)
    ran = _ok(
        client.post("/workbench/scripts/run", json={"path": path, "python": sys.executable}, headers=AUTH)
    )
    assert ran["exit_code"] == 1
    log = ran["log"]
    assert isinstance(log, list)
    assert log[0] == "REPORT_FOLDER is not set on this computer." and any("KeyError" in line for line in log)


def test_the_agent_sets_runs_and_reads_the_history(
    live: Live, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _script(tmp_path)
    done = command(
        "workbench_script_settings",
        path=path,
        set={
            "arguments": "--region West",
            "variables": [{"name": "REPORT_FOLDER", "from": "value", "value": "out"}],
        },
    )
    assert done["arguments"] == "--region West"
    ran = command("workbench_script_run", path=path, python=sys.executable)
    assert ran["exit_code"] == 0 and "region West host none folder out" in ran["log"]
    assert command("workbench_script_history", path=path)["runs"][0]["how"] == "scheduled"
