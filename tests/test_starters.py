"""The built-in starter pack (docs/ideas.md, the starter pack, 2026-11-15): every starter reads, is in its
family, and fills; snippets' placeholders and how a value is written where it stands; the pack in the
app (read-only, Copy as your own, a snippet's form and its filled text) and for the agent."""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import controllers, html_cells, snippets
from swissarmybench.domain.blades import FAMILIES, STARTERS, parse_blade, read_blade, write_blade
from swissarmybench.domain.snippets import SnippetError, fill, placeholders
from swissarmybench.domain.streamlit_cells import facts, text_code
from tests.conftest import AUTH, push

FOLDER = Path(__file__).resolve().parents[1] / "src" / "swissarmybench" / "starters"
FILES = sorted(FOLDER.glob("*.blade.py"))

# What a starter's placeholders are filled with in these tests: the made-up `orders` table's columns,
# the same names the Streamlit run tests make (tests/test_starters_streamlit.py).
VALUES: dict[str, str] = {
    "table": "orders",
    "column": "region",
    "measure": "Total Sales",
    "date table": "Date",
    "date column": "Date",
    "date period column": "Year",
    "date year column": "Year",
    "date month column": "Month",
    "group table": "Customer",
    "group column": "Region",
    "value column": "amount",
    "flag column": "shipped",
    "category column": "region",
    "number column": "amount",
    "search column": "product",
    "lines table": "lines",
}


def blades() -> list[dict[str, Any]]:
    return [read_blade(p.read_text(encoding="utf-8")) | {"file": p.name} for p in FILES]


def filled(blade: dict[str, Any]) -> str:
    return fill(blade["code"], blade["language"], VALUES)


# ===== the pack =====


def test_every_starter_reads_and_is_in_one_of_the_families_in_order() -> None:
    found = blades()
    assert len(found) == 169
    counts = Counter(b["family"] for b in found)
    assert counts == {
        "Power BI": 13,
        "Dataverse": 2,
        "Excel": 12,
        "Files": 3,
        "DAX": 11,
        "HTML": 10,
        "Markdown": 10,
        "Streamlit": 29,
        "Controllers": 5,
        "Text and layout": 9,
        "Components": 9,
        "Write": 56,
    }
    assert set(counts) == set(FAMILIES)
    names = [b["name"].casefold() for b in found]
    assert len(set(names)) == len(names)
    for blade in found:
        assert blade["description"] and len(blade["description"]) <= 90, blade["name"]
        parse_blade(blade)  # every save check passes
        assert write_blade(parse_blade(blade).to_json()) == (FOLDER / blade["file"]).read_text(
            encoding="utf-8"
        )


@pytest.mark.parametrize(
    "path", [p for p in FILES if 'kind = "other"' in p.read_text(encoding="utf-8")], ids=lambda p: p.name
)
def test_a_python_starter_makes_one_function_and_its_settings_are_found(path: Path) -> None:
    blade = parse_blade(read_blade(path.read_text(encoding="utf-8")))
    tree = ast.parse(blade.code)
    functions = [s.name for s in tree.body if isinstance(s, ast.FunctionDef) and not s.name.startswith("_")]
    assert functions == [blade.variable], "the one public function is the blade's variable"
    if blade.family == "Power BI":
        from swissarmybench.domain.blades import detect_settings

        assert [(s.key, s.value) for s in detect_settings(blade.code)] == [("WORKSPACE", "Finance")]
    if blade.family == "Dataverse":
        from swissarmybench.domain.blades import detect_settings

        assert [(s.key, s.value) for s in detect_settings(blade.code)] == [("ENVIRONMENT", "Sales CRM")]


# ===== snippets: placeholders, and writing a value where it stands =====


def test_placeholders_are_read_from_their_names() -> None:
    found = placeholders(
        "'<<date table>>'[<<date year column: Year>>] <<measure>> <<name: by_{column}>> <<column>> "
        "<<label>> <<count: 10>> <<title>>"
    )
    assert [(p.name, p.kind, p.default, p.follows) for p in found] == [
        ("date table", "table", "", ""),
        ("date year column", "column", "Year", "date table"),
        ("measure", "measure", "", ""),
        ("name", "name", "by_{column}", "column"),
        ("column", "column", "", ""),
        ("label", "text", "", "column"),
        ("count", "number", "10", ""),
        ("title", "text", "", ""),
    ]
    assert found[1].label == "Date year column"


def test_defaults_names_and_labels_follow_the_column() -> None:
    text = "<<name: by_{column}>> = <<table>>['<<column>>']  # <<label>> <<plain name>>"
    assert snippets.resolved(text, "streamlit", {"table": "orders", "column": "order_date"}) == {
        "table": "orders",
        "column": "order_date",
        "label": "Order date",
        "plain name": "order_date",
        "name": "by_order_date",
    }
    with pytest.raises(SnippetError, match="Fill in Table"):
        fill(text, "streamlit", {"column": "x"})


