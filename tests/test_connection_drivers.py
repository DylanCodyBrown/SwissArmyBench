"""Every connection type and every way it signs in, against the real client library it calls (the owner,
2026-11-20: "I saw a lot of connection types that were not actually supported by those clients").

tests/driver_check.py does the checking (standard library only): each starter's code compiles, and each
function, class and keyword it gives a library exists in the installed library. Here it runs over every
starter of the Add connection forms in the app's own Python (a driver not installed is skipped), and again in
SWISSARMYBENCH_DRIVERS_PYTHON when that names a Python with every driver (docs/verified.md says which ran).
The multi-factor sign-in (domain/entra.py MultiFactorSignIn) is checked on its own: it imports azure-identity
by name, which no call in its text shows.
"""

from __future__ import annotations

import ast
import inspect
import json
import os
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.domain import connections, dataverse, entra, lakes, portability, sql_server
from swissarmybench.server.blade_templates import TEMPLATES
from tests import driver_check

CONNECTION_GROUPS = {"Databases", "Lakes and SharePoint", "Files", "Your own code", "Vaults", "Other"}


def every_way() -> list[dict[str, str]]:
    """Each starter's code, one per way to sign in, as the form offers them."""
    items = []
    for template in TEMPLATES:
        if template.group not in CONNECTION_GROUPS:
            continue
        ways = template.sign_ins or ((template.label, "", template.code),)
        for label, _, code in ways:
            items.append({"name": f"{template.id}: {label}", "code": code})
    return items


def sql_server_strings() -> list[dict[str, str]]:
    """SQL Server's and Azure SQL's connection string for each way, as its code builds it (the SqlServer
    object made from the starter's own keywords, without connecting)."""
    items = []
    for template in sorted(sql_server.TEMPLATES):
        for label, _, code in sql_server.sign_ins(template):
            call = next(
                node.value
                for node in ast.walk(ast.parse(code))
                if isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and getattr(node.value.func, "id", "") == "SqlServer"
            )
            keywords: dict[str, Any] = {}
            for keyword in call.keywords:
                try:
                    keywords[str(keyword.arg)] = ast.literal_eval(keyword.value)
                except ValueError:  # secret("password"), a credential: made up here
                    keywords[str(keyword.arg)] = (
                        "made-up" if keyword.arg in ("password", "client_secret") else None
                    )
            names: dict[str, Any] = {}
            exec(compile(sql_server._IMPORTS + sql_server.RUNTIME, "<runtime>", "exec"), names)  # noqa: S102
            made = names["SqlServer"].__new__(names["SqlServer"])  # not signed in: its settings only
            defaults = {
                k: v.default
                for k, v in inspect.signature(names["SqlServer"].__init__).parameters.items()
                if k not in ("self", "older")
            }
            made.settings = defaults | keywords
            made.sign_in = keywords["sign_in"]
            items.append({"name": f"{template}: {label}", "connection_string": made.connection_string()})
    return items


def test_every_way_compiles_and_calls_only_what_its_library_has() -> None:
    found = driver_check.check_all(every_way() + sql_server_strings())
    assert found["problems"] == []
    # Every connection type has a way to check it (nothing silently uncovered by the walk).
    assert len(every_way()) >= 80


DRIVERS = os.environ.get("SWISSARMYBENCH_DRIVERS_PYTHON", "")


@pytest.mark.skipif(not DRIVERS, reason="SWISSARMYBENCH_DRIVERS_PYTHON names no Python with every driver")
def test_every_way_against_every_driver_installed(tmp_path: Path) -> None:
    codes = tmp_path / "codes.json"
    codes.write_text(json.dumps(every_way() + sql_server_strings()), encoding="utf-8")
    script = Path(driver_check.__file__)
    answer = subprocess.run(  # noqa: S603 (a Python the tester named, a file of this repository)
        [DRIVERS, "-I", str(script), str(codes)], capture_output=True, text=True, timeout=600, check=True
    )
    found = json.loads(answer.stdout.strip().splitlines()[-1])
    assert found["problems"] == []
    # The drivers venv has them all: only what needs a system library may be missing (pyodbc's unixODBC).
    assert all(name.startswith("pyodbc") for name in found["skipped"]), found["skipped"]


