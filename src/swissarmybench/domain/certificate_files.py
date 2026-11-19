"""A certificate or keystore FILE setting, optionally read from an environment variable (the owner,
2026-11-16: "any other connections that need to map to a keystore or cert, should have the option to
create a local Env").

A connection's settings are read from its code (domain/blades.py). Those that are a certificate or
keystore file (a CA .pem: `verify`, `sslrootcert`, `ssl_ca`, `ca`; a keystore; a client certificate or
key: `sslcert`, `sslkey`) may be written either way:

    verify = r"C:\\certs\\company-ca.pem"                                          a plain path (the default)
    verify = os.environ.get("WAREHOUSE_CERTIFICATE_FILE", r"C:\\certs\\company-ca.pem")   mapped

Mapped, the variable's value wins where it is set (a function app's Application setting names where
the file sits there) and this computer's path is its default. The mapping lives in the code itself:
the one place the app, a Workbench kernel, an export and a scheduled run all read. `blades.env_settings`
lists a code's mappings as {"variable", "setting", "key", "default"}.

SQL Server and Azure SQL map more (the owner, 2026-11-17: the same "From an environment variable" on
server, database, username, client id and tenant): PLACE_SETTINGS, written and read back the same way
(`server=os.environ.get("WAREHOUSE_SERVER", "sql01.example.local")`); the form offers them on those two
connections (domain/sql_server.py ENV_SETTINGS). Standard library only.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Mapping
from typing import Any, TypeGuard

# A connection's own top-level settings by the name its code gives them (the lake and SharePoint kinds,
# domain/lakes.py; Dataverse's and Power BI's tenant and client ids too): their plain names. Each may come
# from an environment variable (the owner, 2026-11-17: "All should be mapable to env vars").
TOP_LEVEL: dict[str, str] = {
    "tenant_id": "tenant_id",  # as Dataverse and Power BI name them (the form: Tenant id, Client id)
    "client_id": "client_id",
    "managed_client_id": "managed identity client id",
    "username": "username",
    "site_url": "site",
    "header_row": "header row",
    "workspace": "workspace",
    "item": "item",
    "sql_endpoint": "sql endpoint",
    "account": "account",
    "container": "container",
    "folder_in_container": "folder in container",
    "root": "root",
    "depth": "depth",
    "region": "region",
    "profile": "profile",
    "access_key_id": "access key id",
}
FILE_SETTINGS = frozenset({"certificate file", "keystore", "client certificate file", "client key file"})
# Where and who, by domain/blades.py KEYWORDS (host= is a server): the SQL Server forms offer them
# (domain/sql_server.py ENV_SETTINGS); a setting here says its source (`env`) only once it is mapped.
PLACE_SETTINGS = frozenset({"server", "database", "user"})
# The settings (their plain names, domain/blades.py KEYWORDS and TOP_LEVEL) that may come from a variable.
ENV_MAPPABLE = FILE_SETTINGS | PLACE_SETTINGS | frozenset(TOP_LEVEL.values())


def mappable(setting: str | None) -> TypeGuard[str]:
    """Whether a setting (its plain name) may come from an environment variable, its value this
    computer's default: a certificate or keystore file, a server, database or user, and every setting of
    TOP_LEVEL. The one rule the settings' reading, writing and the form's "From an environment variable"
    share."""
    return setting in ENV_MAPPABLE


def says_source(setting: str, env: str | None) -> bool:
    """Whether a setting's answer carries its source (`env`): a mapped one always; an unmapped one when
    the form offers the choice by itself (a file, a TOP_LEVEL setting), not a server, database or user
    (only the SQL Server forms offer those, by their env_settings)."""
    return bool(env) or (mappable(setting) and setting not in PLACE_SETTINGS)


def plain_name(identifier: str, keywords: Mapping[str, str]) -> str | None:
    """A top-level name's setting (tenant_id -> tenant; host -> server by `keywords`), or None."""
    return TOP_LEVEL.get(identifier) or keywords.get(identifier.casefold())


_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class MappingError(ValueError):
    """A mapping that cannot be written (the message says why)."""


def env_default(node: ast.expr | None) -> tuple[str, ast.Constant] | None:
    """`os.environ.get("NAME", "default")` (or `os.getenv`): the variable's name and its default."""
    if not (isinstance(node, ast.Call) and len(node.args) == 2 and not node.keywords):
        return None
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    environ_get = (
        func.attr == "get"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "environ"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "os"
    )
    getenv = func.attr == "getenv" and isinstance(func.value, ast.Name) and func.value.id == "os"
    name, default = node.args
    if (
        (environ_get or getenv)
        and isinstance(name, ast.Constant)
        and isinstance(name.value, str)
        and isinstance(default, ast.Constant)
        and isinstance(default.value, str)
    ):
        return name.value, default
    return None


def variable_choice(name: Any, setting: str, key: str) -> str | None:
    """The variable sent for a setting: a name, or None (a plain path)."""
    if name is None or (isinstance(name, str) and not name.strip()):
        return None
    if not mappable(setting):
        raise MappingError(
            f"{key} cannot come from an environment variable: a file, a server, a database, a user, an id "
            "or a place can, a number or an on/off setting cannot."
        )
    if not isinstance(name, str) or not _ENV_NAME.match(name.strip()):
        raise MappingError(
            "An environment variable's name is letters, digits and _, not starting with a digit."
        )
    return name.strip()


def expression(variable: str, default_literal: str) -> str:
    """The code that reads the file's path: the variable, else this computer's path."""
    return f"os.environ.get({json.dumps(variable)}, {default_literal})"


def with_import_os(code: str) -> str:
    """The code with `import os` (before its first import) when it has none at the top level."""
    tree = ast.parse(code)
    if any(
        isinstance(s, ast.Import) and any(a.name == "os" and not a.asname for a in s.names) for s in tree.body
    ):
        return code
    first = next(
        (
            s
            for s in tree.body
            if isinstance(s, ast.Import) or (isinstance(s, ast.ImportFrom) and s.module != "__future__")
        ),
        None,
    )
    if first is not None:
        line = first.lineno - 1
    else:
        future = [s for s in tree.body if isinstance(s, ast.ImportFrom) and s.module == "__future__"]
        line = (future[-1].end_lineno or 0) if future else 0
    parts = code.split("\n")
    return "\n".join([*parts[:line], "import os", *parts[line:]])