def test_dax_doubles_the_quote_that_closes_each_place() -> None:
    text = """-- <<measure>> of '<<table>>'
EVALUATE ROW ( "<<measure>>", [<<measure>>], "n", <<count: 3>>, "t", COUNTROWS ( '<<table>>' ) )"""
    out = fill(text, "dax", {"measure": 'Say "hi" [x]', "table": "O'Brien"})
    assert (
        out
        == """-- Say "hi" [x] of 'O'Brien'
EVALUATE ROW ( "Say ""hi"" [x]", [Say "hi" [x]]], "n", 3, "t", COUNTROWS ( 'O''Brien' ) )"""
    )
    with pytest.raises(SnippetError, match="Count is a number"):
        fill(text, "dax", {"measure": "m", "table": "t", "count": "3; DROP"})


def test_python_takes_names_bare_and_text_inside_strings() -> None:
    text = 'x = <<table>>["<<column>>"]  # <<column>>\ny = f"<<label: {a}>>: {x}"\nz = \'<<label>>\''
    out = fill(text, "streamlit", {"table": "orders", "column": 'a"b\\c', "label": "It's {1}"})
    assert out == 'x = orders["a\\"b\\\\c"]  # a"b\\c\ny = f"It\\\'s {{1}}: {x}"\nz = \'It\\\'s {1}\''
    ast.parse(out)
    with pytest.raises(SnippetError, match="is a Python name or a number here"):
        fill(text, "streamlit", {"table": "orders; import os", "column": "c"})
    with pytest.raises(SnippetError, match="is a Python name"):
        fill(text, "streamlit", {"table": "class", "column": "c"})


def test_html_escapes_markup_and_takes_only_a_name_in_an_html_cells_braces() -> None:
    text = '<p title="<<label>>"><<label>></p>{{ <<table>> }}'
    assert fill(text, "html", {"label": '<b>"x"</b>', "table": "orders"}) == (
        '<p title="&lt;b&gt;&quot;x&quot;&lt;/b&gt;">&lt;b&gt;&quot;x&quot;&lt;/b&gt;</p>{{ orders }}'
    )
    with pytest.raises(SnippetError, match="is a Python name"):
        fill(text, "html", {"label": "x", "table": "orders }}<script>"})


def test_markdown_escapes_the_marks_that_format_and_takes_code_as_typed() -> None:
    text = "# <<title>>\n\n**{{ <<total name>> }}** in `<<column>>`"
    # A value reads as typed, but for the marks that would format, link, fill a name or become markup.
    values = {"title": "Made-up *sales*, 2026-01-31 [draft] <b>", "total name": "total", "column": "c"}
    out = fill(text, "markdown", values)
    assert out.startswith("# Made-up \\*sales\\*, 2026-01-31 \\[draft\\] &lt;b&gt;\n\n**{{ total }}**")
    # Inside a code span the value goes as it is (an underscore is not escaped there); no backtick.
    filled = fill(text, "markdown", {"title": "T", "total name": "total", "column": "order_date"})
    assert filled.endswith("in `order_date`")
    with pytest.raises(SnippetError, match="cannot hold a backtick"):
        fill(text, "markdown", {"title": "T", "total name": "total", "column": "a`b"})
    # Inside a Markdown cell's braces only a name, as in an HTML cell's; a typed value cannot make one.
    with pytest.raises(SnippetError, match="is a Python name"):
        fill(text, "markdown", {"title": "T", "total name": "x }} {{ y", "column": "c"})
    assert "{{" not in fill("<<title>>", "markdown", {"title": "{{ secret }}"})


def test_a_broken_placeholder_or_a_line_break_is_refused() -> None:
    with pytest.raises(SnippetError, match="Line 2: a placeholder is <<name>>"):
        snippets.check("ok\n<<Not Lowercase>>", "dax")
    with pytest.raises(SnippetError, match="is one line"):
        fill("<<title>>", "html", {"title": "a\nb"})
    with pytest.raises(SnippetError, match="language is one of"):
        snippets.check("x", "sql")


# ===== every snippet starter =====


def _balanced(text: str) -> bool:
    """DAX's brackets and quotes pair up (strings, table names and comments skipped)."""
    stack: list[str] = []
    pairs = {")": "(", "]": "["}
    for line in text.split("\n"):
        line = re.sub(r"--.*$", "", re.sub(r'"(?:[^"]|"")*"', '""', re.sub(r"'(?:[^']|'')*'", "''", line)))
        if line.count('"') % 2 or line.count("'") % 2:
            return False
        for char in line:
            if char in "([":
                stack.append(char)
            elif char in ")]":
                if not stack or stack.pop() != pairs[char]:
                    return False
    return not stack


