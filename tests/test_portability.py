"""What runs only on this computer (domain/portability.py; the owner, 2026-11-17: "any connector that does not
scale to a function app needs to carry a warning that it will only work on your machine" / "we want to advise
against any connectors that only work locally for the user, this is meant to scale to a function app or up to
a hosted streamlit application"): each kind and each way to sign in, the words, the forms' defaults."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import dataverse, lakes, portability, sql_server
from swissarmybench.domain.blade_templates import Template
from swissarmybench.server.blade_templates import TEMPLATES
from tests.conftest import AGENT, AUTH

BY_ID = {t.id: t for t in TEMPLATES}


def keys(code: str, template: str | None = None, passwords: tuple[str, ...] = ()) -> list[str]:
    return [f.key for f in portability.check(code, template, passwords)]


def test_the_words_say_why_and_what_works_instead() -> None:
    (found,) = portability.check(sql_server.code("windows"), "sqlserver")
    assert found.words() == (
        "Only works on your machine: Windows sign-in uses this computer's own Windows account. On a Function "
        "App or hosted Streamlit app use a SQL login whose password is in a key vault, a managed identity or "
        "an app registration."
    )
    assert found.to_json()["words"] == found.words()


# ===== SQL Server and Azure SQL: each way to sign in =====
SQL_SERVER_WAYS = {
    "sql_login": [],
    "managed_identity": [],
    "app_secret": [],
    "entra_default": [],  # ActiveDirectoryDefault: a managed identity in Azure
    "entra_password": [],
    "windows": ["windows"],
    "entra_you": ["as_you"],
    "app_certificate": ["certificate"],
}


@pytest.mark.parametrize("way", sorted(SQL_SERVER_WAYS))
def test_each_sql_server_way_to_sign_in(way: str) -> None:
    assert keys(sql_server.code(way), "sqlserver") == SQL_SERVER_WAYS[way]
    assert keys(sql_server.code(way, sql_server.AZURE_SERVER), "azuresql") == SQL_SERVER_WAYS[way]


def test_an_older_sql_server_code_on_pyodbc_needs_its_odbc_driver() -> None:
    old = (Path(__file__).parent / "golden" / "sql_server" / "old_sql_login.txt").read_text(encoding="utf-8")
    assert keys(old, "sqlserver") == []  # by its way: SQL login runs anywhere ...
    assert sql_server.is_old(old)  # ... and its card offers Update to the new driver (no ODBC driver)


# ===== every kind, as its starter makes it =====
KINDS = {
    "odbc": ["odbc"],
    "access": ["access"],
    "sybase": ["sybase"],
    "csv": ["local_file"],
    "excel": ["local_file"],
    "parquet": ["local_file"],
    "json": ["local_file"],
    "folder": ["local_file"],
    "sqlite": ["local_file"],
    "duckdb": ["local_file"],
    "postgres": [],
    "mysql": [],
    "oracle": [],
    "snowflake": [],  # a password from a key vault (single sign-on in a browser: this computer's only)
    "dataverse": [],
    "powerbi": [],
    "onelake": [],
    "datalake": [],
    "delta": [],
    "sharepoint": [],
    "python": [],
}


@pytest.mark.parametrize("template", sorted(KINDS))
def test_each_kind_as_its_starter_makes_it(template: str) -> None:
    starter = BY_ID[template]
    assert keys(starter.code, template) == KINDS[template], template


def test_a_file_read_from_the_web_or_a_storage_account_runs_anywhere() -> None:
    assert keys('conn = read_csv(r"C:\\data\\orders.csv")', "csv") == ["local_file"]
    assert keys('conn = read_csv("https://example.com/orders.csv")', "csv") == []
    assert keys('conn = duckdb.connect("s3://made-up-bucket/orders.duckdb")', "duckdb") == []


@pytest.mark.parametrize(
    ("code", "wanted"),
    [
        (dataverse.YOU, ["as_you"]),
        (dataverse.MANAGED, []),
        (dataverse.APP, []),
        (lakes.DELTA_LOCAL, ["local_folder"]),
        ('import pyodbc\nconn = pyodbc.connect("DSN=sales")', ["odbc"]),
        ('conn = pyodbc.connect("Driver={x};Server=s;Trusted_Connection=yes;")', ["windows"]),
        ("cred = InteractiveBrowserCredential()\nconn = make(cred)", ["as_you"]),
        ('conn = snowflake.connector.connect(account="a", authenticator="externalbrowser")', ["as_you"]),
        (
            'verify = r"C:\\certs\\company-ca.pem"\nconn = trino.dbapi.connect(verify=verify)',
            ["file_setting"],
        ),
        ('verify = os.environ.get("CA_FILE", r"C:\\certs\\company-ca.pem")\nconn = make(verify)', []),
        ('profile = "made-up"\nconn = make(profile)', ["aws_profile"]),
    ],
)
def test_each_rule_by_the_code(code: str, wanted: list[str]) -> None:
    assert keys(code) == wanted


def test_a_password_saved_in_this_computers_keyring_is_said() -> None:
    code = sql_server.code("sql_login")
    assert keys(code, "sqlserver", ("keyring",)) == ["keyring"]
    assert keys(code, "sqlserver", ("vault", "environment")) == []
    found = portability.check(code, "sqlserver", ("keyring",))[0]
    assert "key vault" in found.instead


def test_each_reason_is_said_once() -> None:
    code = sql_server.code("windows") + "\n# Trusted_Connection=yes again\n"
    assert keys(code, "sqlserver", ("keyring", "keyring")) == ["windows", "keyring"]


# ===== the forms: a portable way first, wherever the kind has one =====


@pytest.mark.parametrize("starter", [t for t in TEMPLATES if t.sign_ins], ids=lambda t: t.id)
def test_every_forms_first_way_runs_on_a_function_app_where_one_can(starter: Template) -> None:
    ways = [{"label": label, "mark": mark, "code": code} for label, mark, code in starter.sign_ins]
    assert portability.portable_first(starter.id, ways), starter.id
    shown = portability.sign_ins(starter.id, ways)
    assert [w["label"] for w in shown] == [w["label"] for w in ways]
    assert all(isinstance(w["local"], list) for w in shown)


def test_the_form_says_each_ways_note_and_the_kinds(client: TestClient) -> None:
    types = {t["id"]: t for t in client.get("/connections/types", headers=AUTH).json()["types"]}
    ways = {w["label"]: w["local"] for w in types["sqlserver"]["sign_ins"]}
    assert ways["User name and password (SQL login)"] == []
    assert ways["Windows sign-in"][0]["words"].startswith("Only works on your machine: Windows sign-in")
    assert types["odbc"]["local"][0]["key"] == "odbc" and types["postgres"]["local"] == []
    assert types["csv"]["local"][0]["key"] == "local_file"


# ===== an export's warning =====


def test_an_exports_warning_names_each_connection_that_will_not_run_there() -> None:
    notes = portability.export_notes(
        [
            ("Warehouse", sql_server.code("windows"), "sqlserver", ()),
            ("Lake", lakes.ONELAKE_SIGN_INS[0][2], "onelake", ()),
            ("Ledger", sql_server.code("sql_login"), "sqlserver", ("keyring",)),
        ]
    )
    assert [n["connection"] for n in notes] == ["Warehouse", "Ledger"]
    words = portability.export_words(notes)
    assert words.startswith("Only works on your machine, not on a Function App or a hosted Streamlit app:")
    assert "Warehouse: Windows sign-in" in words and "Ledger: its password is saved" in words
    assert portability.export_words([]) == ""


def test_the_script_export_says_them_before_it_writes(client: TestClient, tmp_path: Path) -> None:
    for name, way in (("Warehouse", "windows"), ("Ledger", "sql_login")):
        made = {"name": name, "kind": "sql", "template": "sqlserver", "dialect": "sqlserver"}
        saved = client.post("/connections", json=made | {"code": sql_server.code(way)}, headers=AUTH)
        assert saved.status_code == 200, saved.text
    source = 'import swissarmybench as sab\nw = sab.connection("Warehouse")\nl = sab.connection("Ledger")'
    target = tmp_path / "job_automation.py"
    body: dict[str, Any] = {
        "kind": "notebook",
        "cells": [{"kind": "code", "source": source, "number": 1}],
        "to": str(target),
    }
    looked = client.post("/workbench/export-script", json=body | {"check": True}, headers=AGENT).json()
    assert [n["connection"] for n in looked["local"]] == ["Warehouse"] and not target.exists()
    assert looked["local_words"].startswith("Only works on your machine, not on a Function App")
    written = client.post("/workbench/export-script", json=body, headers=AGENT).json()
    assert written["path"] and written["local"] == looked["local"]  # the agent's answer says it too


def test_a_write_starter_for_kinds_that_run_only_here_says_so(client: TestClient) -> None:
    assert [f.key for f in portability.for_tags(["write", "odbc"])] == ["odbc"]
    assert [f.key for f in portability.for_tags(["write", "files", "csv", "folder"])] == ["local_file"]
    assert portability.for_tags(["write", "onelake", "datalake", "parquet", "csv"]) == []  # a lake: anywhere
    assert portability.for_tags(["write", "azuresql", "sqlserver"]) == []
    families = client.get("/blades/starters", headers=AUTH).json()["families"]
    shown = {b["name"]: b["local"] for f in families for b in f["blades"]}
    assert shown["Write to ODBC"][0]["words"].startswith("Only works on your machine: it needs an ODBC driver")
    assert shown["Write to SQL Server"] == []
