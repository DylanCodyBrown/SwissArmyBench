"""Structures (the owner, 2026-11-17: "when an API returns data or a payload or you need to author a Json,
Yaml, Xml or other type of data structure, we need a place to visualize them ... that functions like the
grids, where you can transform and save json configurations as well as view returned payloads"; "you can
have json, yaml, and xml that is not a part of an api, they could be used for gates, mapping, and other
various things"). Grids hold rows and columns; Structures hold nested data.

  formats    JSON, YAML (read and written by the adapter, PyYAML, never the app's dependency), XML (the
             standard library's ElementTree, a document with a DOCTYPE or an entity refused outright:
             there is no defusedxml here) and TOML (tomllib reads it; written here, standard library)
  paths      `$.orders[3].lines`, `$["odd key"]`, `[*]` for every item; parsed, written, resolved
  steps      a structure's transformations as data, replayed on the original (which is never changed
             until Save): Pick a path, Filter a list, Rename key, Remove key, Set value, Add key, Sort
             a list, Flatten a list of records; each in plain words
  records    a list of records at any path, flattened (dotted keys) for Open as grid
  shape      what the agent reads: types, counts, keys and the paths of record lists (never the values
             wholesale: a preview is capped like a grid's rows)
  references `sab.structure("gates")` in the user's code (domain/connection_usage.py's finder)

Standard library only; no I/O.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import math
import re
import tomllib
import xml.etree.ElementTree as ElementTree
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

FORMATS: tuple[str, ...] = ("json", "yaml", "xml", "toml")
FORMAT_NAMES: dict[str, str] = {"json": "JSON", "yaml": "YAML", "xml": "XML", "toml": "TOML"}
SUFFIXES: dict[str, str] = {".json": "json", ".yaml": "yaml", ".yml": "yaml", ".xml": "xml", ".toml": "toml"}
SUFFIX_OF: dict[str, str] = {"json": ".json", "yaml": ".yaml", "xml": ".xml", "toml": ".toml"}
MAX_CHARS: int = 50_000_000
MAX_STEPS: int = 200
MAX_DEPTH: int = 200
OPS: tuple[str, ...] = ("pick", "filter", "rename", "remove", "set", "add", "sort", "flatten")
TESTS: tuple[str, ...] = ("=", "!=", ">", ">=", "<", "<=", "contains", "starts with", "exists", "missing")
# The client's calls that name a structure first (sab.structure("gates")): the reference finder's words.
CALLS: dict[str, str] = {"structure": "sab.structure", "structure_table": "sab.structure_table"}
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
_REFUSED_XML = re.compile(r"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)
_XML_NAME = re.compile(r"^(\{[^}]*\})?[A-Za-z_][A-Za-z0-9._-]*$")
_TOML_BARE = re.compile(r"^[A-Za-z0-9_-]+$")
_FILE_NAME = re.compile(r"^[^\\/:*?\"<>|\x00-\x1f]{1,120}$")


class StructureError(ValueError):
    """A document, a path or a step that cannot be used as given; the message says why in plain words."""


# ===== formats =====


def format_of(file_name: str) -> str | None:
    """The format a file's suffix names (None: not a structure's file)."""
    dot = file_name.rfind(".")
    return SUFFIXES.get(file_name[dot:].lower()) if dot >= 0 else None


def detect(text: str) -> str:
    """The format a pasted text is written in: JSON, XML, TOML or YAML (the rest)."""
    start = text.lstrip("﻿ \t\r\n")
    if start.startswith(("{", "[")):
        try:
            json.loads(start)
            return "json"
        except ValueError:
            if start.startswith("{"):
                return "json"  # broken JSON: said as JSON's error, with its line
            # `[table]` is TOML's
    if start.startswith("<"):
        return "xml"
    first = next(
        (line.strip() for line in start.splitlines() if line.strip() and not line.strip().startswith("#")), ""
    )
    if re.match(r"^\[\[?[A-Za-z0-9_.\"' -]+\]\]?$", first) or re.match(r"^[A-Za-z0-9_.\"-]+\s*=", first):
        return "toml"
    return "yaml"


def check_format(value: Any) -> str:
    said = str(value or "").strip().lower()
    said = {"yml": "yaml"}.get(said, said)
    if said not in FORMATS:
        raise StructureError("A structure's format is json, yaml, xml or toml.")
    return said


def _plain(value: Any) -> Any:
    """A value as JSON can hold it: TOML's dates and times become ISO text."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    return value


