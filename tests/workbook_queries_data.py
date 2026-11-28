"""Made-up Excel workbooks with Power Query in them, for tests/test_workbook_queries*.py and the browser test.

The workbook is openpyxl's (a sheet with a named table of made-up sales); its Data Mashup is made by hand,
exactly as [MS-QDEFF] says: the top-level stream (Version 0, then Package Parts, Permissions, Metadata and
Permission Bindings, each after its 4-byte little-endian length), the package an OPC zip of
[Content_Types].xml, Config/Package.xml and Formulas/Section1.m, the metadata a Version 0, the Metadata XML
after its length and an empty Content. The stream is base64 in customXml/item1.xml's DataMashup element,
UTF-16 with a byte-order mark as Excel writes that part. SPEC_EXAMPLE is the specification's own example
(section 3.1), as published.
"""

from __future__ import annotations

import base64
import io
import struct
import zipfile
from pathlib import Path

import openpyxl
from openpyxl.worksheet.table import Table

SECTION = (
    "section Section1;\r\n\r\n"
    "shared Sales = let\r\n"
    '    Source = Excel.CurrentWorkbook(){[Name = "SalesTable"]}[Content],\r\n'
    '    #"Big Ones" = Table.SelectRows(Source, each [Amount] > 100)\r\n'
    "in\r\n"
    '    #"Big Ones";\r\n\r\n'
    "shared Threshold = 100;\r\n\r\n"
    'shared #"By Region" = let\r\n'
    "    Source = Sales,\r\n"
    '    Grouped = Table.Group(Source, {"Region"}, {{"Total", each List.Sum([Amount]), type number}})\r\n'
    "in\r\n"
    "    Grouped;\r\n"
)
PERMISSIONS = (
    b"\xef\xbb\xbf"
    b'<?xml version="1.0" encoding="utf-8"?><PermissionList '
    b'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    b'xmlns:xsd="http://www.w3.org/2001/XMLSchema"><CanEvaluateFuturePackages>false</CanEvaluateFuturePackages>'
    b'<FirewallEnabled>true</FirewallEnabled><WorkbookGroupType xsi:nil="true" /></PermissionList>'
)
# Made-up bytes where Excel keeps its DPAPI checksum: kept as they are by a save.
BINDINGS = bytes(range(64, 104))
PACKAGE_XML = (
    b"\xef\xbb\xbf"
    b'<?xml version="1.0" encoding="utf-8"?><Package xmlns="http://schemas.microsoft.com/DataMashup">'
    b"<Version>2.132.328.0</Version><MinVersion>2.21.0.0</MinVersion><Culture>en-US</Culture></Package>"
)
CONTENT_TYPES = (
    b"\xef\xbb\xbf"
    b'<?xml version="1.0" encoding="utf-8"?>'
    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    b'<Default Extension="xml" ContentType="text/xml" />'
    b'<Default Extension="m" ContentType="application/x-ms-m" />'
    b"</Types>"
)


def _item(path: str, entries: str) -> str:
    kept = f"<StableEntries>{entries}</StableEntries>" if entries else "<StableEntries />"
    where = f"<ItemLocation><ItemType>Formula</ItemType><ItemPath>{path}</ItemPath></ItemLocation>"
    return f"<Item>{where}{kept}</Item>"


def metadata_xml() -> bytes:
    loaded = (
        '<Entry Type="IsPrivate" Value="l0" /><Entry Type="FillEnabled" Value="l1" />'
        '<Entry Type="FillToDataModelEnabled" Value="l0" /><Entry Type="ResultType" Value="sTable" />'
        '<Entry Type="FillTarget" Value="sSales" />'
        '<Entry Type="FillColumnNames" Value="s[&quot;Region&quot;,&quot;Amount&quot;]" />'
        '<Entry Type="FillLastUpdated" Value="d2026-11-02T09:15:00.0000000Z" />'
    )
    only = (
        '<Entry Type="IsPrivate" Value="l0" /><Entry Type="FillEnabled" Value="l0" />'
        '<Entry Type="FillToDataModelEnabled" Value="l0" />'
    )
    items = (
        "<Item><ItemLocation><ItemType>AllFormulas</ItemType><ItemPath /></ItemLocation>"
        "<StableEntries /></Item>"
        + _item("Section1/Sales", loaded)
        + _item("Section1/Sales/Source", "")
        + _item("Section1/Threshold", only)
        + _item("Section1/By%20Region", only)
    )
    return (
        b"\xef\xbb\xbf"
        + (
            '<?xml version="1.0" encoding="utf-8"?><LocalPackageMetadataFile '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">'
            f"<Items>{items}</Items></LocalPackageMetadataFile>"
        ).encode()
    )


