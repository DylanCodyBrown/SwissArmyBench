"""Trino's client certificate from a keystore file (domain/keystores.py), and certificate or keystore
files read from an environment variable (domain/certificate_files.py). Made-up keys, certificates and
keystores only, made here with cryptography (and pyjks for JKS, skipped where it is not installed); the
end-to-end tests sign in to a made-up Trino on 127.0.0.1 that asks for a client certificate
(tests/trino_standin.py)."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from starlette.testclient import TestClient

from swissarmybench.domain import blades, keystores, script_runs
from swissarmybench.domain import script_export as se
from swissarmybench.domain.blades import FillError, apply_settings, detect_settings, env_settings
from swissarmybench.domain.connections import form_order, picker
from swissarmybench.domain.script_export import ExportCell, Piece, Secret
from swissarmybench.server.blade_templates import BY_ID
from tests import trino_standin as made_up
from tests.conftest import AGENT, AUTH
from tests.fake_keyring import memory_keyring

HAS_JKS = True
try:
    import jks  # type: ignore[import-untyped]  # noqa: F401
except ImportError:
    HAS_JKS = False
needs_jks = pytest.mark.skipif(not HAS_JKS, reason="pyjks is not installed in this Python")
HAS_TRINO = True
try:
    import trino  # type: ignore[import-not-found, unused-ignore]  # noqa: F401
except ImportError:
    HAS_TRINO = False
needs_trino = pytest.mark.skipif(not HAS_TRINO, reason="the trino client is not installed in this Python")


@pytest.fixture(autouse=True)
def keyring() -> Iterator[None]:
    with memory_keyring():
        yield


@pytest.fixture(scope="module")
def m() -> made_up.Material:
    return made_up.material()


def helper() -> Any:
    space: dict[str, Any] = {}
    exec(keystores.KEYSTORE_FILES, space)  # noqa: S102 (the connection's own helper, as its code runs it)
    return space["keystore_files"]


def setting(code: str, name: str) -> blades.Setting:
    return next(s for s in detect_settings(code) if s.name == name)


# ===== the format and the reading =====


@needs_jks
def test_the_format_is_told_by_the_first_bytes_never_the_name(m: made_up.Material) -> None:
    assert keystores.keystore_format(made_up.pkcs12_bytes(m)) == "PKCS#12"
    assert keystores.keystore_format(made_up.jks_bytes(m)) == "JKS"
    assert keystores.keystore_format(b"\xce\xce\xce\xce" + b"\0" * 8) == "JCEKS"
    assert keystores.keystore_format(b"-----BEGIN CERTIFICATE-----") == ""


def read_and_check(m: made_up.Material, path: Path, alias: str = "") -> tuple[str, str]:
    cert, key = helper()(str(path), made_up.PASSWORD, alias)
    chain = x509.load_pem_x509_certificates(Path(cert).read_bytes())
    assert chain[0] == m.client_cert and chain[1] == m.ca_cert  # the leaf first, then its chain
    loaded = serialization.load_pem_private_key(Path(key).read_bytes(), None)
    assert loaded.public_key().public_numbers() == m.client_key.public_key().public_numbers()  # type: ignore[union-attr]
    if os.name == "posix":  # only the user can read them
        assert stat.S_IMODE(os.stat(key).st_mode) == 0o600 and stat.S_IMODE(os.stat(cert).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(Path(key).parent).st_mode) == 0o700
    return cert, key


def test_a_pkcs12_keystore_gives_its_key_and_chain_as_files_only_you_can_read(
    m: made_up.Material, tmp_path: Path
) -> None:
    path = tmp_path / "lake.keystore"  # the name says nothing: the bytes do
    path.write_bytes(made_up.pkcs12_bytes(m))
    read_and_check(m, path)
    read_and_check(m, path, "lake")  # its friendly name
    with pytest.raises(ValueError, match="no private key named other: it has lake"):
        helper()(str(path), made_up.PASSWORD, "other")


@needs_jks
@pytest.mark.parametrize("kind", ["jks", "jceks"])
def test_a_java_keystore_is_read_with_pyjks(m: made_up.Material, tmp_path: Path, kind: str) -> None:
    path = tmp_path / "lake.keystore"
    path.write_bytes(made_up.jks_bytes(m) if kind == "jks" else made_up.jceks_bytes(m))
    assert keystores.keystore_format(path.read_bytes()) == kind.upper()
    read_and_check(m, path)


@needs_jks
def test_several_keys_need_the_alias_named(m: made_up.Material, tmp_path: Path) -> None:
    path = tmp_path / "two.jks"
    path.write_bytes(made_up.jks_bytes(m, aliases=("lake", "warehouse")))
    with pytest.raises(ValueError, match=r"holds 2 private keys \(lake, warehouse\): name the one to use"):
        helper()(str(path), made_up.PASSWORD)
    read_and_check(m, path, "warehouse")
    with pytest.raises(ValueError, match="no private key named nope: it has lake, warehouse"):
        helper()(str(path), made_up.PASSWORD, "nope")


def test_the_errors_are_said_plainly(
    m: made_up.Material, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    read = helper()
    p12 = tmp_path / "lake.p12"
    p12.write_bytes(made_up.pkcs12_bytes(m))
    with pytest.raises(ValueError, match="password is wrong") as wrong:
        read(str(p12), "not-it")
    assert "not-it" not in str(wrong.value)
    only_certs = tmp_path / "certs.p12"
    only_certs.write_bytes(
        pkcs12.serialize_key_and_certificates(
            b"ca", None, None, [m.ca_cert], serialization.BestAvailableEncryption(made_up.PASSWORD.encode())
        )
    )
    with pytest.raises(ValueError, match="no private key"):
        read(str(only_certs), made_up.PASSWORD)
    pem = tmp_path / "lake.pem"
    pem.write_bytes(m.ca_pem)
    with pytest.raises(ValueError, match="format is not known: it is not PKCS#12"):
        read(str(pem), made_up.PASSWORD)
    gone = str(tmp_path / "gone.keystore")
    with pytest.raises(FileNotFoundError, match=r"No keystore file at .*gone.keystore\. Choose it again"):
        read(gone, made_up.PASSWORD)
    monkeypatch.setenv("TRINO_KEYSTORE_PATH", gone)  # the variable that gave the path is named
    with pytest.raises(FileNotFoundError, match=r"gone.keystore \(from TRINO_KEYSTORE_PATH\)"):
        read(gone, made_up.PASSWORD)


@needs_jks
def test_a_wrong_password_on_a_java_keystore(m: made_up.Material, tmp_path: Path) -> None:
    path = tmp_path / "lake.jks"
    path.write_bytes(made_up.jks_bytes(m))
    with pytest.raises(ValueError, match="The keystore's password is wrong"):
        helper()(str(path), "not-it")


def run_python(code: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 (this Python, made-up material)
        [sys.executable, "-c", code, *args], capture_output=True, text=True, timeout=120, check=False
    )


def test_the_files_are_removed_when_the_python_ends(m: made_up.Material, tmp_path: Path) -> None:
    path = tmp_path / "lake.p12"
    path.write_bytes(made_up.pkcs12_bytes(m))
    code = (
        keystores.KEYSTORE_FILES
        + "\nimport sys, json\nprint(json.dumps(keystore_files(sys.argv[1], sys.argv[2])))"
    )
    done = run_python(code, str(path), made_up.PASSWORD)
    assert done.returncode == 0, done.stderr
    cert, key = json.loads(done.stdout)
    assert not Path(cert).exists() and not Path(key).exists() and not Path(key).parent.exists()


def test_a_java_keystore_without_pyjks_asks_for_it(m: made_up.Material, tmp_path: Path) -> None:
    path = tmp_path / "lake.jks"
    path.write_bytes(b"\xfe\xed\xfe\xed" + b"\0" * 32)
    code = (
        "import sys\nsys.modules['jks'] = None\n"
        + keystores.KEYSTORE_FILES
        + "\nkeystore_files(sys.argv[1], 'x')"
    )
    done = run_python(code, str(path))
    assert "The keystore is JKS: reading it needs the pyjks package (pip install pyjks)." in done.stderr


# ===== the form =====


def test_trino_signs_in_two_ways_and_the_keystore_asks_for_its_password_by_name(client: TestClient) -> None:
    types = {t["id"]: t for t in client.get("/connections/types", headers=AUTH).json()["types"]}
    trino = types["trino"]
    assert [w["label"] for w in trino["sign_ins"]] == [
        "Username and password",
        "Client certificate (keystore)",
    ]
    code = trino["sign_ins"][1]["code"]
    assert code == keystores.TRINO_KEYSTORE and trino["code"] == keystores.TRINO_BASIC
    assert 'secret("TRINO_KEYSTORE_PASSWORD")' in code and "trino.auth.CertificateAuthentication(" in code
    inspected = client.post("/blades/inspect", json={"code": code, "template": "trino"}, headers=AUTH).json()
    assert inspected["secrets"] == ["TRINO_KEYSTORE_PASSWORD"]
    fields = {s["name"]: s for s in inspected["settings"]}
    assert fields["keystore"]["env"] is None and fields["keystore"]["placeholder"] is True
    assert fields["certificate file"]["env"] is None  # verify: a certificate file too
    assert "env" not in fields["server"] and "env" not in fields["user"]  # no other field is mapped
    assert {p["pip"] for p in inspected["packages"]} >= {"trino", "pyjks", "cryptography", "requests"}
    # The form's parts: the keystore and its entry beside the user; each a file the chooser picks.
    assert form_order(["user", "keystore", "keystore_alias", "certificate file"])["who"] == [
        "user", "keystore", "keystore_alias",
    ]  # fmt: skip
    assert picker({"name": "keystore", "key": "keystore"}, "trino") == "file"
    assert picker({"name": "client key file", "key": "sslkey"}, "postgres") == "file"


# ===== a certificate or keystore file from an environment variable =====


def test_the_keystore_path_maps_to_a_variable_with_this_computers_path_and_back() -> None:
    code = keystores.TRINO_KEYSTORE.replace("import os\n\n", "")  # written in when a variable needs it
    path = r"C:\certs\lake.keystore"
    mapped = apply_settings(
        code, {setting(code, "keystore").id: {"value": path, "env": "TRINO_KEYSTORE_PATH"}}
    )
    assert 'keystore = os.environ.get("TRINO_KEYSTORE_PATH", r"C:\\certs\\lake.keystore")' in mapped
    assert mapped.startswith("import os\nimport requests")
    again = setting(mapped, "keystore")  # Edit shows it again
    assert (again.env, again.value, again.to_json()["env"]) == (
        "TRINO_KEYSTORE_PATH",
        path,
        "TRINO_KEYSTORE_PATH",
    )
    assert env_settings(mapped) == [
        {"variable": "TRINO_KEYSTORE_PATH", "setting": "keystore", "key": "keystore", "default": path}
    ]
    moved = apply_settings(mapped, {again.id: r"D:\certs\new.keystore"})  # a new path keeps the variable
    assert 'os.environ.get("TRINO_KEYSTORE_PATH", r"D:\\certs\\new.keystore")' in moved
    renamed = apply_settings(moved, {setting(moved, "keystore").id: {"env": "LAKE_KEYSTORE"}})
    assert 'os.environ.get("LAKE_KEYSTORE", r"D:\\certs\\new.keystore")' in renamed
    plain = apply_settings(renamed, {setting(renamed, "keystore").id: {"value": path, "env": None}})
    assert 'keystore = r"C:\\certs\\lake.keystore"' in plain and env_settings(plain) == []
    with pytest.raises(FillError, match="letters, digits and _"):
        apply_settings(code, {setting(code, "keystore").id: {"value": path, "env": "1 bad"}})


@pytest.mark.parametrize(
    ("code", "name", "variable"),
    [
        (keystores.TRINO_BASIC, "certificate file", "LAKE_CERTIFICATE_FILE"),  # Trino's CA .pem (verify=)
        (
            'import psycopg\nconn = psycopg.connect(host="db", sslrootcert=r"C:\\certs\\ca.pem")',
            "certificate file",
            "WAREHOUSE_CERTIFICATE_FILE",
        ),
        (
            'import psycopg\nconn = psycopg.connect(host="db", sslcert="/certs/me.crt")',
            "client certificate file",
            "W_CERT",
        ),
        (
            'import pymysql\nconn = pymysql.connect(host="db", ssl_key="/certs/me.key")',
            "client key file",
            "W_KEY",
        ),
    ],
)
def test_every_certificate_file_may_come_from_a_variable(code: str, name: str, variable: str) -> None:
    found = setting(code, name)
    mapped = apply_settings(code, {found.id: {"value": found.value, "env": variable}})
    assert f'os.environ.get("{variable}", ' in mapped and "import os" in mapped
    back = setting(mapped, name)
    assert (back.env, back.value) == (variable, found.value)
    assert (
        apply_settings(mapped, {back.id: {"value": found.value, "env": ""}}).replace("import os\n", "")
        == code
    )


def test_a_server_may_come_from_a_variable_but_a_port_may_not() -> None:
    # A server, database, user, client id or tenant too (the owner, 2026-11-17: SQL Server's form offers
    # them; domain/certificate_files.py PLACE_SETTINGS). A number never: its type would change.
    code = keystores.TRINO_BASIC
    mapped = apply_settings(code, {setting(code, "server").id: {"value": "db", "env": "LAKE_HOST"}})
    assert 'host=os.environ.get("LAKE_HOST", "db")' in mapped
    assert setting(mapped, "server").env == "LAKE_HOST"
    with pytest.raises(FillError, match="port cannot come from an environment variable"):
        apply_settings(code, {setting(code, "port").id: {"value": 443, "env": "LAKE_PORT"}})
    hand = 'import os\nimport trino\nconn = trino.dbapi.connect(host=os.environ.get("LAKE_HOST", "db"))'
    assert [(s.name, s.env) for s in detect_settings(hand)] == [("server", "LAKE_HOST")]


# ===== the export and Run settings: the variable only when mapped, never the file =====


def trino_piece(code: str) -> Piece:
    password = Secret("TRINO_KEYSTORE_PASSWORD", "TRINO_KEYSTORE_PASSWORD", "keyring", blade="Lake")
    return Piece("Lake", "sql", "database", code, "conn", "trino", secrets=(password,))


def test_the_export_lists_a_mapped_keystore_and_its_password_and_never_the_file(
    m: made_up.Material, tmp_path: Path
) -> None:
    keystore = tmp_path / "lake.keystore"
    keystore.write_bytes(made_up.pkcs12_bytes(m))
    code = keystores.TRINO_KEYSTORE
    mapped = apply_settings(
        code, {setting(code, "keystore").id: {"value": str(keystore), "env": "TRINO_KEYSTORE_PATH"}}
    )
    cells = [ExportCell("sql", "SELECT * FROM sales.orders", "Lake -> orders", number=1)]
    made = se.export("Lake report", "/work/lake.ipynb", cells, {"Lake": trino_piece(mapped)}, {})
    text = made.text
    settings = text[text.index("SETTINGS: dict") : text.index("FROM_VAULTS")]
    assert (
        "'TRINO_KEYSTORE_PATH': None,  # Lake's TRINO_KEYSTORE_PATH: a certificate or keystore file's path"
        in settings
    )
    assert "an Azure Function app: an Application setting" in settings
    assert (
        "'TRINO_KEYSTORE_PASSWORD': None,  # Lake's TRINO_KEYSTORE_PASSWORD: saved in the keyring" in settings
    )
    assert {s["variable"]: s["secret"] for s in made.settings} == {
        "TRINO_KEYSTORE_PASSWORD": True,
        "TRINO_KEYSTORE_PATH": False,
    }
    assert made_up.PASSWORD not in text
    raw = keystore.read_bytes()
    assert raw.hex() not in text and "MII" not in text  # never the file, as hex or base64
    assert {"pyjks>=", "cryptography>="} & {r.split(">")[0] + ">=" for r in made.requirements}
    plain = se.export("Lake report", "/work/lake.ipynb", cells, {"Lake": trino_piece(code)}, {})
    assert "TRINO_KEYSTORE_PATH" not in plain.text.split("FROM_VAULTS")[0]  # not mapped: not listed


def test_run_settings_list_a_mapped_file_of_a_connection_the_script_names() -> None:
    script = "import swissarmybench as sab\norders = sab.sql('Lake', 'SELECT 1')\n"
    found = script_runs.needed(
        script, lambda n: ["TRINO_KEYSTORE_PASSWORD"], lambda n: ["TRINO_KEYSTORE_PATH"]
    )
    assert [(f.name, f.why, f.secret) for f in found] == [
        ("LAKE_TRINO_KEYSTORE_PASSWORD", "Lake", True),
        ("TRINO_KEYSTORE_PATH", "Lake", False),
    ]
    assert [f.name for f in script_runs.needed(script, lambda n: ["TRINO_KEYSTORE_PASSWORD"])] == [
        "LAKE_TRINO_KEYSTORE_PASSWORD"
    ]


# ===== end to end: a made-up Trino that asks for a client certificate =====


@pytest.fixture
def trino_server(m: made_up.Material, tmp_path: Path) -> Iterator[made_up.StandIn]:
    running = made_up.StandIn(m, tmp_path).start()
    yield running
    running.stop()


def lake_code(server: made_up.StandIn, keystore: Path, variable: str | None = "TRINO_KEYSTORE_PATH") -> str:
    code = keystores.TRINO_KEYSTORE
    values = {
        setting(code, "server").id: "127.0.0.1",
        setting(code, "port").id: server.port,
        setting(code, "user").id: "lake_reader",
        setting(code, "certificate file").id: str(server.ca_file),
        setting(code, "keystore").id: {"value": str(keystore), "env": variable},
    }
    return apply_settings(code, values)


@needs_trino
@needs_jks
def test_test_and_open_as_grid_sign_in_with_the_keystore(
    client: TestClient, m: made_up.Material, trino_server: made_up.StandIn, tmp_path: Path
) -> None:
    keystore = tmp_path / "lake.keystore"
    keystore.write_bytes(made_up.jks_bytes(m))
    code = lake_code(trino_server, keystore)
    body = {"name": "Lake", "kind": "sql", "template": "trino", "dialect": "trino", "code": code}
    body |= {"catalog": BY_ID["trino"].to_json()["catalog"]}
    wrong = client.post(
        "/connections/test", json=body | {"secrets": {"TRINO_KEYSTORE_PASSWORD": "not-it"}}, headers=AUTH
    )
    assert wrong.status_code == 422 and "password is wrong" in wrong.text and "not-it" not in wrong.text
    tested = client.post(
        "/connections/test",
        json=body | {"secrets": {"TRINO_KEYSTORE_PASSWORD": made_up.PASSWORD}},
        headers=AGENT,
    )
    assert tested.status_code == 200, tested.text
    assert made_up.PASSWORD not in tested.text
    # Saved by the agent (the golden rule), its password into the keyring; then opened as a grid.
    saved = client.post(
        "/connections", json=body | {"secrets": {"TRINO_KEYSTORE_PASSWORD": made_up.PASSWORD}}, headers=AGENT
    )
    assert saved.status_code == 200, saved.text
    got = client.get("/connections/Lake", headers=AGENT)
    assert made_up.PASSWORD not in got.text and "TRINO_KEYSTORE_PATH" in got.text
    opened = client.post("/connections/Lake/open", json={"schema": "sales", "table": "orders"}, headers=AGENT)
    assert opened.status_code == 200, opened.text
    grid = client.get(f"/grids/{opened.json()['grid']}", headers=AUTH).json()
    assert grid["row_count"] == len(made_up.ORDERS)
    assert [c["name"] for c in grid["columns"]] == ["order_id", "region", "amount"]
    assert {s["client"] for s in trino_server.seen} == {made_up.CLIENT}  # every call, by the certificate
    assert {s["user"] for s in trino_server.seen} == {"lake_reader"}
    # The path from the variable: a missing file names it.
    os.environ["TRINO_KEYSTORE_PATH"] = str(tmp_path / "gone.keystore")
    try:
        missing = client.post("/blades/Lake/test", json={}, headers=AUTH)
    finally:
        del os.environ["TRINO_KEYSTORE_PATH"]
    assert missing.status_code == 422 and "(from TRINO_KEYSTORE_PATH)" in missing.text


@needs_trino
def test_without_a_client_certificate_the_standin_lets_no_one_in(trino_server: made_up.StandIn) -> None:
    import requests  # type: ignore[import-untyped, import-not-found, unused-ignore]

    with pytest.raises(requests.exceptions.RequestException):
        requests.post(
            f"https://127.0.0.1:{trino_server.port}/v1/statement",
            data="SELECT 1",
            verify=str(trino_server.ca_file),
            timeout=10,
        )


@needs_trino
def test_test_asks_trino_itself_so_a_sign_in_without_the_certificate_fails_plainly(
    client: TestClient, trino_server: made_up.StandIn
) -> None:
    code = keystores.TRINO_BASIC
    values = {
        setting(code, "server").id: "127.0.0.1",
        setting(code, "port").id: trino_server.port,
        setting(code, "user").id: "lake_reader",
        setting(code, "certificate file").id: str(trino_server.ca_file),
    }
    body: dict[str, Any] = {"name": "Lake", "kind": "sql", "template": "trino", "dialect": "trino"}
    body |= {"code": apply_settings(code, values), "secrets": {"password": "made-up-word"}}
    refused = client.post("/connections/test", json=body, headers=AUTH)
    assert refused.status_code == 422 and "Trino did not let it in" in refused.text
    assert "made-up-word" not in refused.text
