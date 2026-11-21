"""Share a running app with your organization (the owner, 2026-11-21: "I just wanted a place for a user to
host a POC so others can connect to it like an app"), through Microsoft Dev Tunnels.

  who        organization only: the tunnel's access is the signed-in user's Microsoft Entra tenant
             (`devtunnel access create <id> --tenant`), never anonymous (no `--allow-anonymous`, no `-a`, no
             `--anonymous`: refused here, and the access list is read back before hosting); a sign-in with no
             tenant (a personal Microsoft account, GitHub) is refused with the words to sign in with a work
             account; an organization's policy that blocks it is said with what to ask IT, never worked round
  how long   until you stop it: Stop sharing, the app's own stop, or the app (Swiss Army Bench) closing; the
             tunnel is deleted then. A link always ends with its app
  what       only the app's own 127.0.0.1 port (a Streamlit app's); never the Swiss Army Bench server's port:
             check_port refuses it, and every command line is built from a checked port
  program    Microsoft's devtunnel command line, downloaded on the first share into the state folder (never
             with the app's install), from Microsoft's own download store over HTTPS (DOWNLOAD_HOST: the host
             the official install script uses), checked against the Content-MD5 that store publishes with the
             file, and on Windows its Authenticode signature (Microsoft Corporation), on macOS its code
             signature (Microsoft's Team ID). Linux has no published signature: the checksum only
  command    each line's values checked (a tunnel id, a port), one argument each, never a shell; sign-in
             with Entra (`devtunnel user login --entra`, the device code where there is no browser) is the
             user's own, never the agent's
  output     `--json` where the command has it, read loosely (the CLI is in preview); `host`'s lines read for
             the address it prints for the port (https://<id>-<port>.<region>.devtunnels.ms/) and "Ready"
  states     installing, signing_in, starting, sharing, stopped, failed; their words

Pure rules: no I/O, no clock.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# ===== the program =====

DOWNLOAD_HOST: str = (
    "tunnelsassetsprod.blob.core.windows.net"  # Microsoft's (https://aka.ms/DevTunnelCliInstall)
)
DOWNLOAD_PATH: str = "/cli/"
FOLDER: str = "devtunnel"  # in the state folder
MAX_BYTES: int = 200 * 1024 * 1024
# macOS: Microsoft Corporation's Apple Developer Team ID (its Developer ID Application certificate).
MICROSOFT_TEAM_ID: str = "UBF8T346G9"
LABEL: str = "swissarmybench"  # every tunnel this app makes carries it (a stale one is found by it)

# Each system's file in Microsoft's store (the official install script's and aka.ms/TunnelsCliDownload's).
ASSETS: dict[tuple[str, str], str] = {
    ("windows", "x64"): "devtunnel.exe",
    ("windows", "arm64"): "devtunnel.exe",  # x64, run by Windows on Arm's emulation (no arm64 build)
    ("macos", "arm64"): "osx-arm64-devtunnel",
    ("macos", "x64"): "osx-x64-devtunnel",
    ("linux", "x64"): "linux-x64-devtunnel",
    ("linux", "arm64"): "linux-arm64-devtunnel",
}

CHECKS: dict[str, str] = {
    "windows": "the Content-MD5 Microsoft's download store publishes with the file, and its Authenticode "
    "signature (Microsoft Corporation)",
    "macos": "the Content-MD5 Microsoft's download store publishes with the file, and its code signature "
    f"(Microsoft Corporation, Team ID {MICROSOFT_TEAM_ID})",
    "linux": "the Content-MD5 Microsoft's download store publishes with the file (Microsoft publishes no "
    "signature for the Linux build)",
}


class SharingError(ValueError):
    """A share that cannot go ahead (the message says why, in plain words)."""


def system_of(platform: str, machine: str) -> tuple[str, str]:
    """sys.platform and platform.machine() as (windows | macos | linux, x64 | arm64)."""
    system = (
        "windows"
        if platform.startswith(("win", "cygwin"))
        else "macos"
        if platform == "darwin"
        else "linux"
        if platform.startswith("linux")
        else ""
    )
    arch = machine.lower()
    cpu = (
        "arm64"
        if arch in ("arm64", "aarch64", "armv8", "armv8l")
        else "x64"
        if arch in ("x86_64", "amd64", "x64")
        else ""
    )
    if (system, cpu) not in ASSETS:
        raise SharingError(
            f"Sharing is not offered on {platform} ({machine}): devtunnel has no build for it."
        )
    return system, cpu


def download_url(system: str, cpu: str) -> str:
    return f"https://{DOWNLOAD_HOST}{DOWNLOAD_PATH}{ASSETS[(system, cpu)]}"


def program_name(system: str) -> str:
    return "devtunnel.exe" if system == "windows" else "devtunnel"


def checksum_matches(data: bytes, content_md5: str | None) -> bool:
    """The file's bytes against the store's Content-MD5 (base64 of the MD5 digest, RFC 1864)."""
    if not content_md5:
        return False
    try:
        published = base64.b64decode(content_md5.strip(), validate=True)
    except ValueError:
        return False
    digest = hashlib.md5(data, usedforsecurity=False).digest()
    return len(published) == 16 and published == digest


CHECKSUM_REFUSED: str = (
    "The downloaded devtunnel did not match the checksum Microsoft's download store published with it: "
    "it was not kept. Try again later; if it keeps happening, something between this computer and "
    "Microsoft is changing the download."
)
SIGNATURE_REFUSED: str = (
    "The downloaded devtunnel is not signed by Microsoft: it was not kept. Try again later, or ask IT "
    "whether something on this network changes downloads."
)


def windows_signed(said: str) -> bool:
    """PowerShell's answer (SIGNATURE_SCRIPT): Valid, and the signer is Microsoft Corporation."""
    lines = [line.strip() for line in said.strip().splitlines() if line.strip()]
    if len(lines) < 2 or lines[0] != "Valid":
        return False
    return bool(re.search(r"(^|,\s*)O=Microsoft Corporation(,|$)", lines[1]))


