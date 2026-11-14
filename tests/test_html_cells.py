"""HTML cells (docs/ideas.md, 2026-11-14): the cell in a notebook file and in a script, both ways; the
`{{ name }}` filling and its escaping, wherever a name stands; the row cap; the saved height; the uses
line; and the kernel's side on real tables. Made-up data only."""

from __future__ import annotations

import ast
import base64
import json
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmygrid.cli.commands import execute
from swissarmygrid.client import html_cells as kernel_side
from swissarmygrid.domain import html_cells as rules
from swissarmygrid.domain import notebooks, table_cells
from tests.conftest import AGENT, AUTH, make_client
from tests.test_cli import Live, data_of, live  # noqa: F401 (the running server)
from tests.test_cli import run as command

CARD = '<div class="card">\n  <h1>Orders</h1>\n  <p>{{ total }} orders from {{ region }}</p>\n</div>'
HOSTILE = "<script>alert('x')</script><img src=x onerror=alert(1)> & \"quoted\""

# ===== names =====


def test_the_names_an_html_cell_asks_for() -> None:
    assert rules.names(CARD) == ["total", "region"]
    assert rules.names("{{total}} {{  total  }} {{ other_1 }}") == ["total", "other_1"]
    # Not a name: an expression, a dotted name, a number, JavaScript's own braces.
    assert rules.names("{{ a + b }} {{ a.b }} {{ 1 }} const x = {{b: 1}}; {{ }}") == []


# ===== values =====


def test_a_single_value_is_escaped_text() -> None:
    value = rules.text_value(HOSTILE)
    assert value["kind"] == "text" and "<" not in value["html"] and '"' not in value["html"]
    assert value["html"].startswith("&lt;script&gt;alert(&#x27;x&#x27;)")
    # In a <script> it is a quoted text that cannot end the script or start markup.
    assert "<" not in value["json"] and ">" not in value["json"] and "&" not in value["json"]
    assert json.loads(value["json"]) == HOSTILE
    assert rules.text_value(1234.5)["json"] == "1234.5" and rules.text_value(None)["json"] == "null"
    assert rules.text_value(True)["json"] == "true" and rules.text_value(None)["html"] == ""
    assert rules.text_value(float("nan"))["json"] == "null"
    assert len(rules.text_value("x" * 50_000)["text"]) == rules.TEXT_CHARS


def test_a_table_is_drawn_up_to_the_row_cap_and_says_so() -> None:
    rows = [[i, f"<b>{i}</b>"] for i in range(1, 1205)]
    value = rules.table_value(["id", "na<me"], rows, 1204)
    assert value["kind"] == "table"
    assert value["html"].count("<tr>") == 1 + rules.TABLE_ROWS == 51
    assert "<caption>first 50 of 1,204 rows</caption>" in value["html"]
    assert "<th>na&lt;me</th>" in value["html"] and "<td>&lt;b&gt;1&lt;/b&gt;</td>" in value["html"]
    assert "<b>" not in value["html"]
    # A <script> gets rows as a list, up to its own cap.
    data = json.loads(value["json"])
    assert len(data) == rules.DATA_ROWS == 1000 and data[0] == {"id": 1, "na<me": "<b>1</b>"}
    assert "<" not in value["json"]
    # A small table has no caption: nothing is left out.
    small = rules.table_value(["a"], [[1], [None]], 2)
    assert "<caption>" not in small["html"] and small["html"].count("<td>") == 2
    wide = rules.table_value([f"c{i}" for i in range(40)], [list(range(40))], 1)
    assert "first 30 of 40 columns" in wide["html"] and wide["html"].count("<th>") == 30


def test_a_picture_is_an_image_from_a_data_address() -> None:
    png = base64.b64encode(b"\x89PNG made up").decode()
    value = rules.picture_value(png, 'chart"><script>')
    assert value["kind"] == "picture" and f'src="data:image/png;base64,{png}"' in value["html"]
    assert "<script>" not in value["html"]
    assert rules.picture_value('x" onerror="alert(1)', "p")["kind"] == "text"


