"""The agent's variables_* commands: settings and secrets (the Environment's tab): this computer's variables, sources, uses.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import _q, command, opt, req


@command(
    "variables_list",
    "Every variable: its source (vault, value, keyring, env, missing), what uses it, a plain value's "
    "value; a keyring's, a secret's or a vault's value never",
    opt("search", "A name, vault, connection or document."),
    opt("source", "vault, value, keyring, env or missing."),
)
def variables_list(a: dict[str, Any]) -> Any:
    return api.call("GET", "/variables", params={k: a.get(k) for k in ("search", "source")})


@command(
    "variables_set",
    "Add or change a variable; kept=keyring keeps a secret in this computer's keyring (never read back)",
    req("name", "SALES_REGION"),
    opt("value", "Its value (a keyring one: empty keeps the saved one)."),
    opt("kept", "value (default) or keyring."),
    opt("local", "A plain value kept on this computer only (never shared).", "bool"),
)
def variables_set(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("name", "value", "local") if a.get(k) is not None}
    return api.call("PUT", "/variables", body | ({"from": a["kept"]} if a.get("kept") else {}))


@command(
    "variables_rename",
    "Rename a variable: connections' code and Run settings follow; notebooks still reading it are listed",
    req("name", "The old name."),
    req("to", "The new name."),
)
def variables_rename(a: dict[str, Any]) -> Any:
    return api.call("POST", "/variables/rename", {"name": a["name"], "to": a["to"]})


@command(
    "variables_remove",
    "Remove a variable (or a key vault's entry; the secret stays in the vault); what still reads it",
    req("name", "The variable."),
)
def variables_remove(a: dict[str, Any]) -> Any:
    return api.call("DELETE", f"/variables/{_q(a['name'])}")


@command(
    "variables_resolve",
    "A box's ${NAME} as read here (a secret masked); names not set",
    req("text", "https://${TENANT}.x.com, ${PORT:-5432}; $${X}: the text."),
)
def variables_resolve(a: dict[str, Any]) -> Any:
    return api.call("POST", "/variables/resolve", {"text": a["text"]})


@command(
    "variables_uses",
    "What reads each variable: connections' fields, code, Run settings",
    opt("name", "One variable."),
)
def variables_uses(a: dict[str, Any]) -> Any:
    return api.call("GET", "/variables/uses", params={"name": a.get("name")})