def parse(text: str, fmt: str) -> Any:
    """JSON, XML or TOML as a structure (YAML is the adapter's: PyYAML). An error says where."""
    if len(text) > MAX_CHARS:
        raise StructureError("The document is too big (50 MB at most).")
    if fmt == "json":
        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            raise StructureError(
                f"Not JSON: line {error.lineno}, column {error.colno}: {error.msg}."
            ) from None
    if fmt == "xml":
        return parse_xml(text)
    if fmt == "toml":
        try:
            return _plain(tomllib.loads(text))
        except tomllib.TOMLDecodeError as error:
            raise StructureError(f"Not TOML: {error}.") from None
    raise StructureError(f"{FORMAT_NAMES.get(fmt, fmt)} is read by the adapter.")


def dump(value: Any, fmt: str) -> str:
    """A structure written as JSON, XML or TOML (YAML is the adapter's)."""
    if fmt == "json":
        return json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    if fmt == "xml":
        return dump_xml(value)
    if fmt == "toml":
        return dump_toml(value)
    raise StructureError(f"{FORMAT_NAMES.get(fmt, fmt)} is written by the adapter.")


# ===== XML: {"root": {"@attribute": "1", "#text": "...", "child": [...]}} =====

ATTRIBUTE = "@"
TEXT = "#text"


def parse_xml(text: str) -> Any:
    """XML as a structure: the root element as {tag: value}; attributes as "@name", text beside children
    as "#text", a repeated child as a list. A DOCTYPE or an entity declaration is refused outright (this
    Python has no defusedxml: an entity could expand without end or read a file)."""
    if _REFUSED_XML.search(text):
        raise StructureError(
            "This XML declares a DOCTYPE or an entity: it is refused (an entity can expand without end "
            "or reach a file). Remove the <!DOCTYPE ...> to open it."
        )
    try:
        root = ElementTree.fromstring(text)  # noqa: S314 (a DOCTYPE or an entity is refused above)
    except ElementTree.ParseError as error:
        line, column = error.position
        raise StructureError(
            f"Not XML: line {line}, column {column + 1}: {str(error).split(':')[0]}."
        ) from None
    return {root.tag: _element(root)}


def _element(element: ElementTree.Element) -> Any:
    out: dict[str, Any] = {f"{ATTRIBUTE}{k}": v for k, v in element.attrib.items()}
    for child in element:
        if not isinstance(child.tag, str):
            continue  # a comment or a processing instruction
        value = _element(child)
        if child.tag in out:
            if not isinstance(out[child.tag], list):
                out[child.tag] = [out[child.tag]]
            out[child.tag].append(value)
        else:
            out[child.tag] = value
    words = (element.text or "").strip()
    if not out:
        return words
    if words:
        out[TEXT] = words
    return out


def _xml_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _check_tag(tag: str, at: str) -> str:
    if not _XML_NAME.match(tag) or (tag.lower().startswith("xml") and not tag.startswith("{")):
        raise StructureError(f"{at}: {tag!r} cannot be an XML element's name: save as JSON or YAML instead.")
    return tag


def _fill(element: ElementTree.Element, value: Any, at: str) -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            key = str(key)
            if key == TEXT:
                element.text = _xml_text(inner)
            elif key.startswith(ATTRIBUTE):
                element.set(_check_tag(key[1:], at), _xml_text(inner))
            else:
                for one in inner if isinstance(inner, list) else [inner]:
                    child = ElementTree.SubElement(element, _check_tag(key, at))
                    _fill(child, one, f"{at}.{key}")
    elif isinstance(value, list):
        for one in value:
            _fill(ElementTree.SubElement(element, "item"), one, f"{at}[]")
    else:
        element.text = _xml_text(value)


def dump_xml(value: Any) -> str:
    """A structure as XML: one key at the top is the root element's tag (else a <root> holds it)."""
    if isinstance(value, dict) and len(value) == 1 and not next(iter(value)).startswith((ATTRIBUTE, "#")):
        tag, inner = next(iter(value.items()))
        if isinstance(inner, list):
            tag, inner = "root", value
    else:
        tag, inner = "root", value
    root = ElementTree.Element(_check_tag(str(tag), "$"))
    _fill(root, inner, "$")
    ElementTree.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ElementTree.tostring(root, encoding="unicode") + "\n"


# ===== TOML: written here (tomllib only reads) =====


def _toml_key(key: str) -> str:
    return key if _TOML_BARE.match(key) else json.dumps(key, ensure_ascii=False)