# ===== fill =====


def filled(text: str, **values: Any) -> str:
    return rules.fill(text, {name: rules.text_value(value) for name, value in values.items()}).html


def test_names_among_the_words_are_filled_with_escaped_text() -> None:
    assert filled("<p>{{ total }} orders from {{region}}</p>", total=42, region="North & <West>") == (
        "<p>42 orders from North &amp; &lt;West&gt;</p>"
    )
    done = rules.fill(CARD, {"total": rules.text_value(42), "region": rules.text_value("North")})
    assert done.names == ("total", "region") and done.missing == () and done.waiting == ()


def test_hostile_data_never_becomes_markup_or_script_wherever_the_name_stands() -> None:
    template = (
        "<p>{{ x }}</p>"
        '<a href="{{ x }}" title={{ x }} onclick="{{ x }}">link</a>'
        "<style>p { color: {{ x }} }</style>"
        "<script>const v = {{ x }};</script>"
        "<textarea>{{ x }}</textarea><title>{{ x }}</title>"
        "<!-- {{ x }} -->"
    )
    for hostile in (
        HOSTILE,
        "javascript:alert(1)",
        "x onmouseover=alert(1)",
        "red;} body{display:none",
        "</script><script>alert(1)</script>",
        "</textarea><script>alert(1)</script>",
        "--><script>alert(1)</script>",
        "alert(1)",
    ):
        done = rules.fill(template, {"x": rules.text_value(hostile)})
        out = done.html
        # Among the words and in a <textarea>: escaped.
        assert f"<p>{rules.escape(hostile)}</p>" in out
        assert f"<textarea>{rules.escape(hostile)}</textarea><title>{rules.escape(hostile)}</title>" in out
        # Inside a tag and a <style>: left out, and said.
        assert '<a href="" title= onclick="">link</a>' in out
        assert "<style>p { color:  }</style>" in out
        assert any("left out of a tag" in note for note in done.notes)
        # Inside a <script>: one quoted text.
        script = out[out.index("<script>const v = ") + len("<script>const v = ") : out.index(";</script>")]
        assert json.loads(script) == hostile and "<" not in script
        # A comment stays as written.
        assert "<!-- {{ x }} -->" in out
        assert out.count("<script>") == 1


def test_plain_words_and_numbers_go_inside_a_tag_and_a_style() -> None:
    template = (
        '<div class="bar {{ tone }}" style="width: {{ pct }}%"></div><style>.bar{color:{{ colour }}}</style>'
    )
    assert filled(template, tone="good", pct=62.5, colour="#2a7") == (
        '<div class="bar good" style="width: 62.5%"></div><style>.bar{color:#2a7}</style>'
    )


@pytest.mark.parametrize(
    "template",
    [
        # HTML's own script rules: a `</script>` between `<!--` + `<script` and `-->` does not end it.
        "<script><!-- <script> </script> const v = {{ x }}; --></script>",
        "<script>const s = '</scriptx>'; const v = {{ x }};</script>",
        "<SCRIPT type=module>const v = {{ x }};</SCRIPT>",
        "<script><!--> const v = {{ x }};</script>",
        "<!--> <script>const s = '-->'; const v = {{ x }};</script>",
        "<svg><![CDATA[ <p> ]]></svg><script>const v = {{ x }};</script>",
        "<a title='>' href=#></a><script>const v = {{ x }};</script>",
    ],
)
def test_a_name_in_a_script_is_a_literal_however_the_script_is_written(template: str) -> None:
    out = filled(template, x="alert(1)")
    assert 'const v = "alert(1)";' in out and "const v = alert(1)" not in out


