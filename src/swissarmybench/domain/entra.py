# ruff: noqa: E501 (the connections' code is text, written as it runs; its lines are its own)
"""Signing in to Microsoft Entra, as text: the one sign-in code the lake and SharePoint connections share
(OneLake, Data Lake, Delta Lake on Azure, SharePoint lists, SharePoint documents).

The same three ways Dataverse and Power BI sign in (domain/dataverse.py), written once here for these
five kinds, plus a fourth for SharePoint (the owner, 2026-11-17: "My only SharePoint connection is graph
via ropc though"):

- as you: azure-identity's DefaultAzureCredential (the Azure command line's sign-in, else a browser);
- a managed identity: Azure's own local request (a Function App, App Service or VM);
- an app registration whose client secret is a key vault's secret, never typed into the app;
- a username and password (ROPC, the resource owner password credentials grant), with or without the
  app registration's client secret: MSAL's acquire_token_by_username_password when msal is installed,
  else the same POST with the standard library. The password comes from where every password comes from
  (the keyring, a key vault, an environment variable): never in the connection's file or the library.

Each defines `sign_in(scope)`: the token Microsoft gave for that scope, and when it runs out. The
connection keeps it in memory only and signs in again five minutes before it runs out; it is never
written down or logged. Entra's refusals are said in plain words by their codes (AADSTS50126 a wrong
username or password, AADSTS50076/50079 an account that needs MFA, AADSTS7000218 an app registration that
needs public client flows or its secret, AADSTS65001 consent missing for the Graph permissions).

Two environment variables move the sign-in elsewhere (in the tests, to a stand-in on this computer):
SWISSARMYBENCH_LOGIN_URL (Microsoft's sign-in), and the managed identity's own IDENTITY_ENDPOINT and
IDENTITY_HEADER, which Azure sets.

This file is text. Pure: no I/O.
"""

from __future__ import annotations

GRAPH_SCOPE: str = "https://graph.microsoft.com/.default"
STORAGE_SCOPE: str = "https://storage.azure.com/.default"

# The marks each way's code alone holds (the form's Sign in tells them apart by these).
YOU_MARK: str = "DefaultAzureCredential"
MANAGED_MARK: str = "IDENTITY_HEADER"
APP_MARK: str = "# Sign in as an app registration"
ROPC_MARK: str = "# A public app registration"
ROPC_SECRET_MARK: str = "# The app registration's client secret too"  # noqa: S105 (a mark in code, not a secret)
MFA_MARK: str = "class MultiFactorSignIn"
# The multi-factor way's name, as the form and the refusals say it (the owner, 2026-11-20: "the dataverse
# connection didnt support mfa with user and password").
MFA_LABEL: str = "Username, with multi-factor sign-in (a browser window, or a code on another device)"
# Said on the form beside every username-and-password way (ROPC; SQL Server's Entra password): Microsoft's
# protocol for them has no step for a second factor.
NO_MFA_NOTE: str = f"This sign-in cannot do multi-factor sign-in: for an account with MFA pick {MFA_LABEL}."

IMPORTS: str = """import base64
import datetime
import hashlib
import hmac
import importlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
"""

YOU: str = '''
# Sign in as yourself: the Azure command line's sign-in (az login), else a browser window. In Azure (a
# Function App), the app's own managed identity.
from azure.identity import DefaultAzureCredential

credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)


def sign_in(scope):
    """The token Microsoft gave for this scope, and when it runs out."""
    found = credential.get_token(scope)
    return found.token, found.expires_on
'''

MANAGED: str = '''
# Sign in as the managed identity of the Azure app this runs in (a Function App, App Service or VM). A
# user-assigned identity: its client id here.
managed_client_id = ""


def sign_in(scope):
    """The managed identity's token for this scope (Azure's own local request), and when it runs out."""
    query = {"resource": scope.removesuffix("/.default")}
    if managed_client_id:
        query["client_id"] = managed_client_id
    endpoint, header = os.environ.get("IDENTITY_ENDPOINT"), os.environ.get("IDENTITY_HEADER")
    if endpoint and header:  # a Function App or App Service
        address = f"{endpoint}?api-version=2019-08-01&{urllib.parse.urlencode(query)}"
        headers, wait = {"X-IDENTITY-HEADER": header}, 30
    else:  # a virtual machine: its metadata service
        address = "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&"
        address += urllib.parse.urlencode(query)
        headers, wait = {"Metadata": "true"}, 2
    answer = ask(address, None, headers, "The managed identity's sign-in", wait, direct=True)
    return answer["access_token"], float(answer.get("expires_on") or time.time() + 3600)
'''

