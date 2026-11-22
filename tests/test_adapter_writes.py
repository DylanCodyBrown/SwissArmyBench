"""Writes through the adapter for Dataverse, SharePoint lists and the lakes (Plans/adapter.plan.md, after
phase 2: "Writes next ... the Write starters' code moves in"), each in every mode, truncate included, against
the stand-ins on this computer (tests/dataverse_standin.py, tests/lake_standins.py). A dry run is the
adapter's planned(): counted by reads, nothing written. No real tenant, environment or site is reached;
every value is made up."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest

from swissarmybench.adapters import sab_adapter as sab
from swissarmybench.adapters.sab_adapter import Counts
from swissarmybench.domain import dataverse
from tests import dataverse_standin as crm_standin
from tests import lake_standins as made_up
from tests.fake_keyring import memory_keyring
from tests.test_lakes import connected, datalake_code, local_lake, sharepoint_code


@pytest.fixture(autouse=True)
def keyring() -> Iterator[None]:
    with memory_keyring():
        yield


# ===== Dataverse: the Web API's $batch change sets =====


@pytest.fixture
def crm(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[crm_standin.StandIn, Any]]:
    from swissarmybench.adapters.blade_run import run_code

    running = crm_standin.StandIn().start()
    for name, value in running.environment().items():
        monkeypatch.setenv(name, value)
    code = (
        dataverse.APP.replace("https://your-org.crm.dynamics.com", running.url)
        .replace("my-tenant-id", crm_standin.TENANT)
        .replace("my-client-id", crm_standin.CLIENT)
    )
    conn, _ = run_code(code, "conn", {"client secret": crm_standin.SECRET}, "Sales CRM")
    yield running, conn
    running.stop()


def accounts(standin: crm_standin.StandIn) -> dict[str, dict[str, Any]]:
    return {str(r["accountnumber"]): r for r in standin.rows["account"]}


def test_dataverse_inserts_with_choice_labels_and_goes_again_when_throttled(crm: Any) -> None:
    standin, conn = crm
    source = sab.source_from(conn, name="Sales CRM")
    assert isinstance(source, sab.OData)
    rows = pa.table({"name": ["Oak Hollow Tea", "Pine Ridge Bikes"], "accountnumber": ["AC-2001", "AC-2002"],
                     "industrycode": ["Retail", "Consulting"]})  # fmt: skip
    assert sab.planned(source, "account", rows) == Counts(inserted=2) and standin.batches == []
    standin.throttle = 1  # the first $batch is asked to wait: it goes again
    assert sab.write(source, "account", rows) == Counts(inserted=2)
    made = accounts(standin)
    assert made["AC-2001"]["industrycode"] == 19 and made["AC-2002"]["industrycode"] == 7
    assert [b["applied"] for b in standin.batches] == [True]
    with pytest.raises(sab.AdapterError, match="industrycode has no choice 'Bakery': its choices are"):
        sab.write(source, "account", rows.set_column(2, "industrycode", pa.array(["Bakery", "Retail"])))


def test_dataverse_merge_update_delete_by_an_alternate_key(crm: Any) -> None:
    standin, conn = crm
    source = sab.source_from(conn, name="Sales CRM")
    key = ("accountnumber",)
    rows = pa.table(
        {"accountnumber": ["AC-1001", "AC-3001"], "name": ["Bluefin Outfitters Ltd", "Cedar Lane"]}
    )
    assert sab.planned(source, "account", rows, key, "merge") == Counts(inserted=1, updated=1)
    assert sab.write(source, "account", rows, key, "merge") == Counts(inserted=1, updated=1)
    assert accounts(standin)["AC-1001"]["name"] == "Bluefin Outfitters Ltd" and "AC-3001" in accounts(standin)
    missing = pa.table({"accountnumber": ["AC-9999"], "name": ["x"]})
    assert sab.planned(source, "account", missing, key, "update") == Counts(updated=0)
    with pytest.raises(sab.AdapterError, match="1 keys are not records of account: AC-9999"):
        sab.write(source, "account", missing, key, "update")
    renamed = rows.set_column(1, "name", pa.array(["Bluefin", "Cedar"]))
    assert sab.write(source, "account", renamed, key, "update") == Counts(updated=2)
    assert accounts(standin)["AC-3001"]["name"] == "Cedar"
    gone = pa.table({"accountnumber": ["AC-3001", "AC-9999"]})
    assert sab.planned(source, "account", gone, key, "delete") == Counts(deleted=1)
    assert sab.write(source, "account", gone, key, "delete") == Counts(deleted=1)
    assert "AC-3001" not in accounts(standin)
    with pytest.raises(sab.AdapterError, match="one key column"):
        sab.write(source, "account", rows, ("accountnumber", "name"), "merge")


def test_dataverse_truncate_clears_the_table_then_makes_the_rows(crm: Any) -> None:
    standin, conn = crm
    source = sab.source_from(conn, name="Sales CRM")
    before = len(standin.rows["account"])
    fresh = pa.table({"name": ["Larch Gate Farm"], "accountnumber": ["AC-5001"]})
    assert sab.planned(source, "account", fresh, mode="truncate") == Counts(inserted=1, deleted=before)
    assert sab.write(source, "account", fresh, mode="truncate") == Counts(inserted=1, deleted=before)
    assert list(accounts(standin)) == ["AC-5001"]
    assert sab.write(source, "account", mode="truncate") == Counts(deleted=1)
    assert standin.rows["account"] == []


def test_dataverse_a_refused_change_set_is_rolled_back_and_named(crm: Any) -> None:
    standin, conn = crm
    source = sab.OData(conn, "Sales CRM", batch_size=2)
    rows = pa.table({"name": ["A", "B", "C"], "accountnumber": ["AC-4001", "AC-4002", "AC-4003"],
                     "numberofemployees": [1, 2, 3], "industrycode": [1, 1, 999]})  # fmt: skip
    with pytest.raises(sab.AdapterError) as refused:
        sab.write(source, "account", rows)
    said = str(refused.value)
    assert said.startswith(
        "Batch 2 (rows 3 to 3) was refused and rolled back: Dataverse refused (400): 999 is not a valid value"
    )
    assert "the 2 rows before it were written" in said
    assert [b["applied"] for b in standin.batches] == [True, False]
    assert "AC-4003" not in accounts(standin) and "AC-4002" in accounts(standin)


# ===== SharePoint lists: Graph's $batch, retried on 429 =====


@pytest.fixture
def standin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[made_up.StandIn]:
    made_up.make_lake(tmp_path / "storage")
    running = made_up.StandIn(tmp_path / "storage").start()
    for name, value in running.environment().items():
        monkeypatch.setenv(name, value)
    yield running
    running.stop()


def test_a_sharepoint_list_takes_every_mode(standin: made_up.StandIn) -> None:
    conn = connected(sharepoint_code(), {"password": made_up.PASSWORD})
    source = sab.source_from(conn, name="Team")
    assert isinstance(source, sab.Rows)
    standin.refuse_once.add("all")  # the first answer to each request: 429, Retry-After 0
    made = pa.table({"Title": [f"Made-up new task {n}" for n in range(25)], "Status": ["Open"] * 25})
    assert sab.write(source, "Tasks", made) == Counts(inserted=25)
    assert len(standin.tasks) == 35
    change = pa.table({"Title": ["Made-up task 02", "Made-up brand new"], "Status": ["Done", "Waiting"]})
    assert sab.planned(source, "Tasks", change, ("Title",), "merge") == Counts(inserted=1, updated=1)
    assert sab.write(source, "Tasks", change, ("Title",), "merge") == Counts(inserted=1, updated=1)
    assert standin.tasks[2]["Status"] == "Done" and len(standin.tasks) == 36
    one = pa.table({"Title": ["Made-up task 03"], "Status": ["Waiting"]})
    assert sab.write(source, "Tasks", one, ("Title",), "update") == Counts(updated=1)
    gone = pa.table({"Title": ["Made-up task 03", "nobody's"]})
    assert sab.write(source, "Tasks", gone, ("Title",), "delete") == Counts(deleted=1)
    assert 3 not in standin.tasks
    fresh = pa.table({"Title": ["Made-up only task"], "Status": ["Open"]})
    assert sab.write(source, "Tasks", fresh, mode="truncate") == Counts(inserted=1, deleted=35)
    assert [t["Title"] for t in standin.tasks.values()] == ["Made-up only task"]


# ===== lakes: one file put in its place, or a Delta table =====


def test_a_lake_file_is_written_whole_or_added_to(standin: made_up.StandIn) -> None:
    conn = connected(datalake_code(), {"client secret": made_up.SECRET})
    source = sab.source_from(conn, name="Sales Lake")
    first = pa.table({"region": ["North", "South"], "target": [10.5, 20.0]})
    assert sab.write(source, "exports/targets.parquet", first, mode="truncate") == Counts(inserted=2)
    assert conn.rows("exports/targets")[1] == 2
    more = pa.table({"region": ["West"], "target": [5.0]})
    assert sab.write(source, "exports/targets.parquet", more) == Counts(inserted=1)
    assert sorted(conn.rows("exports/targets")[0].column("region").to_pylist()) == ["North", "South", "West"]
    assert sab.write(source, "exports/targets", first, mode="truncate") == Counts(inserted=2, deleted=3)
    with pytest.raises(sab.AdapterError, match="one parquet file: it is written whole"):
        sab.write(source, "exports/targets", first, ("region",), "merge")


LAKES_SITE = os.environ.get("SAB_DELTALAKE_PATH", "")


def test_a_delta_table_takes_every_mode(standin: made_up.StandIn, monkeypatch: pytest.MonkeyPatch) -> None:
    if LAKES_SITE and Path(LAKES_SITE).is_dir():
        monkeypatch.syspath_prepend(LAKES_SITE)
    pytest.importorskip("deltalake")
    conn = local_lake(standin)
    source = sab.source_from(conn, name="Lake")
    key = ("order_id",)
    incoming = pa.table({"order_id": [5, 6], "amount": [99.0, 7.5], "region": ["West", "West"]})
    assert sab.planned(source, "orders", incoming, key, "merge") == Counts(inserted=1, updated=1)
    assert sab.write(source, "orders", incoming, key, "merge") == Counts(inserted=1, updated=1)
    only = pa.table({"order_id": [1, 77], "amount": [1.0, 2.0], "region": ["North", "East"]})
    assert sab.write(source, "orders", only, key, "update") == Counts(updated=1)
    assert sab.write(source, "orders", pa.table({"order_id": [6]}), key, "delete") == Counts(deleted=1)
    assert sab.write(source, "orders", incoming.slice(1), mode="insert") == Counts(inserted=1)
    assert sab.write(source, "orders", incoming.slice(0, 1), mode="truncate") == Counts(inserted=1, deleted=6)
    assert conn.rows("orders")[1] == 1
