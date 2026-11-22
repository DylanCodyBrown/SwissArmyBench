"""The project scaffold's core files and their sandbox mirror, as text (Plans/adapter.plan.md "The exported
project: the fewest files that build the app"; design principle 12a).

The owner, 2026-11-22: "The goal is the app will write these files as the user develops ... the app itself
sticks to one uniform structure per project" / "the files grow as the user creates new connections/apis,
structures and variables" / "dont mix them into the app scaffold". Every project, whatever its type, has the
same core files at its top, written by the app as the user works (never all at once), each new thing one
marked section:

  adapter.py               the app's own adapter, the same bytes (written once something reads through it)
  connections.py           one section per connection the project uses: its own code (list, read and write
                           are the adapter's calls on it), its variables by name only, never a value
  API.py                   the user's (services/local_api.py), never written here
  data.py                  data.ipynb's export (domain/projects.py), with a structure's line when a
                           structure is read as a grid (structure_lines)
  README.md                the user's; only its Variables block is the app's: each variable's name, where it
                           comes from and what uses it, never its value

and the sandbox mirror beside them, never inside them (the app's files never name the sandbox):

  sandbox_connections.py   each used connection's stand-in: the same names, backed by the sandbox's tables
  sandbox_data.py          the sandbox's tables: where each was read from once, its key, the baseline and
                           the checkpoints by name
  sandbox/                 the rows (Git-ignored; domain/sandbox.py)

Removing a thing removes its section; nothing is written for what the project never uses. A made file the
user edited (its bytes not what the app last wrote, `.sab/scaffold.json` keeps that hash) is kept and offered
as Compare / Take the new one, never written over. Pure rules: standard library only.
"""

from __future__ import annotations

import hashlib
import json
import pprint
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

ADAPTER = "adapter.py"
CONNECTIONS = "connections.py"
API = "API.py"
DATA = "data.py"
README = "README.md"
SANDBOX_DATA = "sandbox_data.py"
SANDBOX_CONNECTIONS = "sandbox_connections.py"
STATE = ".sab/scaffold.json"  # each made file's hash as the app last wrote it (never a value)

# The files this module makes, and what each is made from (the Scripts page's "Made from ...").
MADE: dict[str, str] = {
    ADAPTER: "Swiss Army Bench's adapter",
    CONNECTIONS: "the library's connections",
    SANDBOX_DATA: "the sandbox",
    SANDBOX_CONNECTIONS: "the sandbox",
}
SANDBOX_FILES: tuple[str, ...] = (SANDBOX_DATA, SANDBOX_CONNECTIONS)

SECTION = "# ===== connection: {name} ====="
END = "# ===== end of {name} ====="
_SECTION = re.compile(r"^# ===== (?:connection|key vault): (.+?) =====$", re.M)
VARIABLES_OPEN = "<!-- swissarmybench: variables (written by the app: names only, never a value) -->"
VARIABLES_CLOSE = "<!-- /swissarmybench: variables -->"
STRUCTURES_OPEN = "# ===== structures read as grids (written by the app) ====="
STRUCTURES_CLOSE = "# ===== end of the structures ====="


def digest(text: str | bytes) -> str:
    data = text.encode("utf-8") if isinstance(text, str) else text
    return hashlib.sha256(data).hexdigest()


# ===== connections.py =====


@dataclass(frozen=True)
class Section:
    """One connection's part of connections.py: its own code (as a script export writes it) and the
    variables it reads (names only)."""

    name: str
    code: str
    variables: tuple[str, ...] = ()
    kind: str = "connection"  # or "key vault" (a vault a connection's password comes from)


def marked(sections: Sequence[Section]) -> str:
    """Each connection as its own marked section, in the order given (the order they were made)."""
    blocks: list[str] = []
    for s in sections:
        said = (
            f"# Its variables (set where it runs, never here): {', '.join(s.variables)}"
            if s.variables
            else ""
        )
        head = SECTION.format(name=s.name).replace("connection:", f"{s.kind}:", 1)
        lines = [head, *([said] if said else []), s.code.strip("\n"), END.format(name=s.name)]
        blocks.append("\n".join(lines))
    return "\n\n\n".join(blocks)


