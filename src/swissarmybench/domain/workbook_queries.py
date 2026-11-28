"""An Excel workbook's own Power Query, edited here and saved back (the owner, 2026-11-28: "I don't want to
edit power query in powerbi at all. I was the m and .pq features to be aimed at workbook development"; asked
which: "Excel's own Power Query").

Excel keeps a workbook's queries (Data, Get & Transform) in its **Data Mashup**: one `customXml/item<N>.xml`
part whose `DataMashup` element (namespace http://schemas.microsoft.com/DataMashup) holds base64 of a binary
stream. Microsoft publishes the format as **[MS-QDEFF] Query Definition File Format** (Open Specifications,
revision 8.1); this module follows it section by section, and docs/verified.md records what was checked:

  2.2  the top-level stream, every integer little-endian and unsigned:
         Version (4 bytes, MUST be 0) · Package Parts Length (4) · Package Parts · Permissions Length (4) ·
         Permissions · Metadata Length (4) · Metadata · Permission Bindings Length (4) · Permission Bindings
  2.3  Package Parts: an OPC package (a zip) of /Config/Package.xml, /Formulas/Section1.m (every query a
       member of the one section, which MUST be named Section1) and /Content/<guid> parts
  2.4  Permissions: UTF-8 XML (the privacy levels)
  2.5  Metadata: Version (4, MUST be 0) · Metadata XML Length (4) · Metadata XML (UTF-8; an Item per query,
       its ItemPath "Section1/<query>", its StableEntries) · Content Length (4) · Content (an OPC package)
  2.6  Permission Bindings: a checksum of Package Parts and Permissions protected with Windows' DPAPI for
       the user who saved it. A reader whose own checksum differs "MUST" discard Permissions and use the
       defaults: the queries are kept, the privacy levels are asked again. It cannot be made here (DPAPI),
       so it is kept as it is.

What a save changes: `Formulas/Section1.m` inside Package Parts, so Package Parts and its length; with a
query added, one Item in the Metadata XML, so the Metadata's lengths; the base64 in that one customXml
part. Everything else is copied byte for byte: every other entry of both zips is copied raw (its header,
its compressed bytes, its data descriptor), Permissions, the Metadata's Content and the Permission Bindings
as they are, and every other part of the workbook.

A linked file's first line names its workbook, relative to the file: `// workbook: Sales Report.xlsx`.

Pure rules: bytes in, bytes out. The standard library only; no I/O, no clock.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import posixpath
import re
import struct
import zlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree

NAMESPACE = "http://schemas.microsoft.com/DataMashup"
SECTION_PART = "Formulas/Section1.m"
SECTION_NAME = "Section1"
SUFFIXES: tuple[str, ...] = (".xlsx", ".xlsm")
TYPE = "powerquery_workbook"
HEADER = "// workbook:"
MAX_WORKBOOK_BYTES = 256 * 1024 * 1024
MAX_PART_BYTES = 64 * 1024 * 1024
ADD_IN_EXCEL = "Add it in Excel first (Data, Get Data, Blank Query), then edit it here."
CLOSE_IT = "Close it in Excel first."


class Unreadable(ValueError):
    """A workbook (or its Data Mashup) this cannot read, so never writes: one sentence."""


class SectionError(ValueError):
    """The queries' text cannot be saved into a workbook as it is: one sentence and its line."""

    def __init__(self, message: str, line: int = 1) -> None:
        super().__init__(message)
        self.line = line


# ===== a zip read and rewritten raw: one entry replaced, every other one copied byte for byte =====

_EOCD = struct.Struct("<4sHHHHIIH")
_CENTRAL = struct.Struct("<4sHHHHHHIIIHHHHHII")
_LOCAL = struct.Struct("<4sHHHHHIIIHH")
_ENCRYPTED, _DESCRIPTOR = 0x1, 0x8


@dataclass(frozen=True)
class _Entry:
    name: str
    record: tuple[Any, ...]  # its central directory record's fields
    tail: bytes  # the record's name, extra field and comment
    offset: int

    @property
    def flags(self) -> int:
        return int(self.record[3])


@dataclass(frozen=True)
class _Zip:
    entries: tuple[_Entry, ...]
    directory: int  # where the central directory starts
    comment: bytes


