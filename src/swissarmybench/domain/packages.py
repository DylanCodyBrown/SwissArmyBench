"""The pip packages a blade's code needs (domain/blades.py reads its imports; this names their packages).

Standard library only, so the plain client can use it.
"""

from __future__ import annotations

import shlex
import sys
from dataclasses import dataclass
from typing import Any

# ===== the packages =====
# The pip packages a blade needs.
#
# A blade's imports are read from its code (above). Each top-level module maps to the package that
# installs it, where the two names differ (`snowflake.connector` comes from
# `snowflake-connector-python`, `yaml` from `PyYAML`); a few calls need a package the code never
# imports (`pd.read_excel` needs openpyxl). Standard library modules need nothing. A module this table
# does not know is assumed to install under its own name, and is marked as a guess.

# Dotted module (the longest that matches wins) -> pip package.
PIP_NAMES: dict[str, str] = {
    "pyodbc": "pyodbc",
    "pymssql": "pymssql",
    "mssql_python": "mssql-python",
    "pytds": "python-tds",  # Dataverse's SQL endpoint (domain/dataverse.py)
    "OpenSSL": "pyOpenSSL",  # python-tds encrypts with it
    "certifi": "certifi",
    "psycopg": "psycopg[binary]",
    "psycopg2": "psycopg2-binary",
    "pg8000": "pg8000",
    "pymysql": "PyMySQL",
    "MySQLdb": "mysqlclient",
    "mysql.connector": "mysql-connector-python",
    "mariadb": "mariadb",
    "oracledb": "oracledb",
    "cx_Oracle": "cx_Oracle",
    "snowflake.connector": "snowflake-connector-python",
    "google.cloud.bigquery": "google-cloud-bigquery",
    "google.cloud.storage": "google-cloud-storage",
    "redshift_connector": "redshift-connector",
    "databricks.sql": "databricks-sql-connector",
    "ibm_db": "ibm_db",
    "ibm_db_dbi": "ibm_db",
    "teradatasql": "teradatasql",
    "trino": "trino",
    "jks": "pyjks",  # a Java keystore (JKS, JCEKS): domain/keystores.py
    "cryptography": "cryptography",
    "prestodb": "presto-python-client",
    "clickhouse_connect": "clickhouse-connect",
    "hdbcli": "hdbcli",
    "vertica_python": "vertica-python",
    "sqlalchemy": "SQLAlchemy",
    "pandas": "pandas",
    "polars": "polars",
    "pyarrow": "pyarrow",
    "numpy": "numpy",
    "openpyxl": "openpyxl",
    "xlrd": "xlrd",
    "pyxlsb": "pyxlsb",
    "duckdb": "duckdb",
    "requests": "requests",
    "httpx": "httpx",
    "boto3": "boto3",
    "s3fs": "s3fs",
    "azure.storage.blob": "azure-storage-blob",
    "azure.identity": "azure-identity",
    "azure.keyvault.secrets": "azure-keyvault-secrets",
    "google.cloud.secretmanager": "google-cloud-secret-manager",
    "hvac": "hvac",
    "onepassword": "onepassword-sdk",
    "keyring": "keyring",
    "yaml": "PyYAML",
    "dotenv": "python-dotenv",
    "bs4": "beautifulsoup4",
    "lxml": "lxml",
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "pymongo": "pymongo",
    "redis": "redis",
    "elasticsearch": "elasticsearch",
    "simple_salesforce": "simple-salesforce",
    "gspread": "gspread",
}

# Calls that need a package the code may never import: `pd.read_excel(...)` reads .xlsx with openpyxl.
CALL_NEEDS: dict[str, str] = {
    "read_excel": "openpyxl",
    "to_excel": "openpyxl",
    "read_parquet": "pyarrow",
    "to_parquet": "pyarrow",
    "read_xml": "lxml",
    "read_html": "lxml",
}