def test_the_checker_finds_what_a_library_lacks() -> None:
    """The check itself: a made-up keyword, a class that does not exist, code that does not compile."""
    problems, _ = driver_check.check_code(
        "made-up", "import json\nimport duckdb\nduckdb.connect(nonsense=1)\n"
    )
    assert problems and "nonsense" in problems[0]
    problems, _ = driver_check.check_code("made-up", "import duckdb\nduckdb.NoSuchThing()\n")
    assert problems and "does not exist" in problems[0]
    problems, _ = driver_check.check_code("made-up", "conn = (\n")
    assert problems and "does not compile" in problems[0]
    problems, skipped = driver_check.check_code(
        "made-up", "import made_up_driver\nmade_up_driver.connect(a=1)\n"
    )
    assert problems == [] and skipped == {"made_up_driver"}
    problems, skipped = driver_check.check_connection_string("made-up", "Server=made-up;Bogus=1;")
    assert (problems and "bogus" in problems[0].lower()) or skipped == {"mssql_python"}
    problems, skipped = driver_check.check_connection_string(
        "made-up", "Server=x;Authentication=ActiveDirectoryMadeUp;"
    )
    assert (problems and "ActiveDirectoryMadeUp" in problems[0]) or skipped == {"mssql_python"}


# ===== multi-factor sign-in (the owner, 2026-11-20: "the dataverse connection didnt support mfa") =====


def test_the_multi_factor_way_is_offered_beside_the_password_ways() -> None:
    label = entra.MFA_LABEL
    assert label == "Username, with multi-factor sign-in (a browser window, or a code on another device)"
    by_id = {t.id: [w[0] for w in t.sign_ins] for t in TEMPLATES}
    for kind in (
        "dataverse",
        "sqlserver",
        "azuresql",
        "onelake",
        "datalake",
        "sharepoint",
        "sharepoint_docs",
    ):
        assert label in by_id[kind], kind
    assert f"Azure: {label[:1].lower()}{label[1:]}" in by_id["delta"]
    # SharePoint: right after its two username-and-password ways; SQL Server: after its Entra password.
    assert by_id["sharepoint"][:3] == [
        "Username and password (ROPC)",
        "Username and password, with the app's client secret (ROPC)",
        label,
    ]
    ways = by_id["sqlserver"]
    assert ways.index(label) == ways.index("Microsoft Entra: user name and password") + 1


def test_every_username_and_password_way_says_it_cannot_do_mfa() -> None:
    for template in TEMPLATES:
        form = connections.form(template.to_json(), {})
        for way in form["sign_ins"]:
            password_way = way["mark"] in entra.NO_MFA_MARKS or way["mark"] == sql_server.mark(
                "entra_password"
            )
            assert (way["note"] == entra.NO_MFA_NOTE) == password_way, (template.id, way["label"])
    assert entra.MFA_LABEL in entra.NO_MFA_NOTE
    # Entra's own refusals (AADSTS50076, 50079) name the way that can.
    assert entra.COMMON.count(f"Pick the sign-in '{entra.MFA_LABEL}' instead") == 2
    said = sql_server.explain(
        "Failed to authenticate the user (ActiveDirectoryPassword). AADSTS50076: MFA. Login failed"
    )
    assert entra.MFA_LABEL in said and said.startswith("The account needs multi-factor sign-in")


def test_the_multi_factor_way_only_works_on_this_computer() -> None:
    words = (
        "Only works on your machine: it needs you to approve the sign-in. On a Function App or hosted "
        "Streamlit app use an app registration or a managed identity."
    )
    for kind, code in (
        ("dataverse", dataverse.MFA),
        ("sqlserver", sql_server.code("entra_mfa")),
        ("datalake", next(w[2] for w in lakes.DATALAKE_SIGN_INS if w[1] == entra.MFA_MARK)),
    ):
        found = portability.check(code, kind)
        assert [f.words() for f in found] == [words], kind
        assert connections.signs_in_interactively(code)  # never signed in by itself at start-up