# A username signed in by multi-factor sign-in: one class the five kinds, Dataverse and SQL Server share.
# Its methods import what they use (azure-identity by name), so it is pasted into any connection's code.
MFA_CLASS: str = '''

class MultiFactorSignIn:
    """Signed in as `username` by Microsoft's multi-factor sign-in: a browser window (azure-identity's
    InteractiveBrowserCredential, the username filled in), or, where no browser can open, a code typed on
    another device (DeviceCodeCredential). The tokens go into the system's own encrypted token cache and the
    account is remembered (its ids and name, never a token: ~/.IdentityService/swissarmybench-*.json), so a
    later run signs in silently and asks for MFA again only when Microsoft wants it. get_token(scope) is
    azure-identity's own: the token, and when it runs out."""

    def __init__(self, tenant_id, username):
        self.tenant_id, self.username, self.credential = tenant_id or "organizations", username, None

    def record_file(self):
        import hashlib
        import os

        name = hashlib.sha256(f"{self.tenant_id}|{self.username}".lower().encode()).hexdigest()[:16]
        return os.path.join(os.path.expanduser("~"), ".IdentityService", f"swissarmybench-{name}.json")

    def made(self, kind, cached):
        import importlib

        identity = importlib.import_module("azure.identity")
        options = {"tenant_id": self.tenant_id}
        if kind == "browser" and self.username:
            options["login_hint"] = self.username
        if cached:  # the system's encrypted cache (Windows, the macOS keychain, the Linux keyring)
            options["cache_persistence_options"] = identity.TokenCachePersistenceOptions(name="swissarmybench")
            try:
                with open(self.record_file(), encoding="utf-8") as file:
                    options["authentication_record"] = identity.AuthenticationRecord.deserialize(file.read())
            except (OSError, ValueError, KeyError):
                pass
        made = identity.InteractiveBrowserCredential if kind == "browser" else identity.DeviceCodeCredential
        return made(**options), "authentication_record" in options

    def keep(self, record):
        import os

        try:
            path = self.record_file()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                file.write(record.serialize())
        except OSError:  # not remembered: the next run asks again
            pass

    def get_token(self, *scopes, **options):
        import importlib

        if self.credential is not None:
            return self.credential.get_token(*scopes, **options)
        unavailable = importlib.import_module("azure.identity").CredentialUnavailableError
        for kind in ("browser", "device code"):
            for cached in (True, False):  # no encrypted cache here: this run's memory only
                try:
                    credential, known = self.made(kind, cached)
                    if not known:
                        record = credential.authenticate(scopes=list(scopes))
                        if cached:
                            self.keep(record)
                    found = credential.get_token(*scopes, **options)
                except unavailable:
                    break  # no browser opens here: a code typed on another device instead
                except (ValueError, ImportError, NotImplementedError):  # no encrypted cache can be had here
                    if cached:
                        continue
                    raise
                self.credential = credential
                return found
        raise RuntimeError("Multi-factor sign-in could not open a browser or show a code here.")
'''

MFA: str = (
    """
# Sign in as yourself with multi-factor sign-in: a browser window opens with your username filled in (or,
# where none can, a code to type on another device). Remembered afterwards: MFA again only when Microsoft
# asks for it. A username and password (ROPC) cannot do MFA; this can.
tenant_id = "my-tenant-id"
username = "my-user@my-company.com"
"""
    + MFA_CLASS
    + '''
mfa = MultiFactorSignIn(tenant_id, username)


def sign_in(scope):
    """The token Microsoft gave for this scope, and when it runs out."""
    found = mfa.get_token(scope)
    return found.token, found.expires_on
'''
)

_REQUEST = '''

def token_request(form, what):
    """Microsoft's token endpoint for the tenant: the token, and when it runs out."""
    login = os.environ.get("SWISSARMYBENCH_LOGIN_URL", "https://login.microsoftonline.com")
    sent = urllib.parse.urlencode(form).encode()
    answer = ask(f"{login}/{tenant_id}/oauth2/v2.0/token", sent, {}, what)
    return answer["access_token"], time.time() + int(answer.get("expires_in", 3600))
'''

