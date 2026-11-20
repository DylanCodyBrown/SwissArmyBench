"""A client certificate from a key vault (the owner, 2026-11-20: "we need to make it possible that
certificates can be retrieved from the vault for the Trino connection"). Azure Key Vault keeps a
certificate with its private key as a secret whose value is the base64 PKCS#12 (or PEM text): a setting's
`${NAME}` (12.7) names the vault's variable, and the connection's own code reads the value as the
keystore (domain/keystores.py) or, for a driver that wants a file's path, writes it to a 0600 file
(domain/certificate_files.py CERTIFICATE_FILE). Made-up keys, certificates, keystores and vaults only;
the end-to-end tests sign in to a made-up Trino on 127.0.0.1 that asks for a client certificate
(tests/trino_standin.py)."""

from __future__ import annotations

import base64
import json
import os
import re
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

from swissarmybench.domain import certificate_files, keystores, portability
from swissarmybench.domain import script_export as se
from swissarmybench.domain.blades import FillError, apply_settings, detect_settings, env_settings
from swissarmybench.domain.script_export import ExportCell, Piece
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

CERT = keystores.VAULT_VARIABLE  # TRINO_CLIENT_CERTIFICATE
CA = "TRINO_CA_CERTIFICATE"
A_KEY = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----(?:\\n|\s)*[A-Za-z0-9+/]{20}"
)  # a key, not the code's words


@pytest.fixture(autouse=True)
def keyring() -> Iterator[None]:
    with memory_keyring():
        yield


@pytest.fixture(scope="module")
def m() -> made_up.Material:
    return made_up.material()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def pkcs12_plain(m: made_up.Material) -> bytes:
    """A PKCS#12 with no password: what Azure Key Vault's own certificate secret holds."""
    return pkcs12.serialize_key_and_certificates(
        b"lake", m.client_key, m.client_cert, [m.ca_cert], serialization.NoEncryption()
    )


def keystore_files() -> Any:
    space: dict[str, Any] = {}
    exec(keystores.KEYSTORE_FILES, space)  # noqa: S102 (the connection's own helper, as its code runs it)
    return space["keystore_files"]


def certificate_file() -> Any:
    space: dict[str, Any] = {}
    exec(certificate_files.CERTIFICATE_FILE, space)  # noqa: S102 (the helper, as the code runs it)
    return space["certificate_file"]


def only_yours(path: str) -> None:
    if os.name == "posix":
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(Path(path).parent).st_mode) == 0o700


def checked(m: made_up.Material, files: tuple[str, str]) -> None:
    cert, key = files
    chain = x509.load_pem_x509_certificates(Path(cert).read_bytes())
    assert chain[0] == m.client_cert and chain[1] == m.ca_cert  # the leaf first, then its chain
    loaded = serialization.load_pem_private_key(Path(key).read_bytes(), None)
    assert loaded.public_key().public_numbers() == m.client_key.public_key().public_numbers()  # type: ignore[union-attr]
    only_yours(cert)
    only_yours(key)


# ===== the keystore as a vault's value =====


def values(m: made_up.Material) -> dict[str, tuple[str, str]]:
    """Each way a key vault may hold the certificate: (the variable's value, its password)."""
    pem = made_up.pem_text(m)
    wrapped = b64(pkcs12_plain(m))
    return {
        "base64 PKCS#12, no password (Key Vault's own)": (wrapped, ""),
        "base64 PKCS#12 in lines": ("\n".join(wrapped[i : i + 64] for i in range(0, len(wrapped), 64)), ""),
        "base64 PKCS#12 with a password": (b64(made_up.pkcs12_bytes(m)), made_up.PASSWORD),
        "PEM text (Key Vault's PEM content type)": (pem, ""),
        "PEM text, its key encrypted": (made_up.pem_text(m, made_up.PASSWORD), made_up.PASSWORD),
        "base64 of PEM text": (b64(pem.encode()), ""),
    }


@pytest.mark.parametrize(
    "way",
    [
        "base64 PKCS#12, no password (Key Vault's own)",
        "base64 PKCS#12 in lines",
        "base64 PKCS#12 with a password",
        "PEM text (Key Vault's PEM content type)",
        "PEM text, its key encrypted",
        "base64 of PEM text",
    ],
)
def test_a_vaults_value_is_read_as_the_keystore(m: made_up.Material, way: str) -> None:
    value, password = values(m)[way]
    checked(m, keystore_files()(value, password))


