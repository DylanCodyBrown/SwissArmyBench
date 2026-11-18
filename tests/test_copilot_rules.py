"""The GitHub Copilot extension's rules: the protocol's framing and messages, UTF-16 positions, incremental
changes, the documents mirrored into the server, the answers read, the tools. Made-up text only."""

from __future__ import annotations

import json

import pytest

from swissarmybench_copilot.domain import documents, lsp, tools

# ===== framing =====


def test_a_message_is_its_length_then_its_json() -> None:
    framed = lsp.encode({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"name": "é"}})
    head, _, body = framed.partition(b"\r\n\r\n")
    assert head == b"Content-Length: " + str(len(body)).encode()
    assert json.loads(body)["params"]["name"] == "é"
    assert len(body) == len(body.decode("utf-8").encode("utf-8"))  # bytes, not characters


def test_the_reader_takes_messages_in_pieces_and_several_at_once() -> None:
    a = lsp.encode(lsp.request(1, "a", {}))
    b = lsp.encode(lsp.notification("b", {"text": "ünïcode"}))
    reader = lsp.Reader()
    assert reader.feed(a[:7]) == []
    assert reader.feed(a[7:-3]) == []
    rest = lsp.encode(lsp.response(1, None))
    got = reader.feed(a[-3:] + b + rest[:10])
    assert [m.get("method") for m in got] == ["a", "b"]
    assert reader.feed(rest[10:])[0]["id"] == 1
    # A Content-Type header beside the length is read past.
    with_type = rest.replace(
        b"\r\n\r\n", b"\r\nContent-Type: application/vscode-jsonrpc; charset=utf-8\r\n\r\n", 1
    )
    assert lsp.Reader().feed(with_type)[0]["id"] == 1


def test_bytes_that_are_not_the_protocol_are_refused() -> None:
    with pytest.raises(lsp.FramingError):
        lsp.Reader().feed(b"Content-Length: many\r\n\r\n{}")
    with pytest.raises(lsp.FramingError):
        lsp.Reader().feed(b"x" * 2000)
    with pytest.raises(lsp.FramingError):
        lsp.Reader().feed(b"Content-Length: 2\r\n\r\n{x")


def test_kinds_of_messages() -> None:
    assert lsp.kind_of(lsp.request(3, "window/showDocument", {})) == "request"
    assert lsp.kind_of(lsp.notification("didChangeStatus", {})) == "notification"
    assert lsp.kind_of(lsp.response(3, None)) == lsp.kind_of(lsp.error(3, 1, "no")) == "response"


# ===== the opening =====


def test_initialize_names_the_editor_and_no_folder() -> None:
    params = lsp.initialize_params(1234, "0.0.19", "0.0.19")
    assert params["processId"] == 1234
    assert params["initializationOptions"]["editorInfo"]["name"] == "Swiss Army Bench"
    assert params["initializationOptions"]["editorPluginInfo"]["version"] == "0.0.19"
    assert "workspaceFolders" not in params and "rootUri" not in params
    assert params["capabilities"]["window"]["showDocument"]["support"] is True


def test_telemetry_is_off_in_both_ways_the_server_reads_its_settings() -> None:
    assert lsp.configuration()["settings"]["telemetry"]["telemetryLevel"] == "off"
    answer = lsp.configuration_answer({"items": [{"section": "telemetry"}, {"section": "http.proxy"}, {}]})
    assert answer == [{"telemetryLevel": "off"}, None, lsp.SETTINGS]


# ===== positions and changes =====


def test_positions_count_utf16_units() -> None:
    text = "a = 1\nb = '😀x'\n"
    at = text.index("x")
    assert lsp.position_at(text, at) == {"line": 1, "character": 7}  # the emoji is two units
    assert lsp.offset_at(text, {"line": 1, "character": 7}) == at
    assert lsp.offset_at(text, {"line": 9, "character": 0}) == len(text)
    assert lsp.position_at(text, 0) == {"line": 0, "character": 0}


