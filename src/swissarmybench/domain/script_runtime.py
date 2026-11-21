"""The exported script's (and notebook's) own helpers, as text (domain/script_export.py writes them
in): the package check, the settings and their check, the key vault lookups (Azure Key Vault by the
standard library: its managed identity and REST call), the connections by name, the SQL, DAX and
Read a table helpers, and main(). Each is Python for Python 3.10 or later, standard library only, that
runs in the exported file, never here. Pure text: no I/O.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from swissarmybench.domain import python_connections
from swissarmybench.domain.packages import CALL_NEEDS, PIP_NAMES, pip_name, provided

HEAD_DOC: str = '''\
"""{title}: one Python script, exported from {source} by Swiss Army Bench.

Everything it needs is written out here:
    {inlined}.
It needs no Swiss Army Bench, and it holds no password and no row of data: each password is read
from an environment variable (SETTINGS below), each table is read again from where it comes from.

Run it from any Python {python_version} or later:

    python {file}             checks its packages (REQUIREMENTS below), then runs
    python {file} --install   installs the missing ones first, with pip, into this Python
    python -m pip install {pip_line}

It logs to the terminal and exits with 0 when it worked; 1 when it failed, 2 when a setting is
missing, 3 when a package is. (uv users: `uv run {file}` reads the header above.)

In an Azure Function (Python, the v2 programming model): put this file beside function_app.py, put
its requirements in the function app's requirements.txt:

{requirements_txt}

and call main() from a timer trigger (main() raises when the job fails, so the run shows as failed):

    import azure.functions as func

    import {module} as job

    app = func.FunctionApp()


    @app.timer_trigger(schedule="0 0 6 * * *", arg_name="timer")  # every day at 06:00 UTC
    def {module}_timer(timer: func.TimerRequest) -> None:
        job.main()

Set each of SETTINGS in the function app's Application settings: a Key Vault reference there gives a
password from the vault, and the function app's managed identity signs in to a key vault this script
reads itself.
"""
'''

REQUIREMENTS_CHECK: str = r'''

class MissingRequirements(RuntimeError):
    """A package this script needs is not installed in this Python."""


def missing_requirements() -> list[str]:
    """The requirements whose module this Python cannot import."""
    missing = []
    for module, requirement in REQUIREMENTS.items():
        try:
            found = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):  # a parent package is not there (azure, for azure.identity)
            found = False
        if not found:
            missing.append(requirement)
    return missing


def install_command(missing: list[str]) -> list[str]:
    return [sys.executable, "-m", "pip", "install", *missing]


def check_requirements(install: bool = False) -> None:
    """Every package there, before anything else is imported; `install`: pip installs the missing
    ones into this Python first (only when asked)."""
    missing = missing_requirements()
    if missing and install:
        log.info("Installing %s with pip, into %s", ", ".join(missing), sys.executable)
        subprocess.run(install_command(missing), check=True)  # noqa: S603 (pip, asked for with --install)
        importlib.invalidate_caches()
        missing = missing_requirements()
    if missing:
        command = " ".join(shlex.quote(part) for part in install_command(missing))
        raise MissingRequirements(
            f"This script needs {', '.join(missing)}, which this Python ({sys.executable}) does not have. "
            f"Install them with:\n\n    {command}\n\nor run it with --install to do that first."
        )
'''

SETTINGS_HELPERS: str = r'''

class MissingSetting(RuntimeError):
    """A setting the script needs is not set (the message names it and where it came from)."""


class FillIn(RuntimeError):
    """A part the export could not write: its stub says what to fill in."""


def setting(variable: str, why: str) -> str:
    """An environment variable's value; refused, by its name, when it is not set."""
    value = os.environ.get(variable)
    if value:
        return value
    raise MissingSetting(
        f"{variable} is not set ({why}). Set it in the environment, or in the Azure Function app's "
        "Application settings."
    )


def check_settings() -> None:
    """The plain values set (unless the environment has its own), then every setting the script
    cannot run without, named together before anything runs."""
    for name, value in SETTINGS.items():
        if value is not None:
            os.environ.setdefault(name, value)
    missing = [name for name in REQUIRED if not os.environ.get(name) and name not in FROM_VAULTS]
    if missing:
        listed = "\n".join(f"    {name}  ({SETTINGS_FROM[name]})" for name in missing)
        raise MissingSetting(
            "These settings are not set:\n" + listed + "\nSet each in the environment, or in the Azure "
            "Function app's Application settings. No password is ever written into this script."
        )
    for name in FROM_VAULTS:  # read from its key vault now (when not set): a missing role fails first
        from_vault(name)


