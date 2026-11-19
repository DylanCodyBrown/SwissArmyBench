"""App registrations (the owner, 2026-11-19): a generic library item, not Power BI's. One registration is a
name
and three VARIABLE names (tenant id, client id, client secret: the secret a keyring or vault variable); never
a
value in a file. Shared through the team library: `app-registrations/<name>.toml`, one small file each,
byte-stable.

  [ITEM]     the registration's file (sorted keys, the same text for the same thing), read back loosely
  [ACCESS]   an access report: what the registration reaches, each item ✓ (ok), ✗ (refused, with the plain
             reason and the fix: "Add it to the Sales workspace as Viewer") or not checked (with why); names,
             marks, reasons, the time and which computer checked; never a token, row, row count or secret.
             Kept beside the registration (`<name>.access.json`), byte-stable
  [WORDS]    an HTTP answer from Microsoft's sign-in or Power BI read in plain words (401, 403, the tenant
             setting's refusal, a workspace it is not in)

Pure rules: standard library only, no I/O, no clock.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

FOLDER = "app-registrations"
FORMAT = 1
ROLES = ("tenant", "client", "secret")
# Microsoft Learn's service principal pages (the URLs and the date read are in docs/verified.md).
TENANT_SETTING = (
    "the tenant setting “Service principals can call Fabric public APIs” is off for it (Fabric admin "
    "portal, Developer settings)"
)
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}")
_VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")


class Refused(Exception):
    """Microsoft or Power BI said no: the status and its words (read by sign_in_refused, powerbi_refused)."""

    def __init__(self, status: int, said: str) -> None:
        super().__init__(str(status))
        self.status = status
        self.said = said


class RegistrationError(ValueError):
    """A registration that cannot be kept as given; the message says why."""


@dataclass(frozen=True)
class Registration:
    name: str
    tenant: str  # the variable holding the tenant id
    client: str  # the variable holding the client (application) id
    secret: str  # the variable holding the client secret (a keyring or vault variable)
    description: str = ""

    def variables(self) -> tuple[str, str, str]:
        return self.tenant, self.client, self.secret

    def to_json(self) -> dict[str, str]:
        return {
            "name": self.name,
            "tenant": self.tenant,
            "client": self.client,
            "secret": self.secret,
            "description": self.description,
        }


def check(body: Any) -> Registration:
    """A registration from what a form or the agent sent: its name and three variable names."""
    if not isinstance(body, dict):
        raise RegistrationError('Send {"name", "tenant", "client", "secret"}: the variables that hold them.')
    name = str(body.get("name") or "").strip()
    if not _NAME.fullmatch(name):
        raise RegistrationError("Name it with letters, digits, spaces, _ . or - (up to 64).")
    names = []
    for role, words in zip(ROLES, ("tenant id", "client id", "client secret"), strict=True):
        value = str(body.get(role) or "").strip().removeprefix("${").removesuffix("}")
        if not _VARIABLE.fullmatch(value):
            raise RegistrationError(f"Name the variable that holds its {words} (letters, digits and _).")
        names.append(value)
    return Registration(name, names[0], names[1], names[2], str(body.get("description") or "").strip()[:200])


def file_name(name: str) -> str:
    """The registration's file: its name in lower case, spaces as -, .toml."""
    return re.sub(r"[^a-z0-9_.-]+", "-", name.strip().casefold()).strip("-") + ".toml"


def _toml(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def write(reg: Registration) -> str:
    """The file's text (sorted, stable): names only."""
    lines = [f"format = {FORMAT}", f"name = {_toml(reg.name)}"]
    if reg.description:
        lines.append(f"description = {_toml(reg.description)}")
    lines += ["", "[variables]", f"client = {_toml(reg.client)}", f"secret = {_toml(reg.secret)}"]
    lines.append(f"tenant = {_toml(reg.tenant)}")
    return "\n".join(lines) + "\n"


def read(text: str) -> Registration:
    import tomllib

    data = tomllib.loads(text)
    variables = data.get("variables", {}) if isinstance(data.get("variables"), dict) else {}
    return check({"name": data.get("name"), "description": data.get("description", "")} | variables)


# ===== the access report =====


@dataclass(frozen=True)
class Access:
    """One thing a registration should reach: ok True (✓), False (✗) or None (not checked)."""

    area: str  # "Power BI", "Connection"
    target: str  # "the Sales workspace", "Sales model", a connection's name
    ok: bool | None
    reason: str = ""  # ✗ or not checked: why, in plain words
    fix: str = ""  # ✗: what to do
    connection: str = ""  # the connection the item is about, when one is

    def mark(self) -> str:
        return {True: "✓", False: "✗", None: "not checked"}[self.ok]

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"area": self.area, "target": self.target, "ok": self.ok, "mark": self.mark()}
        for key in ("reason", "fix", "connection"):
            if getattr(self, key):
                out[key] = getattr(self, key)
        return out


