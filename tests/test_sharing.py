"""Share a running app with your organization (the owner, 2026-11-21: "a place for a user to host a POC so
others can connect to it like an app"; organization only, until you stop it, devtunnel downloaded on the first
share and checked).

The command lines and the output read from recorded made-up outputs; organization only, never anonymous; the
tunnel's target is the app's port and never the server's; the checksum refusal; the whole share through the
stand-in program (tests/devtunnel_standin.py) with a stand-in app; stop with the app and with the server; the
agent's Allow and the user's own sign-in; over HTTP. Made-up names only; nothing leaves the computer."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import socket
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.adapters import tunnels
from swissarmybench.adapters.tunnels import TunnelFiles
from swissarmybench.domain import session_log
from swissarmybench.domain import sharing as rules
from swissarmybench.domain.sharing import SharingError
from swissarmybench.server.tunnels import DevTunnelProgram
from swissarmybench.services.sharing import Opened, Sharing
from swissarmybench.services.workspace import Conflict, Refused
from tests.conftest import AGENT, AUTH, PORT, make_client

STANDIN = Path(__file__).parent / "devtunnel_standin.py"
SERVER_PORT = 8765
APP_PORT = 8601

# ===== the command lines =====


def test_every_command_line_is_checked_values_one_argument_each() -> None:
    assert rules.login(False) == ["user", "login", "--entra"]
    assert rules.login(True) == ["user", "login", "--entra", "--use-device-code-auth"]
    assert rules.user_show() == ["user", "show", "--json"]
    assert rules.create() == ["create", "--labels", "swissarmybench", "--json"]
    assert rules.access_tenant("made-up-1a2b3c.usw2") == [
        "access",
        "create",
        "made-up-1a2b3c.usw2",
        "--tenant",
        "--json",
    ]
    assert rules.port_create("made-up-1a2b3c", APP_PORT, SERVER_PORT) == [
        "port",
        "create",
        "made-up-1a2b3c",
        "--port-number",
        "8601",
        "--protocol",
        "http",
        "--json",
    ]
    assert rules.host("made-up-1a2b3c") == ["host", "made-up-1a2b3c"]
    assert rules.delete("made-up-1a2b3c") == ["delete", "made-up-1a2b3c", "--force", "--json"]
    for bad in ("x; rm -rf /", "--allow-anonymous", "-a", "Made Up", "", "a" * 80, "x\ny"):
        with pytest.raises(SharingError):
            rules.host(bad)


def test_organization_only_never_anonymous() -> None:
    lines = [
        rules.login(True),
        rules.create(),
        rules.access_tenant("made-up-1"),
        rules.port_create("made-up-1", APP_PORT, SERVER_PORT),
        rules.host("made-up-1"),
    ]
    for line in lines:
        assert not rules.ANONYMOUS_FLAGS & set(line)
    assert "--tenant" in rules.access_tenant("made-up-1")
    with pytest.raises(SharingError, match="organization only"):
        rules._line("create", "--allow-anonymous")
    with pytest.raises(SharingError, match="organization only"):
        rules._line("access", "create", "made-up-1", "--anonymous")


def test_the_tunnels_target_is_never_the_servers_port() -> None:
    with pytest.raises(SharingError, match="Swiss Army Bench's own port"):
        rules.check_port(SERVER_PORT, SERVER_PORT)
    with pytest.raises(SharingError, match="Swiss Army Bench's own port"):
        rules.port_create("made-up-1", SERVER_PORT, SERVER_PORT)
    for bad in (0, 80, 70000, True, "8601", None):
        with pytest.raises(SharingError):
            rules.check_port(bad, SERVER_PORT)
    assert rules.check_port(APP_PORT, SERVER_PORT) == APP_PORT


# ===== what the command line says (recorded made-up outputs) =====


def test_the_sign_in_is_read() -> None:
    assert rules.read_user('{\n  "status": "Not logged in"\n}') == rules.User(False)
    signed = rules.read_user(
        json.dumps(
            {
                "status": "Logged in as dana.lee@contoso-made-up.example using Microsoft.",
                "tenantId": "00000000-0000-4000-8000-00000000c0de",
            }
        )
    )
    assert signed.signed_in and signed.account == "dana.lee@contoso-made-up.example"
    assert signed.provider == "microsoft" and signed.work
    assert rules.read_user("Logged in as dana.lee@contoso-made-up.example using Microsoft.").work
    personal = rules.read_user(
        json.dumps({"status": "Logged in as x using Microsoft.", "tenantId": rules.PERSONAL_TENANT})
    )
    assert personal.signed_in and not personal.work
    github = rules.read_user('{"status": "Logged in as made-up-octo using GitHub."}')
    assert github.signed_in and not github.work
    assert not rules.read_user("").signed_in


def test_a_made_tunnels_id_and_the_list_are_read() -> None:
    made = json.dumps(
        {"tunnel": {"tunnelId": "made-up-7f3a9c", "clusterId": "usw2", "labels": ["swissarmybench"]}},
        indent=1,
    )
    assert rules.read_tunnel_id(made) == "made-up-7f3a9c.usw2"
    assert rules.read_tunnel_id("Tunnel ID             : made-up-7f3a9c.usw2\n") == "made-up-7f3a9c.usw2"
    with pytest.raises(SharingError):
        rules.read_tunnel_id("Something went wrong")
    listed = '{"tunnels": [{"tunnelId": "made-up-1", "clusterId": "euw"}, {"tunnelId": "made-up-2.usw2"}]}'
    assert rules.read_tunnel_ids(listed) == ["made-up-1.euw", "made-up-2.usw2"]


def test_the_access_list_says_anonymous_and_the_tenant() -> None:
    none = rules.read_access('{"accessControlEntries": []}')
    assert not none.anonymous and not none.tenant
    tenant = rules.read_access(
        '{"accessControlEntries": [{"type": "Organizations", "provider": "microsoft", '
        '"subjects": ["00000000-0000-4000-8000-00000000c0de"], "scopes": ["connect"]}]}'
    )
    assert (
        tenant.tenant and not tenant.anonymous and tenant.tenant_id == "00000000-0000-4000-8000-00000000c0de"
    )
    anonymous = rules.read_access('{"accessControlEntries": [{"type": "Anonymous", "scopes": ["connect"]}]}')
    assert anonymous.anonymous
    denied = rules.read_access('{"accessControlEntries": [{"type": "Anonymous", "isDeny": true}]}')
    assert not denied.anonymous


def test_hosts_address_for_the_apps_port() -> None:
    # Microsoft Learn's sample (get-started): the port's own address, never the inspect one.
    line = (
        "Hosting port 8080 at https://abc123xy.usw2.devtunnels.ms:8080/, "
        "https://abc123xy-8080.usw2.devtunnels.ms/ "
        "and inspect it at https:/abc123xy-8080-inspect.usw2.devtunnels.ms/"
    )
    assert rules.read_address(line, 8080) == "https://abc123xy-8080.usw2.devtunnels.ms/"
    assert rules.read_address(line, 3000) is None
    assert rules.read_address("Connect via browser: https://4r9dd5xj-3978.usw2.devtunnels.ms", 3978) == (
        "https://4r9dd5xj-3978.usw2.devtunnels.ms/"
    )
    assert rules.read_address("https://abc-8080-inspect.usw2.devtunnels.ms/", 8080) is None
    assert rules.read_address("https://abc-8080.evil.example/", 8080) is None
    assert rules.ready("Ready to accept connections for tunnel: abc123xy.usw2")


def test_the_device_code_line_is_read() -> None:
    line = (
        "To sign in, use a web browser to open the page https://microsoft.com/devicelogin and enter the code "
        "MADEUP42 to authenticate."
    )
    assert rules.read_device_code(line) == rules.DeviceCode("https://microsoft.com/devicelogin", "MADEUP42")
    assert (
        rules.read_device_code("open the page https://evil.example/devicelogin and enter the code X1Y2Z3W4")
        is None
    )


def test_a_policy_is_said_with_what_to_ask_it() -> None:
    said = rules.failure("Tunnel service error: Forbidden. Access denied by your organization's policy.")
    assert said == rules.POLICY and "Ask IT" in said and "Nothing was shared" in said
    assert (
        rules.failure("AADSTS53003: Access has been blocked by Conditional Access policies.") == rules.POLICY
    )
    assert rules.failure("one\ntwo\nthree\nfour") == "devtunnel said: two three four"


def test_the_systems_file_and_its_checks() -> None:
    assert rules.system_of("win32", "AMD64") == ("windows", "x64")
    assert rules.system_of("darwin", "arm64") == ("macos", "arm64")
    assert rules.system_of("linux", "aarch64") == ("linux", "arm64")
    assert (
        rules.download_url("windows", "x64")
        == "https://tunnelsassetsprod.blob.core.windows.net/cli/devtunnel.exe"
    )
    assert rules.download_url("linux", "x64").endswith("/cli/linux-x64-devtunnel")
    with pytest.raises(SharingError):
        rules.system_of("sunos5", "sparc")
    data = b"made-up program bytes"
    md5 = base64.b64encode(hashlib.md5(data).digest()).decode()  # noqa: S324 (the store's own checksum)
    assert rules.checksum_matches(data, md5)
    assert not rules.checksum_matches(data + b"x", md5)
    assert not rules.checksum_matches(data, None) and not rules.checksum_matches(data, "not base64!")
    assert rules.windows_signed("Valid\nCN=Microsoft Corporation, O=Microsoft Corporation, L=Redmond, C=US\n")
    assert not rules.windows_signed("NotSigned\n\n")
    assert not rules.windows_signed("Valid\nCN=Made Up Ltd, O=Made Up Ltd\n")
    assert rules.macos_signed(0, "Identifier=devtunnel\nTeamIdentifier=UBF8T346G9\n")
    assert not rules.macos_signed(0, "TeamIdentifier=ABCDE12345\n")
    assert not rules.macos_signed(1, "TeamIdentifier=UBF8T346G9\n")


# ===== the download =====


def test_a_download_that_does_not_match_its_checksum_is_refused_and_not_kept(tmp_path: Path) -> None:
    def tampered(url: str) -> tuple[bytes, dict[str, str]]:
        assert url.startswith("https://tunnelsassetsprod.blob.core.windows.net/cli/")
        good = base64.b64encode(hashlib.md5(b"the real bytes").digest()).decode()  # noqa: S324
        return b"something else", {"content-md5": good}

    program = DevTunnelProgram(TunnelFiles(tmp_path / "devtunnel", environ={}, fetch=tampered))
    with pytest.raises(SharingError, match="did not match the checksum"):
        asyncio.run(program.install())
    assert not program.installed()
    assert not (tmp_path / "devtunnel").exists() or not list(
        (tmp_path / "devtunnel").iterdir()
    )  # nothing kept

    def unsaid(url: str) -> tuple[bytes, dict[str, str]]:
        return b"bytes", {}

    with pytest.raises(SharingError, match="checksum"):
        asyncio.run(DevTunnelProgram(TunnelFiles(tmp_path / "other", environ={}, fetch=unsaid)).install())


def test_the_download_is_microsofts_store_only() -> None:
    with pytest.raises(SharingError, match="Microsoft's download store"):
        tunnels.https_fetch("https://example.com/cli/devtunnel")
    with pytest.raises(SharingError, match="Microsoft's download store"):
        tunnels.https_fetch("http://tunnelsassetsprod.blob.core.windows.net/cli/devtunnel")


# ===== the share, through the stand-in =====


class FakeAudit:
    def __init__(self) -> None:
        self.entries: list[tuple[str, str, Any, dict[str, Any]]] = []

    def write(self, actor: str, action: str, dataset: Any = None, **details: Any) -> None:
        self.entries.append((actor, action, dataset, details))


class FakeLive:
    def __init__(self) -> None:
        self.said: list[dict[str, Any]] = []

    async def broadcast(self, message: dict[str, Any]) -> None:
        self.said.append(message)


class FakeWs:
    def __init__(self) -> None:
        self.audit = FakeAudit()
        self.live = FakeLive()


class Asker:
    def __init__(self, answer: bool) -> None:
        self.answer = answer
        self.asked: list[str] = []

    async def ask(self, dataset: str, action: str, detail: str) -> bool:
        self.asked.append(action)
        return self.answer


class App:
    """A stand-in for a launched app: opens its own port when shared."""

    def __init__(self, port: int = APP_PORT) -> None:
        self.port = port
        self.opened: list[str] = []
        self.closed: list[str] = []

    async def open(self, app: str) -> Opened:
        self.opened.append(app)
        return Opened(self.port, "Sales POC · build 3")

    async def close(self, app: str) -> None:
        self.closed.append(app)


def _sharing(
    tmp_path: Path, target: App, allow: bool = True
) -> tuple[Sharing, FakeWs, DevTunnelProgram, Asker]:
    program = DevTunnelProgram(
        TunnelFiles(tmp_path / "devtunnel", environ={tunnels.STANDIN_ENV: str(STANDIN)})
    )
    ws = FakeWs()
    asker = Asker(allow)
    return Sharing(ws, program, lambda: {"streamlit": target}, asker, SERVER_PORT), ws, program, asker  # type: ignore[arg-type]


def _calls(tmp_path: Path) -> list[list[str]]:
    log = tmp_path / "devtunnel" / "calls.log"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


async def _signed_in(sharing: Sharing) -> None:
    said = await sharing.sign_in({"device": True})
    assert said["device"] == {"url": "https://microsoft.com/devicelogin", "code": "MADEUP42"}
    for _ in range(100):
        status = await sharing.status()
        if status["signed_in"] and not status["signing_in"]:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("not signed in")


def test_a_share_from_install_to_stop(tmp_path: Path) -> None:
    async def run() -> None:
        app = App()
        sharing, ws, program, _ = _sharing(tmp_path, app)
        first = await sharing.status()
        assert not first["installed"] and first["needs"] == "Sharing needs devtunnel"
        with pytest.raises(Conflict, match="Install now"):
            await sharing.start({"kind": "streamlit", "app": "sales"})
        await sharing.install()
        assert program.installed()
        with pytest.raises(Conflict, match="Sign in"):
            await sharing.start({"kind": "streamlit", "app": "sales"})
        await _signed_in(sharing)
        shared = await sharing.start({"kind": "streamlit", "app": "sales"})
        assert shared["state"] == "sharing"
        assert shared["url"].startswith("https://made-up-") and shared["url"].endswith(
            f"-{APP_PORT}.usw2.devtunnels.ms/"
        )
        assert shared["who"] == "Your organization" and shared["note"] == rules.NOTE
        calls = _calls(tmp_path)
        # Organization only: the tenant's entry, never anonymous on any line.
        assert any(c[:2] == ["access", "create"] and "--tenant" in c for c in calls)
        assert not any(rules.ANONYMOUS_FLAGS & set(c) for c in calls)
        # The tunnel's one port is the app's, never the server's.
        ports = [int(c[c.index("--port-number") + 1]) for c in calls if c[:2] == ["port", "create"]]
        assert ports == [APP_PORT] and SERVER_PORT not in ports
        assert sharing.shared("streamlit", "sales")
        await sharing.stop({"kind": "streamlit", "app": "sales"})
        assert app.closed == ["sales"]
        assert any(c[0] == "delete" for c in _calls(tmp_path))
        assert (await sharing.status())["shares"] == []
        actions = [e[1] for e in ws.audit.entries]
        assert actions == ["share_install", "share_sign_in", "share_start", "share_stop"]
        # The audit names the app, never the link nor the tunnel.
        written = json.dumps([e[2:] for e in ws.audit.entries])
        assert "devtunnels.ms" not in written and "made-up-" not in written
        assert "Sales POC" in written

    asyncio.run(run())


def test_the_server_port_is_refused_as_a_target(tmp_path: Path) -> None:
    async def run() -> None:
        app = App(port=SERVER_PORT)
        sharing, _, _, _ = _sharing(tmp_path, app)
        await sharing.install()
        await _signed_in(sharing)
        with pytest.raises(Conflict, match="Swiss Army Bench's own port"):
            await sharing.start({"kind": "streamlit", "app": "sales"})
        assert not any(c[:2] == ["port", "create"] for c in _calls(tmp_path))
        assert not any(c[0] == "host" for c in _calls(tmp_path))
        assert app.closed == ["sales"]

    asyncio.run(run())


@pytest.mark.parametrize(
    ("mode", "said"),
    [("policy", "Ask IT"), ("anonymous", "allowed anonymous access"), ("personal", "work account")],
)
def test_a_refusal_shares_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, said: str
) -> None:
    monkeypatch.setenv("SAB_STANDIN_MODE", mode)

    async def run() -> None:
        app = App()
        sharing, _, _, _ = _sharing(tmp_path, app)
        await sharing.install()
        await sharing.sign_in({})
        for _ in range(100):
            if not (await sharing.status())["signing_in"]:
                break
            await asyncio.sleep(0.05)
        if mode == "personal":
            assert (await sharing.status())["sign_in_error"] == rules.NOT_WORK_ACCOUNT
        with pytest.raises(Conflict, match=said):
            await sharing.start({"kind": "streamlit", "app": "sales"})
        calls = _calls(tmp_path)
        # Never worked round: no anonymous asked for; the tunnel made is deleted again.
        assert not any(rules.ANONYMOUS_FLAGS & set(c) for c in calls)
        made = [c for c in calls if c[0] == "create"]
        assert len([c for c in calls if c[0] == "delete"]) >= len(made)
        assert not sharing.shared("streamlit", "sales")

    asyncio.run(run())


def test_a_share_ends_with_its_app_and_with_the_server(tmp_path: Path) -> None:
    async def run() -> None:
        app = App()
        sharing, ws, _, _ = _sharing(tmp_path, app)
        await sharing.install()
        await _signed_in(sharing)
        await sharing.start({"kind": "streamlit", "app": "sales"})
        await sharing.app_stopped("streamlit", "sales")
        assert not sharing.shared("streamlit", "sales") and app.closed == ["sales"]
        assert ws.audit.entries[-1][3]["why"] == "the app stopped"
        await sharing.start({"kind": "streamlit", "app": "sales"})
        await sharing.start({"kind": "streamlit", "app": "orders"})
        await sharing.stop_all()
        assert (await sharing.status())["shares"] == []
        assert sorted(app.closed) == ["orders", "sales", "sales"]
        assert ws.audit.entries[-1][3]["why"] == "Swiss Army Bench closed"
        hosted = [c for c in _calls(tmp_path) if c[0] == "host"]
        deleted = [c for c in _calls(tmp_path) if c[0] == "delete"]
        assert len(deleted) >= len(hosted) == 3

    asyncio.run(run())


def test_the_agent_waits_for_allow_and_never_signs_in(tmp_path: Path) -> None:
    async def run() -> None:
        app = App()
        sharing, _, _, asker = _sharing(tmp_path, app, allow=False)
        with pytest.raises(Refused, match="user's own"):
            await sharing.sign_in({}, "agent")
        with pytest.raises(Refused, match="declined"):
            await sharing.start({"kind": "streamlit", "app": "sales"}, "agent")
        assert asker.asked == ["share_start"] and app.opened == []
        asker.answer = True
        await sharing.install()
        await _signed_in(sharing)
        said = await sharing.start({"kind": "streamlit", "app": "sales"}, "agent")
        assert said["state"] == "sharing"
        assert (await sharing.status({}, "agent"))["account"] is None  # the sign-in's name is the user's
        await sharing.stop({"kind": "streamlit", "app": "sales"}, "agent")
        assert asker.asked[-1] == "share_stop"

    asyncio.run(run())


def test_the_session_log_says_which_app_never_the_link() -> None:
    entry = session_log.entry("user", "share_start", "Sales POC · build 3", {"kind": "streamlit"})
    assert entry is not None and entry["what"] == "Shared Sales POC · build 3 with the organization"
    stopped = session_log.entry("user", "share_stop", "Sales POC · build 3", {"why": "the app stopped"})
    assert stopped is not None and stopped["what"] == "Stopped sharing Sales POC · build 3 (the app stopped)"


# ===== over HTTP =====


class _Echo:
    """A made-up app on its own 127.0.0.1 port (only its port matters to the tunnel)."""

    def __init__(self) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = int(probe.getsockname()[1])


def test_over_http(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        ctx = client.app.state.ctx  # type: ignore[attr-defined]
        app = App(port=_Echo().port)
        ctx.hooks.share_targets["test"] = app
        said = client.get("/sharing", headers=AUTH).json()
        assert said["installed"] is False and "test" in said["kinds"] and said["sentence"] == rules.SENTENCE
        assert client.post("/sharing/sign-in", json={}, headers=AGENT).status_code == 403
        assert client.post("/sharing/install", headers=AUTH).json() == {"installed": True}
        assert (
            client.post("/sharing/sign-in", json={"device": True}, headers=AUTH).json()["device"]["code"]
            == "MADEUP42"
        )
        for _ in range(100):
            if client.get("/sharing?fresh=1", headers=AUTH).json()["signed_in"]:
                break
            asyncio.run(asyncio.sleep(0.05))
        shared = client.post("/sharing/start", json={"kind": "test", "app": "poc"}, headers=AUTH).json()
        assert shared["state"] == "sharing" and f"-{app.port}.usw2.devtunnels.ms" in shared["url"]
        assert app.port != PORT
        listed = client.get("/sharing?kind=test&app=poc", headers=AUTH).json()["shares"]
        assert [s["url"] for s in listed] == [shared["url"]]
        assert (
            client.post("/sharing/start", json={"kind": "nothing", "app": "x"}, headers=AUTH).status_code
            == 404
        )
        assert (
            client.post("/sharing/stop", json={"kind": "test", "app": "poc"}, headers=AUTH).json()["state"]
            == "stopped"
        )
        assert app.closed == ["poc"]
        client.post("/sharing/start", json={"kind": "test", "app": "poc"}, headers=AUTH)
    # The server stopped: its shares ended with it.
    assert app.closed == ["poc", "poc"]