# Never installed by pip: the standard library, and Swiss Army Bench itself (sab.blade gives it).
_PROVIDED: frozenset[str] = frozenset({*sys.stdlib_module_names, "swissarmybench", "__future__"})


@dataclass(frozen=True)
class Package:
    module: str  # the top-level module Python imports
    pip: str  # what installs it
    guessed: bool  # not in PIP_NAMES: assumed to install under its own name
    installed: bool  # importable in this Python

    def to_json(self) -> dict[str, object]:
        return {"module": self.module, "pip": self.pip, "guessed": self.guessed, "installed": self.installed}


def provided(dotted: str) -> bool:
    """A module pip never installs: the standard library's, or Swiss Army Bench's own."""
    return dotted.split(".")[0] in _PROVIDED


def pip_name(dotted: str) -> tuple[str, bool]:
    parts = dotted.split(".")
    for end in range(len(parts), 0, -1):
        known = PIP_NAMES.get(".".join(parts[:end]))
        if known:
            return known, False
    return parts[0], True


def install_command(pips: list[str], python: str | None = None) -> str:
    """`uv pip install ...` for these packages; into `python`'s environment when given."""
    target = f"--python {shlex.quote(python)} " if python else ""
    return f"uv pip install {target}" + " ".join(shlex.quote(p) for p in pips)


def missing_module_hint(module: str) -> str:
    """The sentence for an ImportError: what to install, and the command that does it."""
    pip, _ = pip_name(module)
    return (
        f"This blade needs {pip}, which is not installed in this Python. "
        f"Install it with: {install_command([pip])}"
    )


# ===== a missing package, said the same way everywhere (the owner, 2026-11-16) =====
#
# Wherever the app finds a package missing (a connection's form, a blade, a run that failed on an
# import, a Streamlit app, Test this page, a notebook's cell, a YAML API document), its answer carries
# one shape: {"missing": {"feature", "packages", "python", "command"}}. The page puts it in the user's
# face ("<Feature> needs <package>", Install now, Not now: the front end); the agent reads
# the same words and installs into the Python "python" names: blades_install for the app's own ("app"),
# streamlit_install for a Streamlit app's, `%pip install` in a Workbench kernel for a document's.

APP_PYTHON = "app"  # the app's own Python, where connections and blades run

# A connection form's feature in plain words, where its starter's label is not enough.
_FEATURES: dict[str, str] = {"azure_key_vault": "Key Vault connections"}


def connection_feature(template: str | None, label: str) -> str:
    """A connection form's feature: "Key Vault connections", "Trino connections"."""
    if template and template in _FEATURES:
        return _FEATURES[template]
    words = label.strip() or "These"
    return words if words.lower().endswith("connections") else f"{words} connections"


def blade_feature(name: str | None) -> str:
    """A blade's feature: "The Sales blade", or "This blade" while it has no name."""
    return f"The {name} blade" if name else "This blade"


def missing_packages(feature: str, pips: list[str], python: str, *, own: bool) -> dict[str, Any]:
    """The one answer for packages that are not there: what needs them, which, into which Python
    ("app" for the app's own, else that Python's path), and the command that installs them."""
    unique = list(dict.fromkeys(p for p in pips if p))
    return {
        "feature": feature,
        "packages": unique,
        "python": APP_PYTHON if own else python,
        "command": install_command(unique, python),
    }


def missing_words(missing: dict[str, Any]) -> str:
    """The prompt's one sentence: "Key Vault connections will not work without azure-identity."."""
    packages = [str(p) for p in missing.get("packages") or []]
    listed = ", ".join(packages[:-1]) + f" and {packages[-1]}" if len(packages) > 1 else "".join(packages)
    return f"{missing.get('feature')} will not work without {listed}."


class MissingPackagesError(Exception):
    """A feature that cannot go on without packages: answered 422 with {"error", "missing"}."""

    def __init__(self, missing: dict[str, Any]) -> None:
        super().__init__(missing_words(missing))
        self.missing = missing
