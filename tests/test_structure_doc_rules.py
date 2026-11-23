"""A structure tab's rules that need no page (web/src/structurePaths.ts, pulled out of structureDoc.ts's one
big function): a path's text read back into its parts, a parse error as the editor's problem, a value typed
into Add key…'s box. Run by Node as the page runs them. Made-up data."""

from __future__ import annotations

from typing import Any

import pytest

from tests.web_unit import bundled, needs_node

pytestmark = needs_node

# A path that does not read throws: a small caller gives its words back instead.
CALLER = """
import { partsOf } from "@module";
export function partsOrError(path: string) {
  try {
    return partsOf(path);
  } catch (e) {
    return String((e as Error).message);
  }
}
"""


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return bundled(tmp_path_factory.mktemp("structure-doc"), "structurePaths.ts", CALLER)


def test_a_paths_text_is_read_back_into_its_parts(run: Any) -> None:
    assert run(
        ["partsOrError", "$"],
        ["partsOrError", "$.orders[3].lines"],
        ["partsOrError", '$["order lines"][-1]'],
        ["partsOrError", "$.orders[*]"],
        ["partsOrError", "$.orders x"],
    ) == [
        [],
        ["orders", 3, "lines"],
        ["order lines", -1],
        '$.orders[*]: a path goes on with .name, [n] or ["key"].',
        '$.orders x: a path goes on with .name, [n] or ["key"].',
    ]


def test_a_parse_error_is_underlined_to_its_lines_end(run: Any) -> None:
    text = '{\n  "orders": [1, 2,\n}'
    at_line, nowhere = run(
        ["parseProblem", "Expecting value: line 2, column 5", text, "JSON"],
        ["parseProblem", "Something is wrong", text, "YAML"],
    )
    assert at_line == {
        "line": 2,
        "col": 5,
        "end_line": 2,
        "end_col": 19,
        "message": "Expecting value: line 2, column 5",
        "severity": "error",
        "code": "parse",
        "source": "JSON",
    }
    assert (nowhere["line"], nowhere["col"], nowhere["end_col"]) == (1, 1, 2)


def test_a_typed_value_is_json_when_it_reads_as_json(run: Any) -> None:
    assert run(
        ["parseValue", "12"],
        ["parseValue", '{"a": [true, null]}'],
        ["parseValue", "Held"],
        ["parseValue", ""],
    ) == [
        12,
        {"a": [True, None]},
        "Held",
        "",
    ]