APP: str = (
    '''
# Sign in as an app registration (service principal). Its client secret is a key vault's secret, read by
# name: never typed here.
tenant_id = "my-tenant-id"
client_id = "my-client-id"
client_secret = secret("client secret")


def sign_in(scope):
    """Microsoft's client credentials request."""
    form = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
    return token_request(form | {"scope": scope}, "The sign-in")
'''
    + _REQUEST
)


def _ropc(confidential: bool) -> str:
    secret_line = 'client_secret = secret("client secret")\n' if confidential else ""
    form_secret = ', "client_secret": client_secret' if confidential else ""
    msal_app = (
        "msal.ConfidentialClientApplication(client_id, client_credential=client_secret, authority=authority)"
        if confidential
        else "msal.PublicClientApplication(client_id, authority=authority)"
    )
    comment = (
        "# The app registration's client secret too (a confidential app registration): from a key vault.\n"
        if confidential
        else "# A public app registration: its Authentication page allows public client flows.\n"
    )
    return (
        f'''
# Sign in with a username and password (ROPC: the resource owner password credentials grant). The
# password comes from the keyring, a key vault or an environment variable: never typed into the code.
# ROPC cannot do multi-factor sign-in: an account with MFA picks "Username, with multi-factor sign-in".
{comment}tenant_id = "my-tenant-id"
client_id = "my-client-id"
username = "my-user@my-company.com"
password = secret("password")
{secret_line}

def sign_in(scope):
    """The token for this scope, by the username and password: MSAL when it is installed, else the same
    request with the standard library."""
    form = {{"grant_type": "password", "client_id": client_id{form_secret}}}
    form |= {{"scope": scope, "username": username, "password": password}}
    if os.environ.get("SWISSARMYBENCH_LOGIN_URL"):  # a stand-in's sign-in: MSAL would look for Microsoft's
        return token_request(form, "The sign-in")
    try:
        msal = importlib.import_module("msal")
    except ImportError:
        return token_request(form, "The sign-in")
    authority = f"https://login.microsoftonline.com/{{tenant_id}}"
    app = {msal_app}
    found = app.acquire_token_by_username_password(username, password, scopes=[scope])
    if "access_token" not in found:
        raise AzureError(why("The sign-in", 400, json.dumps(found).encode()))
    return found["access_token"], time.time() + int(found.get("expires_in", 3600))
'''
        + _REQUEST
    )


ROPC: str = _ropc(False)
ROPC_SECRET: str = _ropc(True)

