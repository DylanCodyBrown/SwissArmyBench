"""Workbook queries through the server (services/workbook_queries.py, its routes and the agent's commands): a
workbook's queries opened as one linked .pq file, a query changed and saved back with every other part of the
file byte for byte, Run with Excel.CurrentWorkbook, the conflict, Excel's lock, the backup, the agent's dry
run and its Allow. The workbooks are made up (tests/workbook_queries_data.py)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import openpyxl
import pytest

from swissarmybench.domain import new_files
from swissarmybench.domain import workbook_queries as wq
from tests import workbook_queries_data as data
from tests.conftest import AGENT, AUTH
from tests.fake_keyring import memory_keyring
from tests.test_agent import _answer_when_asked


@pytest.fixture(autouse=True)
def keyring() -> Iterator[None]:
    with memory_keyring():
        yield


def _open(client: Any, tmp_path: Path, workbook: Path, name: str = "report") -> Path:
    body = {"type": "powerquery_workbook", "name": name, "folder": str(tmp_path), "source": str(workbook)}
    made = client.post("/scripts/files/new", json=body, headers=AUTH)
    assert made.status_code == 200, made.text
    return Path(made.json()["path"])


def _edited(file: Path) -> str:
    return file.read_text(encoding="utf-8").replace("[Amount] > 100", "[Amount] > 150")


def test_the_new_file_type_asks_for_the_workbook() -> None:
    kind = new_files.type_of("powerquery_workbook")
    assert kind.label == "Edit workbook queries…" and kind.asks == ("name", "folder", "source")
    assert kind.maker == wq.TYPE and kind.kind == "powerquery" and kind.ending == ".pq"


def test_a_workbooks_queries_open_as_one_linked_file(client: Any, tmp_path: Path) -> None:
    workbook = data.workbook(tmp_path / "Sales Report.xlsx")
    offered = {t["id"]: t for t in client.get("/scripts/files/new", headers=AUTH).json()["types"]}
    assert offered["powerquery_workbook"]["asks"] == ["name", "folder", "source"]
    file = _open(client, tmp_path, workbook)
    raw = file.read_bytes().decode("utf-8")
    assert (
        raw == "// workbook: Sales Report.xlsx\r\n\r\n" + data.SECTION
    )  # Excel's text, its order, its line ends
    link = client.post("/scripts/pq/workbook", json={"path": str(file)}, headers=AUTH).json()
    assert link == {
        "linked": True, "workbook": "Sales Report.xlsx", "workbook_path": str(workbook).replace("\\", "/"),
        "there": True, "queries": 3, "open_in_excel": False, "changed": False, "why": None,
    }  # fmt: skip
    plain = tmp_path / "plain.pq"
    plain.write_text("let x = 1 in x", encoding="utf-8")
    assert client.post("/scripts/pq/workbook", json={"path": str(plain)}, headers=AUTH).json() == {
        "linked": False
    }
    problems = client.post("/scripts/pq/problems", json={"path": str(file)}, headers=AUTH).json()
    assert problems["problems"] == [] and [q["name"] for q in problems["queries"]] == [
        "Sales",
        "Threshold",
        "By Region",
    ]


def test_save_writes_only_the_data_mashup(client: Any, tmp_path: Path) -> None:
    workbook = data.workbook(tmp_path / "Sales Report.xlsx")
    before = data.parts_of(workbook)
    was = data.fields_of(data.stream_of(workbook))
    file = _open(client, tmp_path, workbook)
    text = _edited(file)
    preview = client.post(
        "/scripts/pq/workbook/preview", json={"path": str(file), "text": text}, headers=AUTH
    ).json()
    assert preview["written"] is False and preview["writes"] and preview["changed"] == 1
    assert [(c["query"], c["what"]) for c in preview["changes"]] == [
        ("Sales", "changed"), ("Threshold", "same"), ("By Region", "same"),
    ]  # fmt: skip
    assert data.parts_of(workbook) == before and "[Amount] > 100" in file.read_text(
        encoding="utf-8"
    )  # a dry run
    saved = client.post("/scripts/pq/workbook/save", json={"path": str(file), "text": text}, headers=AUTH)
    assert saved.status_code == 200, saved.text
    answer = saved.json()
    assert answer["written"] and answer["words"].startswith("Saved into Sales Report.xlsx: 1 changed.")
    assert "[Amount] > 150" in file.read_bytes().decode("utf-8")  # the .pq first
    after = data.parts_of(workbook)
    assert list(after) == list(before) and {n for n in after if after[n] != before[n]} == {
        "customXml/item1.xml"
    }
    now = data.fields_of(data.stream_of(workbook))
    assert now[1:] == was[1:]  # permissions, metadata and the permission bindings as they were
    assert "[Amount] > 150" in data.section_of(workbook) and data.section_of(workbook).count(
        "\r\n"
    ) == data.SECTION.count("\r\n")
    assert (
        openpyxl.load_workbook(workbook)["Data"]["B4"].value == 310
    )  # still a workbook, its cells as they were
    # the same text again writes nothing
    again = client.post("/scripts/pq/workbook/save", json={"path": str(file)}, headers=AUTH).json()
    assert again["written"] is False and "nothing was written" in again["words"]
    assert not list(tmp_path.glob(".*.tmp"))


def test_the_backup_is_made_once_beside_a_workbook_outside_a_project(client: Any, tmp_path: Path) -> None:
    workbook = data.workbook(tmp_path / "Sales Report.xlsx")
    original = workbook.read_bytes()
    file = _open(client, tmp_path, workbook)
    first = client.post(
        "/scripts/pq/workbook/save", json={"path": str(file), "text": _edited(file)}, headers=AUTH
    ).json()
    backup = tmp_path / "Sales Report.backup.xlsx"
    assert first["backup"] == str(backup) and backup.read_bytes() == original
    text = file.read_text(encoding="utf-8").replace("> 150", "> 175")
    second = client.post(
        "/scripts/pq/workbook/save", json={"path": str(file), "text": text}, headers=AUTH
    ).json()
    assert second["written"] and second["backup"] is None and backup.read_bytes() == original


def test_a_workbook_in_the_open_project_is_backed_up_in_its_sab_folder(client: Any, tmp_path: Path) -> None:
    project = tmp_path / "shop"
    made = client.post("/project/new", json={"path": str(project)}, headers=AUTH)
    assert made.status_code == 200, made.text
    workbook = data.workbook(project / "Sales Report.xlsx")
    original = workbook.read_bytes()
    body = {"type": "powerquery_workbook", "name": "report", "source": str(workbook)}
    new = client.post("/scripts/files/new", json=body, headers=AUTH)
    assert new.status_code == 200, new.text
    file = Path(new.json()["path"])
    assert file.parent == project / "scripts" and file.read_text(encoding="utf-8").startswith(
        "// workbook: ../Sales Report.xlsx"
    )
    # The agent saves into a workbook inside the open project with no Allow.
    saved = client.post(
        "/scripts/pq/workbook/save", json={"path": str(file), "text": _edited(file)}, headers=AGENT
    )
    assert saved.status_code == 200, saved.text
    kept = list((project / ".sab" / "backup").glob("*/Sales Report.xlsx"))
    assert len(kept) == 1 and kept[0].read_bytes() == original and saved.json()["backup"] == str(kept[0])
    assert (project / ".sab" / "backup" / ".gitignore").read_text() == "*\n"
    assert not (project / "Sales Report.backup.xlsx").exists()
    # The Files pane lists the linked file under its workbook's name.
    tree = client.get("/project/tree", params={"page": "scripts"}, headers=AUTH)
    assert tree.status_code == 200, tree.text
    groups = tree.json()["groups"]
    named = {g["name"]: [f["name"] for f in g["files"]] for g in groups}
    assert named["Sales Report.xlsx"] == ["report.pq"] and "Power Query" not in named


def test_run_reads_excel_current_workbook_from_the_linked_workbook(client: Any, tmp_path: Path) -> None:
    workbook = data.workbook(tmp_path / "Sales Report.xlsx")
    file = _open(client, tmp_path, workbook)
    ran = client.post("/scripts/pq/run", json={"path": str(file)}, headers=AUTH)
    assert ran.status_code == 200, ran.text
    built = {t["table"]: t["rows"] for t in ran.json()["tables"]}
    assert built == {"Sales": 3, "By_Region": 2}  # 120, 310 and 205 are over 100: North and East
    # a file with no link says what Excel.CurrentWorkbook is
    loose = tmp_path / "loose.pq"
    loose.write_text(data.SECTION, encoding="utf-8")
    refused = client.post("/scripts/pq/run", json={"path": str(loose)}, headers=AUTH)
    assert refused.status_code == 400 and "linked to" in refused.json()["error"]
    assert (
        data.parts_of(workbook) == data.parts_of(workbook) and data.section_of(workbook) == data.SECTION
    )  # a run writes nothing


def test_queries_changed_on_disk_are_a_conflict_with_reload_and_keep_mine(
    client: Any, tmp_path: Path
) -> None:
    workbook = data.workbook(tmp_path / "Sales Report.xlsx")
    file = _open(client, tmp_path, workbook)
    # Excel saved the workbook with a query changed, after the file was opened.
    theirs = data.SECTION.replace("shared Threshold = 100;", "shared Threshold = 500;")
    found = wq.read(workbook.read_bytes(), workbook.name)
    workbook.write_bytes(
        wq.written(workbook.read_bytes(), found, wq.plan(found, wq.linked_text("x", theirs)))
    )
    on_disk = workbook.read_bytes()
    assert (
        client.post("/scripts/pq/workbook", json={"path": str(file)}, headers=AUTH).json()["changed"] is True
    )
    body = {"path": str(file), "text": _edited(file)}
    assert client.post("/scripts/pq/workbook/preview", json=body, headers=AUTH).json()["conflict"] is True
    refused = client.post("/scripts/pq/workbook/save", json=body, headers=AUTH)
    assert refused.status_code == 409 and refused.json()["conflict"] is True
    assert refused.json()["error"] == (
        "Sales Report.xlsx's queries changed on disk since this file was opened: Reload them, or Keep mine."
    )
    assert workbook.read_bytes() == on_disk  # never overwritten
    # Reload: the workbook's queries into the file
    reloaded = client.post("/scripts/pq/workbook/reload", json={"path": str(file)}, headers=AUTH).json()
    assert (
        "shared Threshold = 500;" in reloaded["text"]
        and "shared Threshold = 500;" in file.read_bytes().decode()
    )
    assert (
        client.post("/scripts/pq/workbook", json={"path": str(file)}, headers=AUTH).json()["changed"] is False
    )
    # Keep mine, from a second file opened before another change
    other = _open(client, tmp_path, workbook, "other")
    found = wq.read(workbook.read_bytes(), workbook.name)
    again = theirs.replace("= 500;", "= 900;")
    workbook.write_bytes(wq.written(workbook.read_bytes(), found, wq.plan(found, wq.linked_text("x", again))))
    mine = {"path": str(other), "text": other.read_text(encoding="utf-8").replace("= 500;", "= 250;")}
    assert client.post("/scripts/pq/workbook/save", json=mine, headers=AUTH).status_code == 409
    kept = client.post("/scripts/pq/workbook/save", json=mine | {"force": True}, headers=AUTH)
    assert kept.status_code == 200 and "shared Threshold = 250;" in data.section_of(workbook)


def test_a_workbook_open_in_excel_is_never_written(client: Any, tmp_path: Path) -> None:
    workbook = data.workbook(tmp_path / "Sales Report.xlsx")
    file = _open(client, tmp_path, workbook)
    lock = tmp_path / "~$Sales Report.xlsx"
    lock.write_bytes(b"\x05Maria")
    before = workbook.read_bytes()
    assert (
        client.post("/scripts/pq/workbook", json={"path": str(file)}, headers=AUTH).json()["open_in_excel"]
        is True
    )
    refused = client.post(
        "/scripts/pq/workbook/save", json={"path": str(file), "text": _edited(file)}, headers=AUTH
    )
    assert refused.status_code == 409 and refused.json()["open_in_excel"] is True
    assert refused.json()["error"] == "Sales Report.xlsx is open in Excel. Close it in Excel first."
    assert workbook.read_bytes() == before and not (tmp_path / "Sales Report.backup.xlsx").exists()
    lock.unlink()
    assert (
        client.post("/scripts/pq/workbook/save", json={"path": str(file)}, headers=AUTH).json()["written"]
        is True
    )


def test_a_text_that_cannot_go_into_a_workbook_says_its_line(client: Any, tmp_path: Path) -> None:
    workbook = data.workbook(tmp_path / "Sales Report.xlsx")
    file = _open(client, tmp_path, workbook)
    before = workbook.read_bytes()
    text = file.read_text(encoding="utf-8") + "shared Broken = 1"
    refused = client.post("/scripts/pq/workbook/save", json={"path": str(file), "text": text}, headers=AUTH)
    assert refused.status_code == 400 and "no `;` at its end" in refused.json()["error"]
    assert refused.json()["line"] == text.count("\n") + 1 and workbook.read_bytes() == before


@pytest.mark.parametrize(
    ("name", "said"),
    [("old.xls", "older .xls"), ("binary.xlsb", "binary .xlsb"), ("locked.xlsx", "encrypted")],
)
def test_a_workbook_that_cannot_be_read_is_refused_and_no_file_is_made(
    client: Any, tmp_path: Path, name: str, said: str
) -> None:
    workbook = tmp_path / name
    workbook.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600)
    body = {"type": "powerquery_workbook", "name": "report", "folder": str(tmp_path), "source": str(workbook)}
    refused = client.post("/scripts/files/new", json=body, headers=AUTH)
    assert refused.status_code == 403 and said in refused.json()["error"]
    assert not (tmp_path / "report.pq").exists()


def test_a_workbook_with_no_query_opens_a_starter_that_runs_and_says_why_it_cannot_save(
    client: Any, tmp_path: Path
) -> None:
    workbook = data.plain_workbook(tmp_path / "plain.xlsx")
    before = workbook.read_bytes()
    file = _open(client, tmp_path, workbook)
    assert 'Excel.CurrentWorkbook(){[Name = "SalesTable"]}[Content]' in file.read_text(encoding="utf-8")
    ran = client.post("/scripts/pq/run", json={"path": str(file)}, headers=AUTH)
    assert ran.status_code == 200 and ran.json()["rows"] == 5
    link = client.post("/scripts/pq/workbook", json={"path": str(file)}, headers=AUTH).json()
    assert link["queries"] == 0 and "no Power Query yet" in link["why"]
    refused = client.post("/scripts/pq/workbook/save", json={"path": str(file)}, headers=AUTH)
    assert refused.status_code == 403 and "Blank Query" in refused.json()["error"]
    assert workbook.read_bytes() == before


def test_the_agents_dry_run_and_its_save_outside_the_project_waits_for_allow(
    client: Any, tmp_path: Path
) -> None:
    from swissarmybench.cli import commands

    workbook = data.workbook(tmp_path / "Sales Report.xlsx")
    file = _open(client, tmp_path, workbook)
    before = workbook.read_bytes()
    tool = commands.REGISTRY["workbench_sql"]
    assert {a.name for a in tool.args} >= {"force", "path", "text"}
    assert "source" in {a.name for a in commands.REGISTRY["workbench_file"].args}
    body = {"path": str(file), "text": _edited(file)}
    preview = client.post("/scripts/pq/workbook/preview", json=body, headers=AGENT)
    assert preview.status_code == 200 and preview.json()["changes"][0] == {
        "query": "Sales", "what": "changed",
        "words": "Changed: Excel runs it again on Refresh, and its sheet's table (Sales) takes its new "
        "columns then.",
    }  # fmt: skip
    assert preview.json()["words"] == "A save would write into Sales Report.xlsx: 1 changed, 0 added, 0 kept."
    assert workbook.read_bytes() == before
    # The workbook is outside any open project: the agent's save waits for the user's Allow.
    helper = _answer_when_asked(client, False)
    refused = client.post("/scripts/pq/workbook/save", json=body, headers=AGENT)
    helper.join()
    assert refused.status_code == 403 and "declined" in refused.json()["error"]
    assert "Sales Report.xlsx was not changed" in refused.json()["error"]
    assert workbook.read_bytes() == before and not (tmp_path / "Sales Report.backup.xlsx").exists()
    helper = _answer_when_asked(client, True)
    allowed = client.post("/scripts/pq/workbook/save", json=body, headers=AGENT)
    helper.join()
    assert allowed.status_code == 200 and allowed.json()["written"] and "> 150" in data.section_of(workbook)
