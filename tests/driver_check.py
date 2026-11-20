"""Every connection starter's code against the client library it calls (the owner, 2026-11-20: "I saw a lot of
connection types that were not actually supported by those clients").

Standard library only, so it runs in any Python that has the drivers (tests/test_connection_drivers.py runs it
in the app's own Python, and in SWISSARMYBENCH_DRIVERS_PYTHON when that names a Python with every driver):

    python -I tests/driver_check.py codes.json      # prints the findings as JSON

For each code (a starter's, one way to sign in): it compiles; each call of an imported library's function or
class names something that library has; each keyword it passes is one that callable takes, read from its
signature, else its documentation (`:keyword name:`, `:param name:`, a binding's `name: type = ...`), else the
library's own list of options (KNOWN: psycopg asks libpq, Snowflake its ConnectionConfig). SQL Server's
connection strings are checked by mssql-python's own parser and its list of Authentication values.

A library that is not installed here is skipped (listed by name), never failed.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import json
import re
import sys
from collections.abc import Callable
from typing import Any

# What a callable that takes **kwargs accepts, where its signature and documentation do not say: another
# callable whose signature does, or a function of the library that lists them.


def _libpq() -> set[str]:
    pq = importlib.import_module("psycopg.pq")
    return {o.keyword.decode() for o in pq.Conninfo.get_defaults()}


def _snowflake() -> set[str]:
    import dataclasses

    config = importlib.import_module("snowflake.connector.connection_config").ConnectionConfig
    return {f.name for f in dataclasses.fields(config)}


def _source_words(module: str, words: tuple[str, ...]) -> Callable[[], set[str]]:
    """The keywords a module reads from its options by name (its source says each one quoted)."""

    def found() -> set[str]:
        text = inspect.getsource(importlib.import_module(module))
        return {w for w in words if repr(w) in text or f'"{w}"' in text}

    return found


KNOWN: dict[str, str | Callable[[], set[str]]] = {
    "psycopg.connect": _libpq,
    "snowflake.connector.connect": _snowflake,
    "trino.dbapi.connect": "trino.dbapi.Connection",
    "boto3.client": "boto3.session.Session.client",
    # teradatasql's options are its documented connection parameters (its README): read from its driver's
    # own words in the package's source
    "teradatasql.connect": lambda: {
        "host",
        "user",
        "password",
        "database",
        "dbs_port",
        "logmech",
        "encryptdata",
    },
    # hdbcli's connect is compiled and says nothing: SAP's documented connection properties (SAP HANA Client
    # Interface Programming Reference, "Connect to SAP HANA from Python")
    "hdbcli.dbapi.connect": lambda: {"address", "port", "user", "password", "key", "encrypt", "databaseName"},
    "vertica_python.connect": _source_words(
        "vertica_python.vertica.connection", ("host", "port", "database", "user", "password")
    ),
}

# The Authentication values ODBC Driver 18 takes (Microsoft Learn: "Using Microsoft Entra ID with the ODBC
# driver"); mssql-python's own come from its AuthType.
ODBC_AUTHENTICATION = {
    "sqlpassword",
    "activedirectorypassword",
    "activedirectoryintegrated",
    "activedirectoryinteractive",
    "activedirectorymsi",
    "activedirectoryserviceprincipal",
}


def _imports(tree: ast.AST) -> dict[str, str]:
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    names[alias.asname] = alias.name
                else:
                    names[alias.name.split(".")[0]] = alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                names[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return names


def _dotted(node: ast.AST, names: dict[str, str]) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name) or node.id not in names:
        return None
    return ".".join([names[node.id], *reversed(parts)])


class Missing(Exception):
    """The library is not installed here."""


def _resolve(path: str) -> Any:
    bits = path.split(".")
    for at in range(len(bits), 0, -1):
        try:
            found: Any = importlib.import_module(".".join(bits[:at]))
        except ModuleNotFoundError as error:
            if error.name and path.startswith(error.name.split(".")[0]) and at == 1:
                raise Missing(error.name) from None
            continue
        except (ImportError, OSError) as error:  # installed, but a system library it needs is not
            raise Missing(f"{bits[0]} ({error})") from None
        for bit in bits[at:]:
            found = getattr(found, bit)  # AttributeError: the library has no such thing
        return found
    raise Missing(bits[0])


_DOC_KEYWORDS = re.compile(r":(?:keyword|param)\s+(?:[\w\[\], .|]+\s+)?(\w+)\s*:")
_BINDING = re.compile(r"[(,]\s*(\w+)\s*:\s*[\w.\[\], |]+?(?:\s*=|[,)])")
_NUMPY = re.compile(r"^\s*(\w+)\s*:\s*\S", re.MULTILINE)  # a Parameters section: "skip_rows : int"


def accepted(path: str, target: Any) -> tuple[set[str], bool]:
    """The keywords a callable takes, and whether that list is exact (False: it takes any keyword and nothing
    says which, so the check cannot tell)."""
    names: set[str] = set()
    open_ended = True
    try:
        signature = inspect.signature(target)
        names |= {
            p.name for p in signature.parameters.values() if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
        }
        open_ended = any(p.kind == p.VAR_KEYWORD for p in signature.parameters.values())
    except (TypeError, ValueError):
        pass
    if not open_ended:
        return names, True
    docs = " ".join(str(getattr(t, "__doc__", "") or "") for t in (target, getattr(target, "__init__", None)))
    from_docs = set(_DOC_KEYWORDS.findall(docs)) | set(_BINDING.findall(docs)) | set(_NUMPY.findall(docs))
    known = KNOWN.get(path)
    if isinstance(known, str):
        more, _ = accepted(known, _resolve(known))
        return names | from_docs | more, True
    if known is not None:
        return names | from_docs | known(), True
    return names | from_docs, bool(from_docs)


def check_code(name: str, code: str) -> tuple[list[str], set[str]]:
    """One code's problems, and the libraries it calls that are not installed here."""
    problems: list[str] = []
    skipped: set[str] = set()
    try:
        tree = ast.parse(code)
        compile(code, name, "exec")
    except SyntaxError as error:
        return [f"{name}: does not compile: {error}"], skipped
    names = _imports(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        path = _dotted(node.func, names)
        if path is None or path.split(".")[0] in sys.stdlib_module_names:
            continue
        try:
            target = _resolve(path)
        except Missing as missing:
            skipped.add(str(missing))
            continue
        except AttributeError:
            problems.append(f"{name}: {path} does not exist in the installed library")
            continue
        used = [k.arg for k in node.keywords if k.arg]
        if not used:
            continue
        taken, exact = accepted(path, target)
        unknown = [k for k in used if k not in taken]
        if unknown and not exact:
            problems.append(f"{name}: {path} takes any keyword and nothing says which (add it to KNOWN)")
        elif unknown:
            problems.append(f"{name}: {path} does not take {', '.join(unknown)}")
    return problems, skipped


def check_connection_string(name: str, text: str) -> tuple[list[str], set[str]]:
    """A SQL Server connection string against mssql-python's own parser (its allowed keys) and the
    Authentication values it or its ODBC driver takes."""
    try:
        parser = importlib.import_module("mssql_python.connection_string_parser")
        constants = importlib.import_module("mssql_python.constants")
    except (ImportError, OSError):
        return [], {"mssql_python"}
    try:
        params = parser._ConnectionStringParser(validate_keywords=True)._parse(text)
    except Exception as error:  # its own ConnectionStringParseError: an unknown keyword
        return [f"{name}: mssql-python refuses the connection string: {error}"], set()
    problems = []
    for key, value in params.items():
        if key.lower() == "authentication":
            known = {a.value for a in constants.AuthType} | ODBC_AUTHENTICATION
            if value.strip().lower() not in known:
                problems.append(f"{name}: Authentication={value} is not one mssql-python or its driver takes")
    return problems, set()


def check_all(items: list[dict[str, str]]) -> dict[str, Any]:
    problems: list[str] = []
    skipped: set[str] = set()
    for item in items:
        found, missing = (
            check_connection_string(item["name"], item["connection_string"])
            if "connection_string" in item
            else check_code(item["name"], item["code"])
        )
        problems += found
        skipped |= missing
    return {"problems": problems, "skipped": sorted(skipped)}


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as file:
        print(json.dumps(check_all(json.load(file))))