class FakeIdentity:
    """azure-identity's browser and device code credentials stood in for: what each was made with, whether a
    browser could open, and the account a sign-in remembers."""

    def __init__(self, browser_opens: bool = True) -> None:
        self.made: list[tuple[str, dict[str, Any]]] = []
        self.token = ""  # empty: made-up-token-<kind>
        self.scopes: list[str] = []
        self.authenticated = 0
        self.browser_opens = browser_opens
        self.cache_works = True  # False: no encrypted cache here (Linux with no keyring)
        fake = self

        class Unavailable(Exception):
            pass

        class Record:
            def __init__(self, text: str = '{"username": "made-up"}') -> None:
                self.text = text

            def serialize(self) -> str:
                return self.text

            @classmethod
            def deserialize(cls, text: str) -> Record:
                return cls(text)

        class Credential:
            kind = ""

            def __init__(self, **options: Any) -> None:
                fake.made.append((self.kind, options))

            def authenticate(self, scopes: list[str]) -> Record:
                if not fake.cache_works and "cache_persistence_options" in fake.made[-1][1]:
                    raise ValueError(
                        "Cache encryption is impossible because libsecret dependencies are not installed"
                    )
                if self.kind == "browser" and not fake.browser_opens:
                    raise Unavailable("Failed to open a browser")
                fake.authenticated += 1
                return Record()

            def get_token(self, *scopes: str, **options: Any) -> Any:
                fake.scopes += scopes
                token = fake.token or f"made-up-token-{self.kind}"
                return types.SimpleNamespace(token=token, expires_on=4_000_000_000)

        class Browser(Credential):
            kind = "browser"

        class DeviceCode(Credential):
            kind = "device code"

        module = types.ModuleType("azure.identity")
        module.InteractiveBrowserCredential = Browser  # type: ignore[attr-defined]
        module.DeviceCodeCredential = DeviceCode  # type: ignore[attr-defined]
        module.AuthenticationRecord = Record  # type: ignore[attr-defined]
        module.CredentialUnavailableError = Unavailable  # type: ignore[attr-defined]
        module.TokenCachePersistenceOptions = lambda **o: ("cache", o)  # type: ignore[attr-defined]
        self.module = module


def mfa_class() -> Any:
    names: dict[str, Any] = {}
    exec(compile(entra.MFA_CLASS, "<mfa>", "exec"), names)  # noqa: S102
    return names["MultiFactorSignIn"]


@pytest.fixture
def fake_identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeIdentity:
    fake = FakeIdentity()
    monkeypatch.setitem(sys.modules, "azure", types.ModuleType("azure"))
    monkeypatch.setitem(sys.modules, "azure.identity", fake.module)
    monkeypatch.setenv("HOME", str(tmp_path))  # the remembered account lands here, never in the tester's home
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    return fake


def test_mfa_signs_in_once_in_a_browser_and_later_runs_are_silent(fake_identity: FakeIdentity) -> None:
    first = mfa_class()("made-up-tenant", "made-up-user@example.com")
    assert first.get_token("https://made-up.example/.default").token == "made-up-token-browser"
    kind, options = fake_identity.made[0]
    assert kind == "browser" and options["login_hint"] == "made-up-user@example.com"
    assert options["tenant_id"] == "made-up-tenant" and options["cache_persistence_options"][0] == "cache"
    assert fake_identity.authenticated == 1
    record = Path(first.record_file())
    assert record.is_file() and record.read_text() == '{"username": "made-up"}'  # ids and name, never a token
    if os.name == "posix":
        assert record.stat().st_mode & 0o777 == 0o600
    first.get_token("https://made-up.example/.default")
    assert fake_identity.authenticated == 1 and len(fake_identity.made) == 1  # this run: the same credential
    later = mfa_class()("made-up-tenant", "made-up-user@example.com")  # a later run: the account remembered
    later.get_token("https://made-up.example/.default")
    assert fake_identity.authenticated == 1 and "authentication_record" in fake_identity.made[-1][1]


def test_mfa_with_no_browser_shows_a_code_for_another_device(
    fake_identity: FakeIdentity,
) -> None:
    fake_identity.browser_opens = False
    found = mfa_class()("made-up-tenant", "made-up-user@example.com").get_token(
        "https://made-up.example/.default"
    )
    assert found.token == "made-up-token-device code"
    assert [k for k, _ in fake_identity.made] == ["browser", "device code"]
    assert "login_hint" not in fake_identity.made[-1][1]  # the device code credential takes no username


