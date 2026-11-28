"""An Excel workbook's own Power Query, read and saved back (domain/workbook_queries.py): the Data Mashup
parsed and rebuilt as [MS-QDEFF] says, byte for byte where nothing changed, and every refusal. The workbooks
are made up (tests/workbook_queries_data.py)."""

from __future__ import annotations

import base64
import io
import struct
import zipfile
from pathlib import Path
from typing import Any

import openpyxl
import pytest

from swissarmybench.domain import workbook_queries as wq
from tests import workbook_queries_data as data

EDITED = data.SECTION.replace("[Amount] > 100", "[Amount] > 150")


def _read(path: Path) -> wq.Read:
    return wq.read(path.read_bytes(), path.name)


def _linked(section: str) -> str:
    return wq.linked_text("Sales Report.xlsx", section)


# ===== the stream, as the specification says =====


def test_the_specifications_own_example_is_read_and_packed_back_byte_for_byte() -> None:
    raw = base64.b64decode(data.SPEC_EXAMPLE)
    mashup = wq.parse_mashup(raw)
    assert struct.unpack_from("<I", raw, 0) == (0,)  # Version
    assert struct.unpack_from("<I", raw, 4) == (len(mashup.package),)  # Package Parts Length
    assert mashup.pack() == raw
    section = wq.zip_read(mashup.package, "Formulas/Section1.m")
    assert section == b"section Section1;\r\n\r\nshared Query1 = let\r\n    Source = 1+1\r\nin\r\n    Source;"
    assert (
        mashup.permissions.startswith(b"\xef\xbb\xbf<?xml") and b"<FirewallEnabled>true" in mashup.permissions
    )
    metadata = wq.parse_metadata(mashup.metadata)
    assert metadata.pack() == mashup.metadata and metadata.xml.endswith(b"</LocalPackageMetadataFile>")
    facts = wq.query_facts(metadata.xml)
    assert (
        facts["Query1"].to_sheet
        and facts["Query1"].target == "Query1"
        and facts["Query1"].columns == ("Query1",)
    )


def test_a_made_up_stream_parses_into_its_four_fields() -> None:
    mashup = wq.parse_mashup(data.mashup())
    assert [mashup.package, mashup.permissions, mashup.bindings] == [
        data.package(),
        data.PERMISSIONS,
        data.BINDINGS,
    ]
    assert wq.parse_metadata(mashup.metadata).xml == data.metadata_xml()
    assert mashup.pack() == data.mashup()


@pytest.mark.parametrize(
    ("damage", "said"),
    [
        (lambda raw: data.mashup(version=1), "version 1"),
        (lambda raw: raw[:-5], "past its end"),
        (lambda raw: raw + b"\x00", "more than its four parts"),
        (lambda raw: b"\x00\x00", "ends before"),
    ],
    ids=["version", "cut", "longer", "short"],
)
def test_a_stream_that_is_not_as_specified_is_refused(damage: Any, said: str) -> None:
    with pytest.raises(wq.Unreadable, match=said):
        wq.parse_mashup(damage(data.mashup()))


# ===== a zip rewritten raw =====


def test_replacing_one_zip_entry_copies_every_other_one_raw() -> None:
    held = io.BytesIO()
    with zipfile.ZipFile(held, "w") as archive:
        archive.writestr("a.txt", b"alpha " * 50, zipfile.ZIP_DEFLATED)
        archive.writestr("b/b.txt", b"bravo", zipfile.ZIP_STORED)
        archive.writestr("c.txt", b"charlie " * 40, zipfile.ZIP_DEFLATED)
    before = held.getvalue()
    after = wq.zip_replace(before, "b/b.txt", b"a much longer text than it was")
    with zipfile.ZipFile(io.BytesIO(after)) as archive:
        assert archive.testzip() is None
        assert archive.read("b/b.txt") == b"a much longer text than it was"
        assert archive.read("a.txt") == b"alpha " * 50
        moved = archive.getinfo("c.txt").header_offset
    with zipfile.ZipFile(io.BytesIO(before)) as archive:
        was = archive.getinfo("c.txt").header_offset
        first = archive.getinfo("b/b.txt").header_offset
    # The entry before it has not moved a byte, and the one after is the same bytes further on.
    assert after[:first] == before[:first]
    size = len(wq.zip_read(before, "c.txt") or b"")
    assert size and after[moved : moved + 60] == before[was : was + 60]


