"""What runs only on this computer (the owner, 2026-11-17: "any connector that does not scale to a function
app needs to carry a warning that it will only work on your machine" / "we want to advise against any
connectors that only work locally for the user, this is meant to scale to a function app or up to a hosted
streamlit application").

What the app makes (a connection's code, an exported automation, a Streamlit app) should run unchanged on an
Azure Function App or a hosted Streamlit app: Linux, no desktop, no installed drivers, no signed-in user. A
connection that leans on this computer is said, wherever it is chosen or shown (the form, the card, the
starters, an export, the agent's answers), in one amber line:

    Only works on your machine: <reason>. On a Function App or hosted Streamlit app use <instead>.

Each rule is read from what the app already knows of a connection: its kind (its starter's id), its code (a
text only that way's code holds, as the form tells its sign-ins apart) and where its passwords come from.
Pure: no I/O. The rules (RULES) are data; `check` applies them.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from swissarmybench.domain import sql_server

HEAD = "Only works on your machine"
ELSEWHERE = "On a Function App or hosted Streamlit app use"


@dataclass(frozen=True)
class LocalOnly:
    """One thing a connection leans on that only this computer has: why, and what works instead."""

    key: str
    reason: str
    instead: str

    def words(self) -> str:
        return f"{HEAD}: {self.reason}. {ELSEWHERE} {self.instead}."

    def to_json(self) -> dict[str, str]:
        return {"key": self.key, "reason": self.reason, "instead": self.instead, "words": self.words()}


_VAULT_OR_IDENTITY = "a managed identity, or an app registration whose secret is in a key vault"
_STORAGE = "a storage account: a OneLake, Data Lake or SharePoint connection"

ODBC = LocalOnly(
    "odbc",
    "it needs an ODBC driver installed on this computer (pyodbc)",
    "a driver pip installs: mssql-python for SQL Server and Azure SQL, python-tds for Dataverse, the "
    "database's own Python package for the others",
)
ACCESS = LocalOnly(
    "access",
    "it reads an Access file on this computer's disk through Windows' Access driver",
    "the data in a database or a storage account (Azure SQL, OneLake, a Data Lake)",
)
SYBASE = LocalOnly(
    "sybase",
    "it needs SAP's ASE ODBC driver installed on this computer",
    "a database a pip-installed driver reaches (mssql-python, psycopg, oracledb...)",
)
WINDOWS = LocalOnly(
    "windows",
    "Windows sign-in uses this computer's own Windows account",
    "a SQL login whose password is in a key vault, a managed identity or an app registration",
)
AS_YOU = LocalOnly(
    "as_you",
    "it signs in as you (the Azure command line, VS Code or a browser window)",
    _VAULT_OR_IDENTITY,
)
CERTIFICATE = LocalOnly(
    "certificate",
    "it reads a certificate file on this computer's disk",
    "an app registration whose secret is in a key vault, or a managed identity",
)
FILE_SETTING = LocalOnly(
    "file_setting",
    "it reads a certificate or keystore at a path on this computer's disk",
    "the file's path from an environment variable (From an environment variable) set where it runs",
)
LOCAL_FOLDER = LocalOnly("local_folder", "it reads a folder on this computer's disk", _STORAGE)
AWS_PROFILE = LocalOnly(
    "aws_profile",
    "it reads an AWS profile from this computer's ~/.aws folder",
    "an access key whose secret is in a key vault",
)
LOCAL_FILE = LocalOnly("local_file", "it reads a file on this computer's disk", _STORAGE)
KEYRING_CODE = LocalOnly(
    "keyring_code",
    "it reads this computer's keyring",
    "a key vault (Azure Key Vault by a managed identity), or the app's own environment variables",
)
DOTENV = LocalOnly(
    "dotenv",
    "it reads a .env file at a path on this computer's disk",
    "a key vault, or the app's own environment variables",
)
KEYRING = LocalOnly(
    "keyring",
    "its password is saved in this computer's keyring",
    "a key vault, or an environment variable (the app's own settings there)",
)

# A kind of connection that leans on this computer whatever its sign-in (its starter's id).
KINDS: dict[str, LocalOnly] = {"odbc": ODBC, "access": ACCESS, "sybase": SYBASE}
# Kinds whose code reads a file or folder: on this disk unless its address is a web or cloud one.
FILE_KINDS: frozenset[str] = frozenset({"csv", "excel", "parquet", "json", "folder", "sqlite", "duckdb"})
_CLOUD = re.compile(r"""["'](?:https?|s3|s3a|gs|gcs|az|abfss?|azure|hf|r2)://""", re.IGNORECASE)

