# ruff: noqa: F811
"""Script mode (the Workbench's modes, 2026-11-15): a script's run settings (arguments, and where each
variable comes from, never a value but a plain one's), Run as scheduled (a fresh process with no app)
and the run history (memory only). Made-up data only."""

from __future__ import annotations

from pathlib import Path

import pytest

from swissarmybench.domain import script_runs as rules
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


def _script(folder: Path) -> str:
    path = folder / "daily_sales.py"
    path.write_text(SCRIPT, encoding="utf-8")
    return str(path)


def test_the_agent_sets_the_run_settings(live: Live, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    assert command("workbench_script_settings", path=path)["arguments"] == "--region West"