def test_a_name_the_browser_reads_as_text_is_never_given_a_script_literal_in_a_tag() -> None:
    # Unusual markup: whatever the reading, no quoted text lands inside a tag.
    for template in (
        '<svg><![CDATA[ <script> ]]></svg><a title="{{ x }}">t</a>',
        '<!-- <script> --><a title="{{ x }}">t</a>',
        '<textarea><script></textarea><a title="{{ x }}">t</a>',
        '<title><script></title><a title="{{ x }}">t</a>',
    ):
        out = filled(template, x="x onmouseover=alert(1)")
        assert '<a title="">t</a>' in out


def test_a_table_and_a_picture_among_the_words_and_nowhere_else() -> None:
    table = rules.table_value(["store", "amount"], [["North", 10], ["South", 20]], 2)
    done = rules.fill(
        "<h2>Sales</h2>{{ sales }}<p title='{{ sales }}'></p><script>const rows = {{ sales }};</script>",
        {"sales": table},
    )
    assert "<h2>Sales</h2><table" in done.html and "<td>North</td><td>10</td>" in done.html
    assert "<p title=''></p>" in done.html
    assert 'const rows = [{"store":"North","amount":10},{"store":"South","amount":20}];' in done.html
    assert done.notes == ("{{ sales }} is left out of a tag: a table cannot go there.",)


def test_an_unknown_name_is_a_plain_marker_never_an_error() -> None:
    template = "<p>{{ nope }}</p><script>const v = {{ nope }};</script>"
    done = rules.fill(template, {"nope": rules.missing_value("nope")})
    assert "{{ nope }} not found" in done.html and "const v = null;" in done.html
    assert done.missing == ("nope",)
    # Before the cell has run: the name as written, marked.
    waiting = rules.fill("<p>{{ total }}</p>", {})
    assert waiting.waiting == ("total",) and ">{{ total }}</span>" in waiting.html
    # A value record that is not what a run gives draws nothing harmful.
    assert rules.fill("<p>{{ a }}</p>", {"a": {}}).html == "<p></p>"


def test_plain_html_is_left_exactly_as_written() -> None:
    plain = "<h1>Hello</h1>\n<script>document.title = `${1 + 1}`; const o = {{a: 1}};</script>"
    assert rules.fill(plain, {}).html == plain and rules.names(plain) == []


def test_a_values_mark_changes_only_when_what_it_draws_does() -> None:
    assert rules.digest(rules.text_value(42)) == rules.digest(rules.text_value(42))
    assert rules.digest(rules.text_value(42)) != rules.digest(rules.text_value(43))
    one = rules.table_value(["a"], [[1], [2]], 2)
    assert rules.digest(one) != rules.digest(rules.table_value(["a"], [[1], [3]], 2))


def test_the_saved_height_is_kept_within_the_panes_limits() -> None:
    assert rules.check_height(320) == 320 and rules.check_height(320.6) == 321
    assert rules.check_height(5) == rules.HEIGHT_MIN and rules.check_height(99_999) == rules.HEIGHT_MAX
    for odd in (None, "320", True, float("nan"), float("inf"), [1]):
        assert rules.check_height(odd) is None


def test_the_frame_loads_nothing_over_the_network() -> None:
    policy = dict(part.strip().split(" ", 1) for part in rules.FRAME_POLICY.split(";"))
    assert policy["default-src"] == "'none'" and policy["script-src"] == "'unsafe-inline'"
    assert policy["img-src"] == "data:" and policy["font-src"] == "data:"
    assert "connect-src" not in policy  # so it falls back to default-src: none
    assert not any(word in rules.FRAME_POLICY for word in ("http", "*", "'self'"))


# ===== in a notebook file =====