def package(section: str = SECTION) -> bytes:
    """The Package Parts: an OPC zip, its parts in the order Excel writes them."""
    held = io.BytesIO()
    parts = {
        "Config/Package.xml": PACKAGE_XML,
        "[Content_Types].xml": CONTENT_TYPES,
        "Formulas/Section1.m": section.encode("utf-8"),
    }
    with zipfile.ZipFile(held, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():  # one made-up moment, so the same bytes every time
            info = zipfile.ZipInfo(name, (2026, 11, 2, 9, 15, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    return held.getvalue()


def _sized(value: bytes) -> bytes:
    return struct.pack("<I", len(value)) + value


def mashup(section: str = SECTION, version: int = 0) -> bytes:
    """The top-level binary stream of [MS-QDEFF] 2.2, made field by field."""
    metadata = struct.pack("<I", 0) + _sized(metadata_xml()) + _sized(b"")
    return (
        struct.pack("<I", version)
        + _sized(package(section))
        + _sized(PERMISSIONS)
        + _sized(metadata)
        + _sized(BINDINGS)
    )


def item_xml(stream: bytes) -> bytes:
    """customXml/item1.xml as Excel writes it: UTF-16 with its byte-order mark."""
    text = (
        '<?xml version="1.0" encoding="utf-16"?><DataMashup sqmid="6f1e2c1a-3b4d-4e5f-8a9b-0c1d2e3f4a5b" '
        f'xmlns="http://schemas.microsoft.com/DataMashup">{base64.b64encode(stream).decode()}</DataMashup>'
    )
    return b"\xff\xfe" + text.encode("utf-16-le")


def plain_workbook(path: Path) -> Path:
    """A workbook with one sheet and its named table SalesTable (made-up sales), and no query."""
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Data"
    rows = [("Region", "Amount"), ("North", 120), ("South", 80), ("East", 310), ("West", 45), ("North", 205)]
    for row in rows:
        sheet.append(row)
    sheet.add_table(Table(displayName="SalesTable", ref=f"A1:B{len(rows)}"))
    book.save(path)
    return path


def workbook(
    path: Path, section: str = SECTION, stream: bytes | None = None, more: dict[str, bytes] | None = None
) -> Path:
    """The same workbook with a Data Mashup of three queries (Sales loaded to a sheet, Threshold and
    By Region connection only), in customXml/item1.xml. `more`: other parts to add (a protection, a
    signature)."""
    plain_workbook(path)
    parts = {"customXml/item1.xml": item_xml(stream if stream is not None else mashup(section))}
    parts["customXml/itemProps1.xml"] = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="no"?><ds:datastoreItem '
        b'ds:itemID="{6F1E2C1A-3B4D-4E5F-8A9B-0C1D2E3F4A5B}" '
        b'xmlns:ds="http://schemas.openxmlformats.org/officeDocument/2006/customXml"><ds:schemaRefs>'
        b'<ds:schemaRef ds:uri="http://schemas.microsoft.com/DataMashup"/></ds:schemaRefs></ds:datastoreItem>'
    )
    with zipfile.ZipFile(path, "a", zipfile.ZIP_DEFLATED) as archive:
        for name, content in (parts | (more or {})).items():
            archive.writestr(name, content)
    return path


def parts_of(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def stream_of(path: Path) -> bytes:
    """The workbook's Data Mashup stream, read with the standard library alone."""
    text = parts_of(path)["customXml/item1.xml"][2:].decode("utf-16-le")
    return base64.b64decode(text.split(">", 2)[2].split("<", 1)[0])


def fields_of(stream: bytes) -> list[bytes]:
    """The stream's four fields, read by their lengths."""
    (version,) = struct.unpack_from("<I", stream, 0)
    assert version == 0
    found, at = [], 4
    for _ in range(4):
        (length,) = struct.unpack_from("<I", stream, at)
        found.append(stream[at + 4 : at + 4 + length])
        at += 4 + length
    assert at == len(stream)
    return found


def section_of(path: Path) -> str:
    """Section1.m as the workbook on disk holds it."""
    with zipfile.ZipFile(io.BytesIO(fields_of(stream_of(path))[0])) as archive:
        return archive.read("Formulas/Section1.m").decode("utf-8")


# [MS-QDEFF] section 3.1, the specification's own example of the root element's content.
SPEC_EXAMPLE = (
    "AAAAAEUDAABQSwMEFAACAAgAta0pR62KRJynAAAA+QAAABIAHABDb25maWcvUGFja2FnZS54bWwgohgAKKAUAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAhY9NDoIwGESvQrqnP4jGkI+ycCuJCdG4bUqFRiiGFsvdXHgkryCJYti5nMmb5M3r8YRsbJvgrnqrO5MihikKlJFd"
    "qU2VosFdwi3KOByEvIpKBRNsbDJanaLauVtCiPce+xXu+opElDJyzveFrFUrQm2sE0Yq9FuV/1eIw+kjwyMcxTimmzVmMWVA5h5y"
    "bRbMpIwpkEUJu6FxQ6+4MuGxADJHIN8b/A1QSwMEFAACAAgAta0pRw/K6aukAAAA6QAAABMAHABbQ29udGVudF9UeXBlc10ueG1s"
    "IKIYACigFAAAAAAAAAAAAAAAAAAAAAAAAAAAAG2OSw7CMAxErxJ5n7qwQAg1ZQHcgAtEwf2I5qPGReFsLDgSVyBtd4ilZ+Z55vN6"
    "V8dkB/GgMfbeKdgUJQhyxt961yqYuJF7ONbV9Rkoihx1UUHHHA6I0XRkdSx8IJedxo9Wcz7HFoM2d90Sbstyh8Y7JseS5x9QV2dq"
    "9DSwuKQsr7UZB3Fac3OVAqbEuMj4l7A/eR3C0BvN2cQkbZR2IXEZXn8BUEsDBBQAAgAIALWtKUdi3rmEPAAAAEsAAAATABwARm9y"
    "bXVsYXMvU2VjdGlvbjEubSCiGAAooBQAAAAAAAAAAAAAAAAAAAAAAAAAAAArTk0uyczPUwiG0IbWvFy8XMUZiUWpKQqBpalFlYYK"
    "tgo5qSW8XApAEJxfWpScChQx1Dbk5crMQxa1BgBQSwECLQAUAAIACAC1rSlHrYpEnKcAAAD5AAAAEgAAAAAAAAAAAAAAAAAAAAAA"
    "Q29uZmlnL1BhY2thZ2UueG1sUEsBAi0AFAACAAgAta0pRw/K6aukAAAA6QAAABMAAAAAAAAAAAAAAAAA8wAAAFtDb250ZW50X1R5"
    "cGVzXS54bWxQSwECLQAUAAIACAC1rSlHYt65hDwAAABLAAAAEwAAAAAAAAAAAAAAAADkAQAARm9ybXVsYXMvU2VjdGlvbjEubVBL"
    "BQYAAAAAAwADAMIAAABtAgAAAAA0AQAA77u/PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0idXRmLTgiPz48UGVybWlzc2lv"
    "bkxpc3QgeG1sbnM6eHNpPSJodHRwOi8vd3d3LnczLm9yZy8yMDAxL1hNTFNjaGVtYS1pbnN0YW5jZSIgeG1sbnM6eHNkPSJodHRw"
    "Oi8vd3d3LnczLm9yZy8yMDAxL1hNTFNjaGVtYSI+PENhbkV2YWx1YXRlRnV0dXJlUGFja2FnZXM+ZmFsc2U8L0NhbkV2YWx1YXRl"
    "RnV0dXJlUGFja2FnZXM+PEZpcmV3YWxsRW5hYmxlZD50cnVlPC9GaXJld2FsbEVuYWJsZWQ+PFdvcmtib29rR3JvdXBUeXBlIHhz"
    "aTpuaWw9InRydWUiIC8+PC9QZXJtaXNzaW9uTGlzdD7LBwAAAAAAAKkHAADvu788P3htbCB2ZXJzaW9uPSIxLjAiIGVuY29kaW5n"
    "PSJ1dGYtOCI/PjxMb2NhbFBhY2thZ2VNZXRhZGF0YUZpbGUgeG1sbnM6eHNpPSJodHRwOi8vd3d3LnczLm9yZy8yMDAxL1hNTFNj"
    "aGVtYS1pbnN0YW5jZSIgeG1sbnM6eHNkPSJodHRwOi8vd3d3LnczLm9yZy8yMDAxL1hNTFNjaGVtYSI+PEl0ZW1zPjxJdGVtPjxJ"
    "dGVtTG9jYXRpb24+PEl0ZW1UeXBlPkFsbEZvcm11bGFzPC9JdGVtVHlwZT48SXRlbVBhdGggLz48L0l0ZW1Mb2NhdGlvbj48U3Rh"
    "YmxlRW50cmllcyAvPjwvSXRlbT48SXRlbT48SXRlbUxvY2F0aW9uPjxJdGVtVHlwZT5Gb3JtdWxhPC9JdGVtVHlwZT48SXRlbVBh"
    "dGg+U2VjdGlvbjEvUXVlcnkxPC9JdGVtUGF0aD48L0l0ZW1Mb2NhdGlvbj48U3RhYmxlRW50cmllcz48RW50cnkgVHlwZT0iSXNQ"
    "cml2YXRlIiBWYWx1ZT0ibDAiIC8+PEVudHJ5IFR5cGU9IlJlc3VsdFR5cGUiIFZhbHVlPSJzTnVtYmVyIiAvPjxFbnRyeSBUeXBl"
    "PSJGaWxsRW5hYmxlZCIgVmFsdWU9ImwxIiAvPjxFbnRyeSBUeXBlPSJGaWxsVG9EYXRhTW9kZWxFbmFibGVkIiBWYWx1ZT0ibDAi"
    "IC8+PEVudHJ5IFR5cGU9IkZpbGxDb3VudCIgVmFsdWU9ImwxIiAvPjxFbnRyeSBUeXBlPSJGaWxsRXJyb3JDb3VudCIgVmFsdWU9"
    "ImwwIiAvPjxFbnRyeSBUeXBlPSJGaWxsQ29sdW1uVHlwZXMiIFZhbHVlPSJzQlE9PSIgLz48RW50cnkgVHlwZT0iRmlsbENvbHVt"
    "bk5hbWVzIiBWYWx1ZT0ic1smcXVvdDtRdWVyeTEmcXVvdDtdIiAvPjxFbnRyeSBUeXBlPSJGaWxsRXJyb3JDb2RlIiBWYWx1ZT0i"
    "c1Vua25vd24iIC8+PEVudHJ5IFR5cGU9IkZpbGxMYXN0VXBkYXRlZCIgVmFsdWU9ImQyMDE1LTA5LTEwVDA0OjQ1OjQxLjkyNzU5"
    "MDBaIiAvPjxFbnRyeSBUeXBlPSJSZWxhdGlvbnNoaXBJbmZvQ29udGFpbmVyIiBWYWx1ZT0ic3smcXVvdDtjb2x1bW5Db3VudCZx"
    "dW90OzoxLCZxdW90O2tleUNvbHVtbk5hbWVzJnF1b3Q7OltdLCZxdW90O3F1ZXJ5UmVsYXRpb25zaGlwcyZxdW90OzpbXSwmcXVv"
    "dDtjb2x1bW5JZGVudGl0aWVzJnF1b3Q7OlsmcXVvdDtTZWN0aW9uMS9RdWVyeTEvQXV0b1JlbW92ZWRDb2x1bW5zMS57UXVlcnkx"
    "LDB9JnF1b3Q7XSwmcXVvdDtDb2x1bW5Db3VudCZxdW90OzoxLCZxdW90O0tleUNvbHVtbk5hbWVzJnF1b3Q7OltdLCZxdW90O0Nv"
    "bHVtbklkZW50aXRpZXMmcXVvdDs6WyZxdW90O1NlY3Rpb24xL1F1ZXJ5MS9BdXRvUmVtb3ZlZENvbHVtbnMxLntRdWVyeTEsMH0m"
    "cXVvdDtdLCZxdW90O1JlbGF0aW9uc2hpcEluZm8mcXVvdDs6W119IiAvPjxFbnRyeSBUeXBlPSJGaWxsZWRDb21wbGV0ZVJlc3Vs"
    "dFRvV29ya3NoZWV0IiBWYWx1ZT0ibDEiIC8+PEVudHJ5IFR5cGU9IkFkZGVkVG9EYXRhTW9kZWwiIFZhbHVlPSJsMCIgLz48RW50"
    "cnkgVHlwZT0iUmVjb3ZlcnlUYXJnZXRTaGVldCIgVmFsdWU9InNTaGVldDIiIC8+PEVudHJ5IFR5cGU9IlJlY292ZXJ5VGFyZ2V0"
    "Q29sdW1uIiBWYWx1ZT0ibDEiIC8+PEVudHJ5IFR5cGU9IlJlY292ZXJ5VGFyZ2V0Um93IiBWYWx1ZT0ibDEiIC8+PEVudHJ5IFR5"
    "cGU9Ik5hbWVVcGRhdGVkQWZ0ZXJGaWxsIiBWYWx1ZT0ibDAiIC8+PEVudHJ5IFR5cGU9IkZpbGxUYXJnZXQiIFZhbHVlPSJzUXVl"
    "cnkxIiAvPjxFbnRyeSBUeXBlPSJCdWZmZXJOZXh0UmVmcmVzaCIgVmFsdWU9ImwxIiAvPjxFbnRyeSBUeXBlPSJGaWxsU3RhdHVz"
    "IiBWYWx1ZT0ic0NvbXBsZXRlIiAvPjxFbnRyeSBUeXBlPSJRdWVyeUlEIiBWYWx1ZT0iczdlMDQzNjJlLTkyZjUtNGQ4Mi04YjA3"
    "LTI3NjFlYWY2OGFlNSIgLz48L1N0YWJsZUVudHJpZXM+PC9JdGVtPjxJdGVtPjxJdGVtTG9jYXRpb24+PEl0ZW1UeXBlPkZvcm11"
    "bGE8L0l0ZW1UeXBlPjxJdGVtUGF0aD5TZWN0aW9uMS9RdWVyeTEvU291cmNlPC9JdGVtUGF0aD48L0l0ZW1Mb2NhdGlvbj48U3Rh"
    "YmxlRW50cmllcyAvPjwvSXRlbT48L0l0ZW1zPjwvTG9jYWxQYWNrYWdlTWV0YWRhdGFGaWxlPhYAAABQSwUGAAAAAAAAAAAAAAAA"
    "AAAAAAAA2gAAAAEAAADQjJ3fARXREYx6AMBPwpfrAQAAACLWGAG5O6FHjkAGtB+m5EQAAAAAAgAAAAAAA2YAAMAAAAAQAAAAaH8K"
    "Ne2ciHwfVosIvSCr6gAAAAAEgAAAoAAAABAAAAA40fOKWe6kmTAWJSBXs4cYUAAAAPNy7uF6Dtr9PvADu+eZdeV7JutpIQTh41qq"
    "T3QnFoWPwE0Xyrur5N6Q2s2TEzjlBDfkEmNaGtr3htemOjWZYXKQHP+R5u/90zHWiwOwjjowFAAAAF2UC6Jm8C98hVmJBo638e4Q"
    "k65V"
)
