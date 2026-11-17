"""A project folder's rules (domain/sab_files.py) and its files (adapters/sab_files.py): .sab/project.json's
round trip (stable: sorted, no timestamp), unknown fields kept, a newer format read-only, a type-only file,
the old .sab's zip safety for the import (paths outside the project, links, sizes), what is the project's
own, .sab/ written only when its bytes change, the scaffold's Git files. Made-up data only."""

from __future__ import annotations

import json
import stat
import zipfile
from dataclasses import replace
from pathlib import Path

import pyarrow as pa
import pytest

from swissarmybench.adapters.sab_files import RecentProjects, SabArchive
from swissarmybench.domain import sab_files as rules
from swissarmybench.domain.sab_files import EntryInfo, GridEntry, Manifest, SabError, Source, TableEntry
from swissarmybench.domain.table_cells import Origin

STEP = {
    "id": "a1",
    "kind": "filter",
    "params": {"column": "region", "op": "eq", "value": "North"},
    "enabled": True,
}


def _manifest() -> Manifest:
    return Manifest(
        name="sales",
        app_version="0.0.7",
        saved="2026-11-16T10:00:00+00:00",
        tables=(
            TableEntry(
                "orders",
                Source("file", path="orders.csv", absolute="/data/orders.csv"),
                (GridEntry((STEP,), {"case_sensitive": False}),),
            ),
            TableEntry("customers", Source("connection", connection="Warehouse", table="customers")),
            TableEntry("regions", Source("cell", notebook="data.ipynb")),
            TableEntry("pasted_1", Source("pasted", rows=True), rows_file="data/pasted_1.parquet"),
            TableEntry("totals", Source("query", sql="SELECT 1 AS n")),
        ),
        tabs={"order": ["orders", "customers"], "front": "orders"},
        workbench={"documents": ["data.ipynb"]},
        visualizations=rules.VISUALIZATIONS,
        model=rules.MODEL,
    )


def test_project_json_round_trips() -> None:
    manifest = _manifest()
    text = rules.write_manifest(manifest)
    raw = json.loads(text)
    assert raw["swissarmybench"] == "project" and raw["format"] == rules.FORMAT
    assert raw["app_version"] == "0.0.7" and "name" not in raw and "saved" not in raw
    assert list(raw) == sorted(raw)  # sorted keys: the same project is the same bytes
    again, read_only = rules.read_manifest(text)
    assert read_only is None
    assert again == replace(manifest, name="Project", saved="")
    assert rules.write_manifest(again) == text
    assert [t.source.label() for t in again.tables] == [
        "orders.csv",
        "Warehouse · customers",
        "data.ipynb",
        "Pasted",
        "Query",
    ]


def test_fields_this_version_does_not_know_are_kept_when_saved_again() -> None:
    raw = json.loads(rules.write_manifest(_manifest()))
    raw["thumbnail"] = {"page": 2}
    raw["tables"][0]["colour"] = "teal"
    raw["tables"][0]["source"]["checksum"] = "abc"
    raw["tables"][0]["grids"][0]["frozen_columns"] = 2
    read, _ = rules.read_manifest(json.dumps(raw))
    # A save makes the tables again from what is open: what the earlier file knew goes back in.
    fresh = TableEntry("orders", Source("file", path="orders.csv"), (GridEntry((STEP,)),))
    table = rules.carried(read, "orders", fresh)
    written = json.loads(rules.write_manifest(Manifest("sales", (table,), extra=read.extra)))
    assert written["thumbnail"] == {"page": 2}
    assert written["tables"][0]["colour"] == "teal"
    assert written["tables"][0]["source"]["checksum"] == "abc"
    # A grid's own unknown fields survive a read and a write of the same entry.
    again, _ = rules.read_manifest(json.dumps(raw))
    assert again.tables[0].grids[0].to_json()["frozen_columns"] == 2