def test_a_notebook_keeps_an_html_cell_as_a_cell_plain_jupyter_draws() -> None:
    output = {"output_type": "display_data", "data": {"text/html": "<p>42</p>"}, "metadata": {}}
    cells = [
        notebooks.Cell("html", CARD, outputs=[output], execution_count=3, height=320),
        notebooks.Cell("html", "<h1>Plain</h1>"),
        notebooks.Cell("code", "x = 1"),
    ]
    text = notebooks.write_notebook(cells)
    saved = json.loads(text)["cells"]
    # IPython's own cell magic, so Jupyter draws it when run; the height is in the cell's metadata.
    assert saved[0]["cell_type"] == "code" and saved[0]["source"][0] == "%%html\n"
    assert "".join(saved[0]["source"][1:]) == CARD
    assert saved[0]["metadata"]["swissarmygrid"] == {"kind": "html", "height": 320, "number": 1}
    assert saved[1]["metadata"]["swissarmygrid"] == {"kind": "html", "number": 2}
    read = notebooks.read_notebook(text)
    assert [(c.kind, c.source, c.height, c.number) for c in read] == [
        ("html", CARD, 320, 1),
        ("html", "<h1>Plain</h1>", None, 2),
        ("code", "x = 1", None, 3),
    ]
    assert read[0].outputs == [output] and read[0].execution_count == 3
    # A second save changes nothing.
    assert notebooks.write_notebook(read) == text


def test_a_plain_jupyter_html_cell_opens_as_an_html_cell() -> None:
    raw = {
        "cells": [
            {"cell_type": "code", "source": ["%%html\n", "<b>hi</b>"], "metadata": {}, "outputs": []},
            {"cell_type": "code", "source": "%%html --isolated\n<i>x</i>", "metadata": {}, "outputs": []},
            {"cell_type": "code", "source": "%%htmlx\n<i>x</i>", "metadata": {}, "outputs": []},
        ],
        "nbformat": 4,
    }
    read = notebooks.read_notebook(json.dumps(raw))
    assert [(c.kind, c.source) for c in read] == [
        ("html", "<b>hi</b>"),
        ("html", "<i>x</i>"),
        ("code", "%%htmlx\n<i>x</i>"),
    ]


def test_the_page_sends_html_cells_and_their_height() -> None:
    sent = [{"kind": "html", "source": CARD, "height": 5000, "outputs": [{"output_type": "display_data"}]}]
    cells = notebooks.read_cells(sent)
    assert cells[0].kind == "html" and cells[0].height == rules.HEIGHT_MAX and len(cells[0].outputs) == 1
    assert notebooks.read_cells([{"kind": "code", "source": "x", "height": 300}])[0].height is None
    assert notebooks.code_of(cells[0]) == f"%%html\n{CARD}"
    with pytest.raises(notebooks.NotebookError, match="html"):
        notebooks.read_cells([{"kind": "design", "source": ""}])


# ===== in a script =====


@pytest.mark.parametrize(
    "text",
    [
        CARD,
        "",
        "<p>one line</p>",
        'She said """hi""" and left',
        "both \"\"\" and ''' quotes \\ and a backslash \\n",
        "ends with a backslash \\",
        'ends with a quote "',
        "<script>const re = /\\d+\\n/; const s = '\\\\';</script>",
        "tabs\tand\r\nwindows lines",
        "trailing newline\n",
    ],
)
def test_a_scripts_html_cell_holds_its_html_as_one_string_that_does_nothing(text: str) -> None:
    body = rules.script_body(text)
    # One statement, a string by itself: the file still runs as plain Python and makes no name.
    tree = ast.parse(body)
    assert len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr)
    namespace: dict[str, Any] = {}
    exec(body, namespace)  # noqa: S102 (the test's own text)
    assert set(namespace) <= {"__builtins__", "__doc__"}  # first in a file, it is the file's own words
    held, problem = rules.read_script_body(body)
    assert problem is None and held == (text[:-1] if text.endswith("\n") else text)


def test_plain_html_is_written_as_it_is_in_a_script() -> None:
    assert rules.script_body(CARD) == f'r"""\n{CARD}\n"""\n'