@pytest.mark.parametrize(
    "blade", [b for b in blades() if b.get("language") == "dax"], ids=lambda b: b["name"]
)
def test_a_dax_snippet_fills_and_is_well_formed(blade: dict[str, Any]) -> None:
    text = filled(blade)
    assert "<<" not in text and "EVALUATE" in text and text.strip()
    assert _balanced(text), text


@pytest.mark.parametrize(
    "blade", [b for b in blades() if b.get("language") == "html"], ids=lambda b: b["name"]
)
def test_an_html_snippet_fills_with_inline_styles_and_nothing_from_outside(blade: dict[str, Any]) -> None:
    text = filled(blade)
    assert "<<" not in text and text.strip()
    assert not re.search(r"https?://|//[a-z]|<link|@import|url\(|src=", text, re.IGNORECASE)
    assert text.count("<div") == text.count("</div>")


@pytest.mark.parametrize(
    "blade", [b for b in blades() if b.get("language") == "markdown"], ids=lambda b: b["name"]
)
def test_a_markdown_snippet_says_the_names_it_reads_and_fills_as_text(blade: dict[str, Any]) -> None:
    text = filled(blade)
    assert "<<" not in text and text.strip()
    # Its description ends with the names its {{ }} read, as filled with its own defaults.
    said = re.search(r"\(reads (.+)\)$", blade["description"])
    assert said, blade["description"]
    listed = [] if said.group(1) == "no names" else said.group(1).split(", ")
    assert html_cells.names(text) == listed
    # Markdown only: nothing from outside, and no HTML (a Streamlit page's st.markdown shows it as text).
    assert not re.search(r"https?://|<[a-z!/]", text, re.IGNORECASE)
    # On a page it is st.markdown, its names the reads the run order counts.
    page = text_code("markdown", text, 3)
    assert facts(page).reads == ("st", *listed) and "unsafe" not in page


def _header(text: str, word: str) -> list[str]:
    found = re.search(rf"^# {word}: (.*)$", text, re.MULTILINE)
    assert found, f"no '# {word}:' line"
    if word == "Makes":
        # The Makes line is the cell's contract (domain/controllers.py): its names, by Python's parser.
        contract = controllers.describe(text)
        assert contract.problems == (), contract.problems
        return [m.name for m in contract.makes if m.declared]
    words = found.group(1).split(" (")[0]
    return [] if words.strip() == "nothing" else [w.strip() for w in words.split(",")]


def _streamlit_calls(tree: ast.AST) -> set[str]:
    """Every st.<function> (and st.column_config.<function>, st.session_state) the code uses; a
    component's by its whole name (st.components.v2.component, not st.components)."""
    found: set[str] = set()
    for node in ast.walk(tree):
        chain: list[str] = []
        part: ast.AST = node
        while isinstance(part, ast.Attribute):
            chain.insert(0, part.attr)
            part = part.value
        if isinstance(part, ast.Name) and part.id == "st" and chain[:1] == ["components"]:
            if len(chain) == 3:
                found.add(".".join(["st", *chain]))
            continue
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "st":
            found.add(f"st.{node.attr}")
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "st"
        ):
            found.add(f"st.{node.value.attr}.{node.attr}")
    return found - {"st.column_config"}


STREAMLIT = [b for b in blades() if b.get("language") == "streamlit"]


@pytest.mark.parametrize("blade", STREAMLIT, ids=lambda b: b["name"])
def test_a_streamlit_piece_is_python_and_its_header_says_what_it_makes_reads_and_uses(
    blade: dict[str, Any],
) -> None:
    text = filled(blade)
    tree = ast.parse(text)
    found = facts(text)
    imported = {
        (a.asname or a.name.split(".")[0])
        for node in tree.body
        if isinstance(node, ast.Import | ast.ImportFrom)
        for a in node.names
    }
    makes = [n for n in found.makes if n not in imported and not n.startswith("_")]
    assert sorted(makes) == sorted(_header(text, "Makes"))
    assert [n for n in found.reads if not n.startswith("_")] == _header(text, "Reads")
    listed = set(re.findall(r"^#   (st\.[\w.]+)", text, re.MULTILINE))
    assert _streamlit_calls(tree) == listed
    assert text.startswith(f"# {blade['name'].removeprefix('Streamlit ')[:1].upper()}") or text.startswith(
        "# "
    )
    # the lines a learner trips on are explained where they stand
    if re.search(r"key=", text):
        assert "duplicate widget" in text
    if "cache_data" in text:
        assert "forgets" in text
    if "session_state[" in text:
        assert "survives the reruns" in text