# What every way shares: one web request, and a refusal in plain words.
COMMON: str = r'''

class AzureError(RuntimeError):
    """The sign-in or the service refused. The message is its own words, and what usually causes it."""


ENTRA_WORDS = {
    "AADSTS50126": "Microsoft Entra refused the username or password (AADSTS50126): check them.",
    "AADSTS50076": "The account needs multi-factor sign-in (AADSTS50076): a username and password sign-in "
    "(ROPC) cannot do MFA. Pick the sign-in 'MFA_LABEL' instead, or an app registration.",
    "AADSTS50079": "The account must set up multi-factor sign-in (AADSTS50079): a username and password "
    "sign-in (ROPC) cannot do MFA. Pick the sign-in 'MFA_LABEL' instead, or an app registration.",
    "AADSTS7000218": "The app registration needs \"Allow public client flows\" turned on (its "
    "Authentication page, Advanced settings), or sign in with its client secret too (AADSTS7000218).",
    "AADSTS65001": "Consent is missing for the Microsoft Graph permissions this connection uses: "
    "Sites.Read.All (Sites.ReadWrite.All to write), Files.Read.All (Files.ReadWrite.All to upload). An "
    "admin grants them on the app registration's API permissions page (AADSTS65001).",
    "AADSTS700016": "Microsoft Entra does not know that client id in this tenant (AADSTS700016): check the "
    "tenant and the client id.",
    "AADSTS90002": "Microsoft Entra does not know that tenant (AADSTS90002): check the tenant's id or domain.",
    "AADSTS7000215": "Microsoft Entra refused the client secret (AADSTS7000215): it is wrong or has expired.",
}


def ask(address, data, headers, what, wait=120, direct=False, raw=False, method=None):
    """One web request (with `data`, a POST unless `method` says; without, a GET): its JSON answer, or
    with `raw` its bytes and headers. `direct`: a local endpoint (the managed identity's), reached without
    a proxy."""
    request = urllib.request.Request(address, data, headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if direct else None
    try:
        with (opener.open if opener else urllib.request.urlopen)(request, timeout=wait) as answer:
            body = answer.read()
            if raw:
                return body, dict(answer.headers)
            return json.loads(body or b"{}")
    except urllib.error.HTTPError as refused:
        raise AzureError(why(what, refused.code, refused.read(), refused.headers)) from None
    except (urllib.error.URLError, TimeoutError) as error:
        host = urllib.parse.urlsplit(address).netloc
        reason = getattr(error, "reason", error)
        more = " A managed identity signs in only inside Azure." if direct else ""
        raise AzureError(f"{what} could not reach {host}: {reason}.{more}") from None


def why(what, status, body, headers=None):
    """A refusal in plain words: Entra's code's words when it gave one, else the service's own message,
    then what usually causes that status."""
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    for code, words in ENTRA_WORDS.items():
        if code in text:
            return f"{what} was refused: {words}"
    try:
        said = json.loads(text)
        error = said.get("error_description") or said.get("error") or said
    except (ValueError, AttributeError):
        found = re.search(r"<Message>(.*?)</Message>", text, re.S)
        error = found.group(1) if found else text[:300]
    if isinstance(error, dict):
        error = error.get("message") or error.get("code") or "no reason"
    if headers is not None and headers.get("x-ms-error-code"):
        error = f"{headers.get('x-ms-error-code')}: {error}"
    hints = {
        401: "Check the sign-in: an app registration's tenant, client id and secret, the username and "
        "password, or that you are signed in (az login).",
        403: "The sign-in worked, but it may not read this: it needs a role on the storage account or "
        "workspace (Storage Blob Data Reader, a workspace's Viewer), or the Graph permissions.",
        404: "Check the address, the container or workspace, and the path.",
        429: "The service limits how many requests one sign-in makes: wait a minute.",
    }
    first = str(error).strip().splitlines()[0] if str(error).strip() else "no reason"
    first = re.sub(r"(sig|password|client_secret)=[^&\s'\"]+", r"\1=****", first)
    return f"{what} was refused ({status}): {first} {hints.get(status, '')}".strip()


class Token:
    """A token for one scope, kept in memory only: signed in again five minutes before it runs out."""

    def __init__(self, sign_in, scope):
        self.sign_in, self.scope, self.value, self.expires = sign_in, scope, "", 0.0

    def __call__(self):
        if time.time() > self.expires - 300:
            self.value, self.expires = self.sign_in(self.scope)
        return self.value

    def __repr__(self):
        return f"Token({self.scope!r})"
'''

COMMON = COMMON.replace("MFA_LABEL", MFA_LABEL)

# The form's Sign in: (label, a text only that way's code holds, its sign-in text).
SIGN_INS: tuple[tuple[str, str, str], ...] = (
    ("As you (Azure command line or browser)", YOU_MARK, YOU),
    ("Managed identity (in Azure: a Function App, App Service or VM)", MANAGED_MARK, MANAGED),
    ("App registration, its secret from a key vault", APP_MARK, APP),
)
# Beside the username-and-password ways: multi-factor sign-in, for an account ROPC cannot sign in (MFA).
MFA_SIGN_IN: tuple[str, str, str] = (MFA_LABEL, MFA_MARK, MFA)
# SharePoint offers the username and password first (the owner's own SharePoint connection).
ROPC_SIGN_INS: tuple[tuple[str, str, str], ...] = (
    ("Username and password (ROPC)", ROPC_MARK, ROPC),
    ("Username and password, with the app's client secret (ROPC)", ROPC_SECRET_MARK, ROPC_SECRET),
    MFA_SIGN_IN,
)
# The ways a username and password sign in by: each says on the form that it cannot do MFA (NO_MFA_NOTE).
NO_MFA_MARKS: tuple[str, ...] = (ROPC_MARK, ROPC_SECRET_MARK)
