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

A certificate from a key vault (the owner, 2026-11-20): a certificate file setting whose box is one variable
with no default, `${NAME}`, may hold the certificate itself (a vault's secret: PEM text, or base64 of it),
not a path. Its code is `verify = certificate_file(os.environ["NAME"])`: CERTIFICATE_FILE, written into the
connection's code once a setting uses it (and taken out with its last use), gives the driver a path: the
value itself when it is a file's path, else the text written to a file only the user can read (0600, in a
0700 folder) removed when the Python ends. A default (`${NAME:-C:\\certs\\ca.pem}`) says it is a path, so
it stays the plain `os.environ.get(...)` above. A keystore is never wrapped: keystore_files reads a vault's
value itself (domain/keystores.py).
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Mapping
from typing import Any, TypeGuard

from swissarmybench.domain import variable_refs as refs

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
# The files a driver wants a path for, which a key vault may give as text: certificate_file(...) around them.
WRAPPED = FILE_SETTINGS - {"keystore"}
# A password's own setting, shown only as a variable (`${NAME}`) or empty, never a typed value: the key
# vault's keystore password (domain/keystores.py TRINO_VAULT). Every other password is secret("...").
VARIABLE_ONLY = frozenset({"keystore_password"})
HELPER = "certificate_file"

# The helper written into a connection's code once a setting uses it. Standard library only.
CERTIFICATE_FILE = '''def certificate_file(value):
    """A certificate (or key) file for a driver that wants a path: the value itself when it is a file's
    path, else the certificate as a key vault keeps it (PEM text, or base64 of it) written to a file only
    you can read, removed when this Python ends."""
    import atexit
    import base64
    import os
    import shutil
    import tempfile

    if os.path.isfile(value):
        return value
    text = value.strip()
    if "-----BEGIN" not in text:
        try:
            text = base64.b64decode("".join(text.split()), validate=True).decode("ascii").strip()
        except ValueError:
            text = ""
    if "-----BEGIN" not in text:
        named = sorted(k for k, v in os.environ.items() if v == value)
        where = f" (from {', '.join(named)})" if named else ""
        if len(value) < 400 and "\\n" not in value:
            raise FileNotFoundError(
                f"No certificate file at {value}{where}. Choose it again here; where the code runs "
                "elsewhere (a function app), set its variable to the file's path there, or to the "
                "certificate's PEM text (a key vault's)."
            )
        raise ValueError(f"The certificate{where} is neither a file's path nor PEM text (or base64 of it).")
    folder = tempfile.mkdtemp(prefix="sab-certificate-")  # only you can read it (0700)
    atexit.register(shutil.rmtree, folder, True)
    path = os.path.join(folder, "certificate.pem")
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(handle, "w") as file:
        file.write(text + "\\n")
    return path
'''


def wraps(setting: str | None, text: str) -> bool:
    """Whether a box's text for this setting is written as certificate_file(...): a certificate file a
    driver reads by path, its box exactly one variable with no default (a key vault's value)."""
    found = refs.parts(text)
    return (
        setting in WRAPPED and len(found) == 1 and isinstance(found[0], refs.Ref) and found[0].default is None
    )


def unwrapped(node: ast.expr) -> ast.expr:
    """certificate_file(<expr>) -> <expr>; any other expression as it is."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == HELPER
        and len(node.args) == 1
        and not node.keywords
    ):
        return node.args[0]
    return node


def _defines_helper(statement: ast.stmt) -> bool:
    return isinstance(statement, ast.FunctionDef) and statement.name == HELPER


def with_helper(code: str) -> str:
    """The code with CERTIFICATE_FILE defined after its imports when a setting calls it, and without it when
    none does any more (a box put back to a path)."""
    tree = ast.parse(code)
    calls = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == HELPER
        for n in ast.walk(tree)
    )
    defined = next((s for s in tree.body if _defines_helper(s)), None)
    parts = code.split("\n")
    if calls and defined is None:
        imports = [s for s in tree.body if isinstance(s, ast.Import | ast.ImportFrom)]
        line = (imports[-1].end_lineno or 0) if imports else 0
        helper = CERTIFICATE_FILE.rstrip("\n").split("\n")
        rest = parts[line:]
        while rest and not rest[0].strip():
            rest = rest[1:]
        return "\n".join([*parts[:line], *(["", ""] if line else []), *helper, "", "", *rest])
    if not calls and defined is not None and defined.end_lineno is not None:
        start, end = defined.lineno - 1, defined.end_lineno
        while start > 0 and not parts[start - 1].strip():
            start -= 1  # the blank lines it was set apart with
        while end + 1 < len(parts) and not parts[end].strip() and not parts[end + 1].strip():
            end += 1  # one blank line left between the imports and the rest
        return "\n".join([*parts[:start], *parts[end:]])
    return code


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