def test_one_incremental_change_keeps_the_common_start_and_end() -> None:
    assert lsp.change_between("same", "same") is None
    change = lsp.change_between("total = 1\nprint(total)\n", "total = 12\nprint(total)\n")
    assert change == {
        "range": {"start": {"line": 0, "character": 9}, "end": {"line": 0, "character": 9}},
        "text": "2",
    }
    removed = lsp.change_between("a\nbcd\ne", "a\ne")
    assert removed is not None and removed["text"] == ""
    assert removed["range"]["start"] == {"line": 1, "character": 0}


# ===== the documents mirrored =====


def test_a_script_is_opened_once_then_changed_incrementally() -> None:
    mirror = documents.Mirror()
    uri, version, sent = mirror.text("tab-1", "C:\\work\\load.py", "python", "import pan")
    assert uri == "file:///swissarmybench/tab-1/load.py" and version == 1
    assert [m["method"] for m in sent] == ["textDocument/didOpen"]
    assert sent[0]["params"]["textDocument"]["text"] == "import pan"
    _, version, sent = mirror.text("tab-1", "load.py", "python", "import pand")
    assert version == 2 and sent[0]["method"] == "textDocument/didChange"
    assert sent[0]["params"]["contentChanges"] == [
        {"range": {"start": {"line": 0, "character": 10}, "end": {"line": 0, "character": 10}}, "text": "d"}
    ]
    assert mirror.text("tab-1", "load.py", "python", "import pand")[2] == []


def test_a_notebook_is_sent_as_a_notebook_of_its_code_cells() -> None:
    mirror = documents.Mirror()
    cells = [
        {"id": 1, "text": "import duckdb", "language": "python"},
        {"id": 2, "text": "SELECT", "language": "sql"},
    ]
    uri, version, sent = mirror.notebook("nb", "sales.ipynb", cells, 2)
    assert uri.endswith("sales.ipynb#cell-2") and version == 1
    opened = sent[0]["params"]
    assert sent[0]["method"] == "notebookDocument/didOpen"
    assert opened["notebookDocument"]["notebookType"] == "jupyter-notebook"
    assert [c["languageId"] for c in opened["cellTextDocuments"]] == ["python", "sql"]
    # A cell's text changes: only its text content.
    cells[1]["text"] = "SELECT region,"
    _, version, sent = mirror.notebook("nb", "sales.ipynb", cells, 2)
    change = sent[0]["params"]["change"]["cells"]
    assert version == 2 and "structure" not in change
    assert change["textContent"][0]["changes"][0]["text"] == " region,"
    # A cell comes: the list again, the new one opened, nothing closed.
    cells.insert(1, {"id": 5, "text": "orders = 1", "language": "python"})
    _, _, sent = mirror.notebook("nb", "sales.ipynb", cells, 5)
    structure = sent[0]["params"]["change"]["cells"]["structure"]
    assert [c["document"][-1] for c in structure["array"]["cells"]] == ["1", "5", "2"]
    assert [d["uri"][-1] for d in structure["didOpen"]] == ["5"] and structure["didClose"] == []
    # One goes: closed.
    del cells[0]
    structure = mirror.notebook("nb", "sales.ipynb", cells, 5)[2][0]["params"]["change"]["cells"]["structure"]
    assert [d["uri"][-1] for d in structure["didClose"]] == ["1"]
    assert [m["method"] for m in mirror.close_all()] == ["notebookDocument/didClose"]


def test_what_is_not_a_document_is_refused() -> None:
    mirror = documents.Mirror()
    with pytest.raises(documents.DocumentError):
        mirror.text("k", "a.py", "javascript", "x")
    with pytest.raises(documents.DocumentError):
        mirror.text("", "a.py", "python", "x")
    with pytest.raises(documents.DocumentError):
        mirror.notebook("k", "n.ipynb", [{"id": 1, "text": "x"}], 2)  # the cell edited is not sent
    with pytest.raises(documents.DocumentError):
        mirror.notebook("k", "n.ipynb", [{"id": 1, "text": "x"}, {"id": 1, "text": "y"}], 1)
    with pytest.raises(documents.DocumentError):
        mirror.text("k", "a.py", "python", "x" * (documents.MAX_TEXT + 1))