def _toml_value(value: Any, at: str) -> str:
    if value is None:
        raise StructureError(f"TOML has no empty value (null), at {at}: save as JSON or YAML instead.")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v, f"{at}[{n}]") for n, v in enumerate(value)) + "]"
    if isinstance(value, dict):
        inner = ", ".join(f"{_toml_key(str(k))} = {_toml_value(v, f'{at}.{k}')}" for k, v in value.items())
        return "{" + inner + "}" if inner else "{}"
    raise StructureError(f"TOML cannot hold the value at {at}.")


def _is_tables(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(v, dict) for v in value)


def _toml_table(table: Mapping[str, Any], prefix: str, lines: list[str], at: str) -> None:
    plain = [(k, v) for k, v in table.items() if not isinstance(v, dict) and not _is_tables(v)]
    for key, value in plain:
        lines.append(f"{_toml_key(str(key))} = {_toml_value(value, f'{at}.{key}')}")
    for key, value in table.items():
        name = f"{prefix}.{_toml_key(str(key))}" if prefix else _toml_key(str(key))
        if isinstance(value, dict):
            lines += ["", f"[{name}]"]
            _toml_table(value, name, lines, f"{at}.{key}")
        elif _is_tables(value):
            for n, item in enumerate(value):
                lines += ["", f"[[{name}]]"]
                _toml_table(item, name, lines, f"{at}.{key}[{n}]")


def dump_toml(value: Any) -> str:
    """A structure as TOML: an object at the top; no null anywhere (TOML has none)."""
    if not isinstance(value, dict):
        raise StructureError("TOML holds an object at the top (key = value): save a list as JSON or YAML.")
    lines: list[str] = []
    _toml_table(value, "", lines, "$")
    return "\n".join(lines).lstrip("\n") + "\n"


# ===== paths: $.orders[3].lines, $["odd key"], [*] =====

WILD = None  # a path part that is every item (or every key's value) of the node


def parse_path(text: Any) -> tuple[str | int | None, ...]:
    """`$.orders[3]["unit price"]` as its parts (a key, an index or WILD for `[*]`)."""
    said = str(text if text is not None else "$").strip()
    if not said or said == "$":
        return ()
    if not said.startswith("$"):
        said = "$." + said if not said.startswith("[") else "$" + said
    parts: list[str | int | None] = []
    at = 1
    while at < len(said):
        char = said[at]
        if char == ".":
            if said[at + 1 : at + 2] == "*":
                parts.append(WILD)
                at += 2
                continue
            found = _NAME.match(said, at + 1)
            if not found:
                raise StructureError(f'{said}: a name follows each dot (or write ["the key"]).')
            parts.append(found.group())
            at = found.end()
        elif char == "[":
            end = said.find("]", at)
            if said[at + 1 : at + 2] in ('"', "'"):
                quote = said[at + 1]
                close = at + 2
                while close < len(said) and said[close] != quote:
                    close += 2 if said[close] == "\\" else 1
                if close >= len(said) or said[close + 1 : close + 2] != "]":
                    raise StructureError(f"{said}: a quoted key ends with its quote and ].")
                inner = said[at + 1 : close + 1]
                try:
                    key = json.loads(inner) if quote == '"' else inner[1:-1]
                except ValueError:
                    raise StructureError(f"{said}: the key {inner} cannot be read.") from None
                parts.append(str(key))
                at = close + 2
                continue
            if end < 0:
                raise StructureError(f"{said}: a [ has no ].")
            inner = said[at + 1 : end].strip()
            if inner == "*":
                parts.append(WILD)
            elif re.fullmatch(r"-?\d+", inner):
                parts.append(int(inner))
            else:
                raise StructureError(f"{said}: [{inner}] is a number, * or a quoted key.")
            at = end + 1
        else:
            raise StructureError(f'{said}: a path goes on with .name, [n], [*] or ["key"].')
    return tuple(parts)


def format_path(parts: tuple[str | int | None, ...] | list[str | int | None]) -> str:
    out = "$"
    for part in parts:
        if part is WILD:
            out += "[*]"
        elif isinstance(part, int):
            out += f"[{part}]"
        elif _NAME.fullmatch(part):
            out += f".{part}"
        else:
            out += "[" + json.dumps(part, ensure_ascii=False) + "]"
    return out


def _child(node: Any, part: str | int) -> tuple[bool, Any]:
    if isinstance(part, int) and isinstance(node, list):
        if -len(node) <= part < len(node):
            return True, node[part]
        return False, None
    if isinstance(part, str) and isinstance(node, dict) and part in node:
        return True, node[part]
    return False, None