def test_an_entry_with_a_data_descriptor_keeps_it() -> None:
    held = io.BytesIO()
    with zipfile.ZipFile(held, "w", zipfile.ZIP_DEFLATED) as archive:
        with archive.open("streamed.txt", "w") as part:  # written as a stream: sizes after the data
            part.write(b"streamed " * 30)
        archive.writestr("other.txt", b"other")
    after = wq.zip_replace(held.getvalue(), "other.txt", b"changed")
    with zipfile.ZipFile(io.BytesIO(after)) as archive:
        assert archive.testzip() is None and archive.read("streamed.txt") == b"streamed " * 30
    assert wq.zip_read(after, "streamed.txt") == b"streamed " * 30


# ===== a workbook read =====


def test_a_workbooks_queries_are_read_as_excel_wrote_them(tmp_path: Path) -> None:
    found = _read(data.workbook(tmp_path / "Sales Report.xlsx"))
    assert (
        found.part == "customXml/item1.xml" and found.section == data.SECTION and found.text == data.SECTION
    )
    assert found.tables == ("SalesTable",)
    assert [m.name for m in wq.split(found.section).members] == ["Sales", "Threshold", "By Region"]
    assert found.facts["Sales"].to_sheet and not found.facts["By Region"].loaded


def test_a_workbook_with_no_query_opens_a_starter_over_its_named_table(tmp_path: Path) -> None:
    import duckpq

    found = _read(data.plain_workbook(tmp_path / "plain.xlsx"))
    assert found.part is None
    assert 'Excel.CurrentWorkbook(){[Name = "SalesTable"]}[Content]' in found.text
    assert found.text.startswith("section Section1;")
    assert not duckpq.compile(found.text, "plain", duckpq.Context()).problems
    assert "#table(" in wq.starter() and not duckpq.compile(wq.starter(), "x", duckpq.Context()).problems
    with pytest.raises(wq.Unreadable, match=r"no Power Query yet.*Blank Query"):
        wq.plan(found, _linked(found.text))


def _encrypted(path: Path) -> Path:
    path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600)
    return path


