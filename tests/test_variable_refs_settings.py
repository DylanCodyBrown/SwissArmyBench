"""`${NAME}` in a connection's settings (12.7): written into its code as the variables it reads, read back as
the box's text. Made-up servers only."""

from __future__ import annotations

import pytest

from swissarmybench.domain.blades import FillError, Setting, env_settings
from swissarmybench.domain.blades import apply_settings as apply
from swissarmybench.domain.blades import detect_settings as detect

POSTGRES = """import psycopg

conn = psycopg.connect(
    host="my-server",
    port=5432,
    dbname="my_database",
    user="my_user",
    password=secret("password"),
)
"""
ODBC = """import pyodbc

conn = pyodbc.connect("Driver={ODBC Driver 18 for SQL Server};Server=my-server;Database=my_database;")
"""
TOP = """import os

site_url = "https://example.sharepoint.com/sites/x"
tenant_id = "00000000-0000-0000-0000-000000000000"
"""


def by_key(code: str) -> dict[str, Setting]:
    return {s.key: s for s in detect(code)}


def test_a_reference_is_written_as_the_variable_its_code_reads() -> None:
    settings = by_key(POSTGRES)
    code = apply(POSTGRES, {settings["host"].id: "${WAREHOUSE_HOST}", settings["port"].id: "${PGPORT:-5432}"})
    assert 'host=os.environ["WAREHOUSE_HOST"]' in code
    assert 'port=int(os.environ.get("PGPORT", "5432"))' in code
    assert code.startswith("import os\n")
    again = by_key(code)
    assert again["host"].text == "${WAREHOUSE_HOST}"
    assert again["host"].value == "${WAREHOUSE_HOST}"
    assert again["port"].text == "${PGPORT:-5432}"
    assert again["port"].to_json()["type"] == "number"
    # the password stays the code's secret(...): never a setting
    assert "password" not in again


def test_mixed_text_round_trips() -> None:
    settings = by_key(TOP)
    text = "https://${TENANT}.sharepoint.com/sites/${SITE}"
    code = apply(TOP, {settings["site_url"].id: text})
    assert (
        'site_url = "https://" + os.environ["TENANT"] + ".sharepoint.com/sites/" + os.environ["SITE"]' in code
    )
    assert by_key(code)["site_url"].text == text
    assert [m["variable"] for m in env_settings(code)] == ["TENANT", "SITE"]


def test_back_to_a_plain_value() -> None:
    settings = by_key(POSTGRES)
    code = apply(POSTGRES, {settings["host"].id: "${H}", settings["port"].id: "${P}"})
    settings = by_key(code)
    plain = apply(code, {settings["host"].id: "db01.example.local", settings["port"].id: "6432"})
    assert 'host="db01.example.local"' in plain and "port=6432" in plain


def test_the_escape_writes_the_literal_text() -> None:
    settings = by_key(POSTGRES)
    code = apply(POSTGRES, {settings["user"].id: "$${NOT_A_VARIABLE}"})
    assert 'user="${NOT_A_VARIABLE}"' in code
    assert by_key(code)["user"].text == "$${NOT_A_VARIABLE}"
    assert env_settings(code) == []


def test_dollar_signs_that_are_not_references_stay() -> None:
    settings = by_key(POSTGRES)
    code = apply(POSTGRES, {settings["user"].id: "svc$reports"})
    assert 'user="svc$reports"' in code


def test_inside_a_connection_string_is_refused_plainly() -> None:
    settings = by_key(ODBC)
    with pytest.raises(FillError, match="connection string"):
        apply(ODBC, {settings["Server"].id: "${WAREHOUSE_HOST}"})


def test_an_older_mapped_certificate_reads_as_a_reference_with_a_default() -> None:
    code = 'import os\nimport requests\nverify = os.environ.get("CA_FILE", r"C:\\certs\\ca.pem")\n'
    [setting] = detect(code)
    assert setting.env == "CA_FILE"
    assert setting.text == "${CA_FILE:-C:\\certs\\ca.pem}"


def test_the_box_text_form_clears_an_older_mapping() -> None:
    code = 'import os\nimport requests\nverify = os.environ.get("CA_FILE", r"C:\\certs\\ca.pem")\n'
    [setting] = detect(code)
    plain = apply(code, {setting.id: {"text": "C:\\certs\\other.pem"}})
    assert 'verify = r"C:\\certs\\other.pem"' in plain
    [setting] = detect(plain)
    again = apply(plain, {setting.id: {"text": "${CA_FILE:-C:\\certs\\ca.pem}"}})
    assert 'verify = os.environ.get("CA_FILE", r"C:\\certs\\ca.pem")' in again