# (rule, a pattern only code of that kind holds). The first rule a code matches is said once.
RULES: tuple[tuple[LocalOnly, re.Pattern[str]], ...] = (
    (ODBC, re.compile(r"^\s*(?:import\s+pyodbc|from\s+pyodbc\s+import)\b", re.MULTILINE)),
    (
        WINDOWS,
        re.compile(
            r'sign_in\s*=\s*"windows"|Trusted_Connection\s*=\s*yes|Integrated Security\s*=\s*(?:SSPI|true)'
            r"|ActiveDirectoryIntegrated",
            re.IGNORECASE,
        ),
    ),
    (
        AS_YOU,
        re.compile(
            r'sign_in\s*=\s*"entra_you"|ActiveDirectoryInteractive|externalbrowser|InteractiveBrowserCredential'
            r"|DeviceCodeCredential|AzureCliCredential|VisualStudioCodeCredential"
            r"|exclude_interactive_browser_credential\s*=\s*False",
            re.IGNORECASE,
        ),
    ),
    (CERTIFICATE, re.compile(r"\bCertificateCredential\b|\bcertificate_path\s*=")),
    (LOCAL_FOLDER, re.compile(r"^# A folder on this computer", re.MULTILINE)),
    (AWS_PROFILE, re.compile(r'^profile\s*=\s*"', re.MULTILINE)),
    (KEYRING_CODE, re.compile(r"^\s*import\s+keyring\b|\bkeyring\.get_password\(", re.MULTILINE)),
    (DOTENV, re.compile(r"""\bdotenv_values\(\s*r?["'](?:[A-Za-z]:[\\/]|/|~)""")),
)
# SQL Server's and Azure SQL's code (domain/sql_server.py) says its way to sign in: sign_in="...".
SQL_SERVER_WAYS: dict[str, LocalOnly] = {
    "windows": WINDOWS,
    "entra_integrated": WINDOWS,
    "entra_you": AS_YOU,
    "app_certificate": CERTIFICATE,
}
# A certificate or keystore setting holding a plain path (not from an environment variable).
_FILE_SETTING = re.compile(
    r"""\b(?:keystore|sslrootcert|sslcert|sslkey|ssl_ca|verify)\s*=\s*r?["'](?:[A-Za-z]:[\\/]|/|~|\.{1,2}[\\/])"""
)


def check(
    code: str, template: str | None = None, passwords: Iterable[str] = (), sign_in: bool = True
) -> list[LocalOnly]:
    """What a connection leans on that only this computer has, in order, each once: its kind, its code's
    sign-in and files (`sign_in` False: the kind's alone, as a form says it before a sign-in is
    picked), where its passwords come from (`passwords`: each one's source, "keyring" among them). Kept by
    its inputs: a form's ways hold SQL Server's whole runtime, read by a dozen patterns each time."""
    return list(_check(code or "", str(template or ""), tuple(str(p) for p in passwords), sign_in))


@lru_cache(maxsize=1024)
def _check(code: str, kind: str, passwords: tuple[str, ...], sign_in: bool) -> tuple[LocalOnly, ...]:
    found: list[LocalOnly] = []

    def add(item: LocalOnly) -> None:
        if all(f.key != item.key for f in found):
            found.append(item)

    if kind in KINDS:
        add(KINDS[kind])
    if kind in FILE_KINDS and not _CLOUD.search(code or ""):
        add(LOCAL_FILE)
    way = sql_server.way_of(code or "") if sql_server.is_robust(code or "") else None
    if sign_in and way is not None:  # SQL Server's own code: its runtime holds every way's words
        if way in SQL_SERVER_WAYS:
            add(SQL_SERVER_WAYS[way])
    elif sign_in:
        for rule, pattern in RULES:
            if pattern.search(code or "") and not (rule is ODBC and kind in KINDS):
                add(rule)
        if _FILE_SETTING.search(code or ""):
            add(FILE_SETTING)
    if "keyring" in passwords:
        add(KEYRING)
    return tuple(found)


_NOT_KINDS = frozenset({"write", "files"})


def for_tags(tags: Iterable[str]) -> list[LocalOnly]:
    """A starter's note by the kinds it is for (its tags: a Write starter's ["write", "odbc"]): said when
    every kind it names runs only on this computer (an ODBC source; files and SQLite on this disk)."""
    kinds = [str(t) for t in tags if str(t) not in _NOT_KINDS]
    if not kinds or not all(k in KINDS or k in FILE_KINDS for k in kinds):
        return []
    found: list[LocalOnly] = []
    for kind in kinds:
        item = KINDS.get(kind, LOCAL_FILE)
        if item not in found:
            found.append(item)
    return found


def as_json(found: Sequence[LocalOnly]) -> list[dict[str, str]]:
    return [f.to_json() for f in found]


def sign_ins(template: str | None, ways: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The form's Sign in, each way with what it leans on (`local`: [] for a way that runs anywhere)."""
    return [
        {
            **way,
            "local": as_json([f for f in check(str(way.get("code") or ""), template) if f.key not in KINDS]),
        }
        for way in ways
    ]


def portable_first(template: str | None, ways: Sequence[Mapping[str, Any]]) -> bool:
    """Whether a form's first way (the starter's own code) runs on a Function App or a hosted Streamlit
    app, where the kind has such a way at all."""
    if not ways:
        return True
    runs = [not check(str(w.get("code") or ""), template) for w in ways]
    return runs[0] or not any(runs)


def export_notes(connections: Iterable[tuple[str, str, str | None, Iterable[str]]]) -> list[dict[str, Any]]:
    """An export's warning, before it is written: each connection it uses that will not run on a Function
    App or a hosted Streamlit app ((name, code, template, password sources) in), with its reasons."""
    notes = []
    for name, code, template, passwords in connections:
        found = check(code, template, passwords)
        if found:
            notes.append({"connection": name, "local": as_json(found)})
    return notes


def export_words(notes: Sequence[Mapping[str, Any]]) -> str:
    """The export's warning in one paragraph: each connection, then its reasons."""
    if not notes:
        return ""
    lines = [f"{n['connection']}: " + "; ".join(str(x["reason"]) for x in n["local"]) + "." for n in notes]
    return f"{HEAD}, not on a Function App or a hosted Streamlit app: " + " ".join(lines)
