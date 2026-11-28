"""Power Query added to a workbook that has none (domain/workbook_queries.py; the owner, 2026-11-28: "Yea
optional"): the Data Mashup made new against [MS-QDEFF]'s own example byte for byte, the parts the workbook
needs to hold it against [ECMA-376] Part 1 (15.2.5, 15.2.6, 22.5), every part that was there copied raw, and
the refusals. The workbooks are made up (tests/workbook_queries_data.py)."""

from __future__ import annotations

import base64
import io
import re
import struct
import zipfile
from collections.abc import Mapping
from pathlib import Path
from xml.etree import ElementTree

import openpyxl
import pytest

from swissarmybench.domain import workbook_queries as wq
from tests import workbook_queries_data as data

TWO = (
    "section Section1;\n\n"
    "shared Sales = let\n"
    '    Source = Excel.CurrentWorkbook(){[Name = "SalesTable"]}[Content]\n'
    "in\n    Source;\n\n"
    'shared #"By Region" = Table.Group(Sales, {"Region"}, {{"Total", each List.Sum([Amount])}});\n'
)
CRLF = TWO.replace("\n", "\r\n")


def _linked(section: str) -> str:
    return wq.linked_text("plain.xlsx", section)


def _added(path: Path, section: str = TWO) -> tuple[bytes, bytes, wq.Plan]:
    before = path.read_bytes()
    found = wq.read(before, path.name)
    planned = wq.plan(found, _linked(section), add=True)
    return before, wq.written(before, found, planned), planned


def _raw_entries(blob: bytes) -> dict[str, tuple[int, int, int, bytes]]:
    """Each zip entry as it is stored: its checksum, its sizes and its compressed bytes."""
    out = {}
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        for info in archive.infolist():
            start = info.header_offset
            name_length, extra_length = struct.unpack_from("<HH", blob, start + 26)
            at = start + 30 + name_length + extra_length
            out[info.filename] = (
                info.CRC,
                info.compress_size,
                info.file_size,
                blob[at : at + info.compress_size],
            )
    return out


def _example() -> tuple[wq.Mashup, dict[str, bytes]]:
    mashup = wq.parse_mashup(base64.b64decode(data.SPEC_EXAMPLE))
    with zipfile.ZipFile(io.BytesIO(mashup.package)) as package:
        return mashup, {name: package.read(name) for name in package.namelist()}


# ===== the Data Mashup made new, against the specification's own example =====


def test_the_made_parts_are_the_specifications_own_bytes() -> None:
    """[MS-QDEFF] section 3.1's example, as Excel wrote it: what a new Data Mashup holds beside its queries
    is byte for byte what that one holds."""
    example, parts = _example()
    assert list(parts) == ["Config/Package.xml", "[Content_Types].xml", "Formulas/Section1.m"]
    assert parts["Config/Package.xml"] == wq.NEW_PACKAGE_XML  # 2.3.1, 3.2
    assert parts["[Content_Types].xml"] == wq.NEW_PACKAGE_TYPES
    assert example.permissions == wq.NEW_PERMISSIONS  # 2.4, and 2.6's defaults
    theirs = wq.parse_metadata(example.metadata)
    head, tail = wq.NEW_METADATA_XML.split(b"</Items>")
    assert theirs.xml.startswith(head) and theirs.xml.endswith(b"</Items>" + tail)  # 2.5.1: AllFormulas first
    assert theirs.content == wq.parse_metadata(wq.new_mashup(CRLF, ["Sales"]).metadata).content
    assert len(theirs.content) == 22 and zipfile.ZipFile(io.BytesIO(theirs.content)).namelist() == []
    assert wq.NEW_BINDINGS == b"\x00"  # 2.6: "a length of 1 and content of a single 0x00 (null byte)"