def resolve(value: Any, parts: tuple[str | int | None, ...]) -> list[tuple[tuple[str | int, ...], Any]]:
    """Every node a path reaches, each with its own path (no WILD in it): none when it reaches nothing."""
    found: list[tuple[tuple[str | int, ...], Any]] = [((), value)]
    for part in parts:
        reached: list[tuple[tuple[str | int, ...], Any]] = []
        for where, node in found:
            if part is WILD:
                if isinstance(node, list):
                    reached += [((*where, n), item) for n, item in enumerate(node)]
                elif isinstance(node, dict):
                    reached += [((*where, k), item) for k, item in node.items()]
            else:
                ok, child = _child(node, part)
                if ok:
                    index = part % len(node) if isinstance(part, int) else part
                    reached.append(((*where, index), child))
        found = reached
    return found


def get(value: Any, path: Any) -> Any:
    """The one node a path (with no [*]) reaches; a StructureError when it is not there."""
    parts = parse_path(path)
    if WILD in parts:
        raise StructureError(f"{format_path(parts)} reaches many nodes: name one.")
    found = resolve(value, parts)
    if not found:
        raise StructureError(f"{format_path(parts)} is not there.")
    return found[0][1]


def _field(item: Any, field: tuple[str | int | None, ...]) -> tuple[bool, Any]:
    if not field:
        return True, item
    found = resolve(item, field)
    return (True, found[0][1]) if found else (False, None)


# ===== steps =====


@dataclass(frozen=True)
class Step:
    op: str
    path: str = "$"
    key: str = ""  # rename's and add's key
    to: str = ""  # rename's new name
    field: str = ""  # filter's and sort's field, inside each item ("" the item itself)
    test: str = "="
    value: Any = None  # filter's value, set's and add's value
    descending: bool = False

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"op": self.op, "path": self.path}
        if self.op in ("rename", "add"):
            out["key"] = self.key
        if self.op == "rename":
            out["to"] = self.to
        if self.op in ("filter", "sort"):
            out["field"] = self.field
        if self.op == "filter":
            out["test"] = self.test
        if self.op in ("filter", "set", "add"):
            out["value"] = self.value
        if self.op == "sort":
            out["descending"] = self.descending
        return out


def check_step(raw: Any) -> Step:
    """A step as the page or the agent sends it, checked."""
    if not isinstance(raw, Mapping):
        raise StructureError('A step is {"op": "pick", "path": "$.orders"}.')
    op = str(raw.get("op") or "").strip().lower()
    if op not in OPS:
        raise StructureError(f"A step's op is one of {', '.join(OPS)}.")
    path = format_path(parse_path(raw.get("path", "$")))
    key, to, field = str(raw.get("key") or ""), str(raw.get("to") or ""), str(raw.get("field") or "")
    if op in ("rename", "add") and not key:
        raise StructureError(f"{op.capitalize()} names the key.")
    if op == "rename" and not to:
        raise StructureError("Rename names the new key (to).")
    if op == "remove" and not parse_path(path):
        raise StructureError("Remove names what to remove: $ is the whole structure.")
    if op == "set" and "value" not in raw:
        raise StructureError("Set gives the value.")
    if field:
        field = format_path(parse_path(field))[1:].lstrip(".")
    test = str(raw.get("test") or "=").strip().lower()
    if op == "filter" and test not in TESTS:
        raise StructureError(f"A filter's test is one of {', '.join(TESTS)}.")
    value = raw.get("value")
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        raise StructureError("A step's value is a JSON value.") from None
    return Step(op, path, key, to, field, test, value, bool(raw.get("descending")))