def secrets_of(label: str, variables: dict[str, str]) -> Callable[[str], str]:
    """secret("name") for one connection's code: its environment variable, or its key vault entry."""

    def secret(name: str) -> str:
        variable = variables.get(name, name)
        if variable in FROM_VAULTS:
            return from_vault(variable)
        return setting(variable, f"{label} asks for secret({name!r})")

    return secret
'''

PREPARE: str = r'''

def prepare(label: str, variables: list[str]) -> None:
    """A connection from your own Python reads its environment variables itself: each one a key vault
    gives is read from it first, and each it cannot run without is checked."""
    for variable in variables:
        if variable in FROM_VAULTS:
            from_vault(variable)
        elif variable in REQUIRED:
            setting(variable, f"{label} reads it")
'''

VAULT_HELPERS: str = r'''

def from_vault(variable: str) -> str:
    """A setting a key vault gives: the environment's own value when it has one (a local run, or an
    Azure Function's setting), else read from the vault now (once a run), with the vault's own code."""
    value = os.environ.get(variable)
    if value:
        return value
    vault, entry = FROM_VAULTS[variable]
    get, names = VAULTS[vault]()
    if not entry:  # a vault that loads every secret: the entry whose name gives this variable
        if callable(names):
            entry = next((str(n) for n in names() if variable_of(str(n)) == variable), "")
        else:  # Key Vault's names: letters, digits and dashes, any case (warehouse_password -> warehouse-password)
            entry = variable.replace("__", "--").replace("_", "-")
        if not entry:
            raise MissingSetting(f"The key vault {vault} has no entry for {variable}.")
    log.info("Reading %s from the key vault %s", variable, vault)
    found = get(entry)
    if found is None:
        raise MissingSetting(f"The key vault {vault} has no entry {entry!r} (for {variable}).")
    os.environ[variable] = str(found)  # the connections read it as the app's kernels do
    return str(found)


def variable_of(entry: str) -> str:
    """A vault entry's variable, as the app names it (warehouse-password -> warehouse_password)."""
    bare = re.sub(r"^[a-z][a-z0-9+.-]*://", "", entry.strip(), flags=re.IGNORECASE)
    words = re.sub(r"[^A-Za-z0-9_]", "_", bare.replace("--", "__")).strip("_")[:128] or "SECRET"
    return words if not words[0].isdigit() else f"_{words}"[:128]
'''

# An Azure Key Vault, read with the standard library: the managed identity first (an Azure Function or
# App Service's IDENTITY_ENDPOINT, a VM's or container's IMDS), then azure-identity's
# DefaultAzureCredential only when that package is installed (az login, or an app registration's
# AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET), then Key Vault's own REST call. It needs
# only "get secret" (the Key Vault Secrets User role, or an access policy with Get), never list.
AZURE_HELPERS: str = r'''

KEY_VAULT_RESOURCE = "https://vault.azure.net"
IMDS_ENDPOINT = "http://169.254.169.254/metadata/identity/oauth2/token"
_TOKENS: dict[str, str] = {}  # this run's sign-in, kept in memory only
_SECRETS: dict[tuple[str, str], str] = {}  # this run's values, kept in memory only


class KeyVaultError(MissingSetting):
    """A key vault could not be read: which secret, which vault, what was tried (never a value)."""


def _local(url: str) -> bool:
    host = urllib.parse.urlsplit(url).hostname or ""
    return host in ("127.0.0.1", "localhost", "::1", "169.254.169.254")


def _ask_json(url: str, headers: dict[str, str], timeout: float) -> Any:
    """One GET, its JSON answer. A local endpoint (the managed identity's) is reached directly, never
    through a proxy."""
    request = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if _local(url) else urllib.request.build_opener()
    with opener.open(request, timeout=timeout) as answer:  # noqa: S310 (Azure's own endpoints)
        return json.loads(answer.read() or b"null")