def test_the_new_stream_is_laid_out_as_section_2_2_says() -> None:
    made = wq.new_mashup(CRLF, ["Sales", "By Region"])
    raw = made.pack()
    version, package_length = struct.unpack_from("<II", raw, 0)
    assert (version, package_length) == (0, len(made.package))
    at = 8 + package_length
    assert struct.unpack_from("<I", raw, at) == (len(wq.NEW_PERMISSIONS),)
    assert raw[at + 4 : at + 4 + len(wq.NEW_PERMISSIONS)] == wq.NEW_PERMISSIONS
    assert raw[-5:] == struct.pack("<I", 1) + b"\x00"  # Permission Bindings Length 1, the one null byte
    assert wq.parse_mashup(raw) == made and wq.parse_mashup(raw).pack() == raw
    with zipfile.ZipFile(io.BytesIO(made.package)) as package:
        assert package.testzip() is None
        assert package.namelist() == ["Config/Package.xml", "[Content_Types].xml", "Formulas/Section1.m"]
        assert package.read("Formulas/Section1.m") == CRLF.encode("utf-8")  # no byte-order mark, Excel's ends
        assert package.read("Config/Package.xml") == wq.NEW_PACKAGE_XML
    metadata = wq.parse_metadata(made.metadata)
    assert struct.unpack_from("<I", made.metadata, 0) == (0,)  # 2.5: Version 0
    assert metadata.xml == wq.NEW_METADATA_XML.replace(
        b"</Items>",
        b"<Item><ItemLocation><ItemType>Formula</ItemType><ItemPath>Section1/Sales</ItemPath></ItemLocation>"
        b'<StableEntries><Entry Type="IsPrivate" Value="l0" /><Entry Type="FillEnabled" Value="l0" />'
        b'<Entry Type="FillToDataModelEnabled" Value="l0" /></StableEntries></Item>'
        b"<Item><ItemLocation><ItemType>Formula</ItemType><ItemPath>Section1/By%20Region</ItemPath>"
        b'</ItemLocation><StableEntries><Entry Type="IsPrivate" Value="l0" />'
        b'<Entry Type="FillEnabled" Value="l0" /><Entry Type="FillToDataModelEnabled" Value="l0" />'
        b"</StableEntries></Item></Items>",
    )
    facts = wq.query_facts(metadata.xml)  # one Item a query, each connection only
    assert list(facts) == ["Sales", "By Region"] and not any(f.loaded for f in facts.values())
    root = ElementTree.fromstring(metadata.xml.decode("utf-8-sig"))  # noqa: S314 (made here)
    assert [e.text for e in root.iter("ItemType")] == ["AllFormulas", "Formula", "Formula"]


# ===== the parts the workbook gains, and nothing else =====


def test_the_workbook_gains_only_the_parts_that_hold_it(tmp_path: Path) -> None:
    before, after, planned = _added(data.plain_workbook(tmp_path / "plain.xlsx"))
    was, now = _raw_entries(before), _raw_entries(after)
    new = set(now) - set(was)
    assert new == {"customXml/item1.xml", "customXml/itemProps1.xml", "customXml/_rels/item1.xml.rels"}
    assert planned.adds == (
        "customXml/item1.xml",
        "customXml/itemProps1.xml",
        "customXml/_rels/item1.xml.rels",
    )
    changed = {name for name in was if was[name] != now[name]}
    assert changed == {"xl/_rels/workbook.xml.rels", "[Content_Types].xml"}  # every other part copied raw
    with zipfile.ZipFile(io.BytesIO(before)) as old, zipfile.ZipFile(io.BytesIO(after)) as made:
        assert made.testzip() is None and made.namelist()[: len(old.namelist())] == old.namelist()
        rels_was, rels = old.read("xl/_rels/workbook.xml.rels"), made.read("xl/_rels/workbook.xml.rels")
        types_was, types = old.read("[Content_Types].xml"), made.read("[Content_Types].xml")
        props = made.read("customXml/itemProps1.xml")
        item_rels = made.read("customXml/_rels/item1.xml.rels")
        item = made.read("customXml/item1.xml")
    ids = [int(i) for i in re.findall(rb'Id="rId(\d+)"', rels_was)]
    relationship = (
        f'<Relationship Id="rId{max(ids) + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml" '
        'Target="../customXml/item1.xml"/>'
    ).encode()
    assert rels == rels_was.replace(b"</Relationships>", relationship + b"</Relationships>")
    override = (
        b'<Override PartName="/customXml/itemProps1.xml" '
        b'ContentType="application/vnd.openxmlformats-officedocument.customXmlProperties+xml"/>'
    )
    assert types == types_was.replace(b"</Types>", override + b"</Types>")
    assert b'Extension="xml" ContentType="application/xml"' in types  # the item itself: the xml Default's
    identity = re.search(
        rb'ds:itemID="(\{[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\})"', props
    )
    assert identity is not None
    assert props == (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n<ds:datastoreItem ds:itemID="'
        + identity.group(1)
        + b'" xmlns:ds="http://schemas.openxmlformats.org/officeDocument/2006/customXml"><ds:schemaRefs>'
        b'<ds:schemaRef ds:uri="http://schemas.microsoft.com/DataMashup"/></ds:schemaRefs></ds:datastoreItem>'
    )
    assert item_rels == (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        b'<Relationship Id="rId1" '
        b'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXmlProps" '
        b'Target="itemProps1.xml"/></Relationships>'
    )
    stream = wq.new_mashup(CRLF, ["Sales", "By Region"]).pack()
    assert item == b"\xff\xfe" + (
        '<?xml version="1.0" encoding="utf-16"?><DataMashup xmlns="http://schemas.microsoft.com/DataMashup">'
        + base64.b64encode(stream).decode()
        + "</DataMashup>"
    ).encode("utf-16-le")
    for part in (rels, types, props, item_rels, item):
        ElementTree.fromstring(part)  # noqa: S314 (made here) each is well-formed XML
    assert wq.written(before, wq.read(before, "plain.xlsx"), planned) == after  # the same bytes every time