def _words(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value


def describe(step: Step) -> str:
    """A step in plain words (the strip and the steps window)."""
    where = step.path
    field = step.field or "the item"
    if step.op == "pick":
        return f"Pick {where}"
    if step.op == "filter":
        tail = "" if step.test in ("exists", "missing") else f" {_words(step.value)}"
        return f"Keep {where} where {field} {step.test}{tail}"
    if step.op == "rename":
        return f"Rename {step.key} to {step.to} in {where}"
    if step.op == "remove":
        return f"Remove {where}"
    if step.op == "set":
        return f"Set {where} to {_words(step.value)}"
    if step.op == "add":
        return f"Add {step.key} = {_words(step.value)} to {where}"
    if step.op == "sort":
        return f"Sort {where} by {field}{', largest first' if step.descending else ''}"
    return f"Flatten {where}"


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _same(found: Any, given: Any) -> bool:
    if isinstance(found, bool) or isinstance(given, bool):
        return str(found).lower() == str(given).lower()
    a, b = _number(found), _number(given)
    if a is not None and b is not None and not isinstance(found, str):
        return a == b
    return _words(found) == _words(given) if found is not None else given in (None, "null", "")


def matches(item: Any, step: Step) -> bool:
    """Whether a list's item passes a filter step."""
    ok, found = _field(item, parse_path(step.field))
    if step.test == "exists":
        return ok
    if step.test == "missing":
        return not ok
    if not ok:
        return step.test == "!="
    if step.test == "=":
        return _same(found, step.value)
    if step.test == "!=":
        return not _same(found, step.value)
    if step.test == "contains":
        if isinstance(found, list):
            return any(_same(f, step.value) for f in found)
        return _words(step.value).casefold() in _words(found).casefold()
    if step.test == "starts with":
        return _words(found).casefold().startswith(_words(step.value).casefold())
    a, b = _number(found), _number(step.value)
    if a is None or b is None:
        a_text, b_text = _words(found), _words(step.value)
        pairs = {">": a_text > b_text, ">=": a_text >= b_text, "<": a_text < b_text, "<=": a_text <= b_text}
        return pairs[step.test]
    return {">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b}[step.test]


def _sort_key(item: Any, field: tuple[str | int | None, ...]) -> tuple[int, Any]:
    ok, value = _field(item, field)
    if not ok or value is None:
        return (3, "")
    if isinstance(value, bool):
        return (1, int(value))
    if isinstance(value, int | float):
        return (0, value)
    if isinstance(value, str):
        return (2, value.casefold())
    return (2, _words(value))


def flatten_record(record: Any, prefix: str = "") -> dict[str, Any]:
    """A record with its nested objects' keys dotted (customer.region); lists kept as they are."""
    if not isinstance(record, dict):
        return {prefix or "value": record}
    out: dict[str, Any] = {}
    for key, value in record.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict) and value:
            out |= flatten_record(value, name)
        else:
            out[name] = value
    return out


def _parent(value: Any, where: tuple[str | int, ...]) -> Any:
    node = value
    for part in where[:-1]:
        node = node[part]
    return node


def _replace(value: Any, where: tuple[str | int, ...], new: Any) -> Any:
    if not where:
        return new
    _parent(value, where)[where[-1]] = new
    return value


def _apply(value: Any, step: Step) -> Any:
    parts = parse_path(step.path)
    if step.op == "pick":
        found = resolve(value, parts)
        if not found:
            raise StructureError(f"{step.path} is not there.")
        return found[0][1] if WILD not in parts else [node for _, node in found]
    if step.op in ("set",) and WILD not in parts and parts and not resolve(value, parts):
        parent = resolve(value, parts[:-1])
        if not parent or not isinstance(parent[0][1], dict) or not isinstance(parts[-1], str):
            raise StructureError(f"{step.path} is not there, and its parent is not an object.")
        parent[0][1][parts[-1]] = copy.deepcopy(step.value)
        return value
    found = resolve(value, parts)
    if not found:
        raise StructureError(f"{step.path} is not there.")
    if step.op == "set":
        for where, _ in found:
            value = _replace(value, where, copy.deepcopy(step.value))
        return value
    if step.op == "remove":
        # The last index first, so the earlier ones stay where they were.
        for where, _ in sorted(found, key=lambda f: [(-p if isinstance(p, int) else 0) for p in f[0]]):
            del _parent(value, where)[where[-1]]
        return value
    if step.op in ("filter", "sort", "flatten"):
        lists = [(w, n) for w, n in found if isinstance(n, list)]
        if not lists:
            raise StructureError(f"{step.path} is not a list.")
        for where, node in lists:
            if step.op == "filter":
                new: Any = [item for item in node if matches(item, step)]
            elif step.op == "sort":
                field = parse_path(step.field)
                new = sorted(node, key=lambda item: _sort_key(item, field), reverse=step.descending)
                if step.descending:  # the missing ones last whichever way
                    new = [i for i in new if _sort_key(i, field)[0] != 3] + [
                        i for i in new if _sort_key(i, field)[0] == 3
                    ]
            else:
                new = [flatten_record(item) for item in node]
            value = _replace(value, where, new)
        return value
    objects = [(w, n) for w, n in found if isinstance(n, dict)]
    if not objects:
        raise StructureError(f"{step.path} is not an object.")
    if step.op == "rename":
        hit = False
        for place, obj in objects:
            if step.key not in obj:
                continue
            if step.to in obj and step.to != step.key:
                raise StructureError(f"{format_path(place)} has {step.to} already.")
            hit = True
            renamed = {(step.to if k == step.key else k): v for k, v in obj.items()}
            value = _replace(value, place, renamed)
        if not hit:
            raise StructureError(f"{step.path} has no key {step.key}.")
        return value
    # add
    for place, obj in objects:
        if step.key in obj:
            raise StructureError(f"{format_path(place)} has {step.key} already: Set changes it.")
        obj[step.key] = copy.deepcopy(step.value)
    return value


def apply(original: Any, steps: list[Step] | tuple[Step, ...]) -> Any:
    """The steps replayed on a copy of the original (which is left as it was)."""
    value = copy.deepcopy(original)
    for n, step in enumerate(steps, start=1):
        try:
            value = _apply(value, step)
        except StructureError as error:
            raise StructureError(f"Step {n} ({describe(step)}): {error}") from None
    return value


# ===== records: Open as grid =====


def records(node: Any, path: str = "$") -> list[dict[str, Any]]:
    """A list of records as a grid's rows: nested objects' keys dotted, a list or an object left inside
    as its JSON text (one column of text)."""
    if not isinstance(node, list) or not node:
        raise StructureError(f"{path} is not a list of records: Open as table takes a list.")
    if not any(isinstance(item, dict) for item in node):
        return [{"value": _cell(item)} for item in node]
    rows = []
    for item in node:
        flat = flatten_record(item)
        rows.append({k: _cell(v) for k, v in flat.items()})
    return rows


def _cell(value: Any) -> Any:
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False)
    return value