def test_a_scripts_html_cell_reads_what_the_user_wrote() -> None:
    assert rules.read_script_body('card = """<b>hi</b>"""\nprint(card)\n') == ("<b>hi</b>", None)
    assert rules.read_script_body("# uses orders @cell3\nr'''\n<p>{{ orders }}</p>\n'''\n") == (
        "<p>{{ orders }}</p>",
        None,
    )
    assert rules.read_script_body("") == ("", None) and rules.read_script_body("# a note\n\n") == ("", None)
    assert rules.read_script_body('r"""\n<p>half')[0] is None
    held, problem = rules.read_script_body('f"""<p>{total}</p>"""\n')
    assert held is None and problem is not None and "one string" in problem
    assert rules.read_script_body("x = 1\n")[0] is None


SCRIPT = (
    "import pandas as pd\n"
    "# %% [1]\n"
    "total = 42\n"
    "# %% [2] [html] height=320 The summary card\n"
    'r"""\n'
    "<h1>{{ total }} orders</h1>\n"
    '"""\n'
    "# %% [html]\n"
    'r"""\n'
    "<p>plain</p>\n"
    '"""\n'
)


def test_a_scripts_html_cells_keep_their_marker_height_and_words() -> None:
    script = table_cells.parse_script(SCRIPT)
    cells = [c for c in script.cells if not c.fixed]
    assert [(c.number, c.html, c.height, c.title) for c in cells] == [
        (1, False, None, ""),
        (2, True, 320, "The summary card"),
        (None, True, None, ""),
    ]
    text = table_cells.arrange_script(SCRIPT, [])[0]
    # The cell without a number gets one; nothing else changes.
    assert text == SCRIPT.replace("# %% [html]\n", "# %% [3] [html]\n")
    assert table_cells.arrange_script(text, [])[0] == text
    outline = table_cells.outline(text)["cells"]
    assert [(c["number"], c["kind"], c["height"]) for c in outline] == [
        (1, "code", None),
        (2, "html", 320),
        (3, "html", None),
    ]
    assert outline[1]["html"] == "<h1>{{ total }} orders</h1>" and outline[1]["problem"] is None
    assert outline[1]["first"] == "<h1>{{ total }} orders</h1>" and outline[2]["html"] == "<p>plain</p>"
    assert (outline[1]["line"], outline[1]["end"], outline[1]["html_end"]) == (4, 7, 7)
    # Python after the string, in the same cell, is the user's own: it stays in view.
    more = table_cells.outline('# %% [1] [html]\n# uses orders @cell3\nr"""\n<p>x</p>\n"""\nprint(1)\n')[
        "cells"
    ][0]
    assert (more["line"], more["end"], more["html_end"], more["html"]) == (1, 7, 5, "<p>x</p>")
    # The file still runs as plain Python.
    namespace: dict[str, Any] = {}
    exec(text, namespace)  # noqa: S102 (the test's own text)
    assert namespace["total"] == 42


def test_a_broken_html_cell_in_a_script_says_what_is_wrong() -> None:
    outline = table_cells.outline('# %% [1] [html]\nr"""\n<p>half\n')["cells"]
    assert outline[0]["html"] is None and "quotes" in outline[0]["problem"]


# ===== the uses line =====


def test_an_html_cell_that_names_a_table_starts_with_its_uses_line() -> None:
    tables = {"orders": 3, "customers": None}
    source = "<h1>Orders</h1>\n{{ orders }} and {{ customers }} and {{ total }}"
    line = table_cells.uses_line(source, tables, html=True)
    assert line == "<!-- uses orders @cell3, customers -->"
    assert table_cells.USES_HTML.match(line)
    once = table_cells.with_uses(source, tables, html=True)
    assert once == f"{line}\n{source}" and table_cells.with_uses(once, tables, html=True) == once
    # It goes when the cell asks for no table any more; a comment of the user's own is never touched.
    assert table_cells.with_uses(once, {}, html=True) == source
    own = "<!-- uses of this card: the monthly report -->\n<p>{{ total }}</p>"
    assert table_cells.with_uses(own, tables, html=True) == own
    # The name must be asked for: a word in the HTML is not a use.
    assert table_cells.uses_line("<p>orders</p>", tables, html=True) is None