def _zip(data: bytes, what: str) -> _Zip:
    at = data.rfind(b"PK\x05\x06")
    if at < 0 or at + _EOCD.size > len(data):
        raise Unreadable(f"{what} is not a zip file.")
    _, disk, start_disk, here, total, size, directory, comment = _EOCD.unpack_from(data, at)
    if disk or start_disk or here != total or 0xFFFF in (total,) or 0xFFFFFFFF in (size, directory):
        raise Unreadable(f"{what} is a zip of a kind not read here (in several parts, or over 4 GB).")
    entries, place = [], directory
    for _ in range(total):
        if data[place : place + 4] != b"PK\x01\x02":
            raise Unreadable(f"{what}'s zip directory is damaged.")
        record = _CENTRAL.unpack_from(data, place)
        lengths = record[10] + record[11] + record[12]
        tail = data[place + _CENTRAL.size : place + _CENTRAL.size + lengths]
        raw_name = tail[: record[10]]
        name = raw_name.decode("utf-8" if record[3] & 0x800 else "cp437", "replace")
        entries.append(_Entry(name, record, tail, int(record[16])))
        place += _CENTRAL.size + lengths
    return _Zip(tuple(entries), directory, data[at + _EOCD.size : at + _EOCD.size + comment])


def zip_names(data: bytes, what: str = "The file") -> list[str]:
    return [e.name for e in _zip(data, what).entries]


def _found(archive: _Zip, name: str) -> _Entry | None:
    wanted = name.lstrip("/").casefold()
    return next((e for e in archive.entries if e.name.lstrip("/").casefold() == wanted), None)


def zip_read(data: bytes, name: str, what: str = "The file") -> bytes | None:
    """One entry's bytes (None: it has no such entry), its checksum checked."""
    entry = _found(_zip(data, what), name)
    if entry is None:
        return None
    if entry.flags & _ENCRYPTED:
        raise Unreadable(f"{what} is encrypted.")
    if data[entry.offset : entry.offset + 4] != b"PK\x03\x04":
        raise Unreadable(f"{what}'s zip is damaged at {entry.name}.")
    local = _LOCAL.unpack_from(data, entry.offset)
    start = entry.offset + _LOCAL.size + local[9] + local[10]
    method, crc, packed, size = entry.record[4], entry.record[7], entry.record[8], entry.record[9]
    if size > MAX_PART_BYTES:
        raise Unreadable(f"{what}'s {entry.name} is too large to read here.")
    raw = data[start : start + packed]
    try:
        plain = raw if method == 0 else zlib.decompressobj(-15).decompress(raw) if method == 8 else None
    except zlib.error:
        plain = None
    if plain is None or len(plain) != size or zlib.crc32(plain) != crc:
        raise Unreadable(f"{what}'s {entry.name} could not be read (its zip entry is damaged).")
    return plain


def zip_replace(data: bytes, name: str, content: bytes, what: str = "The file") -> bytes:
    """The zip with one entry's content replaced. Every other entry is copied raw, in its place: its local
    header, its bytes as they were compressed and its data descriptor; the central directory keeps every
    record as it was but for the offsets, and the replaced entry's checksum and sizes."""
    archive = _zip(data, what)
    target = _found(archive, name)
    if target is None:
        raise Unreadable(f"{what} has no {name}.")
    order = sorted(archive.entries, key=lambda e: e.offset)
    out = bytearray(data[: order[0].offset])
    moved: dict[str, int] = {}
    changed: tuple[Any, ...] = ()
    for at, entry in enumerate(order):
        end = order[at + 1].offset if at + 1 < len(order) else archive.directory
        moved[entry.name] = len(out)
        if entry is not target:
            out += data[entry.offset : end]
            continue
        local = _LOCAL.unpack_from(data, entry.offset)
        raw_name = data[entry.offset + _LOCAL.size : entry.offset + _LOCAL.size + local[9]]
        stored = entry.record[4] == 0
        packer = zlib.compressobj(6, zlib.DEFLATED, -15)
        packed = content if stored else packer.compress(content) + packer.flush()
        flags = entry.flags & ~_DESCRIPTOR
        crc = zlib.crc32(content)
        out += _LOCAL.pack(
            b"PK\x03\x04", local[1], flags, entry.record[4], local[4], local[5], crc, len(packed),
            len(content), len(raw_name), 0,
        )  # fmt: skip
        out += raw_name + packed
        changed = (crc, len(packed), len(content), flags)
    directory = len(out)
    for entry in archive.entries:
        record = list(entry.record)
        record[16] = moved[entry.name]
        if entry is target:
            record[7], record[8], record[9], record[3] = changed
        out += _CENTRAL.pack(*record) + entry.tail
    size = len(out) - directory
    count = len(archive.entries)
    out += _EOCD.pack(b"PK\x05\x06", 0, 0, count, count, size, directory, len(archive.comment))
    return bytes(out + archive.comment)