def section_names(text: str) -> list[str]:
    """The connections a connections.py holds, by its sections' marks, in their order."""
    return _SECTION.findall(text or "")


_SETTING = re.compile(r"^(    (['\"])[A-Za-z_][A-Za-z0-9_]*\2: )(?!None,)(.+?),(  # .*)?$")


def without_values(settings: str) -> str:
    """The SETTINGS block with every plain value taken out (None: set it where it runs). The scaffold holds
    names only; a script export may keep a plain value as its default, a project's connections.py never."""
    out: list[str] = []
    inside = False
    for line in settings.split("\n"):
        if line.startswith("SETTINGS: "):
            inside = True
        elif inside and line.startswith("}"):
            inside = False
        elif inside:
            line = _SETTING.sub(lambda m: f"{m.group(1)}None,{m.group(4) or ''}", line)
        out.append(line)
    return "\n".join(out)


CONNECTIONS_HEAD = '''"""connections.py: each connection this project uses, as its own code (written by
Swiss Army Bench as the project grows: a section per connection, taken out when nothing uses it). Its
variables are named, never their values: set them where it runs (README.md lists them). Every read and write
goes through adapter.py: tables(), read(), query() and write() on connection(name)'s own client. The sandbox's
stand-ins are in sandbox_connections.py, never here."""

from __future__ import annotations

import adapter
'''

CONNECTIONS_FOOT = """

# ===== the adapter: a connection's name to its own client, in its backend =====


def _source(name: str):
    return adapter.source_from(connection(name), name=name)


adapter.use(_source)
"""


def connections_py(parts: str) -> str:
    """connections.py from the connections' code (`parts`: the shared settings and helpers, the marked
    sections, the registry, as services/script_export.py connections_code gives them)."""
    return CONNECTIONS_HEAD + "\n" + parts.strip("\n") + "\n" + CONNECTIONS_FOOT


# ===== README.md's Variables =====


@dataclass(frozen=True)
class Variable:
    name: str
    source: str  # where it comes from, in words: "a key vault (finance-vault)", "this computer's keyring"
    uses: tuple[str, ...] = ()  # what uses it: "connection Warehouse", "data.ipynb"


def variables_block(variables: Sequence[Variable]) -> str:
    rows = ["| Variable | Where it comes from | What uses it |", "|---|---|---|"]
    rows += [f"| `{v.name}` | {v.source or 'not set'} | {', '.join(v.uses) or '-'} |" for v in variables]
    return "\n".join(
        [
            VARIABLES_OPEN,
            "## Variables",
            "",
            "Set each one where the project runs (the terminal, the Function App's or hosted app's "
            "settings); no value is ever written in this folder.",
            "",
            *rows,
            VARIABLES_CLOSE,
        ]
    )


def with_variables(readme: str | None, variables: Sequence[Variable], title: str = "") -> str | None:
    """README.md with its Variables block as `variables` say (put in at the end, replaced, or taken out when
    there are none); the rest of it left byte for byte. None: nothing to write (no README, no variables)."""
    text = readme or ""
    start, end = text.find(VARIABLES_OPEN), text.find(VARIABLES_CLOSE)
    block = variables_block(variables) if variables else ""
    if start >= 0 and end > start:
        tail = text[end + len(VARIABLES_CLOSE) :]
        head = text[:start]
        if not block:
            return head.rstrip("\n") + ("\n" + tail.lstrip("\n") if tail.strip() else "\n")
        return head + block + tail
    if not block:
        return readme
    if readme is None:
        return f"# {title or 'The project'}\n\n{block}\n"
    return text.rstrip("\n") + "\n\n" + block + "\n"


# ===== the sandbox mirror =====


def _source_record(source: Mapping[str, Any]) -> dict[str, Any]:
    """Where a sandbox table was read from, in names only: never a value, a query's text or a path on this
    disk (a file by its own name)."""
    kind = str(source.get("kind") or source.get("from") or "")
    out: dict[str, Any] = {"kind": kind} if kind else {}
    for key in ("connection", "table", "schema", "database", "grid", "structure"):
        if isinstance(source.get(key), str) and source[key]:
            out[key] = source[key]
    path = source.get("path") or source.get("file")
    if isinstance(path, str) and path:
        out["file"] = re.split(r"[\\/]", path)[-1]
    return out