@needs_jks
def test_a_base64_java_keystore_is_told_by_its_decoded_first_bytes(m: made_up.Material) -> None:
    checked(m, keystore_files()(b64(made_up.jks_bytes(m)), made_up.PASSWORD))


def test_a_vaults_value_that_is_not_a_certificate_is_said_without_its_bytes(
    m: made_up.Material, monkeypatch: pytest.MonkeyPatch
) -> None:
    read = keystore_files()
    junk = "Zm9v" * 200  # base64, but not a keystore
    monkeypatch.setenv("LAKE_CERTIFICATE", junk)
    with pytest.raises(
        ValueError, match=r"The keystore from LAKE_CERTIFICATE is neither a file's path"
    ) as said:
        read(junk, "")
    assert junk[:40] not in str(said.value)
    with pytest.raises(ValueError, match="password is wrong") as wrong:
        read(b64(made_up.pkcs12_bytes(m)), "not-it")
    assert "not-it" not in str(wrong.value) and "MII" not in str(wrong.value)
    with pytest.raises(ValueError, match="encrypted: give its password"):
        read(made_up.pem_text(m, made_up.PASSWORD), "")
    with pytest.raises(ValueError, match="PEM's password is wrong"):
        read(made_up.pem_text(m, made_up.PASSWORD), "not-it")
    with pytest.raises(ValueError, match="no private key with its certificate"):
        read(m.ca_pem.decode(), "")
    with pytest.raises(FileNotFoundError, match=r"No keystore file at /made/up/gone\.p12"):
        read("/made/up/gone.p12", "")  # a path-like value is still a missing file


def run_python(code: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 (this Python, made-up material)
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={**os.environ, **env},
    )


def test_the_vaults_keystore_lands_only_in_files_removed_when_the_python_ends(m: made_up.Material) -> None:
    code = keystores.KEYSTORE_FILES + (
        "\nimport json, os\nprint(json.dumps(keystore_files(os.environ['LAKE_CERTIFICATE'], '')))"
    )
    done = run_python(code, {"LAKE_CERTIFICATE": b64(pkcs12_plain(m))})
    assert done.returncode == 0, done.stderr
    cert, key = json.loads(done.stdout)
    assert not Path(cert).exists() and not Path(key).exists() and not Path(key).parent.exists()


# ===== a certificate a driver reads by path (the shared helper) =====