def test_the_arrangement_gives_html_cells_their_uses_line_in_a_notebook_and_a_script() -> None:
    spec = table_cells.TableSpec("orders", "# orders: no transformations yet.", "orders = 1", 0)
    cells = [
        table_cells.PlanCell(1, "code", "orders = pd.DataFrame({'a': [1]})"),
        table_cells.PlanCell(2, "html", "<h1>Orders</h1>\n{{ orders }}"),
        table_cells.PlanCell(3, "html", "<p>plain</p>"),
    ]
    done = table_cells.arrange(cells, [spec], next_number=4)
    by_number = {c.number: c for c in done.cells}
    table = next(c for c in done.cells if c.role == "transformations")
    assert by_number[2].uses == f"<!-- uses orders @cell{table.number} -->" and by_number[3].uses is None
    assert by_number[2].kind == "html" and by_number[2].role == ""
    # A script's HTML cell: a Python comment above the string, so the HTML stays as written.
    script = '# %% [1]\norders = make()\n# %% [2] [html]\nr"""\n<h1>Orders</h1>\n{{ orders }}\n"""\n'
    text, arrangement = table_cells.arrange_script(script, [spec])
    number = next(c.number for c in arrangement.cells if c.role == "transformations")
    assert f'[html]\n# uses orders @cell{number}\nr"""\n<h1>Orders</h1>\n{{{{ orders }}}}\n"""\n' in text
    assert table_cells.arrange_script(text, [spec])[0] == text
    html_cell = next(c for c in table_cells.outline(text)["cells"] if c["kind"] == "html")
    assert html_cell["html"] == "<h1>Orders</h1>\n{{ orders }}"
    # A file that no longer holds the table: the line goes.
    stale = script.replace("[html]\n", "[html]\n# uses orders @cell9\n")
    assert table_cells.arrange_script(stale, [])[0] == script


# ===== the kernel's side: real tables =====

SALES = pd.DataFrame({"store": ["North", "South", "<East>"], "amount": [10.5, 20.0, None]})


def test_each_kind_of_table_is_drawn_from_its_first_rows() -> None:
    relation = duckdb.sql("SELECT * FROM range(2500) t(n)")
    namespace = {
        "sales": SALES,
        "arrow": pa.Table.from_pandas(SALES),
        "numbers": relation,
        "big": pd.DataFrame({"n": range(1204)}),
    }
    found = kernel_side.values(["sales", "arrow", "numbers", "big"], namespace)
    assert {name: value["kind"] for name, value in found.items()} == dict.fromkeys(namespace, "table")
    assert "<td>&lt;East&gt;</td><td></td>" in found["sales"]["html"]  # a missing amount is empty
    assert found["sales"]["html"] == found["arrow"]["html"]
    assert "first 50 of 2,500 rows" in found["numbers"]["html"]
    assert len(json.loads(found["numbers"]["json"])) == 1000
    assert "first 50 of 1,204 rows" in found["big"]["html"]
    assert json.loads(found["sales"]["json"])[2] == {"store": "<East>", "amount": None}
    assert found["sales"]["size"] == "3 rows, 2 columns"


def test_values_a_picture_and_what_is_missing() -> None:
    class Picture:
        def _repr_png_(self) -> bytes:
            return b"\x89PNG made up"

    class Broken:
        def __str__(self) -> str:
            raise RuntimeError("no")

    namespace = {"total": 42, "name": HOSTILE, "chart": Picture(), "odd": Broken()}
    found = kernel_side.values(["total", "name", "chart", "odd", "nope"], namespace)
    assert found["total"]["html"] == "42" and found["name"]["html"] == rules.escape(HOSTILE)
    assert found["chart"]["kind"] == "picture" and "data:image/png;base64," in found["chart"]["html"]
    assert found["odd"]["html"] == "(odd could not be shown: RuntimeError)"
    assert found["nope"]["kind"] == "missing"
    marks = json.loads(kernel_side.marks(["total", "nope"], namespace))
    assert marks["total"] == rules.digest(found["total"]) and set(marks) == {"total", "nope"}
    namespace["total"] = 43
    assert json.loads(kernel_side.marks(["total"], namespace))["total"] != marks["total"]