def _literal(value: Any) -> str:
    """A plain value as Python, the same text for the same value (sorted keys)."""
    return pprint.pformat(value, indent=1, width=100, sort_dicts=True)


def sandbox_data_py(
    tables: Mapping[str, Mapping[str, Any]], baseline_at: str | None, checkpoints: Iterable[str]
) -> str | None:
    """sandbox_data.py: the sandbox's tables (where each was read from once, its key, the client it is mocked
    as), the baseline's time and the checkpoints by name. None: the sandbox has no table."""
    if not tables:
        return None
    listed: dict[str, Any] = {}
    for name in sorted(tables):
        record = tables[name]
        entry: dict[str, Any] = {"from": _source_record(record.get("source") or {})}
        connection = str((record.get("client") or {}).get("connection") or "")
        if connection:
            entry["as"] = connection
        if record.get("key"):
            entry["key"] = [str(k) for k in record["key"]]
        listed[name] = entry
    points = sorted(dict.fromkeys(str(c) for c in checkpoints), key=str.casefold)
    return (
        '"""sandbox_data.py: the project\'s sandbox (written by Swiss Army Bench; test data, never live).\n'
        "Each table's rows are in sandbox/sandbox.duckdb (Git-ignored), read once from where TABLES says;\n"
        "Reset puts them back to the baseline (sandbox/baseline.duckdb), a checkpoint to its copy in\n"
        "sandbox/checkpoints/. Remove the sandbox deletes this file, sandbox_connections.py and sandbox/,\n"
        'and nothing else. Names only: never a value, a query or a path on this computer."""\n\n'
        'FOLDER = "sandbox"\n'
        f"BASELINE_AT = {baseline_at!r}\n"
        f"CHECKPOINTS: list[str] = {points!r}\n"
        f"TABLES: dict[str, dict] = {_literal(listed)}\n"
    )


def stand_ins(tables: Mapping[str, Mapping[str, Any]]) -> dict[str, list[str]]:
    """Each connection the sandbox stands in for: the sandbox's tables mocked as it, sorted."""
    out: dict[str, list[str]] = {}
    for name in sorted(tables):
        connection = str((tables[name].get("client") or {}).get("connection") or "")
        if connection:
            out.setdefault(connection, []).append(name)
    return dict(sorted(out.items(), key=lambda kv: kv[0].casefold()))


SANDBOX_CONNECTIONS_HEAD = '''"""sandbox_connections.py: connections.py's mirror for testing (written by
Swiss Army Bench). Each connection the project uses is stood in for by the sandbox's tables read from it
(sandbox/sandbox.duckdb): the same names, so API.py and the app run unchanged on either side, but never a
connection's real code, variable or secret.
Import this instead of connections.py to run the project on its sandbox: `import sandbox_connections`.
The two never import each other; Remove the sandbox deletes this file."""

from __future__ import annotations

from pathlib import Path

import duckdb

import adapter

_DB = Path(__file__).resolve().parent / "sandbox" / "sandbox.duckdb"
_OPEN: list[duckdb.DuckDBPyConnection] = []


def _sandbox() -> duckdb.DuckDBPyConnection:
    if not _OPEN:
        if not _DB.is_file():
            raise RuntimeError("This project has no sandbox here (sandbox/sandbox.duckdb).")
        try:
            _OPEN.append(duckdb.connect(str(_DB)))
        except duckdb.IOException as error:  # the app has it open: one process at a time holds the file
            raise RuntimeError(
                "The sandbox is open in Swiss Army Bench: close the project there, then run this again."
            ) from error
    return _OPEN[0]

'''