def test_a_file_saved_before_the_sandbox_was_renamed_reads_its_cards() -> None:
    """The Sandbox became Visualizations (2026-11-16): an older .sab's "sandbox" entry is read for one
    release, and written again under the new name."""
    raw = json.loads(rules.write_manifest(_manifest()))
    del raw["visualizations"]
    raw["sandbox"] = rules.OLD_SANDBOX
    read, _ = rules.read_manifest(json.dumps(raw))
    assert read.visualizations == rules.OLD_SANDBOX
    written = json.loads(rules.write_manifest(read))
    assert "sandbox" not in written and written["visualizations"] == rules.OLD_SANDBOX


def test_a_newer_format_opens_read_only_with_a_plain_message() -> None:
    raw = json.loads(rules.write_manifest(_manifest())) | {"format": rules.FORMAT + 1, "app_version": "9.0"}
    manifest, read_only = rules.read_manifest(json.dumps(raw))
    assert manifest.tables[0].name == "orders"
    assert read_only is not None and "9.0" in read_only and "read-only" in read_only
    for bad in ("{}", "[]", "not json", json.dumps({"swissarmybench": "tang", "format": 1})):
        with pytest.raises(SabError):
            rules.read_manifest(bad)


@pytest.mark.parametrize(
    "name",
    [
        "../evil.py",
        "a/../../evil.py",
        "/etc/passwd",
        "C:/Windows/evil.py",
        "C:evil",
        "a\\..\\b",
        "a//b",
        "./a",
        "bad\x00name",
    ],
)
def test_an_entry_outside_the_project_is_refused(name: str) -> None:
    with pytest.raises(SabError):
        rules.check_entry(name)


def test_links_sizes_and_counts_are_refused_before_anything_is_written() -> None:
    fine = [EntryInfo("project.json", 10, False, False), EntryInfo("data.ipynb", 10, False, False)]
    rules.check_entries(fine, 10, 1000, 1000)
    with pytest.raises(SabError, match="link"):
        rules.check_entries([*fine, EntryInfo("evil", 10, True, False)], 10, 1000, 1000)
    with pytest.raises(SabError, match="entries"):
        rules.check_entries(fine * 6, 10, 1000, 1000)
    with pytest.raises(SabError, match="unpacks to"):
        rules.check_entries([*fine, EntryInfo("big.py", 990, False, False)], 10, 1000, 1000)
    with pytest.raises(SabError, match="twice"):
        rules.check_entries([*fine, EntryInfo("DATA.ipynb", 1, False, False)], 10, 1000, 1000)
    with pytest.raises(SabError, match=r"no project\.json"):
        rules.check_entries([EntryInfo("data.ipynb", 1, False, False)], 10, 1000, 1000)


def test_only_the_projects_code_and_text_go_in_never_a_data_file() -> None:
    assert (
        rules.packed("data.ipynb") and rules.packed("pages/1_Sales.py") and rules.packed("sales.stapp.json")
    )
    assert rules.packed("README.md") and rules.packed(".streamlit/config.toml") and rules.packed("logo.png")
    for left_out in (
        "orders.csv",
        "book.xlsx",
        "rows.parquet",
        "export.json",
        ".venv/lib/x.py",
        "__pycache__/data.cpython-312.pyc",
        ".ipynb_checkpoints/data-checkpoint.ipynb",
        ".data.ipynb.saving",
        ".git/config",
    ):
        assert not rules.packed(left_out), left_out


def test_a_file_source_is_kept_relative_when_it_sits_beside_the_project() -> None:
    near = rules.source_of(
        Origin("file", path="/work/sales/data/orders.csv"), "/work/sales", None, None, None, True, False
    )
    assert near.path == "data/orders.csv" and near.absolute == "/work/sales/data/orders.csv"
    far = rules.source_of(
        Origin("file", path="/elsewhere/orders.csv"), "/work/sales", None, None, None, True, False
    )
    assert far.path == "/elsewhere/orders.csv"
    # Opened from another folder: beside the .sab first, then where it was.
    assert rules.candidates(near, "/moved/sales") == [
        "/moved/sales/data/orders.csv",
        "/work/sales/data/orders.csv",
    ]
    windows = rules.source_of(
        Origin("file", path="C:\\Users\\Ann\\sales\\orders.csv"),
        "C:\\Users\\Ann\\sales",
        None,
        None,
        None,
        True,
        False,
    )
    assert windows.path == "orders.csv"