def record_lists(value: Any, limit: int = 50) -> list[str]:
    """The paths of the lists of records in a structure (the ones Open as grid takes), outermost first."""
    found: list[str] = []
    queue: list[tuple[tuple[str | int, ...], Any]] = [((), value)]
    while queue and len(found) < limit:
        where, node = queue.pop(0)
        if isinstance(node, list):
            if node and all(isinstance(i, dict) for i in node[:50]):
                found.append(format_path(where))
                first = node[0]
                queue += [((*where, 0, k), v) for k, v in first.items() if isinstance(v, dict | list)]
            continue
        if isinstance(node, dict):
            queue += [((*where, k), v) for k, v in node.items() if isinstance(v, dict | list)]
    return found


# ===== the structure's tab beside the code (2026-11-22): edits in its tree, its search, a node as code =====

EDITS: tuple[str, ...] = ("set", "rename", "remove", "add", "duplicate", "move")
MAX_FOUND: int = 1000


def code_of(path: Any, variable: str = "data") -> str:
    """The Python that reaches a node from the file's value, for a script beside it: `$.orders[3].lines` is
    `data["orders"][3]["lines"]` (the front end accessCode says the same: tests/golden)."""
    parts = tuple(path) if isinstance(path, tuple | list) else parse_path(path)
    out = variable
    for part in parts:
        if part is WILD:
            raise StructureError(f"{format_path(parts)} reaches many nodes: name one.")
        out += f"[{part}]" if isinstance(part, int) else "[" + json.dumps(part, ensure_ascii=False) + "]"
    return out


def _words_of(node: Any) -> str:
    return node if isinstance(node, str) else json.dumps(node)


def search(value: Any, words: Any, limit: int = MAX_FOUND) -> dict[str, Any]:
    """Where `words` stand (in any case) in a structure's keys and values, in the document's order:
    {"words", "found": [{path, where: key | value, code}], "count", "more"}. No words: nothing."""
    said = str(words or "").strip().lower()
    found: list[dict[str, Any]] = []
    count = 0
    if not said:
        return {"words": "", "found": [], "count": 0, "more": False}
    stack: list[tuple[tuple[str | int, ...], Any, str | None]] = [((), value, None)]
    while stack:
        where, node, key = stack.pop()
        hit = "key" if key is not None and said in key.lower() else None
        if hit is None and not isinstance(node, dict | list) and said in _words_of(node).lower():
            hit = "value"
        if hit:
            count += 1
            if len(found) < limit:
                found.append({"path": format_path(where), "where": hit, "code": code_of(where)})
        if isinstance(node, dict):
            stack += [((*where, str(k)), v, str(k)) for k, v in reversed(list(node.items()))]
        elif isinstance(node, list):
            stack += [((*where, n), v, None) for n, v in reversed(list(enumerate(node)))]
    return {"words": said, "found": found, "count": count, "more": count > len(found)}