SANDBOX_CONNECTIONS_FOOT = '''

def _source(name: str):
    """A connection's name to the sandbox (its stand-in's tables; "Sandbox": every table)."""
    known = {n.casefold() for n in STAND_INS} | {"sandbox"}
    if name.strip().casefold() not in known:
        raise RuntimeError(f"The sandbox stands in for no connection named {name}: add one of its tables.")
    return adapter.source_from(_sandbox(), name=name)


adapter.use(_source)
'''


def sandbox_connections_py(tables: Mapping[str, Mapping[str, Any]]) -> str | None:
    """sandbox_connections.py: each connection the sandbox stands in for, a marked section naming its
    tables. None: the sandbox has no table."""
    if not tables:
        return None
    found = stand_ins(tables)
    sections = [
        "\n".join(
            [
                SECTION.format(name=name),
                f"# Stood in for by the sandbox's tables: {', '.join(listed)}",
                END.format(name=name),
            ]
        )
        for name, listed in found.items()
    ]
    body = "\n\n".join(sections)
    return (
        SANDBOX_CONNECTIONS_HEAD
        + ("\n" + body + "\n\n" if body else "\n")
        + f"STAND_INS: dict[str, list[str]] = {_literal(found)}\n"
        + SANDBOX_CONNECTIONS_FOOT
    )


# ===== data.py: a structure read as a grid =====


@dataclass(frozen=True)
class StructureGrid:
    variable: str  # the grid's table as data.py names it
    file: str  # its file in the project (structures/orders.json)
    path: str = "$"  # the records' place in it


_READER = '''

def _records(file: str, path: str = "$"):
    """A structure's list of records (structures/<file>: JSON, YAML, XML or TOML), at its path ($.orders,
    $.data[*]), nested keys dotted: the same table Swiss Army Bench's Open as grid shows. The standard
    library only, but for YAML (PyYAML)."""
    import json as _json
    from pathlib import Path as _Path

    text = (_Path(__file__).resolve().parent / file).read_text(encoding="utf-8")
    kind = file.rsplit(".", 1)[-1].lower()
    if kind in ("yaml", "yml"):
        try:
            import yaml as _yaml
        except ImportError:
            raise ImportError(f"{file} is YAML, which needs PyYAML: pip install pyyaml") from None
        found = list(_yaml.safe_load_all(text))
        value = _json.loads(_json.dumps(found[0] if len(found) == 1 else found, default=str))
    elif kind == "toml":
        import tomllib as _toml

        def plain(item):  # a date or a time as its text, as the app shows it
            return item.isoformat() if hasattr(item, "isoformat") else str(item)

        value = _json.loads(_json.dumps(_toml.loads(text), default=plain))
    elif kind == "xml":
        import re as _re
        import xml.etree.ElementTree as _tree

        if _re.search(r"<!\\s*(DOCTYPE|ENTITY)", text, _re.IGNORECASE):
            raise ValueError(f"{file} declares a DOCTYPE or an entity: it is not read (remove it first).")

        def element(node):  # attributes as "@name", text beside children as "#text", repeats as a list
            out = {f"@{k}": v for k, v in node.attrib.items()}
            for child in node:
                if not isinstance(child.tag, str):
                    continue
                inner = element(child)
                if child.tag in out:
                    if not isinstance(out[child.tag], list):
                        out[child.tag] = [out[child.tag]]
                    out[child.tag].append(inner)
                else:
                    out[child.tag] = inner
            words = (node.text or "").strip()
            if not out:
                return words
            if words:
                out["#text"] = words
            return out

        root = _tree.fromstring(text)
        value = {root.tag: element(root)}
    else:
        value = _json.loads(text)
    steps = path.lstrip("$").replace("[*]", "").replace("]", "").replace("[", ".")
    for part in [p for p in steps.split(".") if p]:
        value = value[int(part)] if isinstance(value, list) else value[part]
    rows = value if isinstance(value, list) else [value]

    def flat(row, prefix=""):
        out = {}
        for key, item in (row.items() if isinstance(row, dict) else [("value", row)]):
            if isinstance(item, dict):
                out.update(flat(item, f"{prefix}{key}."))
            else:
                out[f"{prefix}{key}"] = item
        return out

    try:
        import pandas as _pandas
    except ImportError:
        return [flat(r) for r in rows]
    return _pandas.DataFrame.from_records([flat(r) for r in rows])
'''

