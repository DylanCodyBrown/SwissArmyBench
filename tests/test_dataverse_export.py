# ruff: noqa: F811
"""A Dataverse connection end to end (docs/ideas.md, Dataverse): a notebook's Python reads a table with
sab.read through the running app, then Export as one Python script runs the same reads in a fresh
Python, signed in by a managed identity as in an Azure Function. Against the stand-in on this computer
(tests/dataverse_standin.py); made-up data only."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest

import swissarmybench as sab
from swissarmybench.domain import dataverse
from swissarmybench.server.blade_templates import BY_ID
from tests import dataverse_standin as made_up
from tests.test_cli import Live, live  # noqa: F401 (the running server)
from tests.test_script_export import fresh_python, install_from_this_machine, run_script


@pytest.fixture
def standin(monkeypatch: pytest.MonkeyPatch) -> Iterator[made_up.StandIn]:
    running = made_up.StandIn().start()
    for name, value in running.environment().items():
        monkeypatch.setenv(name, value)
    yield running
    running.stop()


CELL = """import os

import swissarmybench as sab

accounts = sab.read("Sales CRM", "account")
won = sab.connection("Sales CRM").read("opportunity", filter="statecode eq 1", limit=50)
accounts.to_csv(os.environ["REPORT_FOLDER"] + "/accounts.csv", index=False)
won.to_csv(os.environ["REPORT_FOLDER"] + "/won.csv", index=False)
"""


def test_a_notebook_reads_a_table_then_its_export_runs_by_managed_identity(
    live: Live, standin: made_up.StandIn, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code = dataverse.MANAGED.replace("https://your-org.crm.dynamics.com", standin.url)
    template = BY_ID["dataverse"].to_json()
    body = {"name": "Sales CRM", "kind": "sql", "template": "dataverse", "dialect": "dataverse"}
    live.user(
        "POST", "/connections", body | {"code": code, "variable": "conn", "catalog": template["catalog"]}
    )
    # In the notebook's Python: the connection's own read, through the Web API.
    accounts = sab.read("Sales CRM", "account")
    assert isinstance(accounts, pd.DataFrame) and len(accounts) == 12
    assert accounts.loc[0, "industrycode"] == "Consulting" and accounts.loc[0, "statecode"] == "Active"
    assert len(sab.read("Sales CRM", "opportunity", limit=7)) == 7
    conn = sab.connection("Sales CRM")
    assert [t["table"] for t in conn.tables()] == ["account", "contact", "opportunity", "systemuser"]
    # Export as one Python script: the connection written out, its sign-in the managed identity.
    script = tmp_path / "sales_automation.py"
    cells = [{"kind": "code", "source": CELL, "number": 1}]
    done = live.user(
        "POST", "/workbench/export-script", {"kind": "notebook", "cells": cells, "to": str(script)}
    )
    assert done["path"] == str(script) and not done["problems"] and not done["lint"], done
    text = script.read_text(encoding="utf-8")
    assert "def connect_sales_crm():" in text and "class Dataverse:" in text
    assert (
        "accounts = read_table('Sales CRM', 'account')" in text
        or 'read_table("Sales CRM", "account")' in text
    ), [line for line in text.splitlines() if "read_table(" in line]
    # No SQL runs on it: its SQL endpoint's pyodbc is not a requirement; the managed identity needs none.
    assert "pyodbc" not in json.dumps(done["requirements"])
    assert not any("azure" in r for r in done["requirements"])
    assert made_up.TOKEN not in text and made_up.IDENTITY_HEADER not in text
    python = fresh_python(tmp_path / "venv")
    install_from_this_machine(python, done["requirements"])
    env = standin.environment() | {"REPORT_FOLDER": str(tmp_path)}
    ran = run_script(python, script, env=env)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    with (tmp_path / "accounts.csv").open(encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 12 and rows[0]["name"] == "Bluefin Outfitters" and rows[0]["statecode"] == "Active"
    with (tmp_path / "won.csv").open(encoding="utf-8") as file:
        won = list(csv.DictReader(file))
    assert len(won) == 50 and {r["statecode"] for r in won} == {"Won"}
    signed = [r for r in standin.requests if r["what"] == "managed identity"]
    assert signed and signed[-1]["query"]["resource"] == standin.url  # the Function's own identity
    assert made_up.TOKEN not in ran.stdout + ran.stderr
    # Outside Azure (no managed identity): said plainly, with a code that is not 0.
    nowhere = {"IDENTITY_ENDPOINT": "", "IDENTITY_HEADER": "", "REPORT_FOLDER": str(tmp_path)}
    outside = run_script(python, script, env=nowhere)
    assert outside.returncode != 0 and "The managed identity's sign-in" in outside.stdout + outside.stderr