def _refused(error: urllib.error.HTTPError) -> str:
    try:
        said = json.loads(error.read() or b"{}")
        found = said.get("error") or said
        return str(found.get("message") or found.get("code") or found) if isinstance(found, dict) else str(found)
    except (ValueError, AttributeError):
        return error.reason or "no reason"


def _managed_identity(client: str | None) -> tuple[str, str, dict[str, str], float]:
    """The managed identity's token request: an Azure Function or App Service's IDENTITY_ENDPOINT,
    else a VM's or container's metadata service (a short wait: a local run fails fast)."""
    client = client or os.environ.get("AZURE_CLIENT_ID")  # a user-assigned identity's
    query = {"resource": KEY_VAULT_RESOURCE} | ({"client_id": client} if client else {})
    endpoint, header = os.environ.get("IDENTITY_ENDPOINT"), os.environ.get("IDENTITY_HEADER")
    if endpoint and header:
        url = f"{endpoint}?{urllib.parse.urlencode(query | {'api-version': '2019-08-01'})}"
        return "the managed identity (IDENTITY_ENDPOINT)", url, {"X-IDENTITY-HEADER": header}, 30.0
    url = f"{IMDS_ENDPOINT}?{urllib.parse.urlencode(query | {'api-version': '2018-02-01'})}"
    return "the managed identity (the VM's metadata service)", url, {"Metadata": "true"}, 2.0


def azure_token(vault: str, entry: str, sign_in: dict[str, Any] | None = None) -> str:
    """A token for Key Vault, by the vault's own sign-in: the managed identity (in Azure), then, for a
    vault that signs in as you, azure-identity's DefaultAzureCredential when that package is installed
    (az login). Nothing is entered on this computer to open a vault."""
    sign_in = sign_in or {"how": "you"}
    key = f"{sign_in['how']}:{vault}"
    if key in _TOKENS:
        return _TOKENS[key]
    tried: list[str] = []
    client = sign_in["client"]() if "client" in sign_in else None
    what, url, headers, timeout = _managed_identity(str(client) if client else None)
    try:
        _TOKENS[key] = str(_ask_json(url, headers, timeout)["access_token"])
        return _TOKENS[key]
    except urllib.error.HTTPError as error:
        tried.append(f"{what}: refused ({error.code}: {_refused(error)})")
    except Exception as error:
        tried.append(f"{what}: {type(error).__name__}")
    if sign_in["how"] == "you":
        try:
            from azure.identity import DefaultAzureCredential
        except ImportError:
            tried.append("azure-identity: not installed (optional: pip install azure-identity, for az login)")
        else:
            try:
                _TOKENS[key] = DefaultAzureCredential().get_token(f"{KEY_VAULT_RESOURCE}/.default").token
                return _TOKENS[key]
            except Exception as error:
                tried.append(f"azure-identity's DefaultAzureCredential: {type(error).__name__}")
    raise KeyVaultError(
        f"No sign-in to the key vault {vault} worked (for its secret {entry!r}). Tried: " + "; ".join(tried) + "."
    )


def azure_secret(vault: str, url: str, entry: str, sign_in: dict[str, Any] | None = None) -> str | None:
    """One secret's value by Key Vault's REST call (GET, needs only "get secret")."""
    if (url, entry) in _SECRETS:
        return _SECRETS[(url, entry)]
    token = azure_token(vault, entry, sign_in)


    address = f"{url.rstrip('/')}/secrets/{urllib.parse.quote(entry, safe='')}?api-version=7.4"
    try:
        found = _ask_json(address, {"Authorization": f"Bearer {token}"}, 30.0)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        hint = {
            401: "the sign-in was not accepted",
            403: "this identity may not read its secrets: give it the Key Vault Secrets User role "
            "(or an access policy with Get)",
        }.get(error.code, "")
        raise KeyVaultError(
            f"The key vault {vault} refused its secret {entry!r} ({error.code}: {_refused(error)})"
            + (f": {hint}." if hint else ".")
        ) from None
    except OSError as error:
        raise KeyVaultError(f"The key vault {vault} ({url}) could not be reached: {error}") from None
    _SECRETS[(url, entry)] = str(found.get("value"))
    return _SECRETS[(url, entry)]
'''

MADE_HELPERS: str = r'''