# The files a structure's line reads (domain/structures.py SUFFIXES: the formats Open as grid takes).
STRUCTURE_SUFFIXES = (".json", ".yaml", ".yml", ".xml", ".toml")


def structure_lines(structures: Sequence[StructureGrid]) -> str:
    """data.py's part for the structures read as grids: one line each, marked (empty: none)."""
    if not structures:
        return ""
    lines = [f"{s.variable} = _records({s.file!r}, {s.path!r})" for s in structures]
    return "\n".join([STRUCTURES_OPEN, _READER.strip("\n"), "", "", *lines, STRUCTURES_CLOSE])


def with_structures(data_py: str, structures: Sequence[StructureGrid]) -> str:
    """data.py with its structures' part as given (replaced, appended, or taken out)."""
    start, end = data_py.find(STRUCTURES_OPEN), data_py.find(STRUCTURES_CLOSE)
    if start >= 0 and end > start:
        data_py = data_py[:start].rstrip("\n") + "\n" + data_py[end + len(STRUCTURES_CLOSE) :].lstrip("\n")
    part = structure_lines(structures)
    return data_py.rstrip("\n") + ("\n\n\n" + part if part else "") + "\n"


def keeping_structures(old: str | None, new: str) -> str:
    """data.py made again from data.ipynb (`new`) with the structures' part the file had (`old`): the part
    is the scaffold's, so data.ipynb's own write carries it over as it stands (none: `new` as it is)."""
    if old is None:
        return new
    start, end = old.find(STRUCTURES_OPEN), old.find(STRUCTURES_CLOSE)
    if start < 0 or end <= start:
        return new
    return new.rstrip("\n") + "\n\n\n" + old[start : end + len(STRUCTURES_CLOSE)] + "\n"


# ===== what to write =====


@dataclass(frozen=True)
class Change:
    path: str
    action: str  # write, remove, same, edited (kept: Compare / Take the new one), none
    words: str = ""


@dataclass
class Plan:
    changes: list[Change] = field(default_factory=list)

    def by(self, action: str) -> list[str]:
        return [c.path for c in self.changes if c.action == action]


def plan(
    wanted: Mapping[str, str | None],
    have: Mapping[str, str | None],
    written: Mapping[str, str],
    hand: Iterable[str] = (),
    take: Iterable[str] = (),
) -> Plan:
    """What each made file needs: `wanted` the text it should hold (None: nothing uses it), `have` its text
    now (None: absent), `written` the hash of what the app last wrote, `hand` the files marked edited by hand,
    `take` the files the user asked to take the new one for. A file whose bytes are not what the app last
    wrote (or that the app never wrote) is the user's from then on: kept and said, never written over or
    removed."""
    hand_edited, taken = set(hand), set(take)
    out = Plan()
    for path in wanted:
        want, now = wanted[path], have.get(path)
        ours = now is not None and (written.get(path) == digest(now)) and path not in hand_edited
        if now == want:
            out.changes.append(Change(path, "same" if want is not None else "none"))
        elif now is None:
            out.changes.append(Change(path, "write", "made") if want is not None else Change(path, "none"))
        elif ours or path in taken:
            if want is None:
                out.changes.append(Change(path, "remove", "nothing uses it now"))
            else:
                out.changes.append(
                    Change(path, "write", "taken" if path in taken and not ours else "updated")
                )
        else:
            words = (
                "edited by hand: kept (Compare, or Take the new one)"
                if want is not None
                else "edited by hand: kept, though nothing uses it now"
            )
            out.changes.append(Change(path, "edited", words))
    return out


def state_text(written: Mapping[str, str]) -> str:
    return json.dumps({k: written[k] for k in sorted(written)}, indent=1) + "\n"


def read_state(text: str | None) -> dict[str, str]:
    try:
        raw = json.loads(text or "{}")
    except ValueError:
        return {}
    return {str(k): str(v) for k, v in raw.items() if isinstance(v, str)} if isinstance(raw, dict) else {}