# Run with the file's path in the SAB_DEVTUNNEL environment variable, never in the script's text.
SIGNATURE_SCRIPT: str = (
    "$s = Get-AuthenticodeSignature -LiteralPath $env:SAB_DEVTUNNEL; "
    "Write-Output $s.Status; Write-Output $s.SignerCertificate.Subject"
)


def macos_signed(verify_code: int, details: str) -> bool:
    """`codesign --verify --strict` passed, and `codesign -dv` names Microsoft's Team ID."""
    return verify_code == 0 and bool(
        re.search(rf"^TeamIdentifier={MICROSOFT_TEAM_ID}$", details, re.MULTILINE)
    )


# ===== the values on a command line =====

_TUNNEL_ID = re.compile(r"[a-z0-9][a-z0-9-]{1,62}(\.[a-z0-9]{2,12})?")
ANONYMOUS_FLAGS: frozenset[str] = frozenset({"-a", "--allow-anonymous", "--anonymous"})


def check_tunnel_id(value: Any) -> str:
    if not isinstance(value, str) or not _TUNNEL_ID.fullmatch(value):
        raise SharingError("That is not a dev tunnel's id.")
    return value


def check_port(port: Any, server_port: int) -> int:
    """The app's own port: 1024 to 65535, and never this server's (its token, routes and pages stay here)."""
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise SharingError("The app's port is not a port this computer's apps listen on.")
    if port == server_port:
        raise SharingError("That is Swiss Army Bench's own port: it is never shared, only an app's.")
    return port


def _line(*parts: str) -> list[str]:
    """A command line, checked once more as a whole: one value each, no shell, never anonymous."""
    for part in parts:
        if not part or "\n" in part or "\x00" in part:
            raise SharingError("A value on the command line is not one line.")
    if ANONYMOUS_FLAGS & set(parts):
        raise SharingError("Anonymous access is never asked for: sharing is for your organization only.")
    return list(parts)


def login(device: bool) -> list[str]:
    """Sign in with Microsoft Entra (a work account): in the browser, or with a device code."""
    return _line("user", "login", "--entra", *(("--use-device-code-auth",) if device else ()))


def user_show() -> list[str]:
    return _line("user", "show", "--json")


def listing() -> list[str]:
    return _line("list", "--labels", LABEL, "--json")


def create() -> list[str]:
    """A tunnel with a random id, private to its owner until the tenant's entry is added; labelled so a stale
    one is found. No description: nothing of the app's goes to the service but its traffic."""
    return _line("create", "--labels", LABEL, "--json")


def access_tenant(tunnel: str) -> list[str]:
    """The signed-in user's Microsoft Entra tenant may connect (organization only)."""
    return _line("access", "create", check_tunnel_id(tunnel), "--tenant", "--json")


def access_list(tunnel: str) -> list[str]:
    return _line("access", "list", check_tunnel_id(tunnel), "--json")


def port_create(tunnel: str, port: int, server_port: int) -> list[str]:
    return _line(
        "port",
        "create",
        check_tunnel_id(tunnel),
        "--port-number",
        str(check_port(port, server_port)),
        "--protocol",
        "http",
        "--json",
    )