def connection(name: str) -> Any:
    """What a connection's (or a blade's) code makes, made once."""
    return MADE[name]()


blade = connection
'''

SQL_HELPERS: str = r'''

# The file kinds a SQL cell reads, by suffix (DuckDB's readers; a workbook through pandas).
FILE_READERS = {
    ".csv": "read_csv_auto",
    ".tsv": "read_csv_auto",
    ".txt": "read_csv_auto",
    ".parquet": "read_parquet",
    ".json": "read_json_auto",
    ".jsonl": "read_json_auto",
    ".ndjson": "read_json_auto",
}
WORKBOOKS = (".xlsx", ".xlsm", ".xls")


def quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def frame(names: list[str], rows: list[Any]) -> Any:
    import pandas as pd

    return pd.DataFrame.from_records([tuple(r) for r in rows], columns=names)


def run_database(target: Any, query: str, params: Any = None) -> Any:
    """A query on a database connection, in its own SQL (or a Power BI dataset, in DAX). `params`: the
    query's bound values, in the driver's own style (a page's widget values: never pasted in)."""
    module = type(target).__module__
    if module.startswith("duckdb"):
        if params:
            return target.execute(query, params).df()
        relation = target.sql(query)
        return None if relation is None else relation.df()
    if module.startswith("sqlalchemy"):
        from sqlalchemy import text

        with target.begin() as live:
            result = live.execute(text(query), params) if params else live.execute(text(query))
            if not result.returns_rows:
                return f"{result.rowcount} row(s) changed."
            return frame(list(result.keys()), result.fetchall())
    cursor = target.cursor()
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        if cursor.description is None:  # an UPDATE, INSERT, CREATE: no rows
            commit = getattr(target, "commit", None)
            if callable(commit):
                commit()
            return f"{getattr(cursor, 'rowcount', -1)} row(s) changed."
        return frame([str(d[0]) for d in cursor.description], cursor.fetchall())
    finally:
        close = getattr(cursor, "close", None)
        if callable(close):
            close()


def is_table(value: Any) -> bool:
    module = type(value).__module__.split(".")[0]
    return module in ("pandas", "polars", "pyarrow") and hasattr(value, "columns")


def view(con: Any, schema: str | None, table: str, select: str) -> None:
    """A file's table by its bare name (the first to claim it) and as the connection's catalog names it."""
    names = [quoted(table)]
    if schema and schema.lower() not in ("main", "temp", "system", "information_schema", "pg_catalog"):
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {quoted(schema)}")
        names.append(f"{quoted(schema)}.{quoted(table)}")
    taken = {r[0].lower() for r in con.execute("SELECT view_name FROM duckdb_views()").fetchall()}
    for i, name in enumerate(names):
        if i == 0 and table.lower() in taken:
            continue
        con.execute(f"CREATE OR REPLACE VIEW {name} AS {select}")


def open_files(label: str, value: Any) -> Any:
    """DuckDB over a file connection's path: a file is a table named after it, a workbook's sheets
    are tables named after them, a folder's files are tables named after the files."""
    import duckdb

    path = Path(value).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"{label} points at {path}, which is not there.")
    con = duckdb.connect()
    folder = path.is_dir()
    files = sorted(p for p in path.iterdir() if p.is_file()) if folder else [path]
    for file in files:
        reader = FILE_READERS.get(file.suffix.lower())
        literal = "'" + str(file).replace("'", "''") + "'"
        if reader:
            select = f"SELECT * FROM {reader}({literal})"
            if folder:
                view(con, path.name, file.name, select)
            view(con, None if folder else file.parent.name, file.stem, select)
        elif file.suffix.lower() in WORKBOOKS:
            import pandas as pd

            for i, (sheet, sheet_frame) in enumerate(pd.read_excel(file, sheet_name=None).items()):
                hidden = f"sheet_{abs(hash((str(file), str(sheet))))}"
                con.register(hidden, sheet_frame)
                if folder and i == 0:
                    view(con, path.name, file.name, f"SELECT * FROM {hidden}")
                    view(con, None, file.stem, f"SELECT * FROM {hidden}")
                view(con, file.stem, str(sheet), f"SELECT * FROM {hidden}")
    return con


