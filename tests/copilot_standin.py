"""A stand-in for GitHub's Copilot Language Server: a small stdio server speaking the messages its README
documents (Content-Length framing, initialize, initialized, workspace/didChangeConfiguration, didOpen,
didChange, didClose and didFocus, notebookDocument/*, checkStatus, signIn and the device flow's
github.copilot.finishDeviceFlow (with window/showDocument asked of the client), signOut,
textDocument/inlineCompletion with $/cancelRequest, didShowCompletion, didPartiallyAcceptCompletion,
workspace/executeCommand for the accept command, shutdown and exit). Its suggestions are made up.

The real server needs a GitHub Copilot plan, so the tests never run it (docs/verified.md).

Environment:
  COPILOT_STANDIN_LOG    a file each message received is appended to, one JSON object a line
  COPILOT_STANDIN_STATE  a JSON file: {"user": "<login>"} signed in, {"user": ..., "plan": false} no plan
  COPILOT_STANDIN_DELAY  seconds before an inline completion is answered (to cancel one)
Standard library only; it shares no code with the client it stands in for.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Any

LOG = os.environ.get("COPILOT_STANDIN_LOG", "")
STATE = os.environ.get("COPILOT_STANDIN_STATE", "")
DELAY = float(os.environ.get("COPILOT_STANDIN_DELAY", "0") or 0)
CODE = "MADE-UP1"
DEVICE_PAGE = "https://github.com/login/device"
# Made-up suggestions: the line's text before the cursor (stripped) -> what follows it.
SUGGESTIONS = {
    "def total_by_region(orders):": "\n    return orders.groupby('region')['amount'].sum()",
    "SELECT region,": " sum(amount) AS total FROM orders GROUP BY region",
    "import pan": "das as pd",
}
DEFAULT = "print('made-up suggestion')"

out_lock = threading.Lock()
documents: dict[str, str] = {}
cancelled: set[Any] = set()


def log(message: dict[str, Any]) -> None:
    if LOG:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(message) + "\n")


def send(message: dict[str, Any]) -> None:
    body = json.dumps(message).encode("utf-8")
    with out_lock:
        sys.stdout.buffer.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        sys.stdout.buffer.flush()


def read() -> dict[str, Any] | None:
    length = None
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        name, _, value = line.decode("ascii").partition(":")
        if name.strip().lower() == "content-length":
            length = int(value.strip())
    assert length is not None
    message: dict[str, Any] = json.loads(sys.stdin.buffer.read(length).decode("utf-8"))
    return message


def account() -> dict[str, Any]:
    if STATE and os.path.exists(STATE):
        said = json.load(open(STATE, encoding="utf-8"))
        if said.get("user"):
            return {"status": "OK" if said.get("plan", True) else "NotAuthorized", "user": said["user"]}
    return {"status": "NotSignedIn"}


def save(state: dict[str, Any] | None) -> None:
    if not STATE:
        return
    if state is None:
        if os.path.exists(STATE):
            os.remove(STATE)
        return
    json.dump(state, open(STATE, "w", encoding="utf-8"))


def offset(text: str, p: dict[str, int]) -> int:
    return sum(len(x) + 1 for x in text.split("\n")[: p["line"]]) + p["character"]


def apply(uri: str, changes: list[dict[str, Any]]) -> None:
    text = documents.get(uri, "")
    for change in changes:
        if "range" not in change:
            text = change["text"]
            continue
        start, end = offset(text, change["range"]["start"]), offset(text, change["range"]["end"])
        text = text[:start] + change["text"] + text[end:]
    documents[uri] = text


asked: dict[Any, threading.Event] = {}
answers: dict[Any, Any] = {}
ids = iter(range(1000, 10**9))


def ask_client(method: str, params: Any) -> Any:
    ident = next(ids)
    done = threading.Event()
    asked[ident] = done
    send({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
    done.wait(10)
    return answers.pop(ident, None)


def complete(ident: Any, params: dict[str, Any]) -> None:
    if DELAY:
        time.sleep(DELAY)
    if ident in cancelled:
        send({"jsonrpc": "2.0", "id": ident, "error": {"code": -32800, "message": "Request cancelled"}})
        return
    uri = params["textDocument"]["uri"]
    if account()["status"] != "OK" or uri not in documents:
        send({"jsonrpc": "2.0", "id": ident, "result": {"items": []}})
        return
    line_no, character = params["position"]["line"], params["position"]["character"]
    lines = documents[uri].split("\n")
    before = lines[line_no][:character] if line_no < len(lines) else ""
    text = SUGGESTIONS.get(before.strip(), DEFAULT if not before.strip() else "")
    items = []
    if text:
        point = {"line": line_no, "character": character}
        items = [
            {
                "insertText": text,
                "range": {"start": point, "end": point},
                "command": {
                    "command": "github.copilot.didAcceptCompletionItem",
                    "arguments": [f"made-up-{ident}"],
                },
            },
            {"insertText": text + "  # second", "range": {"start": point, "end": point}},
        ]
    send({"jsonrpc": "2.0", "id": ident, "result": {"items": items}})


def finish_device_flow(ident: Any) -> None:
    answer = ask_client("window/showDocument", {"uri": DEVICE_PAGE, "external": True})
    if not isinstance(answer, dict) or answer.get("success") is not True:
        send({"jsonrpc": "2.0", "id": ident, "error": {"code": 1001, "message": "The page was not opened"}})
        return
    save({"user": "made-up-octocat"})
    send({"jsonrpc": "2.0", "id": ident, "result": {"status": "OK", "user": "made-up-octocat"}})
    send(
        {
            "jsonrpc": "2.0",
            "method": "didChangeStatus",
            "params": {"kind": "Normal", "message": "", "busy": False},
        }
    )


def main() -> None:
    initialized = False
    while True:
        message = read()
        if message is None:
            return
        log(message)
        method, ident, params = message.get("method"), message.get("id"), message.get("params") or {}
        if method is None:  # an answer to what this asked
            answers[ident] = message.get("result")
            done = asked.pop(ident, None)
            if done is not None:
                done.set()
            continue
        if method == "initialize":
            send(
                {
                    "jsonrpc": "2.0",
                    "id": ident,
                    "result": {
                        "capabilities": {
                            "textDocumentSync": {"openClose": True, "change": 2},
                            "notebookDocumentSync": {"notebookSelector": [{"notebook": "*"}]},
                            "inlineCompletionProvider": {},
                        },
                        "serverInfo": {"name": "Copilot stand-in", "version": "0.0.0"},
                    },
                }
            )
        elif method == "initialized":
            initialized = True
            send(
                {
                    "jsonrpc": "2.0",
                    "method": "window/logMessage",
                    "params": {"type": 3, "message": "made-up log"},
                }
            )
            threading.Thread(
                target=ask_client,
                args=("workspace/configuration", {"items": [{"section": "telemetry"}]}),
                daemon=True,
            ).start()
        elif not initialized and ident is not None and method != "shutdown":
            send({"jsonrpc": "2.0", "id": ident, "error": {"code": -32002, "message": "Not initialized"}})
        elif method == "textDocument/didOpen":
            documents[params["textDocument"]["uri"]] = params["textDocument"]["text"]
        elif method == "textDocument/didChange":
            apply(params["textDocument"]["uri"], params["contentChanges"])
        elif method == "textDocument/didClose":
            documents.pop(params["textDocument"]["uri"], None)
        elif method == "notebookDocument/didOpen":
            for cell in params["cellTextDocuments"]:
                documents[cell["uri"]] = cell["text"]
        elif method == "notebookDocument/didChange":
            cells = params["change"].get("cells", {})
            structure = cells.get("structure") or {}
            for cell in structure.get("didOpen") or []:
                documents[cell["uri"]] = cell["text"]
            for cell in structure.get("didClose") or []:
                documents.pop(cell["uri"], None)
            for content in cells.get("textContent") or []:
                apply(content["document"]["uri"], content["changes"])
        elif method == "notebookDocument/didClose":
            for cell in params["cellTextDocuments"]:
                documents.pop(cell["uri"], None)
        elif method == "checkStatus":
            send({"jsonrpc": "2.0", "id": ident, "result": account()})
        elif method == "signIn":
            if account()["status"] == "OK":
                send(
                    {
                        "jsonrpc": "2.0",
                        "id": ident,
                        "result": {"status": "AlreadySignedIn", "user": account()["user"]},
                    }
                )
            else:
                result = {
                    "status": "PromptUserDeviceFlow",
                    "userCode": CODE,
                    "verificationUri": DEVICE_PAGE,
                    "expiresIn": 899,
                    "interval": 5,
                    "command": {
                        "command": "github.copilot.finishDeviceFlow",
                        "title": "Sign in with GitHub",
                        "arguments": [],
                    },
                }
                send({"jsonrpc": "2.0", "id": ident, "result": result})
        elif method == "signOut":
            save(None)
            send({"jsonrpc": "2.0", "id": ident, "result": {"status": "NotSignedIn"}})
        elif method == "workspace/executeCommand":
            if params.get("command") == "github.copilot.finishDeviceFlow":
                threading.Thread(target=finish_device_flow, args=(ident,), daemon=True).start()
            else:
                send({"jsonrpc": "2.0", "id": ident, "result": None})
        elif method == "textDocument/inlineCompletion":
            threading.Thread(target=complete, args=(ident, params), daemon=True).start()
        elif method == "$/cancelRequest":
            cancelled.add(params.get("id"))
        elif method == "shutdown":
            send({"jsonrpc": "2.0", "id": ident, "result": None})
        elif method == "exit":
            return
        elif ident is not None:
            send({"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": f"No {method} here"}})


if __name__ == "__main__":
    main()