def _protected(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", b'<workbook><workbookProtection lockStructure="1"/></workbook>')
    return path


@pytest.mark.parametrize(
    ("name", "make", "said"),
    [
        ("old.xls", _encrypted, "older .xls workbook"),
        ("binary.xlsb", _encrypted, "binary .xlsb workbook"),
        ("notes.txt", _encrypted, "not an Excel workbook"),
        ("locked.xlsx", _encrypted, "encrypted"),
        ("words.xlsx", lambda p: (p.write_bytes(b"not a zip at all"), p)[1], "not a zip"),
        ("protected.xlsx", lambda p: _protected(p), "protected"),
        (
            "signed.xlsx",
            lambda p: data.workbook(p, more={"_xmlsignatures/sig1.xml": b"<Signature/>"}),
            "signed",
        ),
        ("newer.xlsx", lambda p: data.workbook(p, stream=data.mashup(version=2)), "version 2"),
        ("cut.xlsx", lambda p: data.workbook(p, stream=data.mashup()[:200]), "past its end"),
        (
            "empty.xlsx",
            lambda p: data.workbook(p, stream=struct.pack("<IIIIII", 0, 4, 0, 0, 0, 0)),
            "not a zip",
        ),
    ],
)
def test_what_cannot_be_read_is_refused_in_one_sentence(tmp_path: Path, name: str, make, said: str) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / name
    make(path)
    with pytest.raises(wq.Unreadable, match=said) as refused:
        _read(path)
    assert str(refused.value).count("\n") == 0


# ===== the section's text =====


def test_a_section_is_split_into_its_queries_whatever_they_hold() -> None:
    text = (
        "// about; this file\nsection Section1;\n\n"
        '/* a; comment */\nshared A = "one; two ""three"";";\n'
        'shared #"B; C" = let x = 1 in x;\n[Description = "d;"] D = A;\n'
    )
    section = wq.split(text)
    assert section.name == "Section1" and [m.name for m in section.members] == ["A", "B; C", "D"]
    assert section.member("A").m == '/* a; comment */\nshared A = "one; two ""three"";";'  # type: ignore[union-attr]
    assert [m.line for m in section.members] == [5, 6, 7]
    assert section.head + "".join(m.text for m in section.members) + section.tail == text


@pytest.mark.parametrize(
    ("text", "said", "line"),
    [
        ("let x = 1 in x", "must start with `section Section1;`", 1),
        ("section Section1;\nshared A = 1;\nshared B = 2", "no `;` at its end", 3),
        ("section Section1;\nshared A = 1;\nshared A = 2;", "written twice", 3),
        ('section Section1;\nshared A = "open;', "never closed", 2),
        ("section Section1;\n1 + 1;", "not a query", 2),
    ],
)
def test_a_text_that_is_not_one_section_of_queries_says_its_line(text: str, said: str, line: int) -> None:
    with pytest.raises(wq.SectionError, match=said) as refused:
        wq.split(text)
    assert refused.value.line == line


def test_the_header_names_the_workbook_relative_to_the_file() -> None:
    text = wq.linked_text("../books/Sales Report.xlsx", data.SECTION)
    assert text.startswith("// workbook: ../books/Sales Report.xlsx\r\n\r\nsection Section1;")
    assert wq.linked_to(text) == "../books/Sales Report.xlsx" and wq.linked_to(data.SECTION) is None
    assert wq.body(text) == (data.SECTION, 2)
    assert wq.relative_to("/p/scripts/q.pq", "/p/books/Sales Report.xlsx") == "../books/Sales Report.xlsx"
    assert wq.relative_to("C:\\p\\q.pq", "D:\\books\\b.xlsx") == "D:/books/b.xlsx"
    assert wq.workbook_path("/p/scripts/q.pq", "../books/b.xlsx") == "/p/books/b.xlsx"
    assert wq.workbook_path("/p/scripts/q.pq", "/else/b.xlsx") == "/else/b.xlsx"
    import duckpq

    assert [q.name for q in duckpq.compile(text, "q", duckpq.Context()).queries] == [
        "Sales",
        "Threshold",
        "By Region",
    ]


# ===== a save: what it changes and what it never touches =====


def test_nothing_changed_writes_the_same_bytes(tmp_path: Path) -> None:
    path = data.workbook(tmp_path / "Sales Report.xlsx")
    before = path.read_bytes()
    found = _read(path)
    planned = wq.plan(
        found, _linked(data.SECTION.replace("\r\n", "\n"))
    )  # an editor's line ends: still the same
    assert not planned.writes and {c.what for c in planned.changes} == {"same"}
    assert wq.written(before, found, planned) == before
    assert (
        planned.words("Sales Report.xlsx")
        == "Sales Report.xlsx already holds these queries: nothing was written."
    )


def test_a_changed_query_replaces_section1_and_nothing_else(tmp_path: Path) -> None:
    path = data.workbook(tmp_path / "Sales Report.xlsx")
    before = path.read_bytes()
    found = _read(path)
    planned = wq.plan(found, _linked(EDITED))
    assert [(c.query, c.what) for c in planned.changes] == [
        ("Sales", "changed"),
        ("Threshold", "same"),
        ("By Region", "same"),
    ]
    assert "its sheet's table (Sales) takes its new columns then" in planned.changes[0].words
    path.write_bytes(wq.written(before, found, planned))
    # every other part of the workbook, byte for byte
    old, new = data.parts_of(tmp_path / "Sales Report.xlsx"), None
    with zipfile.ZipFile(io.BytesIO(before)) as archive:
        new, old = old, {n: archive.read(n) for n in archive.namelist()}
    assert list(new) == list(old)
    assert {n for n in old if old[n] != new[n]} == {"customXml/item1.xml"}
    # the stream: every length right, the other three fields as they were
    was, now = data.fields_of(data.mashup()), data.fields_of(data.stream_of(path))
    assert now[1:] == was[1:] == [data.PERMISSIONS, was[2], data.BINDINGS]
    with zipfile.ZipFile(io.BytesIO(now[0])) as archive, zipfile.ZipFile(io.BytesIO(was[0])) as original:
        assert archive.testzip() is None and archive.namelist() == original.namelist()
        assert archive.read("Formulas/Section1.m").decode() == EDITED
        for name in ("Config/Package.xml", "[Content_Types].xml"):
            assert archive.read(name) == original.read(name)
            a, b = archive.getinfo(name), original.getinfo(name)
            assert (a.CRC, a.compress_size, a.date_time, a.flag_bits) == (
                b.CRC,
                b.compress_size,
                b.date_time,
                b.flag_bits,
            )
    # the part is still UTF-16 with its mark, its attributes as they were
    item = new["customXml/item1.xml"]
    assert item[:2] == b"\xff\xfe" and 'sqmid="6f1e2c1a-3b4d-4e5f-8a9b-0c1d2e3f4a5b"' in item[2:].decode(
        "utf-16-le"
    )
    # and the file is still a workbook openpyxl opens, its cells as they were
    book = openpyxl.load_workbook(path)
    assert book["Data"]["A2"].value == "North" and "SalesTable" in book["Data"].tables
    assert _read(path).section == EDITED


def test_an_added_query_is_connection_only_with_its_metadata_item(tmp_path: Path) -> None:
    path = data.workbook(tmp_path / "Sales Report.xlsx")
    found = _read(path)
    added = EDITED + '\r\nshared #"Top Regions" = Table.FirstN(#"By Region", 3);\r\n'
    planned = wq.plan(found, _linked(added))
    assert planned.added == ("Top Regions",)
    assert "connection only (no sheet)" in planned.changes[-1].words
    path.write_bytes(wq.written(path.read_bytes(), found, planned))
    fields = data.fields_of(data.stream_of(path))
    metadata = wq.parse_metadata(fields[2])
    assert metadata.content == b"" and fields[1] == data.PERMISSIONS and fields[3] == data.BINDINGS
    item = (
        b"<Item><ItemLocation><ItemType>Formula</ItemType><ItemPath>Section1/Top%20Regions</ItemPath></ItemLocation>"
        b'<StableEntries><Entry Type="IsPrivate" Value="l0" /><Entry Type="FillEnabled" Value="l0" />'
        b'<Entry Type="FillToDataModelEnabled" Value="l0" /></StableEntries></Item>'
    )
    assert metadata.xml == data.metadata_xml().replace(b"</Items>", item + b"</Items>")
    facts = wq.query_facts(metadata.xml)
    assert not facts["Top Regions"].loaded and facts["Sales"].to_sheet
    # no sheet, no table and no connection was made: the workbook's other parts are as they were
    assert not any(
        n.startswith("xl/connections") or n.startswith("xl/queryTables") for n in data.parts_of(path)
    )
    assert [m.name for m in wq.split(_read(path).section).members][-1] == "Top Regions"


def test_an_added_querys_name_follows_the_specification() -> None:
    assert wq.name_problem("Top Regions") is None
    for bad in ("a.b", 'say "hi"', "tab\there", " lead", ""):
        assert wq.name_problem(bad)
    found = wq.read(data.workbook(Path(__file__).parent / "_made_up.xlsx").read_bytes(), "b.xlsx")
    (Path(__file__).parent / "_made_up.xlsx").unlink()
    with pytest.raises(wq.SectionError, match="no period") as refused:
        wq.plan(found, _linked(data.SECTION + 'shared #"a.b" = 1;\r\n'))
    assert refused.value.line == 2 + data.SECTION.count("\n") + 1


def test_a_metadata_with_no_list_refuses_the_new_query_in_one_sentence() -> None:
    assert b"Section1/New" in wq.metadata_with(b"<L><Items /></L>", ["New"])
    assert b"Section1/My Query" in wq.metadata_with(
        b"<L><Items><Item><ItemPath>Section1/Old Query</ItemPath></Item></Items></L>", ["My Query"]
    )  # this workbook writes its names as they are
    with pytest.raises(wq.Unreadable):
        wq.metadata_with(b"<L></L>", ["New"])


def test_a_query_taken_out_of_the_file_is_kept_in_the_workbook(tmp_path: Path) -> None:
    path = data.workbook(tmp_path / "Sales Report.xlsx")
    found = _read(path)
    without = EDITED.replace("shared Threshold = 100;\r\n\r\n", "")
    planned = wq.plan(found, _linked(without))
    assert [(c.query, c.what) for c in planned.changes] == [
        ("Sales", "changed"),
        ("By Region", "same"),
        ("Threshold", "kept"),
    ]
    assert "never removed" in planned.changes[-1].words
    path.write_bytes(wq.written(path.read_bytes(), found, planned))
    members = wq.split(_read(path).section).members
    assert [m.name for m in members] == ["Sales", "By Region", "Threshold"] and members[
        -1
    ].m == "shared Threshold = 100;"
    assert planned.words("Sales Report.xlsx") == (
        "Saved into Sales Report.xlsx: 1 changed, 1 kept. Excel runs them on its next Refresh."
    )


def test_a_section_of_another_name_is_refused(tmp_path: Path) -> None:
    found = _read(data.workbook(tmp_path / "b.xlsx"))
    with pytest.raises(wq.SectionError, match="must be named Section1"):
        wq.plan(found, _linked(data.SECTION.replace("section Section1;", "section Sales;")))


def test_the_words_around_the_file() -> None:
    assert wq.lock_names("Sales Report.xlsx") == ("~$Sales Report.xlsx", "~$les Report.xlsx")
    assert (
        wq.locked_words("Sales Report.xlsx") == "Sales Report.xlsx is open in Excel. Close it in Excel first."
    )
    assert wq.conflict_words("b.xlsx").endswith("Reload them, or Keep mine.")
    assert wq.backup_name("Sales Report.xlsx") == "Sales Report.backup.xlsx"