def test_mfa_with_no_encrypted_cache_signs_in_for_this_run_only(fake_identity: FakeIdentity) -> None:
    fake_identity.cache_works = False
    first = mfa_class()("made-up-tenant", "made-up-user@example.com")
    assert first.get_token("https://made-up.example/.default").token == "made-up-token-browser"
    assert "cache_persistence_options" not in fake_identity.made[-1][1]
    assert not Path(first.record_file()).exists()  # nothing remembered that no cache holds


def test_the_installed_azure_identity_takes_what_mfa_gives_it() -> None:
    identity = pytest.importorskip("azure.identity")
    for name in ("InteractiveBrowserCredential", "DeviceCodeCredential"):
        taken, _ = driver_check.accepted(f"azure.identity.{name}", getattr(identity, name))
        assert {"tenant_id", "cache_persistence_options", "authentication_record"} <= taken, name
    taken, _ = driver_check.accepted(
        "azure.identity.InteractiveBrowserCredential", identity.InteractiveBrowserCredential
    )
    assert "login_hint" in taken
    assert callable(identity.AuthenticationRecord.deserialize) and callable(
        identity.AuthenticationRecord.serialize
    )
    assert identity.TokenCachePersistenceOptions(name="swissarmybench").name == "swissarmybench"
    assert "scopes" in inspect.signature(identity.InteractiveBrowserCredential.authenticate).parameters


# ===== multi-factor sign-in against the stand-ins: Dataverse, a Data Lake, SharePoint =====


def test_mfa_reads_dataverse_through_the_stand_in(
    fake_identity: FakeIdentity, monkeypatch: pytest.MonkeyPatch
) -> None:
    from swissarmybench.adapters.blade_run import run_code
    from tests import dataverse_standin

    running = dataverse_standin.StandIn().start()
    try:
        for name, value in running.environment().items():
            monkeypatch.setenv(name, value)
        fake_identity.token = dataverse_standin.TOKEN
        code = dataverse.MFA.replace("https://your-org.crm.dynamics.com", running.url)
        conn, _ = run_code(
            code.replace("my-user@my-company.com", "made-up-user@example.com"), "conn", {}, "CRM"
        )
        assert {t["table_name"] for t in conn.catalog()} >= {"account", "contact"}
        assert fake_identity.scopes[0] == f"{running.url}/.default"  # the environment's own scope
        assert fake_identity.made[0][1]["login_hint"] == "made-up-user@example.com"
    finally:
        running.stop()


def test_mfa_reads_a_data_lake_and_sharepoint_through_the_stand_ins(
    fake_identity: FakeIdentity, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from swissarmybench.adapters.blade_run import run_code
    from swissarmybench.server.blade_templates import BY_ID
    from tests import lake_standins

    lake_standins.make_lake(tmp_path / "storage")
    running = lake_standins.StandIn(tmp_path / "storage").start()
    try:
        for name, value in running.environment().items():
            monkeypatch.setenv(name, value)
        fake_identity.token = lake_standins.TOKEN

        def mfa(template: str) -> str:
            return next(code for _, mark, code in BY_ID[template].sign_ins if mark == entra.MFA_MARK)

        lake = mfa("datalake").replace("my-storage-account", lake_standins.ACCOUNT)
        lake = lake.replace("my-container", lake_standins.CONTAINER)
        lake = lake.replace('folder_in_container = ""', 'folder_in_container = "lake"')
        conn, _ = run_code(lake, "conn", {}, "Lake")
        assert conn.catalog() and fake_identity.scopes[-1] == entra.STORAGE_SCOPE
        site = f"https://{lake_standins.SITE_HOST}{lake_standins.SITE_PATH}"
        lists = mfa("sharepoint").replace("https://my-company.sharepoint.com/sites/my-site", site)
        conn, _ = run_code(lists, "conn", {}, "Team")
        assert {t["table_name"] for t in conn.catalog()} >= {"Tasks", "Customers"}
        assert fake_identity.scopes[-1] == entra.GRAPH_SCOPE
    finally:
        running.stop()
