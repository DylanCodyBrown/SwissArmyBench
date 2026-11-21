"""The blade IDE (the owner, 2026-11-21: "this entire panel should be an ide, with small save, saves, cancel
buttons at the top and a play button to execute with a realtime linter and output at the bottom to see the
results. This is an IDE not a save form"). It reverses 2026-11-17's "blades can only be edited in the folder":
the code is saved from the app, written into its file after the header (the bytes are the file's, written
only when they change); an edit made outside is noticed, never saved over without Keep mine. Run streams the
output, answers the result and the problems; the agent does all of it. Made-up data only."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import blade_tables
from swissarmybench.domain.blade_tables import follow_variable, with_code
from swissarmybench.domain.blades import read_blade
from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring


@pytest.fixture(autouse=True)
def vault() -> Iterator[None]:
    with memory_keyring():
        yield


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with make_client(tmp_path) as test_client:
        yield test_client


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


FILE = """# /// swissarmybench-blade
# format = 1
# name = "Bakery"
# kind = "other"
# variable = "loaves"
# ///
loaves = 12
"""


# ===== the file: the code replaced after the header, the rest as it was =====


def test_the_code_is_written_after_the_header_and_read_back_the_same() -> None:
    assert with_code(FILE, read_blade(FILE)["code"]) == FILE  # its own code: the same bytes
    changed = with_code(FILE, "loaves = 13\n")
    assert changed == FILE.replace("loaves = 12", "loaves = 13")
    crlf = FILE.replace("\n", "\r\n")
    assert with_code(crlf, "a = 1\nb = 2\n").endswith("# ///\r\na = 1\r\nb = 2\r\n")  # the file's line ends


def test_the_variable_follows_a_renamed_function() -> None:
    assert follow_variable("def make():\n    return 1\n", "make") == "make"
    assert follow_variable("def build():\n    return 1\n", "make") == "build"
    assert follow_variable("def (:\n", "make") == "make"  # broken code keeps it: its run says why


# ===== saving code: the file written, a starter refused, an outside edit noticed =====


def new_table(client: TestClient) -> dict[str, Any]:
    made: dict[str, Any] = ok(
        client.post("/blades/new", json={"template": "table", "name": "Loaves"}, headers=AUTH)
    )
    return made


def test_the_ide_saves_code_into_the_file_only_when_it_changes(client: TestClient) -> None:
    file = Path(new_table(client)["file"])
    whole = ok(client.get("/blades/Loaves", headers=AUTH))
    assert whole["stamp"] and whole["read_only"] is False
    before = file.read_bytes()
    same = ok(
        client.put("/blades/Loaves", json={"code": whole["code"], "stamp": whole["stamp"]}, headers=AUTH)
    )
    assert file.read_bytes() == before and same["stamp"] == whole["stamp"]  # nothing changed: no byte
    code = (
        'import pandas as pd\n\n\ndef bake() -> pd.DataFrame:\n    return pd.DataFrame({"loaf": ["rye"]})\n'
    )
    saved = ok(client.put("/blades/Loaves", json={"code": code, "stamp": whole["stamp"]}, headers=AUTH))
    text = file.read_text(encoding="utf-8")
    assert text.endswith(code) and '# variable = "bake"' in text  # its variable followed the rename
    assert saved["stamp"] != whole["stamp"] and saved["variable"] == "bake"
    assert ok(client.get("/blades/Loaves/code", headers=AUTH)) == {
        "name": "Loaves",
        "code": code,
        "stamp": saved["stamp"],
        "file": str(file),
        "read_only": False,
    }
    # Code that does not parse is not saved: the file stays as it was, the words say where.
    refused = client.put("/blades/Loaves", json={"code": "def (:\n"}, headers=AUTH)
    assert refused.status_code == 400 and "not valid Python" in refused.text
    assert file.read_text(encoding="utf-8").endswith(code)
    # Its kind is not the app's to change.
    assert client.put("/blades/Loaves", json={"kind": "analysis"}, headers=AUTH).status_code == 400


def test_an_edit_made_outside_is_never_saved_over_without_keep_mine(client: TestClient) -> None:
    file = Path(new_table(client)["file"])
    opened = ok(client.get("/blades/Loaves/code", headers=AUTH))
    outside = file.read_text(encoding="utf-8").replace('"Ada"', '"Dot"')
    file.write_text(outside, encoding="utf-8")  # the user's own editor
    looked = ok(client.get("/blades/Loaves/code", headers=AUTH))
    assert looked["stamp"] != opened["stamp"] and '"Dot"' in looked["code"]
    mine = opened["code"].replace('"Ada"', '"Ann"')
    refused = client.put("/blades/Loaves", json={"code": mine, "stamp": opened["stamp"]}, headers=AUTH)
    assert refused.status_code == 409
    said = refused.json()
    assert said["changed_on_disk"] is True and said["stamp"] == looked["stamp"]
    assert "changed on disk" in said["error"] and file.read_text(encoding="utf-8") == outside
    # Keep mine: saved over it on the user's word.
    ok(
        client.put(
            "/blades/Loaves", json={"code": mine, "stamp": opened["stamp"], "force": True}, headers=AUTH
        )
    )
    assert '"Ann"' in file.read_text(encoding="utf-8")


def test_a_starters_save_is_refused_and_save_as_copies_the_editors_code(client: TestClient) -> None:
    starter = next(
        b["name"]
        for f in ok(client.get("/blades/starters", headers=AUTH))["families"]
        for b in f["blades"]
        if b["kind"] == "other"
    )
    whole = ok(client.get(f"/blades/{starter}", headers=AUTH))
    assert whole["read_only"] is True
    for who in (AUTH, AGENT):
        refused = client.put(f"/blades/{starter}", json={"code": whole["code"] + "\n# mine\n"}, headers=who)
        assert refused.status_code == 400 and "Copy as your own" in refused.text
    assert ok(client.get("/blades/name-check", params={"name": starter}, headers=AUTH))["available"] is False
    assert ok(client.get("/blades/name-check", params={"name": "My copy"}, headers=AUTH)) == {
        "name": "My copy",
        "available": True,
        "said": "available",
    }
    assert ok(client.get("/blades/name-check", params={"name": "a:b"}, headers=AUTH))["available"] is False
    copied = ok(
        client.post(
            f"/blades/{starter}/copy",
            json={"name": "My copy", "code": whole["code"] + "\n# mine\n"},
            headers=AGENT,
        )
    )
    assert copied["name"] == "My copy"
    assert ok(client.get("/blades/My%20copy", headers=AUTH))["code"].endswith("# mine\n")


# ===== Run: the output, the result, the error with its line, the problems =====


def run(client: TestClient, name: str, body: dict[str, Any], who: dict[str, str] = AUTH) -> dict[str, Any]:
    answer: dict[str, Any] = ok(client.post(f"/blades/{name}/run", json=body, headers=who))
    return answer


def test_run_answers_its_output_and_a_table_result_opened_as_a_grid(client: TestClient) -> None:
    new_table(client)
    code = (
        "import sys\n\nimport pandas as pd\n\n\ndef make_table() -> pd.DataFrame:\n"
        "    print('baking')\n    print('warm', file=sys.stderr)\n"
        '    return pd.DataFrame({"loaf": ["rye", "spelt", "wheat"], "grams": [800, 750, 900]})\n'
    )
    ran = run(client, "Loaves", {"code": code}, AGENT)  # the editor's code, not saved
    assert ran["ok"] is True, ran
    assert {"stream": "stdout", "text": "baking\n"} in ran["output"]
    assert any(o["stream"] == "stderr" and "warm" in o["text"] for o in ran["output"])
    result = ran["result"]
    assert result["kind"] == "table" and result["total"] == 3 and result["columns"] == ["loaf", "grams"]
    assert result["rows"][0] == ["rye", 800] and result["made_by"] == "make_table"
    assert ran["problems"] == []
    assert ok(client.get("/blades/Loaves/run", headers=AGENT))["run"] == ran["run"]  # the last run, kept
    assert "Ada" in ok(client.get("/blades/Loaves", headers=AUTH))["code"]  # nothing saved
    opened = ok(client.post("/blades/Loaves/result/open", headers=AGENT))
    rows = ok(client.get(f"/grids/{opened['grid']}/rows", params={"start": 0, "end": 10}, headers=AUTH))
    assert len(rows["rows"]) == 3 and opened["dataset"] == "make_table"


def test_a_value_and_a_failure_with_its_line_and_the_lints_problems(client: TestClient) -> None:
    ok(client.post("/blades/new", json={"template": "code", "name": "Count"}, headers=AUTH))
    value = run(client, "Count", {"code": "value = {'rye': 3}\n"})
    assert value["result"] == {"kind": "value", "type": "dict", "made_by": None, "text": "{'rye': 3}"}
    failed = run(client, "Count", {"code": "x = 1\nvalue = x / 0\n"})
    assert failed["ok"] is False and "ZeroDivisionError" in failed["error"]
    entry = failed["error_detail"]["chain"][-1]
    frame = entry["frames"][entry["your_frame"]]
    assert frame["where"] == "file" and frame["line"] == 2
    assert failed["error_detail"]["where"] == "count.py, line 2"
    syntax = run(client, "Count", {"code": "value = (\n"})
    assert syntax["ok"] is False and syntax["error_detail"]["chain"][-1]["syntax"]["line"] == 1
    # The lint: secret() is known (the run gives it); an undefined name is a problem, with its line.
    problems = ok(
        client.post(
            "/blades/Count/problems", json={"code": "a = secret('k')\nvalue = missing\n"}, headers=AGENT
        )
    )
    errors = [p for p in problems["problems"] if p["severity"] == "error"]
    assert [p["line"] for p in errors] == [2] and "missing" in errors[0]["message"]
    assert not any("secret" in p["message"] for p in problems["problems"])


def test_a_streamed_run_sends_each_line_then_the_answer(client: TestClient) -> None:
    ok(client.post("/blades/new", json={"template": "code", "name": "Count"}, headers=AUTH))
    with client.stream(
        "POST", "/blades/Count/run", json={"code": "print('one')\nvalue = 2\n", "stream": True}, headers=AUTH
    ) as response:
        assert response.status_code == 200
        items = [json.loads(line) for line in response.iter_lines() if line.strip()]
    assert items[0] == {"output": {"stream": "stdout", "text": "one"}} or items[0]["output"][
        "text"
    ].startswith("one")
    assert items[-1]["done"]["ok"] is True and items[-1]["done"]["result"]["text"] == "2"
    # A snippet has nothing to run: refused before any stream.
    ok(client.post("/blades/new", json={"template": "snippet", "name": "Note"}, headers=AUTH))
    assert client.post("/blades/Note/run", json={"stream": True}, headers=AUTH).status_code == 400


def test_a_secret_in_the_output_is_never_sent_back(client: TestClient) -> None:
    ok(
        client.post(
            "/blades",
            json={
                "name": "Shop",
                "kind": "other",
                "code": "token = secret('api')\nprint(token)\nvalue = token\n",
            },
            headers=AUTH,
        )
    )
    ok(client.put("/blades/Shop/secrets", json={"api": "made-up-token-42"}, headers=AUTH))
    ran = run(client, "Shop", {}, AGENT)
    assert ran["ok"] is True
    assert "made-up-token-42" not in json.dumps(ran) and "****" in json.dumps(ran)


def test_the_secret_stub_is_one_line_of_python() -> None:
    assert compile(blade_tables.SECRET_STUB, "stub", "exec")