@functools.cache
def sql_target(name: str) -> tuple[str, Any]:
    """What runs a connection's SQL: its database, or DuckDB over its file or its tables."""
    value = connection(name)
    if isinstance(value, (str, os.PathLike)):
        return "files", open_files(name, value)
    if is_table(value) or (isinstance(value, dict) and value and all(map(is_table, value.values()))):
        import duckdb

        con = duckdb.connect()
        for table, held in (value if isinstance(value, dict) else {VARIABLES[name]: value}).items():
            con.register(str(table), held)
        return "tables", con
    return "database", value


def run_sql(name: str, query: str) -> Any:
    """A query on a connection, as a SQL cell runs it: a DataFrame, or a line saying what changed."""
    kind, target = sql_target(name)
    text = query.strip()
    if kind == "database":
        return run_database(target, text.rstrip(";") if text.count(";") == 1 else text)
    relation = target.sql(text)
    return None if relation is None else relation.df()
'''

DAX_HELPERS: str = r'''

@functools.cache
def dax_dataset(name: str) -> Any:
    """One dataset of a Power BI workspace: `Finance/Sales model` (a workspace with one dataset needs
    no dataset's name)."""
    base, _, dataset = name.partition("/")
    workspace = connection(base.strip())
    lister = getattr(workspace, "datasets", None)
    if not callable(lister):
        return workspace
    if not dataset.strip():
        listed = [str(d["name"]) for d in lister()]
        if len(listed) != 1:
            raise ValueError(f"{base} has {len(listed)} datasets: name one, as {base}/<dataset>.")
        dataset = listed[0]
    return workspace.dataset(dataset.strip())


def run_dax(name: str, query: str) -> Any:
    """A DAX query on one dataset of a Power BI workspace, as a DAX cell runs it: a DataFrame."""
    return run_database(dax_dataset(name), query.strip())
'''

READ_HELPERS: str = r'''

def read_table(name: str, table: str, schema: str = "", limit: int | None = None) -> Any:
    """A table by a connection's own Read a table box (a connection from your own Python)."""
    result = READERS[name]()[1](schema, table, limit)
    if isinstance(result, tuple) and len(result) == 2 and (result[1] is None or isinstance(result[1], int)):
        return result[0]  # (rows, total): the rows
    return result
'''

MAIN: str = r'''

def main(install: bool = False) -> None:
    """Run the whole job once (an Azure Function's timer trigger calls this). Raises when it fails."""
    check_requirements(install)
    check_settings()
    log.info("Started")
    run()
    log.info("Done")