def host(tunnel: str) -> list[str]:
    """Host the configured tunnel (its one port): runs until it is stopped."""
    return _line("host", check_tunnel_id(tunnel))


def delete(tunnel: str) -> list[str]:
    return _line("delete", check_tunnel_id(tunnel), "--force", "--json")


# ===== what the command line says =====


def _json(text: str) -> Any:
    text = text.strip()
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        return None
    try:
        return json.loads(text[start:])
    except ValueError:
        return None


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for inner in value.values():
            yield from _walk(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _walk(inner)


def _first(value: Any, *keys: str) -> str | None:
    wanted = {k.lower() for k in keys}
    for found in _walk(value):
        for key, inner in found.items():
            if key.lower() in wanted and isinstance(inner, str) and inner.strip():
                return inner.strip()
    return None


@dataclass(frozen=True)
class User:
    signed_in: bool
    account: str | None = None  # the sign-in's name (an email address), shown to the user only
    provider: str | None = None  # microsoft | github
    tenant: str | None = None  # the Entra tenant's id, when the CLI says it

    @property
    def work(self) -> bool:
        """A work account: signed in with Microsoft and not a personal account (a tenant is said, or
        nothing says otherwise)."""
        if not self.signed_in or (self.provider or "microsoft").lower() not in ("microsoft", "entra", "aad"):
            return False
        return self.tenant != PERSONAL_TENANT


# Personal Microsoft accounts sign in through this tenant (Microsoft Entra's consumers tenant).
PERSONAL_TENANT: str = "9188040d-6c67-4c5b-b112-36a304b66dad"


def read_user(text: str) -> User:
    """`devtunnel user show --json` (or its words): signed in or not, as whom, with which provider."""
    found = _json(text)
    if isinstance(found, dict):
        status = str(found.get("status") or "")
        signed = status.lower().startswith("logged in")
        if not signed:
            return User(False)
        account = _first(found, "username", "userName", "login", "email", "name")
        provider = _first(found, "provider", "loginProvider")
        tenant = _first(found, "tenantId", "tenant", "tid")
        if account is None or provider is None:
            said = re.search(r"Logged in as (\S+) using (\w+)", status)
            if said:
                account = account or said.group(1)
                provider = provider or said.group(2)
        return User(True, account, (provider or "").lower() or None, tenant)
    said = re.search(r"Logged in as (\S+?)\.? using (\w+)", text)
    if said:
        return User(True, said.group(1), said.group(2).lower(), None)
    return User(False)


def read_tunnel_id(text: str) -> str:
    """`devtunnel create --json`: the new tunnel's id (with its cluster: <id>.<region>)."""
    found = _json(text)
    tunnel = _first(found, "tunnelId") if found is not None else None
    cluster = _first(found, "clusterId") if found is not None else None
    if tunnel is None:
        said = re.search(r"Tunnel ID\s*:\s*(\S+)", text)
        tunnel = said.group(1) if said else None
    if tunnel is None:
        raise SharingError("devtunnel did not say which tunnel it made.")
    if cluster and "." not in tunnel:
        tunnel = f"{tunnel}.{cluster}"
    return check_tunnel_id(tunnel.lower())


def read_tunnel_ids(text: str) -> list[str]:
    """`devtunnel list --json`: the ids of this app's tunnels (by their label)."""
    found = _json(text)
    out: list[str] = []
    for entry in _walk(found):
        tunnel = entry.get("tunnelId")
        if isinstance(tunnel, str):
            cluster = entry.get("clusterId")
            full = f"{tunnel}.{cluster}" if isinstance(cluster, str) and "." not in tunnel else tunnel
            if _TUNNEL_ID.fullmatch(full.lower()):
                out.append(full.lower())
    return sorted(set(out))


@dataclass(frozen=True)
class Access:
    anonymous: bool  # an allow entry for anonymous clients (must never be)
    tenant: bool  # an allow entry for the tenant (must be)
    tenant_id: str | None


def read_access(text: str) -> Access:
    """`devtunnel access list --json`: is anyone anonymous allowed, is the tenant allowed (read loosely: an
    entry's type Anonymous; Organizations or Tenant with Microsoft as its provider)."""
    found = _json(text)
    anonymous = tenant = False
    tenant_id: str | None = None
    for entry in _walk(found):
        kind = str(entry.get("type") or "").lower()
        if not kind or entry.get("isDeny") is True:
            continue
        if kind == "anonymous":
            anonymous = True
        elif kind in ("organizations", "tenant", "tenants") and str(
            entry.get("provider") or "microsoft"
        ).lower() in (
            "microsoft",
            "entra",
            "aad",
        ):
            tenant = True
            subjects = entry.get("subjects")
            if isinstance(subjects, list) and subjects and isinstance(subjects[0], str):
                tenant_id = subjects[0]
    if found is None and re.search(r"\banonymous\b", text, re.IGNORECASE) and "deny" not in text.lower():
        anonymous = True
    return Access(anonymous, tenant, tenant_id)


_ADDRESS = re.compile(r"https://([a-z0-9-]+)-(\d{2,5})\.([a-z0-9]+)\.devtunnels\.ms/?", re.IGNORECASE)


def read_address(line: str, port: int) -> str | None:
    """`devtunnel host`'s line that names the address for the app's port (never the -inspect one)."""
    for found in _ADDRESS.finditer(line):
        if found.group(1).endswith("-inspect") or int(found.group(2)) != port:
            continue
        if line[found.end() : found.end() + 8].startswith("-inspect"):
            continue
        return f"https://{found.group(1)}-{found.group(2)}.{found.group(3)}.devtunnels.ms/".lower()
    return None


def ready(line: str) -> bool:
    return "ready to accept connections" in line.lower()


@dataclass(frozen=True)
class DeviceCode:
    url: str
    code: str


_DEVICE = re.compile(r"(https://\S*devicelogin\S*)\s+and enter the code\s+([A-Z0-9-]{6,16})", re.IGNORECASE)


def read_device_code(line: str) -> DeviceCode | None:
    """The device code sign-in's line: the page to open and the code to type there."""
    found = _DEVICE.search(line)
    if not found:
        return None
    url = found.group(1).rstrip(".,")
    if not url.startswith(
        ("https://microsoft.com/", "https://login.microsoft.com/", "https://www.microsoft.com/")
    ):
        return None
    return DeviceCode(url, found.group(2).upper())


# ===== the words =====

STATES: tuple[str, ...] = ("installing", "signing_in", "starting", "sharing", "stopped", "failed")

SENTENCE: str = (
    "People in your organization can open this app after signing in with their work account. It runs on this "
    "computer while it is shared."
)
NOTE: str = (
    "Shared: anyone in your organization with the link can use this app. Its queries run on this computer "
    "with your connections."
)
NEEDS: str = "Sharing needs devtunnel"
NOT_WORK_ACCOUNT: str = (
    "Sign in with your work account: a personal Microsoft account or GitHub has no organization to share "
    "with."
)
NOT_SIGNED_IN: str = "Sign in with your work account first (Share…, Sign in): the user's own step."
NOT_RUNNING: str = "The app is not running: Launch it first, then share it."
ANONYMOUS_FOUND: str = (
    "The tunnel allowed anonymous access, so it was deleted and nothing was shared. Sharing is for your "
    "organization only."
)
NO_TENANT_ENTRY: str = (
    "The tunnel did not take your organization's access, so it was deleted and nothing was shared."
)
POLICY: str = (
    "Your organization's policy does not allow this: Dev Tunnels is turned off for your account, or not "
    "with access for your organization. Ask IT to allow Microsoft Dev Tunnels with organization (tenant) "
    'access for your work account: the Dev Tunnels policies "Disable Dev Tunnels" and "Allow only selected '
    'Microsoft Entra tenant IDs" (your tenant must be in its list), and any Conditional Access policy on '
    "the Dev Tunnels service. Nothing was shared."
)

_POLICY = re.compile(
    r"(policy|policies|conditional access|AADSTS53003|AADSTS530|not allowed by your|blocked by your "
    r"organi[sz]ation|tenant (is )?not allowed|forbidden by)",
    re.IGNORECASE,
)


def blocked_by_policy(text: str) -> bool:
    return bool(_POLICY.search(text))


def failure(text: str) -> str:
    """A devtunnel failure in plain words: a policy's said with what to ask IT; else its last lines."""
    if blocked_by_policy(text):
        return POLICY
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()][-3:]
    return "devtunnel said: " + " ".join(lines) if lines else "devtunnel stopped without saying why."


def who_can_open(tenant_name: str | None) -> str:
    return f"Your organization: {tenant_name}" if tenant_name else "Your organization"


def state_words(state: str) -> str:
    return {
        "installing": "Installing devtunnel…",
        "signing_in": "Signing in…",
        "starting": "Starting the tunnel…",
        "sharing": "Shared",
        "stopped": "Not shared",
        "failed": "Not shared",
    }.get(state, "Not shared")
