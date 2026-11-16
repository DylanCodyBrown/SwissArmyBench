"""A missing package, said the same way everywhere (the owner, 2026-11-16): every place that finds one
answers {"missing": {"feature", "packages", "python", "command"}}, which the page's prompt reads
("<Feature> needs <package>", Install now, Not now) and the agent acts on. The packages here are
made up or absent from this Python; nothing is installed."""

from __future__ import annotations

import sys

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain.packages import (
    MissingPackagesError,
    blade_feature,
    connection_feature,
    missing_packages,
    missing_words,
)
from swissarmybench.server.http import error_response
from tests.conftest import AGENT, AUTH

SHAPE = {"feature", "packages", "python", "command"}


# ===== the shape and its words =====


def test_the_answer_names_the_feature_the_packages_and_the_python() -> None:
    own = missing_packages(
        "Key Vault connections", ["azure-identity", "azure-identity", ""], "/app/py", own=True
    )
    assert own == {
        "feature": "Key Vault connections",
        "packages": ["azure-identity"],  # once, and no empty name
        "python": "app",  # the app's own: blades_install
        "command": "uv pip install --python /app/py azure-identity",
    }
    other = missing_packages("Streamlit apps", ["streamlit", "pyarrow"], "/envs/shop/python", own=False)
    assert other["python"] == "/envs/shop/python"  # another Python: its path


def test_the_prompts_sentence_is_plain_words() -> None:
    one = missing_packages("Key Vault connections", ["azure-identity"], "p", own=True)
    assert missing_words(one) == "Key Vault connections will not work without azure-identity."
    three = missing_packages("Streamlit apps", ["streamlit", "pandas", "pyarrow"], "p", own=False)
    assert missing_words(three) == "Streamlit apps will not work without streamlit, pandas and pyarrow."


def test_features_are_named_in_plain_words() -> None:
    assert connection_feature("azure_key_vault", "Azure Key Vault") == "Key Vault connections"
    assert connection_feature("trino", "Trino") == "Trino connections"
    assert connection_feature(None, "Python connections") == "Python connections"
    assert blade_feature("Sales") == "The Sales blade" and blade_feature(None) == "This blade"


def test_the_error_is_answered_422_with_the_shape() -> None:
    missing = missing_packages("Reading YAML API documents", ["PyYAML"], "p", own=True)
    response = error_response(MissingPackagesError(missing))
    assert response.status_code == 422
    assert b'"missing"' in response.body and b"will not work without PyYAML" in response.body


# ===== each place =====


def test_inspect_says_what_is_missing_for_a_blade(client: TestClient) -> None:
    seen = client.post(
        "/blades/inspect", json={"code": "import made_up_driver\nconn = 1\n", "name": "Bakery"}, headers=AUTH
    ).json()
    assert seen["missing"]["feature"] == "The Bakery blade"
    assert seen["missing"]["packages"] == ["made_up_driver"] and seen["missing"]["python"] == "app"
    nothing = client.post("/blades/inspect", json={"code": "import json\nconn = 1\n"}, headers=AUTH).json()
    assert nothing["missing"] is None


def test_a_connections_form_says_what_is_missing_by_its_kind(client: TestClient) -> None:
    types = {t["id"]: t for t in client.get("/connections/types", headers=AUTH).json()["types"]}
    for template, feature, module in (
        ("azure_key_vault", "Key Vault connections", "azure.identity"),
        ("trino", "Trino / Presto connections", "trino"),
    ):
        try:
            __import__(module)
            continue  # here, the package is there: nothing to say
        except ImportError:
            pass
        missing = types[template]["missing"]
        assert set(missing) == SHAPE and missing["feature"] == feature and missing["python"] == "app"
    # A form whose code needs nothing from pip says nothing.
    assert types["sqlite"]["missing"] is None


def test_a_connection_test_that_stops_on_an_import_names_its_kind(client: TestClient) -> None:
    body = {
        "name": "",
        "kind": "sql",
        "template": "trino",
        "variable": "conn",
        "code": "import made_up_trino_driver\nconn = 1\n",
    }
    failed = client.post("/connections/test", json=body, headers=AUTH)
    assert failed.status_code == 422, failed.text
    assert failed.json()["missing"]["feature"] == "Trino / Presto connections"
    assert failed.json()["missing"]["packages"] == ["made_up_trino_driver"]


def test_a_yaml_api_document_without_pyyaml_asks_for_it(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "yaml", None)  # this Python has no PyYAML
    answer = client.post("/apis/preview", json={"spec": "openapi: 3.0.0\npaths: {}\n"}, headers=AUTH)
    assert answer.status_code == 422
    assert answer.json()["missing"] == {
        "feature": "Reading YAML API documents",
        "packages": ["PyYAML"],
        "python": "app",
        "command": answer.json()["missing"]["command"],
    }
    assert answer.json()["error"] == "Reading YAML API documents will not work without PyYAML."
    # The agent reads the same answer.
    told = client.post("/apis/preview", json={"spec": "openapi: 3.0.0\npaths: {}\n"}, headers=AGENT)
    assert told.status_code == 422 and told.json()["missing"]["packages"] == ["PyYAML"]
