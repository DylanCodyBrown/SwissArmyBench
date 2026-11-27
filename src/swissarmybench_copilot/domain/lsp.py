"""The Copilot Language Server's protocol as data (github/copilot-language-server-release's README, read
2026-11-18 for version 1.572.0): the Language Server Protocol, JSON-RPC 2.0 over stdio with Content-Length
headers, plus Copilot's own messages.

  framing      encode(message) -> bytes; Reader.feed(bytes) -> the whole messages so far
  messages     request, notification, response, error; initialize's parameters (editorInfo,
               editorPluginInfo), the configuration (telemetry off), inline completion's parameters
  positions    LSP positions count UTF-16 code units: position_at(text, offset), offset_at(text, position)
  changes      one incremental change between two texts (the common start and end kept)
  answers      the inline completion items read (insertText, range, command); checkStatus's and signIn's
               answers in plain words (signed in as <login>, no subscription, not signed in)

Pure: standard library only, no I/O.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# The language server pinned (the extension's Install puts this exact version in the state folder).
PACKAGE: str = "@github/copilot-language-server"
PINNED: str = "1.572.0"
MINIMUM_NODE: tuple[int, ...] = (20, 8)  # its README: "Node.js version 20.8 or later"

# Its README's custom methods and commands.
SIGN_IN = "signIn"
SIGN_OUT = "signOut"
CHECK_STATUS = "checkStatus"
FINISH_DEVICE_FLOW = "github.copilot.finishDeviceFlow"
INLINE = "textDocument/inlineCompletion"
DID_SHOW = "textDocument/didShowCompletion"
DID_PARTIALLY_ACCEPT = "textDocument/didPartiallyAcceptCompletion"
DID_FOCUS = "textDocument/didFocus"
EXECUTE = "workspace/executeCommand"
CANCEL = "$/cancelRequest"
# JSON-RPC's and LSP's error codes the client reads.
REQUEST_CANCELLED = -32800
SERVER_CANCELLED = -32802
METHOD_NOT_FOUND = -32601

MAX_HEADER = 1024  # a header block longer than this is not the protocol's
MAX_BODY = 64 * 1024 * 1024
DEVICE_PAGE = "https://github.com/login/device"


class LspError(Exception):
    """The server answered a request with an error."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


class ServerGone(Exception):
    """The server's process ended (or never started)."""


class FramingError(ValueError):
    """Bytes on the server's stdout that are not the base protocol."""


def encode(message: dict[str, Any]) -> bytes:
    """One message with its header: `Content-Length: N\\r\\n\\r\\n` then N bytes of UTF-8 JSON."""
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body


@dataclass
class Reader:
    """Messages taken from a byte stream as they complete (a message may arrive in pieces, or several at
    once). Content-Type, when there, is ignored (the protocol's default is UTF-8 JSON)."""

    buffer: bytes = b""

    def feed(self, data: bytes) -> list[dict[str, Any]]:
        self.buffer += data
        out: list[dict[str, Any]] = []
        while True:
            end = self.buffer.find(b"\r\n\r\n")
            if end < 0:
                if len(self.buffer) > MAX_HEADER and b"Content-Length" not in self.buffer[:MAX_HEADER]:
                    raise FramingError("No Content-Length header.")
                return out
            if end > MAX_HEADER:
                raise FramingError("The header block is too long.")
            length = None
            for line in self.buffer[:end].split(b"\r\n"):
                name, _, value = line.partition(b":")
                if name.strip().lower() == b"content-length":
                    try:
                        length = int(value.strip())
                    except ValueError:
                        raise FramingError("Content-Length is not a number.") from None
            if length is None or length < 0 or length > MAX_BODY:
                raise FramingError("No usable Content-Length header.")
            start = end + 4
            if len(self.buffer) < start + length:
                return out
            body = self.buffer[start : start + length]
            self.buffer = self.buffer[start + length :]
            try:
                message = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise FramingError("A message's body is not JSON.") from None
            if isinstance(message, dict):
                out.append(message)