# ===== [MS-QDEFF] 2.2 and 2.5: the binary stream =====

_U32 = struct.Struct("<I")


class _Stream:
    def __init__(self, raw: bytes, what: str) -> None:
        self.raw, self.at, self.what = raw, 0, what

    def number(self) -> int:
        if self.at + 4 > len(self.raw):
            raise Unreadable(f"{self.what} ends before its lengths do: it is not read here.")
        (value,) = _U32.unpack_from(self.raw, self.at)
        self.at += 4
        return int(value)

    def field(self) -> bytes:
        length = self.number()
        if self.at + length > len(self.raw):
            raise Unreadable(f"{self.what} names a length past its end: it is not read here.")
        value = self.raw[self.at : self.at + length]
        self.at += length
        return value


def _sized(value: bytes) -> bytes:
    return _U32.pack(len(value)) + value


@dataclass(frozen=True)
class Mashup:
    """The top-level binary stream ([MS-QDEFF] 2.2): its four fields, each as its bytes."""

    package: bytes
    permissions: bytes
    metadata: bytes
    bindings: bytes

    def pack(self) -> bytes:
        """The stream again: Version 0, then each field after its own 4-byte length."""
        fields = (self.package, self.permissions, self.metadata, self.bindings)
        return _U32.pack(0) + b"".join(_sized(f) for f in fields)


def parse_mashup(raw: bytes) -> Mashup:
    stream = _Stream(raw, "The workbook's Data Mashup")
    version = stream.number()
    if version != 0:
        raise Unreadable(f"The workbook's Data Mashup is version {version}, and only version 0 is read here.")
    found = Mashup(stream.field(), stream.field(), stream.field(), stream.field())
    if stream.at != len(raw):
        raise Unreadable("The workbook's Data Mashup holds more than its four parts: it is not read here.")
    return found


@dataclass(frozen=True)
class Metadata:
    """The Metadata stream ([MS-QDEFF] 2.5): its XML and its Content package, each as its bytes."""

    xml: bytes
    content: bytes

    def pack(self) -> bytes:
        return _U32.pack(0) + _sized(self.xml) + _sized(self.content)


def parse_metadata(raw: bytes) -> Metadata:
    stream = _Stream(raw, "The Data Mashup's metadata")
    version = stream.number()
    if version != 0:
        raise Unreadable(f"The Data Mashup's metadata is version {version}, and only version 0 is read here.")
    found = Metadata(stream.field(), stream.field())
    if stream.at != len(raw):
        raise Unreadable("The Data Mashup's metadata holds more than its two parts: it is not read here.")
    return found


@dataclass(frozen=True)
class QueryFacts:
    """What the metadata says of one query (2.5.1's entries): whether it loads to a sheet or to the data
    model, the sheet's table it fills, and the columns of its last refresh (a record, not a rule: Excel
    writes them again on each Refresh)."""

    name: str
    to_sheet: bool = False
    to_model: bool = False
    target: str = ""
    columns: tuple[str, ...] = ()

    @property
    def loaded(self) -> bool:
        return self.to_sheet or self.to_model


def _percent(text: str, safe: str = "") -> str:
    """A name percent-encoded as a URI's data is (unreserved characters as they are)."""
    return "".join(
        c if (c.isascii() and c.isalnum()) or c in "-_.~" + safe else "".join(f"%{b:02X}" for b in c.encode())
        for c in text
    )


def _unpercent(text: str) -> str:
    return re.sub(
        r"(?:%[0-9A-Fa-f]{2})+",
        lambda found: bytes.fromhex(found.group().replace("%", "")).decode("utf-8", "replace"),
        text,
    )


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _column_names(value: str) -> tuple[str, ...]:
    try:
        names = json.loads(value)
    except ValueError:
        return ()
    return tuple(str(n) for n in names) if isinstance(names, list) else ()