def test_each_origin_becomes_a_source_and_a_connection_is_only_named() -> None:
    made = rules.source_of(
        Origin("connection", connection="Warehouse", sql="SELECT * FROM orders"),
        None,
        None,
        None,
        ("", "sales", "orders"),
        False,
        False,
    )
    assert made.to_json() == {
        "kind": "connection",
        "connection": "Warehouse",
        "database": "",
        "schema": "sales",
        "table": "orders",
        "whole": False,
    }
    dax = rules.source_of(
        Origin("connection", connection="Finance/Sales model", sql="EVALUATE 'Date'", dax=True),
        None,
        None,
        None,
        ("", "Sales model", "Date"),
        True,
        False,
    )
    assert dax.connection == "Finance" and dax.sql == "EVALUATE 'Date'" and dax.dax
    cell = rules.source_of(
        Origin("python", kernel="k1"), None, "/work/p/sales", "/work/p/sales/data.ipynb", None, True, False
    )
    assert cell.to_json() == {"kind": "cell", "notebook": "data.ipynb"}
    pushed = rules.source_of(Origin("python"), None, "/work/p/sales", None, None, True, True)
    assert pushed.to_json() == {"kind": "pasted", "rows": True} and pushed.needs_rows
    assert (
        rules.source_of(Origin("query", sql="SELECT 1"), None, None, None, None, True, False).kind == "query"
    )


def test_a_table_that_did_not_come_back_has_one_click_that_fixes_it() -> None:
    missing = rules.fix_for("customers", Source("connection", connection="Warehouse"), "no_connection")
    assert missing["fix"] == {
        "kind": "add_connection",
        "label": "Add connection Warehouse",
        "connection": "Warehouse",
    }
    moved = rules.fix_for("orders", Source("file", path="data/orders.csv"), "no_file")
    assert moved["fix"]["label"] == "Find orders.csv" and moved["fix"]["suffix"] == ".csv"
    assert (
        rules.fix_for("r", Source("cell", notebook="data.ipynb"), "not_run")["fix"]["label"]
        == "Open data.ipynb"
    )
    assert rules.fix_for("p", Source("pasted"), "no_rows")["fix"]["kind"] == "remove"
    assert rules.fix_for("p", Source("pasted"), "The server said no")["fix"]["label"] == "Try again"


def test_a_type_only_project_json_is_a_project_with_no_tables_yet() -> None:
    manifest, read_only = rules.read_manifest(json.dumps({"type": "accounting"}), folder=True)
    assert read_only is None and manifest.tables == () and manifest.autosave is True
    assert json.loads(rules.write_manifest(manifest))["type"] == "accounting"
    with pytest.raises(SabError):
        rules.read_manifest(json.dumps({"type": "accounting"}))  # an old .sab's must say it is one


def test_an_old_sabs_entries_go_to_their_places_in_the_folder() -> None:
    old = Manifest(
        "sales",
        tables=(TableEntry("pasted_1", Source("pasted", rows=True), rows_file="data/pasted_1.parquet"),),
        visualizations=rules.VISUALIZATIONS,
        model=rules.MODEL,
    )
    places = {e: rules.old_entry_place(e, old) for e in (
        "project.json", rules.VISUALIZATIONS, rules.MODEL, "data/pasted_1.parquet",
        ".sab/dashboards/q1.json", ".sab/blades/shop.json", "data.ipynb", "pages/1_Sales.py",
    )}  # fmt: skip
    assert places == {
        "project.json": "",
        rules.VISUALIZATIONS: ".sab/visualizations.json",
        rules.MODEL: ".sab/model.json",
        "data/pasted_1.parquet": ".sab/data/pasted_1.parquet",
        ".sab/dashboards/q1.json": ".sab/visualizations/q1.json",
        ".sab/blades/shop.json": None,
        "data.ipynb": None,
        "pages/1_Sales.py": None,
    }
    found = {
        rules.VISUALIZATIONS: ".sab/visualizations.json",
        "data/pasted_1.parquet": ".sab/data/pasted_1.parquet",
    }
    new = rules.converted(old, found)
    assert new.visualizations == ".sab/visualizations.json" and new.model is None and new.autosave is True
    assert new.tables[0].rows_file == ".sab/data/pasted_1.parquet"