def request(ident: int, method: str, params: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": ident, "method": method, "params": params}


def notification(method: str, params: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "method": method, "params": params}


def response(ident: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": ident, "result": result}


def error(ident: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": ident, "error": {"code": code, "message": message}}


def kind_of(message: dict[str, Any]) -> str:
    """ "response", "request" (the server asks the client) or "notification"."""
    if "method" in message:
        return "request" if "id" in message else "notification"
    return "response"


# ===== the session's opening =====


def initialize_params(process_id: int, app_version: str, plugin_version: str) -> dict[str, Any]:
    """`initialize`'s parameters as the README gives them. No workspace folders: only the document being
    edited is the server's to read. window.showDocument: the device flow's page is the page's to open (on
    the user's click), so the client answers it without opening anything."""
    return {
        "processId": process_id,
        "clientInfo": {"name": "Swiss Army Bench", "version": app_version},
        "capabilities": {
            "workspace": {"workspaceFolders": False, "configuration": True},
            "window": {"showDocument": {"support": True}},
            "textDocument": {"inlineCompletion": {"dynamicRegistration": False}},
        },
        "initializationOptions": {
            "editorInfo": {"name": "Swiss Army Bench", "version": app_version},
            "editorPluginInfo": {"name": "Swiss Army Bench GitHub Copilot", "version": plugin_version},
        },
    }


# The configuration the client sends after `initialized`, and answers `workspace/configuration` with:
# telemetry off (the server turns it on only for "all").
SETTINGS: dict[str, Any] = {"telemetry": {"telemetryLevel": "off"}}


def configuration() -> dict[str, Any]:
    return {"settings": SETTINGS}


def configuration_answer(params: Any) -> list[Any]:
    """`workspace/configuration`'s answer: one value per item asked, by its section."""
    items = params.get("items") if isinstance(params, dict) else None
    out: list[Any] = []
    for item in items if isinstance(items, list) else []:
        section = item.get("section") if isinstance(item, dict) else None
        if not section:
            out.append(SETTINGS)
            continue
        value: Any = SETTINGS
        for part in str(section).split("."):
            value = value.get(part) if isinstance(value, dict) else None
        out.append(value)
    return out


# ===== positions: UTF-16 code units, as LSP counts them =====


def _units(char: str) -> int:
    return 2 if ord(char) > 0xFFFF else 1


def position_at(text: str, offset: int) -> dict[str, int]:
    """The {line, character} of a code-point offset in `text` (character in UTF-16 code units)."""
    offset = max(0, min(offset, len(text)))
    line = text.count("\n", 0, offset)
    start = text.rfind("\n", 0, offset) + 1
    return {"line": line, "character": sum(_units(c) for c in text[start:offset])}


def offset_at(text: str, position: dict[str, Any]) -> int:
    """The code-point offset of an LSP position (clamped to the text)."""
    line = int(position.get("line", 0))
    units = int(position.get("character", 0))
    start = 0
    for _ in range(max(0, line)):
        found = text.find("\n", start)
        if found < 0:
            return len(text)
        start = found + 1
    end = text.find("\n", start)
    end = len(text) if end < 0 else end
    at = start
    while at < end and units > 0:
        units -= _units(text[at])
        at += 1
    return at


def change_between(old: str, new: str) -> dict[str, Any] | None:
    """One incremental change turning `old` into `new` (the common start and end kept); None: the same."""
    if old == new:
        return None
    start = 0
    limit = min(len(old), len(new))
    while start < limit and old[start] == new[start]:
        start += 1
    end_old, end_new = len(old), len(new)
    while end_old > start and end_new > start and old[end_old - 1] == new[end_new - 1]:
        end_old -= 1
        end_new -= 1
    return {
        "range": {"start": position_at(old, start), "end": position_at(old, end_old)},
        "text": new[start:end_new],
    }


# ===== inline completions =====


def inline_params(
    uri: str, version: int, position: dict[str, int], tab_size: int = 4, insert_spaces: bool = True
) -> dict[str, Any]:
    """`textDocument/inlineCompletion`'s parameters, with the README's additions (the version and the
    formatting options). triggerKind 2: automatic (as typing goes)."""
    return {
        "textDocument": {"uri": uri, "version": version},
        "position": position,
        "context": {"triggerKind": 2},
        "formattingOptions": {"tabSize": tab_size, "insertSpaces": insert_spaces},
    }


def _range(raw: Any) -> dict[str, dict[str, int]] | None:
    if not isinstance(raw, dict):
        return None
    out: dict[str, dict[str, int]] = {}
    for end in ("start", "end"):
        point = raw.get(end)
        if not isinstance(point, dict):
            return None
        line, character = point.get("line"), point.get("character")
        if not isinstance(line, int) or not isinstance(character, int) or line < 0 or character < 0:
            return None
        out[end] = {"line": line, "character": character}
    return out


def items_of(result: Any, limit: int = 10) -> list[dict[str, Any]]:
    """The answer's items, each {text, range, command, raw}: `raw` is the item as the server sent it (the
    shown and partial-accept notifications carry it back whole); a newline is "\\n" in the editor."""
    items = result.get("items") if isinstance(result, dict) else result if isinstance(result, list) else []
    out: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        text = item.get("insertText")
        if isinstance(text, dict):  # a snippet's text: shown as it reads
            text = text.get("value")
        if not isinstance(text, str) or not text:
            continue
        command = item.get("command")
        out.append(
            {
                "text": text.replace("\r\n", "\n"),
                "range": _range(item.get("range")),
                "command": command if isinstance(command, dict) and command.get("command") else None,
                "raw": item,
            }
        )
        if len(out) >= limit:
            break
    return out


# ===== signing in, in plain words =====

SIGNED_IN = ("OK", "MaybeOK", "AlreadySignedIn")


def account_of(answer: Any) -> dict[str, Any]:
    """checkStatus's (or signIn's, signInConfirm's) answer: {"state", "user"}. state: signed_in,
    no_subscription (NotAuthorized: signed in to GitHub, no Copilot plan), not_signed_in."""
    said = answer if isinstance(answer, dict) else {}
    status = str(said.get("status") or "")
    user = said.get("user")
    login = str(user)[:100] if isinstance(user, str) and user else None
    if status in SIGNED_IN:
        return {"state": "signed_in", "user": login}
    if status == "NotAuthorized":
        return {"state": "no_subscription", "user": login}
    return {"state": "not_signed_in", "user": None}


def device_flow_of(answer: Any) -> dict[str, Any] | None:
    """signIn's device flow: {"code", "link"} (the page shows the code; github.com/login/device is opened on
    the user's click). None: no device flow asked (already signed in, or an answer this does not read). A
    link that is not https is replaced by GitHub's own device page."""
    said = answer if isinstance(answer, dict) else {}
    code = said.get("userCode")
    if said.get("status") != "PromptUserDeviceFlow" or not isinstance(code, str) or not code.strip():
        return None
    link = said.get("verificationUri")
    if not isinstance(link, str) or not link.startswith("https://"):
        link = DEVICE_PAGE
    return {"code": code.strip()[:40], "link": link[:300]}