def query_facts(xml: bytes) -> dict[str, QueryFacts]:
    """Each query's facts by its name, read from the Metadata XML (an ItemPath is "Section1/<query>", its
    name percent-encoded where Excel wrote it so; a deeper path is a step's, not a query's)."""
    try:
        if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
            raise ElementTree.ParseError("a DOCTYPE")
        root = ElementTree.fromstring(xml.decode("utf-8-sig"))  # noqa: S314 (a DOCTYPE is refused above)
    except (ElementTree.ParseError, UnicodeDecodeError):
        raise Unreadable("The Data Mashup's metadata is not XML: it is not read here.") from None
    facts: dict[str, QueryFacts] = {}
    for item in (e for e in root.iter() if _local(e.tag) == "Item"):
        kind = next((e.text or "" for e in item.iter() if _local(e.tag) == "ItemType"), "")
        path = next((e.text or "" for e in item.iter() if _local(e.tag) == "ItemPath"), "")
        parts = path.split("/")
        if kind != "Formula" or len(parts) != 2 or parts[0] != SECTION_NAME:
            continue
        entries = {
            str(e.get("Type")): str(e.get("Value") or "") for e in item.iter() if _local(e.tag) == "Entry"
        }
        facts[_unpercent(parts[1])] = QueryFacts(
            _unpercent(parts[1]),
            entries.get("FillEnabled") == "l1",
            entries.get("FillToDataModelEnabled") == "l1",
            entries.get("FillTarget", "")[1:],
            _column_names(entries.get("FillColumnNames", "")[1:]),
        )
    return facts


_ITEMS_END = re.compile(rb"</(?:\w+:)?Items\s*>")
_ITEMS_EMPTY = re.compile(rb"<Items\s*/>")
_ITEM_PATH = re.compile(rb"<ItemPath>([^<]*)</ItemPath>")