def test_a_folder_is_a_project_by_its_sab_or_its_data_notebook() -> None:
    assert rules.is_project([".sab/project.json"]) and rules.is_project(["data.ipynb", "notes.md"])
    assert not rules.is_project(["notes.md", "orders.csv"])


# ===== the folder on disk, and an old .sab read for the import =====


def _archive(tmp_path: Path, **limits: int) -> SabArchive:
    return SabArchive(
        limits.get("file", 10_000_000), limits.get("entries", 100), limits.get("total", 10_000_000)
    )


def _zip(path: Path, entries: dict[str, bytes], link: str | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as out:
        for name, body in entries.items():
            out.writestr(name, body)
        if link:
            info = zipfile.ZipInfo(link)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            out.writestr(info, "/etc/passwd")
    return path


def test_state_is_written_only_when_its_bytes_change_and_never_outside(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    folder = tmp_path / "sales"
    folder.mkdir()
    assert archive.write_state(str(folder), ".sab/project.json", b"{}") is True
    first = (folder / ".sab" / "project.json").stat().st_mtime_ns
    assert archive.write_state(str(folder), ".sab/project.json", b"{}") is False
    assert (folder / ".sab" / "project.json").stat().st_mtime_ns == first
    assert archive.write_state(str(folder), ".sab/project.json", b'{"a": 1}') is True
    assert archive.read_state(str(folder), ".sab/project.json") == b'{"a": 1}'
    assert archive.read_state(str(folder), ".sab/model.json") is None
    with pytest.raises(SabError):
        archive.write_state(str(folder), "../evil.py", b"x")
    with pytest.raises(SabError):
        archive.remove_state(str(folder), "data.ipynb")  # only the app's own files go
    assert [p.name for p in folder.rglob("*.saving")] == []


def test_the_scaffolds_git_files_never_write_over_the_users(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    folder = tmp_path / "sales"
    folder.mkdir()
    (folder / "README.md").write_text("Mine.\n")
    assert archive.ensure_ignored(str(folder), "sales") == [".sab/.gitignore", ".gitignore"]
    assert (folder / "README.md").read_text() == "Mine.\n"
    assert ".sab/data/" in (folder / ".gitignore").read_text()
    assert archive.ensure_ignored(str(folder), "sales") == []


def test_an_old_sab_unpacks_into_an_empty_folder_its_own_entries_in_their_places(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    manifest = rules.write_manifest(_manifest()).encode()
    path = _zip(
        tmp_path / "sales.sab",
        {
            "project.json": manifest,
            "data.ipynb": b"{}",
            "pages/1_Sales.py": b"x = 1",
            "data/pasted_1.parquet": b"PAR1",
            rules.MODEL: b"{}",
        },
    )
    old, _ = rules.read_manifest(archive.manifest(str(path)))
    target = tmp_path / "into"
    found = archive.unpack_into(str(path), str(target), lambda entry: rules.old_entry_place(entry, old))
    assert (target / "data.ipynb").read_bytes() == b"{}" and (target / "pages" / "1_Sales.py").exists()
    assert not (target / "project.json").exists() and not (target / "data").exists()
    assert (target / ".sab" / "model.json").read_bytes() == b"{}"
    assert found["data/pasted_1.parquet"] == ".sab/data/pasted_1.parquet"
    with pytest.raises(FileExistsError):  # a folder that holds something: nothing written into it
        archive.unpack_into(str(path), str(target), lambda entry: None)


def test_a_zip_that_reaches_outside_lies_about_sizes_or_links_is_not_imported(tmp_path: Path) -> None:
    archive = _archive(tmp_path, total=1000)
    manifest = rules.write_manifest(Manifest("x")).encode()
    for name, entries, link in (
        ("outside.sab", {"project.json": manifest, "../evil.py": b"x"}, None),
        ("link.sab", {"project.json": manifest}, "data.ipynb"),
        ("big.sab", {"project.json": manifest, "big.py": b"x" * 5000}, None),
        ("none.sab", {"data.ipynb": b"{}"}, None),
    ):
        path = _zip(tmp_path / name, entries, link)
        with pytest.raises(SabError):
            archive.unpack_into(str(path), str(tmp_path / f"into-{name}"), lambda entry: None)
        assert not (tmp_path / f"into-{name}").exists()  # nothing left behind
    (tmp_path / "plain.sab").write_bytes(b"not a zip")
    with pytest.raises(SabError, match="not a zip"):
        archive.manifest(str(tmp_path / "plain.sab"))
    assert not (tmp_path / "evil.py").exists()


def test_an_entry_that_unpacks_to_more_than_it_says_stops(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    manifest = rules.write_manifest(Manifest("x")).encode()
    path = _zip(tmp_path / "liar.sab", {"project.json": manifest, "data.ipynb": b"y" * 4000})
    raw = bytearray(path.read_bytes())
    # Each header says the entry is 10 bytes (a zip bomb's trick): the read counts for itself.
    for signature, size_at, name_at in ((b"PK\x03\x04", 22, 30), (b"PK\x01\x02", 24, 46)):
        at = raw.find(signature)
        while at >= 0:
            if bytes(raw[at + name_at : at + name_at + 10]) == b"data.ipynb":
                raw[at + size_at : at + size_at + 4] = (10).to_bytes(4, "little")
            at = raw.find(signature, at + 4)
    path.write_bytes(bytes(raw))
    with pytest.raises(SabError):
        archive.unpack_into(str(path), str(tmp_path / "into"), lambda entry: None)
    assert not (tmp_path / "into").exists()


def test_rows_go_through_parquet_the_same_rows_the_same_bytes(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    table = pa.table({"region": ["North", "South"], "units": [3, 5]})
    body = archive.rows_bytes(table)
    assert archive.rows_bytes(table) == body
    (tmp_path / "rows.parquet").write_bytes(body)
    assert archive.read_rows(str(tmp_path / "rows.parquet")).to_pylist() == table.to_pylist()


def test_copy_project_leaves_kept_rows_and_caches_behind_unless_ticked(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    source = tmp_path / "sales"
    (source / ".sab" / "data").mkdir(parents=True)
    (source / ".sab" / "data" / "t.parquet").write_bytes(b"PAR1")
    (source / ".sab" / "project.json").write_text("{}")
    (source / "__pycache__").mkdir()
    (source / "data.ipynb").write_text("{}")
    archive.copy_project(str(source), str(tmp_path / "copy"), data=False)
    assert (tmp_path / "copy" / "data.ipynb").is_file() and (
        tmp_path / "copy" / ".sab" / "project.json"
    ).is_file()
    assert (
        not (tmp_path / "copy" / ".sab" / "data").exists()
        and not (tmp_path / "copy" / "__pycache__").exists()
    )
    archive.copy_project(str(source), str(tmp_path / "whole"), data=True)
    assert (tmp_path / "whole" / ".sab" / "data" / "t.parquet").is_file()
    with pytest.raises(FileExistsError):
        archive.copy_project(str(source), str(source / "inside"), data=False)


def test_the_recent_list_keeps_folders_and_times_only(tmp_path: Path) -> None:
    listed = RecentProjects(tmp_path / "state" / "recent_projects.json")
    there = tmp_path / "sales"
    there.mkdir()
    old = tmp_path / "older.sab"
    old.write_bytes(b"x")
    listed.add(str(tmp_path / "gone"), 1.0)
    listed.add(str(there), 2.0)
    listed.add(str(old), 2.5)
    listed.add(str(tmp_path / "gone"), 3.0)  # opened again: first
    assert [(Path(r["path"]).name, r["exists"], r["sab"]) for r in listed.all()] == [
        ("gone", False, False),
        ("older.sab", False, True),
        ("sales", True, False),
    ]
    saved = json.loads((tmp_path / "state" / "recent_projects.json").read_text())
    assert all(set(r) == {"path", "opened"} for r in saved)
    assert listed.replace(str(tmp_path / "gone"), str(there)) and next(
        r["path"] for r in listed.all()
    ) == str(there)
    assert listed.remove(str(there)) and not listed.remove(str(there))