def test_polars_and_matplotlib_are_told_by_their_shape() -> None:
    """Neither library is installed here: stand-ins with the methods the kernel's side calls (Polars'
    head, rows, height, width; matplotlib's savefig)."""

    class DataFrame:
        __module__ = "polars.dataframe.frame"
        columns = ("store", "amount")
        height, width = 120, 2

        def head(self, n: int) -> DataFrame:
            return self

        def rows(self) -> list[tuple[Any, ...]]:
            return [("North", i) for i in range(120)]

    class Figure:
        __module__ = "matplotlib.figure"

        def savefig(self, target: Any, **options: Any) -> None:
            assert options["format"] == "png"
            target.write(b"\x89PNG made up")

    found = kernel_side.values(["frame", "chart"], {"frame": DataFrame(), "chart": Figure()})
    assert found["frame"]["kind"] == "table" and "first 50 of 120 rows" in found["frame"]["html"]
    assert found["chart"]["kind"] == "picture"
    assert found["chart"]["html"].startswith('<img class="sag-picture" alt="chart"')


def test_the_cells_output_is_the_filled_design_and_what_filled_it() -> None:
    data, metadata = kernel_side.bundle(CARD, {"total": 42, "region": "<North>"})
    assert data["text/html"] == CARD.replace("{{ total }}", "42").replace("{{ region }}", "&lt;North&gt;")
    detail = data[kernel_side.MIME]
    assert set(detail["values"]) == {"total", "region"} and detail["missing"] == []
    assert detail["marks"]["total"] == rules.digest(detail["values"]["total"])
    assert metadata == {"swissarmygrid": {"html_cell": True}}
    json.dumps(data)  # it travels as JSON


# ===== the server: a real kernel =====


def run(client: TestClient, kernel: str, body: dict[str, Any]) -> list[dict[str, Any]]:
    with client.stream("POST", f"/workbench/kernels/{kernel}/execute", headers=AUTH, json=body) as response:
        assert response.status_code == 200, response.read()
        return [json.loads(line) for line in response.iter_lines() if line.strip()]


def test_an_html_cell_runs_in_a_kernel_and_goes_out_of_date_with_its_variables(tmp_path: Path) -> None:
    with make_client(tmp_path, workbench_dir=tmp_path / "home" / "SwissArmyGrid") as client:
        kernel = client.post("/workbench/kernels", headers=AUTH, json={}).json()["kernel"]
        setup = (
            "import pandas as pd\ntotal = 42\nsales = pd.DataFrame({'store': ['<North>'], 'amount': [10]})"
        )
        assert run(client, kernel, {"code": setup})[-1]["done"]["ok"]
        template = "<h1>{{ total }} orders</h1>{{ sales }}<p>{{ nope }}</p>"
        lines = run(client, kernel, {"code": template, "kind": "html"})
        assert lines[-1]["done"]["ok"]
        output = next(item for item in lines if item.get("output_type") == "display_data")
        design = output["data"]["text/html"]
        assert design.startswith("<h1>42 orders</h1><table") and "<td>&lt;North&gt;</td>" in design
        assert "{{ nope }} not found" in design
        detail = output["data"][kernel_side.MIME]
        assert detail["missing"] == ["nope"] and output["metadata"]["swissarmygrid"]["html_cell"] is True

        # The design again, from the values the run gave: no kernel needed.
        again = client.post(
            "/workbench/html/fill",
            headers=AUTH,
            json={"html": "<b>{{ total }}</b>", "values": detail["values"]},
        ).json()
        assert again["html"] == "<b>42</b>" and again["names"] == ["total"]
        assert again["policy"] == rules.FRAME_POLICY
        waiting = client.post("/workbench/html/fill", headers=AUTH, json={"html": "<b>{{ later }}</b>"})
        assert waiting.json()["waiting"] == ["later"]

        # A variable it names changes: its mark does, and only its.
        path = f"/workbench/kernels/{kernel}/html-marks"
        before = client.post(path, headers=AUTH, json={"names": ["total", "sales", "nope"]}).json()
        assert before == {"busy": False, "marks": detail["marks"]}
        assert run(client, kernel, {"code": "total = 43"})[-1]["done"]["ok"]
        after = client.post(path, headers=AGENT, json={"names": ["total", "sales"]}).json()["marks"]
        assert after["total"] != before["marks"]["total"] and after["sales"] == before["marks"]["sales"]

        for bad in ({}, {"names": "total"}, {"names": ["a b"]}, {"names": ["x"] * 500}):
            assert client.post(path, headers=AUTH, json=bad).status_code == 400
        wrong: tuple[dict[str, Any], ...] = (
            {},
            {"html": 1},
            {"html": "x", "values": {"a": 1}},
            {"html": "x" * 1_000_001},
        )
        for bad in wrong:
            assert client.post("/workbench/html/fill", headers=AUTH, json=bad).status_code == 400
        assert client.post("/workbench/html/fill", json={"html": "x"}).status_code == 401
        client.delete(f"/workbench/kernels/{kernel}", headers=AUTH)