def test_the_workbook_still_opens_with_its_sheets_and_reads_back_its_queries(tmp_path: Path) -> None:
    path = data.plain_workbook(tmp_path / "plain.xlsx")
    _, after, planned = _added(path)
    path.write_bytes(after)
    book = openpyxl.load_workbook(path)
    assert book.sheetnames == ["Data"] and list(book["Data"].tables) == ["SalesTable"]
    assert [c.value for c in book["Data"][2]] == ["North", 120] and book["Data"].max_row == 6
    found = wq.read(after, path.name)
    assert found.part == "customXml/item1.xml" and found.section == CRLF == planned.section
    assert [m.name for m in wq.split(found.section).members] == ["Sales", "By Region"]
    assert not any(f.loaded for f in found.facts.values()) and found.tables == ("SalesTable",)
    assert "Added Power Query to plain.xlsx: 2 queries, connection only" in planned.words("plain.xlsx")
    assert "customXml/item1.xml" in planned.words("plain.xlsx")


def test_a_second_save_changes_only_section1_m(tmp_path: Path) -> None:
    path = data.plain_workbook(tmp_path / "plain.xlsx")
    _, first, _ = _added(path)
    found = wq.read(first, path.name)
    edited = CRLF.replace("in\r\n    Source;", "in\r\n    Table.SelectRows(Source, each [Amount] > 100);")
    planned = wq.plan(found, _linked(edited))  # no `add` now: it is a workbook with queries
    assert planned.adds == () and [c.what for c in planned.changes] == ["changed", "same"]
    second = wq.written(first, found, planned)
    was, now = _raw_entries(first), _raw_entries(second)
    assert set(was) == set(now) and {n for n in was if was[n] != now[n]} == {"customXml/item1.xml"}
    old, new = wq.parse_mashup(data.stream_of_bytes(first)), wq.parse_mashup(data.stream_of_bytes(second))
    assert (old.permissions, old.metadata, old.bindings) == (new.permissions, new.metadata, new.bindings)
    inside_was, inside = _raw_entries(old.package), _raw_entries(new.package)
    assert {n for n in inside_was if inside_was[n] != inside[n]} == {"Formulas/Section1.m"}
    assert wq.read(second, path.name).section == edited
    assert (
        wq.written(second, wq.read(second, path.name), wq.plan(wq.read(second, path.name), _linked(edited)))
        == second
    )


def test_the_new_part_takes_a_free_number_and_an_item_with_no_xml_default_gets_its_own_type(
    tmp_path: Path,
) -> None:
    path = data.plain_workbook(tmp_path / "plain.xlsx")
    held = io.BytesIO()
    with zipfile.ZipFile(path) as old, zipfile.ZipFile(held, "w", zipfile.ZIP_DEFLATED) as new:
        for info in old.infolist():
            content = old.read(info)
            if info.filename == "[Content_Types].xml":
                content = re.sub(rb'<Default Extension="xml"[^>]*/>', b"", content)
                content = content.replace(
                    b"</Types>",
                    b'<Override PartName="/customXml/item1.xml" ContentType="application/xml"/></Types>',
                )
            new.writestr(info, content)
        new.writestr("customXml/item1.xml", "<notes xmlns='urn:made-up'>kept</notes>")
        new.writestr("customXml/itemProps3.xml", "<x/>")
    before = held.getvalue()
    found = wq.read(before, "plain.xlsx")
    assert found.part is None and found.free == 4
    after = wq.written(before, found, wq.plan(found, _linked(TWO), add=True))
    with zipfile.ZipFile(io.BytesIO(after)) as made:
        assert made.read("customXml/item1.xml") == b"<notes xmlns='urn:made-up'>kept</notes>"
        assert {"customXml/item4.xml", "customXml/itemProps4.xml", "customXml/_rels/item4.xml.rels"} <= set(
            made.namelist()
        )
        types = made.read("[Content_Types].xml")
        assert b'<Override PartName="/customXml/item4.xml" ContentType="application/xml"/>' in types
        assert b'Target="../customXml/item4.xml"' in made.read("xl/_rels/workbook.xml.rels")
        assert b'Target="itemProps4.xml"' in made.read("customXml/_rels/item4.xml.rels")
    assert wq.read(after, "plain.xlsx").part == "customXml/item4.xml"


