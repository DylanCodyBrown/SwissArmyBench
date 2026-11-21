"""Microsoft's devtunnel command line stood in for (SWISSARMYBENCH_DEVTUNNEL_STANDIN names this file).

The app "downloads" this file's bytes into its state folder and runs that copy with its own Python; its state
(the signed-in user, the tunnels, every command line asked) is beside the copy, in standin.json and calls.log.
Nothing leaves the computer: host prints the lines the real one prints (a made-up tunnel id and region) and
waits until it is stopped. Made-up names only.

SAB_STANDIN_MODE in the environment changes it: "policy" (host refuses as a tenant policy would),
"personal" (the sign-in is a personal Microsoft account), "anonymous" (the made tunnel allows anonymous).
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
STATE = HERE / "standin.json"
CALLS = HERE / "calls.log"
TENANT = "00000000-0000-4000-8000-00000000c0de"  # made up
ACCOUNT = "dana.lee@contoso-made-up.example"
MODE = os.environ.get("SAB_STANDIN_MODE", "")


def _state() -> dict[str, Any]:
    try:
        found: dict[str, Any] = json.loads(STATE.read_text(encoding="utf-8"))
        return found
    except (OSError, ValueError):
        return {"user": None, "tunnels": {}}


def _save(state: dict[str, Any]) -> None:
    STATE.write_text(json.dumps(state), encoding="utf-8")


def _say(value: object) -> None:
    print(json.dumps(value, indent=2), flush=True)


def _arg(args: list[str], name: str) -> str | None:
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else None


def main(args: list[str]) -> int:
    with CALLS.open("a", encoding="utf-8") as log:
        log.write(json.dumps(args) + "\n")
    state = _state()
    if args[:2] == ["user", "login"]:
        if "--use-device-code-auth" in args:
            print(
                "To sign in, use a web browser to open the page https://microsoft.com/devicelogin and enter "
                "the code MADEUP42 to authenticate.",
                flush=True,
            )
        time.sleep(float(os.environ.get("SAB_STANDIN_LOGIN_SECONDS", "0.6")))
        tenant = "9188040d-6c67-4c5b-b112-36a304b66dad" if MODE == "personal" else TENANT
        state["user"] = {"username": ACCOUNT, "provider": "microsoft", "tenantId": tenant}
        _save(state)
        print(f"Logged in as {ACCOUNT} using Microsoft.", flush=True)
        return 0
    if args[:2] == ["user", "show"]:
        user = state.get("user")
        if not user:
            _say({"status": "Not logged in"})
        else:
            _say({"status": f"Logged in as {user['username']} using Microsoft."} | user)
        return 0
    if not state.get("user"):
        print("Not logged in. Run 'devtunnel user login'.", flush=True)
        return 1
    tunnels: dict[str, Any] = state["tunnels"]
    if args[0] == "list":
        _say({"tunnels": [{"tunnelId": t, "clusterId": "usw2"} for t in tunnels]})
        return 0
    if args[0] == "create":
        if set(args) & {"-a", "--allow-anonymous"}:
            print("standin: anonymous asked for", flush=True)
            return 3
        tunnel = f"made-up-{secrets.token_hex(3)}"
        aces = [{"type": "Anonymous", "subjects": [], "scopes": ["connect"]}] if MODE == "anonymous" else []
        tunnels[tunnel] = {"access": aces, "ports": []}
        _save(state)
        _say({"tunnel": {"tunnelId": tunnel, "clusterId": "usw2", "labels": [_arg(args, "--labels")]}})
        return 0
    tunnel = args[2].split(".")[0] if args[0] in ("access", "port") else args[1].split(".")[0]
    if tunnel not in tunnels:
        print(f"Tunnel not found: {tunnel}", flush=True)
        return 2
    held = tunnels[tunnel]
    if args[:2] == ["access", "create"]:
        if "--tenant" in args:
            held["access"].append({"type": "Organizations", "provider": "microsoft", "subjects": [TENANT]})
        _save(state)
        _say({"accessControlEntry": held["access"][-1] if held["access"] else None})
        return 0
    if args[:2] == ["access", "list"]:
        _say({"accessControlEntries": held["access"]})
        return 0
    if args[:2] == ["port", "create"]:
        held["ports"].append(int(_arg(args, "--port-number") or 0))
        _save(state)
        _say({"port": {"portNumber": held["ports"][-1], "protocol": _arg(args, "--protocol")}})
        return 0
    if args[0] == "delete":
        tunnels.pop(tunnel, None)
        _save(state)
        _say({"deleted": tunnel})
        return 0
    if args[0] == "host":
        print(
            f"Connecting to host tunnel relay wss://usw2-data.rel.tunnels.api.visualstudio.com/{tunnel}",
            flush=True,
        )
        if MODE == "policy":
            print("Tunnel service error: Forbidden. Access denied by your organization's policy.", flush=True)
            return 4
        for port in held["ports"]:
            print(
                f"Hosting port: {port} at https://{tunnel}-{port}.usw2.devtunnels.ms/ and inspect it at "
                f"https://{tunnel}-{port}-inspect.usw2.devtunnels.ms/",
                flush=True,
            )
        print(f"Ready to accept connections for tunnel: {tunnel}.usw2", flush=True)
        while True:
            time.sleep(1)
    print(f"standin: {args} not known", flush=True)
    return 9


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