def test_every_streamlit_piece_names_its_cell() -> None:
    for blade in STREAMLIT:
        given = snippets.resolved(blade["code"], "streamlit", VALUES)
        named = snippets.cell_name(blade.get("cell_name", ""), given, blade["name"])
        assert named and "<<" not in named, blade["name"]
    selectbox = next(b for b in STREAMLIT if b["name"] == "Streamlit selectbox filter")
    given = snippets.resolved(selectbox["code"], "streamlit", {"table": "orders", "column": "region"})
    assert snippets.cell_name(selectbox["cell_name"], given, "x") == "Region filter"
    assert given["name"] == "by_region"


# ===== the pack in the app =====


def test_the_pack_is_listed_by_family_and_kept_apart_from_your_blades(client: TestClient) -> None:
    listed = client.get("/blades/starters", headers=AUTH).json()
    assert listed["pack"] == STARTERS
    assert [f["family"] for f in listed["families"]] == list(FAMILIES)
    first = listed["families"][0]["blades"][0]
    assert first["source"] == "starter" and first["pack"] == STARTERS
    dax = next(f for f in listed["families"] if f["family"] == "DAX")["blades"]
    ytd = next(b for b in dax if b["name"] == "DAX year to date")
    assert ytd["language"] == "dax" and [p["name"] for p in ytd["placeholders"]] == [
        "measure",
        "table",
        "date table",
        "date column",
    ]
    assert client.get("/blades", headers=AUTH).json()["blades"] == []  # your own list stays yours
    got = client.get("/blades/DAX%20year%20to%20date", headers=AUTH).json()
    assert got["source"] == "starter" and got["placeholders"][0]["kind"] == "measure"


def test_a_starter_is_read_only_and_copies_as_your_own(client: TestClient) -> None:
    name = "Excel%20add%20sheet"
    starter = client.get(f"/blades/{name}", headers=AUTH).json()
    changed = client.put(f"/blades/{name}", json=starter | {"description": "mine"}, headers=AUTH)
    assert changed.status_code == 400 and "starter (read-only): copy it as your own" in changed.text
    assert "comes with the app" in client.delete(f"/blades/{name}", headers=AUTH).text
    copied = client.post(f"/blades/{name}/copy", headers=AUTH).json()
    assert copied["name"] == "Excel add sheet copy" and copied["source"] == "saved"
    again = client.post(f"/blades/{name}/copy", headers=AUTH).json()
    assert again["name"] == "Excel add sheet copy 2"
    named = client.post(f"/blades/{name}/copy", json={"name": "My sheets"}, headers=AUTH).json()
    assert named["name"] == "My sheets"
    mine = client.get("/blades/My%20sheets", headers=AUTH).json()
    assert mine["code"] == starter["code"] and mine["family"] == "Excel" and mine["variable"] == "add_sheet"
    edited = client.put("/blades/My%20sheets", json=mine | {"description": "mine"}, headers=AUTH)
    assert edited.status_code == 200
    assert {b["name"] for b in client.get("/blades", headers=AUTH).json()["blades"]} == {
        "Excel add sheet copy",
        "Excel add sheet copy 2",
        "My sheets",
    }
    taken = client.post(f"/blades/{name}/copy", json={"name": "My sheets"}, headers=AUTH)
    assert taken.status_code == 400 and "already exists" in taken.text


def test_a_snippet_gives_its_form_and_its_filled_text(client: TestClient) -> None:
    pushed = push(client, "orders", pa.table({"region": ["North", "South"], "amount": [1.5, 2.0]}))
    assert pushed.status_code == 200, pushed.text
    form = client.get("/blades/Streamlit%20selectbox%20filter/snippet", headers=AUTH).json()
    assert (
        form["language"] == "streamlit" and form["cell"] == "code" and form["cell_words"] == "a Python cell"
    )
    assert {"name": "orders", "columns": ["region", "amount"], "measures": []} in form["options"]["tables"]
    done = client.post(
        "/blades/Streamlit%20selectbox%20filter/snippet",
        json={"values": {"table": "orders", "column": "region"}},
        headers=AUTH,
    ).json()
    assert done["cell_name"] == "Region filter" and "by_region = orders if _pick" in done["text"]
    refused = client.post("/blades/DAX%20year%20to%20date/snippet", json={"values": {}}, headers=AUTH)
    assert refused.status_code == 400 and "Fill in Measure, Table, Date table, Date column" in refused.text
    dax = client.get("/blades/DAX%20year%20to%20date/snippet?dataset=Finance/Sales%20model", headers=AUTH)
    assert dax.json()["options"] == {"tables": [], "dataset": "Finance/Sales model"}  # no catalog loaded
    assert "nothing to run" in client.post("/blades/DAX%20year%20to%20date/test", headers=AUTH).text