def test_the_document_used_longest_ago_is_closed_for_a_new_one() -> None:
    mirror = documents.Mirror()
    for n in range(documents.MAX_DOCUMENTS):
        mirror.text(f"d{n}", "a.py", "python", "x")
    mirror.text("d0", "a.py", "python", "xy")  # d0 used again: d1 is now the oldest
    _, _, sent = mirror.text("new", "a.py", "python", "x")
    assert [m["method"] for m in sent] == ["textDocument/didClose", "textDocument/didOpen"]
    assert sent[0]["params"]["textDocument"]["uri"].endswith("/d1/a.py")


# ===== answers =====


def test_inline_items_are_read_with_their_command_kept_aside() -> None:
    result = {
        "items": [
            {
                "insertText": "das as pd\r\nimport duckdb",
                "range": {"start": {"line": 0, "character": 10}, "end": {"line": 0, "character": 10}},
                "command": {"command": "github.copilot.didAcceptCompletionItem", "arguments": ["made-up"]},
            },
            {"insertText": ""},
            "not an item",
            {"insertText": "x", "range": {"start": {"line": -1, "character": 0}, "end": {}}},
        ]
    }
    items = lsp.items_of(result)
    assert [i["text"] for i in items] == ["das as pd\nimport duckdb", "x"]
    assert items[0]["command"]["arguments"] == ["made-up"] and items[1]["range"] is None
    assert items[0]["raw"] is result["items"][0]
    assert lsp.items_of(None) == [] and lsp.items_of({"items": "no"}) == []


def test_the_account_in_plain_words() -> None:
    assert lsp.account_of({"status": "OK", "user": "made-up-octocat"}) == {
        "state": "signed_in",
        "user": "made-up-octocat",
    }
    assert lsp.account_of({"status": "MaybeOK", "user": "a"})["state"] == "signed_in"
    assert lsp.account_of({"status": "NotAuthorized", "user": "a"})["state"] == "no_subscription"
    assert lsp.account_of({"status": "NotSignedIn"}) == {"state": "not_signed_in", "user": None}
    assert lsp.account_of(None)["state"] == "not_signed_in"


def test_the_device_flow_is_its_code_and_githubs_page() -> None:
    flow = lsp.device_flow_of(
        {
            "status": "PromptUserDeviceFlow",
            "userCode": "ABCD-EFGH",
            "verificationUri": "https://github.com/login/device",
        }
    )
    assert flow == {"code": "ABCD-EFGH", "link": "https://github.com/login/device"}
    odd = lsp.device_flow_of(
        {"status": "PromptUserDeviceFlow", "userCode": "X", "verificationUri": "javascript:alert(1)"}
    )
    assert odd is not None and odd["link"] == lsp.DEVICE_PAGE
    assert lsp.device_flow_of({"status": "AlreadySignedIn", "user": "a"}) is None


# ===== tools =====


def test_node_is_found_new_enough_and_missing_says_the_install() -> None:
    old = tools.tool_state("node", "/usr/bin/node", "18.19.0", "linux")
    assert not old["ok"] and "older than 20.8" in old["problem"]
    assert tools.tool_state("node", "/usr/bin/node", "22.11.0", "linux")["ok"]
    states = {
        "node": tools.tool_state("node", None, None, "windows"),
        "npm": tools.tool_state("npm", None, None, "windows"),
    }
    said = tools.missing("install", states, "windows")
    assert said is not None
    assert said["missing"]["packages"] == ["Node.js"] and said["missing"]["python"] == "tool"
    assert said["missing"]["command"] == "winget install --id OpenJS.NodeJS.LTS -e"
    assert tools.parse_version("v22.23.4\n") == "22.23.4"


def test_the_install_is_the_pinned_package_into_its_own_folder() -> None:
    argv = tools.install_argv("npm", "/state/copilot")
    assert argv[:4] == ["npm", "install", "--prefix", "/state/copilot"]
    assert argv[-1] == f"@github/copilot-language-server@{lsp.PINNED}" and "--ignore-scripts" in argv