def _escaped(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def metadata_with(xml: bytes, added: Sequence[str]) -> bytes:
    """The Metadata XML with one Item per added query, written connection only: not loaded to a sheet
    (FillEnabled 0) nor to the data model (FillToDataModelEnabled 0). The Items are put before the end of
    <Items>; every other byte stays. A name that is not plain letters, digits and _ is written
    percent-encoded, as Excel writes its own, unless this workbook's other paths show it does not."""
    if not added:
        return xml
    paths = [p.decode("utf-8", "replace") for p in _ITEM_PATH.findall(xml)]
    literal = any("%" not in p and _percent(p, "/") != p for p in paths)
    items = "".join(
        "<Item><ItemLocation><ItemType>Formula</ItemType>"
        f"<ItemPath>{SECTION_NAME}/{_escaped(name if literal else _percent(name))}</ItemPath>"
        '</ItemLocation><StableEntries><Entry Type="IsPrivate" Value="l0" />'
        '<Entry Type="FillEnabled" Value="l0" /><Entry Type="FillToDataModelEnabled" Value="l0" />'
        "</StableEntries></Item>"
        for name in added
    ).encode("utf-8")
    ends = list(_ITEMS_END.finditer(xml))
    if ends:
        at = ends[-1].start()
        return xml[:at] + items + xml[at:]
    empty = _ITEMS_EMPTY.search(xml)
    if empty is None:
        raise Unreadable("The Data Mashup's metadata has no list of queries to add one to.")
    return xml[: empty.start()] + b"<Items>" + items + b"</Items>" + xml[empty.end() :]


# ===== the customXml part: the DataMashup element's base64 =====

_ELEMENT = re.compile(r"<DataMashup\b([^>]*)>([^<]*)</DataMashup\s*>")


@dataclass(frozen=True)
class _Item:
    """A customXml part as text: its byte-order mark, its encoding, and where the base64 is."""

    mark: bytes
    encoding: str
    text: str
    start: int
    end: int


def _item(raw: bytes) -> _Item | None:
    """The part read as the Data Mashup's, None when it is some other custom XML."""
    if raw[:2] == b"\xff\xfe":
        mark, encoding = raw[:2], "utf-16-le"
    elif raw[:2] == b"\xfe\xff":
        mark, encoding = raw[:2], "utf-16-be"
    elif raw[:3] == b"\xef\xbb\xbf":
        mark, encoding = raw[:3], "utf-8"
    elif len(raw) > 1 and raw[1:2] == b"\x00":
        mark, encoding = b"", "utf-16-le"
    else:
        mark, encoding = b"", "utf-8"
    try:
        text = raw[len(mark) :].decode(encoding)
    except UnicodeDecodeError:
        return None
    found = _ELEMENT.search(text)
    if found is None or NAMESPACE not in found.group(1):
        return None
    return _Item(mark, encoding, text, found.start(2), found.end(2))


# ===== the section's text: its members split, with no parser (a `;` ends each one) =====


@dataclass(frozen=True)
class Member:
    """One query of the section: its name, its whole text (the comments and blank lines before it, to its
    `;`), its line in the text, and its M alone."""

    name: str
    text: str
    line: int

    @property
    def m(self) -> str:
        return self.text.strip()


@dataclass(frozen=True)
class Section:
    name: str
    head: str
    members: tuple[Member, ...]
    tail: str

    def member(self, name: str) -> Member | None:
        return next((m for m in self.members if m.name == name), None)


def _statements(text: str) -> tuple[list[tuple[int, int]], int]:
    """Where each statement of the text is (start, end after its `;`), and where the last one ends. A `;`
    inside a text, a quoted name or a comment ends nothing."""
    found: list[tuple[int, int]] = []
    at, start, size = 0, 0, len(text)
    while at < size:
        two = text[at : at + 2]
        if two == "//":
            end = text.find("\n", at)
            at = size if end < 0 else end + 1
        elif two == "/*":
            end = text.find("*/", at + 2)
            if end < 0:
                raise SectionError("A /* comment is never closed.", text.count("\n", 0, at) + 1)
            at = end + 2
        elif text[at] == '"':
            opened = at
            at += 1
            while True:
                end = text.find('"', at)
                if end < 0:
                    raise SectionError(
                        'A text is never closed (its " is missing).', text.count("\n", 0, opened) + 1
                    )
                if text[end : end + 2] == '""':
                    at = end + 2
                    continue
                at = end + 1
                break
        elif text[at] == ";":
            found.append((start, at + 1))
            at += 1
            start = at
        else:
            at += 1
    return found, start


_TRIVIA = re.compile(r"(?:\s+|//[^\n]*(?:\n|$)|/\*.*?\*/)*", re.DOTALL)
_SECTION = re.compile(r"(?:\[.*\]\s*)?section\s+(#\"(?:[^\"]|\"\")*\"|[^\s;]+)\s*;", re.DOTALL)
_MEMBER = re.compile(r"(?:\[.*?\]\s*)?(?:shared\s+)?(#\"(?:[^\"]|\"\")*\"|[A-Za-z_][\w.]*)\s*=", re.DOTALL)


def _unquoted(name: str) -> str:
    return name[2:-1].replace('""', '"') if name.startswith('#"') else name


def split(text: str) -> Section:
    """A section document's members, each with its own text, so one can be compared, kept or put back."""
    statements, last = _statements(text)

    def line_of(at: int) -> int:
        return text.count("\n", 0, at) + 1

    if not statements:
        raise SectionError(
            f"The file must start with `section {SECTION_NAME};`: Excel keeps its queries in one."
        )
    first = text[statements[0][0] : statements[0][1]]
    head = _SECTION.fullmatch(first[_TRIVIA.match(first).end() :])  # type: ignore[union-attr]
    if head is None:
        raise SectionError(
            f"The file must start with `section {SECTION_NAME};`: Excel keeps its queries in one."
        )
    members: list[Member] = []
    for start, end in statements[1:]:
        whole = text[start:end]
        lead = _TRIVIA.match(whole).end()  # type: ignore[union-attr]
        named = _MEMBER.match(whole, lead)
        if named is None:
            raise SectionError(
                "This is not a query: each one is `shared Name = ...;`.", line_of(start + lead)
            )
        name = _unquoted(named.group(1))
        if any(m.name == name for m in members):
            raise SectionError(f"{name} is written twice: a workbook's queries each have their own name.",
                               line_of(start + lead))  # fmt: skip
        members.append(Member(name, whole, line_of(start + lead)))
    tail = text[last:]
    rest = _TRIVIA.match(tail).end()  # type: ignore[union-attr]
    if rest != len(tail):
        raise SectionError("The last query has no `;` at its end.", line_of(last + rest))
    return Section(_unquoted(head.group(1)), first, tuple(members), tail)


def name_problem(name: str) -> str | None:
    """Why a query's name cannot go into a workbook ([MS-QDEFF] 2.3.2), None when it can."""
    if not name.strip():
        return "A query needs a name."
    if name != name.strip() or any(c in name for c in '."\t\r\n'):
        return (
            f"{name.strip() or 'This name'} cannot be a workbook query's name: Excel takes no period, "
            "double quote, tab or line break in one, nor a space at either end."
        )
    return None


# ===== the linked file: its header line, and the section's text under it =====

_HEADER = re.compile(r"[ \t]*//[ \t]*workbook:[ \t]*(.*?)[ \t]*\r?(?:\n|$)", re.IGNORECASE)


def linked_to(text: str) -> str | None:
    """The workbook a Power Query file's first line names (`// workbook: Sales Report.xlsx`), as written:
    relative to the file. None: the file is not linked to one."""
    found = _HEADER.match(text.lstrip("﻿"))
    return (found.group(1) or None) if found else None


def body(text: str) -> tuple[str, int]:
    """The file's text without its header line (and the blank line after it): the section as it goes into
    the workbook; and how many lines were taken off (a line of the section is that many lower in the file)."""
    text = text.lstrip("﻿")
    found = _HEADER.match(text)
    if not found:
        return text, 0
    rest = text[found.end() :]
    blank = re.match(r"[ \t]*\r?\n", rest)
    return (rest[blank.end() :], 2) if blank else (rest, 1)


def relative_to(file: str, workbook: str) -> str:
    """The workbook as the file's header names it: relative to the file's folder, with `/`; its whole path
    when they share no root (another drive)."""
    folder = posixpath.dirname(file.replace("\\", "/"))
    target = workbook.replace("\\", "/")
    (drive, here), (other, there) = _drive(folder), _drive(target)
    if drive.casefold() != other.casefold() or not here.startswith("/") or not there.startswith("/"):
        return target
    return posixpath.relpath(there, here)


def _drive(path: str) -> tuple[str, str]:
    found = re.match(r"([A-Za-z]:)(.*)", path, re.DOTALL)
    return (found.group(1), found.group(2)) if found else ("", path)


def workbook_path(file: str, named: str) -> str:
    """The workbook a header names, as a whole path: relative to the file's folder."""
    named = named.replace("\\", "/")
    if posixpath.isabs(named) or re.match(r"[A-Za-z]:/", named):
        return named
    return posixpath.normpath(posixpath.join(posixpath.dirname(file.replace("\\", "/")), named))


def linked_text(workbook: str, section: str) -> str:
    """A linked file's text: the header line, a blank line, then the section as Excel wrote it (its own
    line ends kept, and used for the two lines above it)."""
    end = "\r\n" if "\r\n" in section else "\n"
    return f"{HEADER} {workbook}{end}{end}{section}"


def starter(tables: Sequence[str] = ()) -> str:
    """A workbook with no query yet: one section with one query Excel and the app's Run both read, the
    workbook's first named table through Excel.CurrentWorkbook, else a small table written out."""
    if tables:
        name = tables[0].replace('"', '""')
        source = f'    Source = Excel.CurrentWorkbook(){{[Name = "{name}"]}}[Content]\n'
    else:
        rows = '{{"North", 120}, {"South", 80}}'
        source = f"    Source = #table(type table [Region = text, Amount = number], {rows})\n"
    return f"section {SECTION_NAME};\n\nshared Query1 = let\n{source}in\n    Source;\n"


# ===== a workbook read =====

_TABLE_NAME = re.compile(rb"<table\b[^>]*?\bdisplayName=\"([^\"]*)\"")
_PROTECTED = re.compile(
    rb"<workbookProtection\b[^>]*\block(?:Structure|Windows|Revision)=[\"'](?:1|true)[\"']"
)
_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


@dataclass(frozen=True)
class Read:
    """A workbook's queries as read: the customXml part that holds them (None: it has no query yet), the
    stream, the section's text as Excel wrote it and its bytes' own mark, each query's facts, and the
    workbook's named tables."""

    name: str
    part: str | None = None
    mashup: Mashup | None = None
    section: str = ""
    mark: bytes = b""
    facts: dict[str, QueryFacts] = field(default_factory=dict)
    tables: tuple[str, ...] = ()

    @property
    def stamp(self) -> str:
        """What a conflict compares: the hash of the queries' text as the workbook holds it. A workbook
        saved in Excel with its queries as they were (cells edited, a Refresh) is not a conflict: a save
        here reads everything else from the file as it is then."""
        return hashlib.sha256(self.mark + self.section.encode("utf-8")).hexdigest()

    @property
    def text(self) -> str:
        """What a linked file opens with: Section1.m as Excel wrote it, else the starter."""
        return self.section if self.part is not None else starter(self.tables)


def _refuse_kind(data: bytes, name: str) -> None:
    lowered = name.lower()
    if lowered.endswith(".xls"):
        raise Unreadable(
            f"{name} is an older .xls workbook: save it as .xlsx in Excel to edit its queries here."
        )
    if lowered.endswith(".xlsb"):
        raise Unreadable(
            f"{name} is a binary .xlsb workbook: save it as .xlsx in Excel to edit its queries here."
        )
    if not lowered.endswith(SUFFIXES):
        raise Unreadable(f"{name} is not an Excel workbook (.xlsx or .xlsm).")
    if data[:8] == _OLE:
        raise Unreadable(
            f"{name} is encrypted (it opens with a password): its queries cannot be read or written here."
        )
    if data[:2] != b"PK":
        raise Unreadable(f"{name} is not an Excel workbook (it is not a zip).")


def read(data: bytes, name: str) -> Read:
    """The workbook's queries. Unreadable, in one sentence, for an .xls, an .xlsb, an encrypted, protected
    or signed workbook, and a Data Mashup that is not as [MS-QDEFF] says."""
    _refuse_kind(data, name)
    names = zip_names(data, name)
    book = zip_read(data, "xl/workbook.xml", name)
    if book is None:
        raise Unreadable(f"{name} is not an Excel workbook (it has no xl/workbook.xml).")
    if _PROTECTED.search(book):
        raise Unreadable(
            f"{name} is protected: unprotect the workbook in Excel (Review, Protect Workbook) first."
        )
    if any(n.startswith("_xmlsignatures/") for n in names):
        raise Unreadable(f"{name} is signed: a change to its queries would break its signature.")
    tables = tuple(
        found.group(1).decode("utf-8", "replace")
        for part in sorted(n for n in names if re.fullmatch(r"xl/tables/[^/]+\.xml", n))
        for found in [_TABLE_NAME.search(zip_read(data, part, name) or b"")]
        if found
    )
    parts = [
        (n, item)
        for n in names
        if re.fullmatch(r"customXml/item\d+\.xml", n, re.IGNORECASE)
        for item in [_item(zip_read(data, n, name) or b"")]
        if item is not None
    ]
    if not parts:
        return Read(name, tables=tables)
    if len(parts) > 1:
        raise Unreadable(f"{name} holds more than one Data Mashup: it is not read here.")
    part, item = parts[0]
    try:
        raw = base64.b64decode("".join(item.text[item.start : item.end].split()), validate=True)
    except (binascii.Error, ValueError):
        raise Unreadable(f"{name}'s Data Mashup is not base64: it is not read here.") from None
    mashup = parse_mashup(raw)
    section = zip_read(mashup.package, SECTION_PART, "The Data Mashup's package")
    if section is None:
        raise Unreadable(f"{name}'s Data Mashup has no {SECTION_PART}: it is not read here.")
    mark = b"\xef\xbb\xbf" if section[:3] == b"\xef\xbb\xbf" else b""
    try:
        text = section[len(mark) :].decode("utf-8")
    except UnicodeDecodeError:
        raise Unreadable(f"{name}'s queries are not UTF-8 text: they are not read here.") from None
    facts = query_facts(parse_metadata(mashup.metadata).xml)
    return Read(name, part, mashup, text, mark, facts, tables)


# ===== what a save would change, and the workbook's new bytes =====

CHANGED, ADDED, KEPT, SAME = "changed", "added", "kept", "same"


@dataclass(frozen=True)
class Change:
    query: str
    what: str
    words: str

    def to_json(self) -> dict[str, str]:
        return {"query": self.query, "what": self.what, "words": self.words}


@dataclass(frozen=True)
class Plan:
    """What a save does: the section's text as it goes into the workbook, each query changed, added, kept
    (taken out of the file, never out of the workbook) or the same, and whether anything is written."""

    section: str
    changes: tuple[Change, ...]
    writes: bool

    @property
    def added(self) -> tuple[str, ...]:
        return tuple(c.query for c in self.changes if c.what == ADDED)

    def count(self, what: str) -> int:
        return sum(1 for c in self.changes if c.what == what)

    def words(self, workbook: str) -> str:
        """The save notice's one sentence."""
        if not self.writes:
            return f"{workbook} already holds these queries: nothing was written."
        parts = [f"{self.count(w)} {w}" for w in (CHANGED, ADDED, KEPT) if self.count(w)]
        return f"Saved into {workbook}: {', '.join(parts)}. Excel runs them on its next Refresh."


def _changed_words(facts: QueryFacts | None) -> str:
    if facts is not None and facts.to_sheet:
        table = f" ({facts.target})" if facts.target else ""
        then = f"its sheet's table{table} takes its new columns then."
        return f"Changed: Excel runs it again on Refresh, and {then}"
    if facts is not None and facts.to_model:
        return "Changed: Excel runs it again on Refresh and loads it to the data model."
    return "Changed: connection only, run when a query that uses it refreshes."


def _line_ends(text: str, like: str) -> str:
    """The text with the line ends the workbook's own text uses (Excel writes CRLF)."""
    if "\r\n" in like and "\n" not in like.replace("\r\n", ""):
        return text.replace("\r\n", "\n").replace("\n", "\r\n")
    return text


def plan(found: Read, text: str) -> Plan:
    """What saving a linked file's text into its workbook does. SectionError (with the file's line) for a
    text that is not one section of named queries; Unreadable for a workbook with no query yet."""
    section, lines = body(text)
    if found.part is None or found.mashup is None:
        raise Unreadable(
            f"{found.name} has no Power Query yet, and its first one cannot be made here: add one in Excel "
            "first (Data, Get Data, Blank Query), then edit it here."
        )
    section = _line_ends(section, found.section)
    try:
        new, old = split(section), split(found.section)
    except SectionError as error:
        raise SectionError(str(error), error.line + lines) from None
    if new.name != SECTION_NAME:
        raise SectionError(f"The section must be named {SECTION_NAME}: Excel reads no other.", 1 + lines)
    changes: list[Change] = []
    for member in new.members:
        before = old.member(member.name)
        if before is None:
            problem = name_problem(member.name)
            if problem:
                raise SectionError(problem, member.line + lines)
            words = "Added as connection only (no sheet): load it to a sheet in Excel if you want one."
            changes.append(Change(member.name, ADDED, words))
        elif before.m != member.m:
            changes.append(Change(member.name, CHANGED, _changed_words(found.facts.get(member.name))))
        else:
            changes.append(Change(member.name, SAME, "The same."))
    end = "\r\n" if "\r\n" in found.section else "\n"
    for member in old.members:
        if new.member(member.name) is None:
            section = section.rstrip() + end + end + member.m + end
            words = "Kept in the workbook: a query is never removed from here. Delete it in Excel."
            changes.append(Change(member.name, KEPT, words))
    return Plan(section, tuple(changes), section != found.section)


def written(data: bytes, found: Read, planned: Plan) -> bytes:
    """The workbook's new bytes: Section1.m replaced inside the Data Mashup's package, an added query's
    Item in its metadata, every length written again, the base64 put back into the same customXml part.
    Nothing else of the workbook changes; a plan that writes nothing gives the same bytes."""
    if not planned.writes or found.part is None or found.mashup is None:
        return data
    mashup = found.mashup
    package = zip_replace(
        mashup.package,
        SECTION_PART,
        found.mark + planned.section.encode("utf-8"),
        "The Data Mashup's package",
    )
    metadata = mashup.metadata
    if planned.added:
        try:
            parsed = parse_metadata(metadata)
            metadata = Metadata(metadata_with(parsed.xml, planned.added), parsed.content).pack()
        except Unreadable:
            new = planned.added[0]
            raise Unreadable(
                f"{new} is new, and this workbook's metadata takes no new query here. {ADD_IN_EXCEL}"
            ) from None
    stream = Mashup(package, mashup.permissions, metadata, mashup.bindings).pack()
    raw = zip_read(data, found.part, found.name) or b""
    item = _item(raw)
    if item is None:
        raise Unreadable(f"{found.name}'s Data Mashup changed while it was being saved.")
    text = item.text[: item.start] + base64.b64encode(stream).decode("ascii") + item.text[item.end :]
    return zip_replace(data, found.part, item.mark + text.encode(item.encoding), found.name)


# ===== around the file: the lock Excel leaves, the one backup =====


def lock_names(name: str) -> tuple[str, ...]:
    """The owner files Office leaves beside an open document: `~$<name>`, and for a long name `~$` over its
    first two letters."""
    return (f"~${name}", f"~${name[2:]}")


def locked_words(name: str) -> str:
    return f"{name} is open in Excel. {CLOSE_IT}"


def conflict_words(name: str) -> str:
    return f"{name}'s queries changed on disk since this file was opened: Reload them, or Keep mine."


def backup_name(name: str) -> str:
    """Beside a workbook outside the open project: `<name>.backup.xlsx`."""
    stem, dot, ending = name.rpartition(".")
    return f"{stem}.backup{dot}{ending}"


BACKUP_FOLDER = ".sab/backup"