def _one(value: Any, path: Any) -> tuple[tuple[str | int, ...], Any]:
    parts = parse_path(path)
    if WILD in parts:
        raise StructureError(f"{format_path(parts)} reaches many nodes: an edit names one.")
    found = resolve(value, parts)
    if not found:
        raise StructureError(f"{format_path(parts)} is not there.")
    return found[0]


def edit(value: Any, raw: Any) -> Any:
    """An edit made in the tab's tree, on the file's value itself (not a step: its text is written again
    from it): set, rename (path the object, key, to), remove, add (path the object, key, value), duplicate
    (a list's item after itself; an object's key beside it as "<key> copy"), move (a list's item to `to`).
    A new value; the one given is left as it was."""
    if not isinstance(raw, Mapping):
        raise StructureError('An edit is {"op": "set", "path": "$.orders[0].status", "value": "open"}.')
    op = str(raw.get("op") or "").strip().lower()
    if op not in EDITS:
        raise StructureError(f"An edit's op is one of {', '.join(EDITS)}.")
    out = copy.deepcopy(value)
    if op in ("set", "rename", "remove", "add"):
        step = check_step(raw)
        if WILD in parse_path(step.path):
            raise StructureError(f"{step.path} reaches many nodes: an edit names one.")
        return _apply(out, step)
    where, node = _one(out, raw.get("path", "$"))
    if not where:
        raise StructureError(f"{op.capitalize()} names a node inside: $ is the whole structure.")
    parent = _parent(out, where)
    last = where[-1]
    if op == "duplicate":
        if isinstance(parent, list):
            parent.insert(int(last) + 1, copy.deepcopy(node))
            return out
        base, n = f"{last} copy", 2
        key = base
        while key in parent:
            key, n = f"{base} {n}", n + 1
        items = list(parent.items())
        items.insert([k for k, _ in items].index(last) + 1, (key, copy.deepcopy(node)))
        return _replace(out, where[:-1], dict(items))
    if not isinstance(parent, list):  # move
        raise StructureError(f"{format_path(where)} is not a list's item: only a list's items move.")
    to = raw.get("to")
    if isinstance(to, bool) or not isinstance(to, int) or not 0 <= to < len(parent):
        raise StructureError(f"to is 0 to {len(parent) - 1}.")
    parent.insert(to, parent.pop(int(last)))
    return out


# ===== the shape: what a card and the agent read =====


def kind(value: Any) -> str:
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "list"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if value is None:
        return "null"
    return "text"


def count_nodes(value: Any) -> int:
    total, stack = 0, [value]
    while stack:
        node = stack.pop()
        total += 1
        if isinstance(node, dict):
            stack += list(node.values())
        elif isinstance(node, list):
            stack += node
    return total


def shape(value: Any, depth: int = 4, keys: int = 40) -> dict[str, Any]:
    """Types, counts and keys down to `depth` (a list's items as one merged shape): no values."""
    out: dict[str, Any] = {"type": kind(value)}
    if isinstance(value, dict):
        out["count"] = len(value)
        if depth > 0:
            out["keys"] = {str(k): shape(v, depth - 1, keys) for k, v in list(value.items())[:keys]}
            if len(value) > keys:
                out["more_keys"] = len(value) - keys
    elif isinstance(value, list):
        out["count"] = len(value)
        if depth > 0 and value:
            merged: dict[str, Any] = {}
            kinds = sorted({kind(i) for i in value[:200]})
            for item in value[:200]:
                if isinstance(item, dict):
                    for k, v in item.items():
                        merged.setdefault(str(k), v)
            if kinds == ["object"]:
                out["items"] = {
                    "type": "object",
                    "keys": {k: shape(v, depth - 1, keys) for k, v in list(merged.items())[:keys]},
                }
            else:
                out["items"] = {"type": " | ".join(kinds)}
    return out


def preview(value: Any, items: int = 20, chars: int = 200, depth: int = 6) -> Any:
    """A value cut down for the agent, as a grid's rows are: lists to `items`, text to `chars`."""
    if isinstance(value, str):
        return value if len(value) <= chars else value[:chars] + "…"
    if depth <= 0 and isinstance(value, dict | list):
        return f"<{kind(value)} of {len(value)}>"
    if isinstance(value, dict):
        return {k: preview(v, items, chars, depth - 1) for k, v in list(value.items())[: items * 5]}
    if isinstance(value, list):
        shown = [preview(v, items, chars, depth - 1) for v in value[:items]]
        return shown + ([f"<{len(value) - items} more>"] if len(value) > items else [])
    return value