def cli(arguments: list[str]) -> int:
    """`python {file} [--install]`: logging to the terminal, an exit code that says how it went."""
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    unknown = [a for a in arguments if a != "--install"]
    if unknown:
        print(f"Unknown option {unknown[0]}: the one option is --install.", file=sys.stderr)
        return 2
    try:
        main(install="--install" in arguments)
    except MissingRequirements as error:
        print(error, file=sys.stderr)
        return 3
    except MissingSetting as error:
        log.error("%s", error)
        return 2
    except Exception:
        log.exception("Failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
'''

NO_VAULTS: str = '''
def from_vault(variable: str) -> str:
    """No key vault gives this script a setting."""
    return setting(variable, "no key vault gives it here")
'''

LOAD_VAULT: str = '''
def load_vault(name: str) -> list[str]:
    """A key vault used by its name: its entries this script maps, set as environment variables."""
    wanted = [v for v, (vault, _) in FROM_VAULTS.items() if vault == name]
    for variable in wanted:
        from_vault(variable)
    return sorted(wanted)
'''

IMPORTS: str = """import functools
import importlib.util
import json
import logging
import os
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any"""

NOTEBOOK_HEAD: str = """# {title}

One notebook, exported from {source} by Swiss Army Bench. Everything it needs is written out here:
{inlined}. It needs no Swiss Army Bench and no magics, and it holds no password and no row of data:
each password is read from an environment variable (the settings cell), each table is read again
from where it comes from. It runs top to bottom in any plain Jupyter kernel (Python {python_version}
or later), as a scheduler runs it:

    jupyter nbconvert --to notebook --execute {file}
    papermill {file} out.ipynb -p REPORT_DATE 2026-11-15

The first cell checks its packages and says the exact `pip install` for this kernel's Python (or set
`INSTALL = True` there to install them). Its requirements, for a requirements.txt:

{requirements_txt}

The settings cell is tagged `parameters`, so papermill can pass any of them. Give passwords as
environment variables rather than parameters: papermill writes its parameters into the notebook it
runs.
"""


# ===== the settings and the requirements =====


# Lower versions where they matter: what the written-out code needs of each.
MINIMUM: dict[str, str] = {
    "duckdb": ">=1.1",
    "pandas": ">=2.0",
    "pyarrow": ">=14",
    "polars": ">=1.0",
    "openpyxl": ">=3.1",
    "SQLAlchemy": ">=2.0",
    "azure-identity": ">=1.15",
    "azure-keyvault-secrets": ">=4.7",
}


@dataclass(frozen=True)
class Secret:
    """One value a piece's code reads: by `secret("name")`, or (a connection from your own Python) by
    the environment variable its boxes read."""

    name: str  # as the code asks for it
    variable: str  # the environment variable the script reads
    where: str  # keyring, environment, vault, every (a vault that loads every secret), typed, value, api,
    # file (a certificate or keystore file's path, mapped to a variable: domain/certificate_files.py)
    vault: str = ""  # the key vault's name (vault, every)
    entry: str = ""  # its entry's name (vault)
    blade: str = ""  # the secret blade that asks for it (typed)
    value: str = ""  # a plain value (value only: never a secret)
    required: bool = True


AZURE_URL = re.compile(r"""vault_url\s*=\s*["'](?P<url>https?://[^"'\s]+)["']""")


def azure_vault_url(code: str) -> str | None:
    """An Azure Key Vault blade's address (its `SecretClient(vault_url="https://...")`), or None."""
    if "SecretClient" not in code:
        return None
    found = AZURE_URL.search(code)
    return found.group("url") if found else None


def azure_sign_in(code: str) -> tuple[str, dict[str, str]]:
    """How an Azure Key Vault blade signs in (the form's Sign in): "managed" (with a client id, as
    the Python that gives it, for a user-assigned identity) or "you"."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return "you", {}
    assigned: dict[str, ast.expr] = {}
    for statement in tree.body:
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
        ):
            assigned[statement.targets[0].id] = statement.value

    class _Values(ast.NodeTransformer):
        def visit_Name(self, node: ast.Name) -> ast.AST:
            return assigned.get(node.id, node)  # tenant_id -> "made-up-tenant" (as the code set it)

    def given(node: ast.expr | None) -> str | None:
        return None if node is None else ast.unparse(_Values().visit(node))

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name | ast.Attribute)):
            continue
        called = node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        named = {k.arg: k.value for k in node.keywords if k.arg}
        if called == "ManagedIdentityCredential":
            client = given(named.get("client_id"))
            return "managed", {"client": client} if client else {}
    return "you", {}


def requirements_of(text: str, extra: Iterable[str]) -> dict[str, str]:
    """module -> requirement, for what the code imports (and the calls that need a package)."""
    found: dict[str, str] = {}  # module -> requirement
    pips: set[str] = set()

    def add(module: str, pip: str) -> None:
        if pip.lower() not in pips:
            pips.add(pip.lower())
            found[module] = pip + MINIMUM.get(pip, "")

    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = ast.Module(body=[], type_ignores=[])
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            modules = [node.module]
        for dotted in modules:
            if not provided(dotted):
                add(module_for(dotted), pip_name(dotted)[0])
        if isinstance(node, ast.Attribute):
            if node.attr in CALL_NEEDS:
                add(CALL_NEEDS[node.attr], CALL_NEEDS[node.attr])
            if node.attr in ("df", "read_excel", "to_excel", "to_csv"):
                add("pandas", "pandas")
            if node.attr == "pl":
                add("polars", "polars")
            if node.attr == "arrow":
                add("pyarrow", "pyarrow")
    for wanted in extra:  # %pip install in a cell
        bare = re.split(r"[<>=!~\[; ]", wanted, maxsplit=1)[0]
        if bare and bare.lower() not in pips:
            pips.add(bare.lower())
            found[IMPORTED_AS.get(bare, bare.replace("-", "_").lower())] = wanted
    return found


# What a package is imported as, where the two differ (the package check imports it).
IMPORTED_AS: dict[str, str] = {
    "PyYAML": "yaml",
    "Pillow": "PIL",
    "scikit-learn": "sklearn",
    "python-dotenv": "dotenv",
    "beautifulsoup4": "bs4",
}


def module_for(dotted: str) -> str:
    """The module the package check imports for an import: the longest known dotted name
    (snowflake.connector, azure.identity), else the top level."""
    parts = dotted.split(".")
    for end in range(len(parts), 1, -1):
        if ".".join(parts[:end]) in PIP_NAMES:
            return ".".join(parts[:end])
    return parts[0]


def settings_block(secrets: Sequence[Secret]) -> tuple[str, list[dict[str, object]]]:
    """SETTINGS (each variable, one per line, where it came from), REQUIRED, FROM_VAULTS."""
    seen: dict[str, Secret] = {}
    for secret in secrets:
        held = seen.get(secret.variable)
        if (
            held is None
            or (secret.required and not held.required)
            or (secret.where == "vault" and held.where != "vault")
        ):
            seen[secret.variable] = secret
    rows: list[str] = []
    said: list[str] = []
    listed: list[dict[str, object]] = []
    required: list[str] = []
    vaults: list[str] = []
    for variable, secret in seen.items():
        where = where_from(secret)
        value = repr(secret.value) if secret.where == "value" else "None"
        rows.append(f"    {variable!r}: {value},  # {where}")
        said.append(f"    {variable!r}: {where!r},")
        if secret.required and secret.where != "value":
            required.append(variable)
        if secret.where in ("vault", "every"):
            vaults.append(f"    {variable!r}: ({secret.vault!r}, {secret.entry!r}),")
        listed.append(
            {
                "variable": variable,
                "from": secret.where,
                "where": where,
                "secret": secret.where in ("keyring", "vault", "every", "typed", "notebook")
                or python_connections.looks_secret(variable),
                "required": secret.required,
            }
        )
    text = (
        "# ===== SETTINGS: every environment variable this script reads =====\n"
        "# Set each where the script runs (the terminal, or the Azure Function app's Application settings).\n"
        "# A secret's value is never written here: only a plain value, as its default.\n"
        "SETTINGS: dict[str, str | None] = {\n" + "\n".join(rows) + ("\n" if rows else "") + "}\n"
        "SETTINGS_FROM: dict[str, str] = {\n" + "\n".join(said) + ("\n" if said else "") + "}\n"
        f"# The ones the script cannot run without (a key vault's are read from it when not set).\n"
        f"REQUIRED: tuple[str, ...] = ({''.join(f'{n!r}, ' for n in required).rstrip()})\n"
        "# variable -> (the key vault, its entry): read from the vault at run time when not set.\n"
        "FROM_VAULTS: dict[str, tuple[str, str]] = {\n" + "\n".join(vaults) + ("\n" if vaults else "") + "}\n"
    )
    return text, listed


def where_from(secret: Secret) -> str:
    what = f"secret({secret.name!r})" if secret.name != secret.variable else secret.variable
    owner = f"{secret.blade}'s {what}" if secret.blade else what
    if secret.where == "keyring":
        return f"{owner}: saved in the keyring where it was exported; a secret, set it here"
    if secret.where == "vault":
        return f"{owner}: the key vault {secret.vault}, entry {secret.entry!r} (read from it when not set)"
    if secret.where == "every":
        return f"{owner}: the key vault {secret.vault}, which loads every secret (read from it when not set)"
    if secret.where == "typed":
        return f"{owner}: typed into the secret blade {secret.vault} in the app; a secret, set it here"
    if secret.where == "value":
        return f"{owner}: a plain value in the app (no secret), its default here"
    if secret.where == "notebook":
        return f"{owner}: set with %env in the notebook; a secret, set it here"
    if secret.where == "file":
        return (
            f"{owner}: a certificate or keystore file's path; set it to where the file is here (an Azure "
            "Function app: an Application setting). Unset, the path on the computer it was exported from"
        )
    if secret.where == "api":
        return f"{owner}: the API client reads it when no argument gives it (optional)"
    if secret.where == "code":
        return f"{owner}: the notebook's own code reads it" + ("" if secret.required else " (optional)")
    return f"{owner}: this computer's environment in the app" + ("" if secret.required else " (optional)")