def test_a_certificate_file_is_a_path_or_the_vaults_text_written_only_for_you(
    m: made_up.Material, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make = certificate_file()
    on_disk = tmp_path / "ca.pem"
    on_disk.write_bytes(m.ca_pem)
    assert make(str(on_disk)) == str(on_disk)  # a path: itself, nothing written
    for value, text in (
        (m.ca_pem.decode(), m.ca_pem.decode()),
        (b64(m.ca_pem), m.ca_pem.decode()),  # base64 of the PEM
        (made_up.pem_text(m), made_up.pem_text(m)),  # a key with its certificates (sslkey and sslcert)
    ):
        path = make(value)
        assert path != value and Path(path).name == "certificate.pem"
        assert Path(path).read_text().strip() == text.strip()
        only_yours(path)
    junk = "Zm9v" * 200
    monkeypatch.setenv("LAKE_CA", junk)
    with pytest.raises(ValueError, match=r"The certificate \(from LAKE_CA\) is neither") as said:
        make(junk)
    assert junk[:40] not in str(said.value)
    with pytest.raises(FileNotFoundError, match=r"No certificate file at /made/up/ca\.pem"):
        make("/made/up/ca.pem")


def test_the_certificate_file_is_removed_when_the_python_ends(m: made_up.Material) -> None:
    code = certificate_files.CERTIFICATE_FILE + (
        "\nimport os\nprint(certificate_file(os.environ['LAKE_CA']))"
    )
    done = run_python(code, {"LAKE_CA": m.ca_pem.decode()})
    assert done.returncode == 0, done.stderr
    path = Path(done.stdout.strip())
    assert path.name == "certificate.pem" and not path.exists() and not path.parent.exists()


# ===== the settings: the vault's way, its password's variable, the wrapped certificate =====


def by_name(code: str) -> dict[str, Any]:
    return {s.name: s for s in detect_settings(code)}


def test_the_vault_way_names_its_variables_and_runs_on_a_function_app() -> None:
    code = keystores.TRINO_VAULT
    found = by_name(code)
    assert found["keystore"].text == "${" + CERT + "}"
    assert found["keystore_password"].value == ""  # none: Key Vault's own have none
    assert found["certificate file"].value == ""  # the system's own authorities
    assert portability.check(code, "trino") == []  # nothing of it on this disk
    assert keystores.VAULT_MARK in code and "secret(" not in code
    # A path typed into the certificate's box: that one is on this disk (the amber note, as before).
    local = apply_settings(code, {found["certificate file"].id: "/made/up/ca.pem"})
    assert [f.key for f in portability.check(local, "trino")] == ["file_setting"]
    # The file way says it, the vault way does not, on the form's Sign in.
    ways = {
        w["label"]: w["local"] for w in portability.sign_ins("trino", BY_ID["trino"].to_json()["sign_ins"])
    }
    assert ways["Client certificate (from a key vault)"] == []
    assert ways["Client certificate (a file on this computer)"][0]["key"] == "file_setting"


def test_the_keystores_password_is_a_variable_or_none_never_a_typed_value() -> None:
    code = keystores.TRINO_VAULT
    setting = by_name(code)["keystore_password"]
    assert setting.value == "" and not setting.text
    named = apply_settings(code, {setting.id: "${LAKE_KEYSTORE_PASSWORD}"})
    assert 'keystore_password = os.environ["LAKE_KEYSTORE_PASSWORD"]' in named
    again = by_name(named)["keystore_password"]
    none = apply_settings(named, {again.id: {"text": ""}})
    assert 'keystore_password = ""' in none and by_name(none)["keystore_password"].value == ""
    cleared = by_name(none)["keystore_password"]
    for typed in (
        "made-up-word",
        {"text": "pre${LAKE_KEYSTORE_PASSWORD}"},
        "${LAKE_KEYSTORE_PASSWORD:-made-up}",
    ):
        with pytest.raises(FillError, match="takes a variable on its own") as refused:
            apply_settings(none, {cleared.id: typed})
        assert "made-up" not in str(refused.value)
    # Any other password is never a setting: it stays secret("...").
    assert "keystore_password" not in by_name(keystores.TRINO_KEYSTORE)
    assert "password" not in by_name(
        'import x\npassword = os.environ["SHOP_PASSWORD"]\nx.connect(password=password)'
    )


def test_a_certificate_from_a_vault_is_wrapped_for_the_driver_and_read_back() -> None:
    code = keystores.TRINO_VAULT
    setting = by_name(code)["certificate file"]
    wrapped = apply_settings(code, {setting.id: "${" + CA + "}"})
    assert f'verify = certificate_file(os.environ["{CA}"])' in wrapped
    assert wrapped.count("def certificate_file(value):") == 1
    assert wrapped.index("def certificate_file") < wrapped.index("verify = certificate_file")
    back = by_name(wrapped)["certificate file"]
    assert back.text == "${" + CA + "}"
    assert {m["variable"] for m in env_settings(wrapped)} == {CERT, CA}
    plain = apply_settings(wrapped, {back.id: {"text": ""}})
    assert plain == code  # the helper goes with its last use
    # A default is a path on this computer: the plain variable read, as before (no helper).
    mapped = apply_settings(code, {setting.id: "${" + CA + ":-/made/up/ca.pem}"})
    assert (
        f'verify = os.environ.get("{CA}", "/made/up/ca.pem")' in mapped and "certificate_file" not in mapped
    )
    # A keystore is never wrapped: keystore_files reads the vault's value itself.
    assert "certificate_file(" not in apply_settings(code, {by_name(code)["keystore"].id: "${LAKE_CERT}"})


@pytest.mark.parametrize(
    ("code", "names"),
    [
        (
            'import psycopg\nconn = psycopg.connect(host="db", sslrootcert=r"C:\\certs\\ca.pem", '
            'sslcert="/certs/me.crt", sslkey="/certs/me.key")',
            ("certificate file", "client certificate file", "client key file"),
        ),
        (
            'import pymysql\nconn = pymysql.connect(host="db", ssl_ca="/certs/ca.pem", ssl_cert="/c/me.crt")',
            ("certificate file", "client certificate file"),
        ),
    ],
)
def test_every_certificate_file_may_come_from_a_vault(code: str, names: tuple[str, ...]) -> None:
    found = by_name(code)
    values = {found[n].id: "${VAULT_" + str(i) + "}" for i, n in enumerate(names)}
    made = apply_settings(code, values)
    for i, name in enumerate(names):
        assert f'certificate_file(os.environ["VAULT_{i}"])' in made
        assert by_name(made)[name].text == "${VAULT_" + str(i) + "}"
    assert made.startswith("import os\n") and made.count("def certificate_file") == 1
    compile(made, "connection", "exec")
    assert portability.check(made, "postgres") == []


# ===== the export: the vault read where it runs, never the certificate =====


VAULT_CODE = """import os


def get(name):
    with open(os.path.join(os.environ["MADE_UP_VAULT_FOLDER"], name), encoding="utf-8") as file:
        return file.read()
"""


def lake_code(port: int, ca: str = "${" + CA + "}", password: str | None = None) -> str:
    code = keystores.TRINO_VAULT
    found = by_name(code)
    values: dict[str, Any] = {
        found["server"].id: "127.0.0.1",
        found["port"].id: port,
        found["user"].id: "lake_reader",
        found["certificate file"].id: ca,
    }
    if password is not None:
        values[found["keystore_password"].id] = password
    return apply_settings(code, values)


def vault_folder(where: Path, m: made_up.Material, certificate: str) -> Path:
    """The made-up vault's entries, one file each (never in the library: the vault's code reads them)."""
    where.mkdir(exist_ok=True)
    (where / "lake-client-certificate").write_text(certificate)
    (where / "lake-ca").write_text(m.ca_pem.decode())
    (where / "lake-certificate-password").write_text(made_up.PASSWORD)
    return where


MAPPING = {
    CERT: "lake-client-certificate",
    CA: "lake-ca",
    "LAKE_KEYSTORE_PASSWORD": "lake-certificate-password",
}


def test_the_export_reads_the_certificate_from_its_vault_and_never_holds_it(m: made_up.Material) -> None:
    lake = Piece("Lake", "sql", "database", lake_code(443), "conn", "trino")
    vault = Piece("Team vault", "vault", "vault", VAULT_CODE, "get", vault_mapping=MAPPING)
    cells = [ExportCell("sql", "SELECT * FROM sales.orders", "Lake -> orders", number=1)]
    made = se.export("Lake report", "/work/lake.ipynb", cells, {"Lake": lake, "Team vault": vault}, {})
    text = made.text
    vaults = text[text.index("FROM_VAULTS: dict") : text.index("}", text.index("FROM_VAULTS: dict"))]
    assert f"'{CERT}': ('Team vault', 'lake-client-certificate')," in vaults
    assert f"'{CA}': ('Team vault', 'lake-ca')," in vaults
    assert "def vault_team_vault():" in text and "def certificate_file(value):" in text
    assert {s["variable"]: s["from"] for s in made.settings}[CERT] == "vault"
    assert "BEGIN" not in text.replace("-----BEGIN", "") and "MII" not in text
    assert [n for n in portability.export_notes([("Lake", lake.code, "trino", ())])] == []
    compile(text, "script", "exec")


@needs_trino
def test_the_exported_script_signs_in_with_the_vaults_certificate(
    m: made_up.Material, tmp_path: Path, trino_server: made_up.StandIn
) -> None:
    folder = vault_folder(tmp_path / "vault-entries", m, b64(pkcs12_plain(m)))
    lake = Piece("Lake", "sql", "database", lake_code(trino_server.port), "conn", "trino")
    vault = Piece("Team vault", "vault", "vault", VAULT_CODE, "get", vault_mapping=MAPPING)
    cells = [ExportCell("sql", "SELECT * FROM sales.orders", "Lake -> orders", number=1)]
    made = se.export(
        "Lake report", str(tmp_path / "lake.ipynb"), cells, {"Lake": lake, "Team vault": vault}, {}
    )
    script = tmp_path / "lake_report.py"
    script.write_text(made.text, encoding="utf-8")
    clean = {k: v for k, v in os.environ.items() if k not in (CERT, CA)}
    done = subprocess.run(  # noqa: S603 (this Python, the made-up script)
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        cwd=tmp_path,
        env={**clean, "MADE_UP_VAULT_FOLDER": str(folder)},
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert {s["client"] for s in trino_server.seen} == {made_up.CLIENT}
    assert "MII" not in done.stdout + done.stderr


# ===== end to end in the app: Test, save and open as a grid, the agent's way (the golden rule) =====


@pytest.fixture
def trino_server(m: made_up.Material, tmp_path: Path) -> Iterator[made_up.StandIn]:
    (tmp_path / "trino").mkdir()
    running = made_up.StandIn(m, tmp_path / "trino").start()
    yield running
    running.stop()


def leftovers(folder: Path) -> list[str]:
    """What the connection's child processes left in their own temporary folder (TMPDIR)."""
    return sorted(p.name for p in folder.iterdir())


@needs_trino
@pytest.mark.parametrize("way", ["base64 PKCS#12", "PEM text", "base64 JKS with its password"])
def test_test_save_and_open_sign_in_with_the_vaults_certificate(
    client: TestClient,
    m: made_up.Material,
    trino_server: made_up.StandIn,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    way: str,
) -> None:
    if way == "base64 JKS with its password" and not HAS_JKS:
        pytest.skip("pyjks is not installed in this Python")
    certificate = {
        "base64 PKCS#12": b64(pkcs12_plain(m)),
        "PEM text": made_up.pem_text(m),
        "base64 JKS with its password": b64(made_up.jks_bytes(m)) if HAS_JKS else "",
    }[way]
    folder = vault_folder(tmp_path / "vault-entries", m, certificate)
    monkeypatch.setenv("MADE_UP_VAULT_FOLDER", str(folder))
    for name in (CERT, CA, "LAKE_KEYSTORE_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    scratch = tmp_path / "temporary"  # the child processes' temporary folder: theirs alone
    scratch.mkdir()
    monkeypatch.setenv("TMPDIR", str(scratch))
    monkeypatch.setenv("TEMP", str(scratch))
    vault: dict[str, Any] = {"name": "Team vault", "kind": "vault", "code": VAULT_CODE, "variable": "get"}
    vault |= {"vault_mapping": [{"env": e, "secret": s} for e, s in MAPPING.items()]}
    assert client.post("/blades", json=vault, headers=AGENT).status_code == 200
    password = "${LAKE_KEYSTORE_PASSWORD}" if "password" in way else None
    code = lake_code(trino_server.port, password=password)
    body = {"name": "Lake", "kind": "sql", "template": "trino", "dialect": "trino", "code": code}
    body |= {"catalog": BY_ID["trino"].to_json()["catalog"]}
    tested = client.post("/connections/test", json=body, headers=AGENT)  # the agent's Test, as the user's
    assert tested.status_code == 200, tested.text
    saved = client.post("/connections", json=body, headers=AGENT)
    assert saved.status_code == 200, saved.text
    got = client.get("/connections/Lake", headers=AGENT)
    assert got.status_code == 200 and CERT in got.text
    opened = client.post("/connections/Lake/open", json={"schema": "sales", "table": "orders"}, headers=AGENT)
    assert opened.status_code == 200, opened.text
    grid = client.get(f"/grids/{opened.json()['grid']}", headers=AUTH).json()
    assert grid["row_count"] == len(made_up.ORDERS)
    assert {s["client"] for s in trino_server.seen} == {made_up.CLIENT}  # every call, by the certificate
    # Never the certificate's bytes in an answer, the library, the state folder or a log.
    raw = certificate.replace("\n", "")
    marks = {raw[:60], raw[-60:], b64(pkcs12_plain(m))[:60], made_up.PASSWORD}
    for answer in (tested.text, saved.text, got.text, opened.text, json.dumps(grid)):
        assert not any(mark in answer for mark in marks)
        assert not A_KEY.search(answer)
    for path in tmp_path.rglob("*"):
        if path.is_file() and folder not in path.parents and (tmp_path / "trino") not in path.parents:
            text = path.read_bytes().decode("utf-8", "replace").replace("\n", "")
            assert not any(mark in text for mark in marks), path
            assert not A_KEY.search(text), path
    # The child processes ended: their 0600 files with them.
    assert leftovers(scratch) == []
    # A variable no vault gives: the one error, named.
    unset = apply_settings(code, {by_name(code)["keystore"].id: "${LAKE_NOT_SET}"})
    missing = client.post("/connections/test", json=body | {"code": unset}, headers=AGENT)
    assert missing.status_code == 422 and "LAKE_NOT_SET is not set on this computer" in missing.text