@dataclass(frozen=True)
class Report:
    registration: str
    checked: str  # ISO time, given by the caller (no clock here)
    computer: str
    identity: Mapping[str, Any] = field(default_factory=dict)  # tenant, app name, roles/scopes (names)
    items: tuple[Access, ...] = ()

    def for_connection(self, name: str) -> list[Access]:
        """What the connection reaches: the registration's sign-in first (it signs the connection in), then
        its own items; nothing when the report names it nowhere."""
        own = [i for i in self.items if i.connection.casefold() == name.casefold()]
        if not own:
            return []
        return [i for i in self.items if i.area == "Sign-in"] + own

    def to_json(self) -> dict[str, Any]:
        return {
            "format": FORMAT,
            "registration": self.registration,
            "checked": self.checked,
            "computer": self.computer,
            "identity": dict(self.identity),
            "items": [i.to_json() for i in self.items],
        }


def write_report(report: Report) -> str:
    return json.dumps(report.to_json(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def read_report(text: str) -> Report:
    data = json.loads(text)
    items = tuple(
        Access(
            str(i.get("area", "")),
            str(i.get("target", "")),
            i.get("ok") if isinstance(i.get("ok"), bool) else None,
            str(i.get("reason", "")),
            str(i.get("fix", "")),
            str(i.get("connection", "")),
        )
        for i in data.get("items", [])
        if isinstance(i, dict)
    )
    return Report(
        str(data.get("registration", "")),
        str(data.get("checked", "")),
        str(data.get("computer", "")),
        dict(data.get("identity") or {}),
        items,
    )


def one_line(items: Sequence[Access]) -> str:
    """A connection's access in one line (context.md, a card): "✓ 3, ✗ 1 (Sales workspace)"."""
    if not items:
        return "not checked"
    good = sum(1 for i in items if i.ok is True)
    bad = [i for i in items if i.ok is False]
    unchecked = sum(1 for i in items if i.ok is None)
    parts = [f"✓ {good}"] if good else []
    if bad:
        parts.append(f"✗ {len(bad)} ({', '.join(i.target for i in bad[:2])})")
    if unchecked:
        parts.append(f"{unchecked} not checked")
    return ", ".join(parts)


# ===== Microsoft's answers in plain words =====


def token_claims(token: str) -> dict[str, Any]:
    """A JWT's claims (its middle part), for the tenant, app name and roles: read, never kept or logged."""
    import base64

    parts = token.split(".")
    if len(parts) < 2:
        return {}
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, TypeError):
        return {}
    return claims if isinstance(claims, dict) else {}


def identity(claims: Mapping[str, Any], registration: Registration) -> dict[str, Any]:
    """The token's tenant, app name and roles/scopes: names only (never the token)."""
    roles = claims.get("roles") or []
    scopes = str(claims.get("scp") or "").split()
    return {
        "tenant": str(claims.get("tid") or ""),
        "app": str(claims.get("app_displayname") or claims.get("appid") or registration.name),
        "roles": sorted(str(r) for r in roles) if isinstance(roles, list) else [],
        "scopes": sorted(scopes),
    }


def sign_in_refused(status: int, said: str) -> str:
    """A refused sign-in in plain words (AADSTS codes read)."""
    if "AADSTS7000215" in said or "invalid_client" in said:
        return (
            "Microsoft refused its client secret: it is wrong or has expired. Set the secret variable again."
        )
    if "AADSTS700016" in said or "unauthorized_client" in said:
        return "Microsoft does not know this client id in that tenant: check the client id variable."
    if "AADSTS90002" in said:
        return "Microsoft does not know that tenant: check the tenant id variable."
    return f"Microsoft refused the sign-in ({status})."


def powerbi_refused(status: int, said: str, workspace: str = "") -> tuple[str, str]:
    """A Power BI refusal: (the plain reason, the fix)."""
    where = f"the {workspace} workspace" if workspace else "the workspace"
    if status == 401 and ("PowerBINotAuthorizedException" in said or "API is not accessible" in said):
        return (
            f"Power BI refused it: {TENANT_SETTING}",
            "Ask a Fabric admin to allow service principals (or the security group it is in).",
        )
    if status in (401, 403) and "ExecuteQueries" in said:
        return (
            "it may not run DAX on this dataset: the Execute Queries tenant setting is off, or "
            "it lacks Build permission",
            f"Give it Build permission on the dataset, or add it to {where} as Viewer",
        )
    if status == 404 or "PowerBIEntityNotFound" in said:
        return f"it is not a member of {where}", f"Add it to {where} as Viewer"
    if status in (401, 403):
        return f"Power BI refused it ({status})", f"Add it to {where} as Viewer"
    return f"Power BI answered {status}", "Check again later"


NOT_CHECKED_KINDS: dict[str, str] = {
    "sqlserver": "reaching the database needs its server on this network: Check again there",
    "dataverse": "WhoAmI is asked once the connection signs in with this registration",
    "sharepoint": "its sites are listed once the connection signs in with this registration",
    "datalake": "its paths are listed once the connection signs in with this registration",
    "onelake": "its paths are listed once the connection signs in with this registration",
}


def uses(code: str, registration: Registration) -> bool:
    """A connection's code signs in with this registration: it reads all three of its variables."""
    return all(re.search(rf"\b{re.escape(v)}\b", code) for v in registration.variables())


def names_in(found: Iterable[Registration]) -> list[str]:
    return sorted((r.name for r in found), key=str.casefold)