# ===== the refusals =====


def test_it_is_never_added_without_the_explicit_word(tmp_path: Path) -> None:
    path = data.plain_workbook(tmp_path / "plain.xlsx")
    before = path.read_bytes()
    found = wq.read(before, path.name)
    with pytest.raises(wq.NoPowerQuery, match=r"no Power Query yet\. Add Power Query to this workbook"):
        wq.plan(found, _linked(TWO))
    with pytest.raises(wq.NoPowerQuery):
        wq.plan(found, _linked(TWO), add=False)
    assert issubclass(wq.NoPowerQuery, wq.Unreadable)
    # `add` on a workbook that has queries changes nothing about its save
    has = data.workbook(tmp_path / "has.xlsx")
    there = wq.read(has.read_bytes(), has.name)
    assert wq.plan(there, wq.linked_text("has.xlsx", data.SECTION), add=True).adds == ()


def test_a_text_that_cannot_be_a_workbooks_queries_is_refused_with_its_line(tmp_path: Path) -> None:
    found = wq.read(data.plain_workbook(tmp_path / "plain.xlsx").read_bytes(), "plain.xlsx")
    cases = {
        "section Section1;\n": ("no query to add", 3),
        "section Other;\nshared A = 1;\n": ("must be named Section1", 3),
        'section Section1;\n\nshared #"a.b" = 1;\n': ("cannot be a workbook query's name", 5),
        "section Section1;\nshared A = 1;\nshared A = 2;\n": ("written twice", 5),
        "let x = 1 in x": ("must start with `section Section1;`", 3),
    }
    for text, (words, line) in cases.items():
        with pytest.raises(wq.SectionError, match=re.escape(words)) as raised:
            wq.plan(found, _linked(text), add=True)
        assert raised.value.line == line, text


def _rewritten(path: Path, change: Mapping[str, bytes | None]) -> bytes:
    held = io.BytesIO()
    with zipfile.ZipFile(path) as old, zipfile.ZipFile(held, "w", zipfile.ZIP_DEFLATED) as new:
        for info in old.infolist():
            if info.filename in change:
                if change[info.filename] is not None:
                    new.writestr(info, change[info.filename] or b"")
                continue
            new.writestr(info, old.read(info))
    return held.getvalue()


def test_a_workbook_it_cannot_be_added_to_is_refused_and_not_changed(tmp_path: Path) -> None:
    path = data.plain_workbook(tmp_path / "plain.xlsx")
    with zipfile.ZipFile(path) as old:
        book, types = old.read("xl/workbook.xml"), old.read("[Content_Types].xml")
    strict = book.replace(
        b"http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        b"http://purl.oclc.org/ooxml/spreadsheetml/main",
    )
    cases: dict[str, dict[str, bytes | None]] = {
        "Strict Open XML": {"xl/workbook.xml": strict},
        "xl/_rels/workbook.xml.rels is not as expected": {"xl/_rels/workbook.xml.rels": None},
        "[Content_Types].xml is not as expected": {"[Content_Types].xml": types.replace(b"</Types>", b"")},
    }
    for words, change in cases.items():
        before = _rewritten(path, change)
        found = wq.read(before, "plain.xlsx")
        with pytest.raises(wq.Unreadable, match=re.escape(words)):
            wq.written(before, found, wq.plan(found, _linked(TWO), add=True))
    for refused in ("protected", "signed"):  # read refuses these before anything is planned
        more = (
            {"xl/workbook.xml": book.replace(b"<sheets>", b'<workbookProtection lockStructure="1"/><sheets>')}
            if refused == "protected"
            else {}
        )
        blob = _rewritten(path, more)
        if refused == "signed":
            held = io.BytesIO(blob)
            with zipfile.ZipFile(held, "a") as archive:
                archive.writestr("_xmlsignatures/sig1.xml", "<Signature/>")
            blob = held.getvalue()
        with pytest.raises(wq.Unreadable, match=refused):
            wq.read(blob, "plain.xlsx")