def test_an_html_cell_is_saved_and_opened_again(tmp_path: Path) -> None:
    with make_client(tmp_path, workbench_dir=tmp_path / "home" / "SwissArmyGrid") as client:
        path = str(tmp_path / "story.ipynb")
        cells = [{"kind": "html", "source": CARD, "height": 280}, {"kind": "code", "source": "total = 1"}]
        saved = client.post("/workbench/save", headers=AUTH, json={"path": path, "cells": cells})
        assert saved.status_code == 200, saved.text
        assert json.loads(Path(path).read_text(encoding="utf-8"))["cells"][0]["source"][0] == "%%html\n"
        opened = client.post("/workbench/open", headers=AUTH, json={"path": path}).json()
        first = opened["cells"][0]
        assert (first["kind"], first["source"], first["height"], first["number"]) == ("html", CARD, 280, 1)


# ===== the agent's commands =====


def test_the_agent_runs_fills_and_checks_an_html_cell(live: Live, tmp_path: Path) -> None:  # noqa: F811
    """The golden rule: an HTML cell run in a kernel, its design filled again from the run's values,
    its names' marks read, and a notebook with an HTML cell run and saved."""
    kernel = command("workbench_kernel_start", path=str(tmp_path / "x.py"))["kernel"]
    try:
        assert data_of(execute("workbench_run", dict(kernel=kernel, code="total = 42")))["done"]["ok"]
        ran = data_of(
            execute("workbench_run", dict(kernel=kernel, kind="html", code="<b>{{ total }}</b>{{ nope }}"))
        )
        cell = ran["outputs"][0]
        assert cell["design"].startswith("<b>42</b>") and cell["missing"] == ["nope"]
        again = data_of(
            execute("workbench_html_fill", {"html": "<i>{{ total }}</i>", "values": cell["values"]})
        )
        assert again["html"] == "<i>42</i>"
        marks = command("workbench_html_marks", kernel=kernel, names=["total"])
        assert marks == {"busy": False, "marks": {"total": cell["marks"]["total"]}}
        book = tmp_path / "story.ipynb"
        command(
            "workbench_save",
            path=str(book),
            cells=[{"kind": "html", "source": "<h1>{{ total }} orders</h1>", "height": 200}],
        )
        done = data_of(execute("workbench_run_notebook", dict(path=str(book), kernel=kernel)))
        assert done["results"][0]["outputs"][0]["design"] == "<h1>42 orders</h1>"
        saved = data_of(execute("workbench_open", {"path": str(book)}))["cells"][0]
        assert saved["kind"] == "html" and saved["height"] == 200
        assert saved["outputs"][0]["data"]["text/html"] == "<h1>42 orders</h1>"
    finally:
        command("workbench_kernel", kernel=kernel, action="stop")