# ===== names =====


def check_name(value: Any) -> str:
    """A structure's name (its file's name without the suffix)."""
    name = " ".join(str(value or "").split())
    if not name or not _FILE_NAME.match(name) or name.startswith("."):
        raise StructureError("A structure's name is a file's name: no / \\ : * ? \" < > |.")
    return name


def file_name(name: str, fmt: str) -> str:
    known = format_of(name)
    stem = name[: name.rfind(".")] if known else name
    return check_name(stem) + SUFFIX_OF[fmt]


def name_of(file_name_: str) -> str:
    """A structure's name from its file: gates.yaml -> gates."""
    base = re.split(r"[\\/]", file_name_)[-1]
    return base[: base.rfind(".")] if format_of(base) else base


# ===== lineage: where a structure came from, what was done to it, what was made of it =====


def lineage(
    name: str,
    origin: Mapping[str, Any],
    steps: list[str],
    grids: list[tuple[str, str, list[str]]],
    cells: Sequence[Mapping[str, Any]] = (),
) -> Any:
    """A structure's lineage as the Workbench's (domain/lineage.py): its source (an API call with its
    operation, a file, a paste, a kernel's value), the structure, each step, each grid made from it (its
    path, then the grid's own steps), and the notebook and script cells that read it (`cells`: references
    as connection_usage finds them; `how` sab.structure_table reads its table, after the last grid).
    Names and words only: never a value or a secret."""
    from swissarmybench.domain.lineage import Edge, Graph, Node

    nodes: list[Node] = []
    edges: list[Edge] = []
    kind = str(origin.get("kind") or "new")
    if kind == "api" and origin.get("input"):
        nodes.append(
            Node("in", "table", str(origin["input"]), "the rows written", table=str(origin["input"]))
        )
        edges.append(Edge("in", "src", "rows", "table"))
    if kind == "api":
        label = f"{origin.get('method', '')} {origin.get('path', '')}".strip()
        where = f"{origin.get('api', '')} · {origin.get('operation', '')}"
        if origin.get("status"):
            where += f" · {origin['status']}"
        nodes.append(Node("src", "source", label or "API call", where))
    elif kind == "file":
        nodes.append(Node("src", "source", str(origin.get("file") or name), "file"))
    else:
        words = {"paste": "Pasted", "kernel": "Python", "agent": "The agent", "new": "New"}.get(kind, kind)
        nodes.append(Node("src", "source", words, kind))
    nodes.append(Node("doc", "text", name, "structure", target=not steps and not grids))
    edges.append(Edge("src", "doc", "", "name"))
    before = "doc"
    for n, words in enumerate(steps, start=1):
        ident = f"s{n}"
        nodes.append(Node(ident, "step", words, f"step {n}", step=n, target=n == len(steps) and not grids))
        edges.append(Edge(before, ident, "", "step"))
        before = ident
    for g, (table, path, grid_steps) in enumerate(grids, start=1):
        ident = f"g{g}"
        nodes.append(Node(ident, "table", table, f"table of {path}", table=table, target=g == len(grids)))
        edges.append(Edge(before, ident, path, "table"))
        last = ident
        for n, words in enumerate(grid_steps, start=1):
            step = f"g{g}s{n}"
            nodes.append(Node(step, "step", words, f"step {n}", table=table, step=n))
            edges.append(Edge(last, step, "", "step"))
            last = step
    tail = before
    if grids:
        tail = f"g{len(grids)}s{len(grids[-1][2])}" if grids[-1][2] else f"g{len(grids)}"
    for c, ref in enumerate(cells, start=1):
        ident = f"c{c}"
        cell = ref.get("cell")
        named = f" {ref['name']}" if ref.get("name") else ""
        where = f"{ref.get('title', '')} @cell{cell}" if isinstance(cell, int) else str(ref.get("title", ""))
        reads_table = str(ref.get("how") or "") == CALLS["structure_table"]
        nodes.append(
            Node(
                ident,
                "cell",
                f"{'cell' if isinstance(cell, int) else 'code'}{named}".strip(),
                where,
                document=str(ref.get("document") or "") or None,
                cell=cell if isinstance(cell, int) else None,
                doc_kind=str(ref.get("kind") or "") or None,
                reads=(name,),
            )
        )
        edges.append(Edge(tail if reads_table else before, ident, str(ref.get("how") or ""), "name"))
    return Graph(tuple(nodes), tuple(edges))
