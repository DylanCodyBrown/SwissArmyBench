"""Every new file is named and written by the server (the owner, 2026-11-27: "Everything should get a name or
the file is not created and yes every file should go scaffolding file on the back. The list of follow-ups
available should change with projects"), the documentation starters ("The idea is the context documentation
for a project can be created and edited"), text documents and their previews, a Markdown file's blocks
through the route and the agent's command, the Docs group, context.md's docs, and ARCHITECTURE.md kept when
edited by hand."""

from __future__ import annotations

import base64
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.cli import commands
from swissarmybench.domain import code_tree, context_md, new_files, text_documents, workbench_pages
from swissarmybench.domain import markdown_blocks as blocks
from tests.conftest import AGENT, AUTH, make_client, push

ORDERS = pa.table({"order_id": [1, 2, 3], "customer": ["Avery Ltd", "Birch Co", "Cedar Inc"]})
NEW = "/scripts/files/new"


def ok(answer: Any) -> Any:
    assert answer.status_code == 200, answer.text
    return answer.json()


def project(client: TestClient, tmp_path: Path, kind: str | None = None) -> Path:
    body = {"path": str(tmp_path / "work" / "shop")} | ({"type": kind} if kind else {})
    state = ok(client.post("/project/new", json=body, headers=AUTH))
    return Path(state.get("folder") or state["project"]["folder"])


def type_ids(client: TestClient) -> list[str]:
    return [t["id"] for t in ok(client.get(NEW, headers=AUTH))["types"]]


# ===== no name, no file; no project: any folder =====


def test_no_name_no_file(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        folder = project(client, tmp_path)
        before = sorted(p.name for p in folder.rglob("*") if p.is_file())
        for body in ({"type": "python"}, {"type": "sql", "name": "  "}, {"type": "markdown", "name": None}):
            refused = client.post(NEW, json=body, headers=AUTH)
            assert refused.status_code == 400, body
            assert refused.json()["error"] == new_files.NO_NAME
        assert sorted(p.name for p in folder.rglob("*") if p.is_file()) == before


def test_with_no_project_open_a_file_is_written_in_the_folder_named(tmp_path: Path) -> None:
    loose = tmp_path / "loose files"
    loose.mkdir()
    with make_client(tmp_path) as client:
        options = ok(client.get(NEW, headers=AUTH))
        assert options["project"] is False and options["folders"] == []
        assert "python" in [t["id"] for t in options["types"]]
        made = ok(
            client.post(NEW, json={"type": "python", "name": "tidy", "folder": str(loose)}, headers=AUTH)
        )
        assert Path(made["path"]) == loose / "tidy.py" and made["relative"] == "tidy.py" and made["made"]
        compile((loose / "tidy.py").read_text(encoding="utf-8"), "tidy.py", "exec")
        note = ok(
            client.post(NEW, json={"type": "markdown", "name": "notes", "folder": str(loose)}, headers=AUTH)
        )
        assert (loose / "notes.md").read_text(encoding="utf-8") == "# notes\n" and note["page"] == "scripts"
        # The check writes nothing; a taken name, a folder that is not whole or not there: one sentence.
        would = {"type": "sql", "name": "q", "folder": str(loose), "check": True}
        assert ok(client.post(NEW, json=would, headers=AUTH))["made"] is False
        assert not (loose / "q.sql").exists()
        taken = client.post(NEW, json={"type": "python", "name": "tidy", "folder": str(loose)}, headers=AUTH)
        assert (
            taken.status_code == 409
            and taken.json()["error"] == "tidy.py is there already: pick another name."
        )
        for folder, words in (
            ("scripts", "not a whole path"),
            (None, "No project is open"),
            (str(loose / "no"), "no folder"),
        ):
            refused = client.post(NEW, json={"type": "python", "name": "x", "folder": folder}, headers=AUTH)
            assert refused.status_code in (400, 403) and words in refused.json()["error"], refused.text
        # A loose file opens as any other (its own Python).
        opened = ok(client.post("/workbench/open", json={"path": made["path"]}, headers=AUTH))
        assert opened["kind"] == "script"


# ===== the types follow the project =====


def test_a_streamlit_projects_list_has_its_types_and_a_plain_ones_does_not(tmp_path: Path) -> None:
    base = [t.id for t in new_files.TYPES]
    with make_client(tmp_path) as client:
        assert type_ids(client) == base  # no project: the base's, all of them made loose
        folder = project(client, tmp_path)
        assert type_ids(client) == base  # a plain (BI) project
        refused = client.post(NEW, json={"type": "widget", "name": "kpi"}, headers=AUTH)
        assert refused.status_code == 400 and "type is one of" in refused.json()["error"]
        ok(client.post("/project/close", json={}, headers=AUTH))
        assert not list(folder.glob("widgets/*"))

    with make_client(tmp_path / "second") as client:
        folder = project(client, tmp_path / "second", "streamlit")
        listed = ok(client.get(NEW, headers=AUTH))["types"]
        assert [t["id"] for t in listed] == [*base, "widget", "canvas"]
        widget = next(t for t in listed if t["id"] == "widget")
        assert widget["label"] == "Widget" and widget["asks"] == ["name"] and widget["loose"] is False
        # Each is made by the extension's own "new" path: a widget in the project's widgets/, a canvas file.
        would = ok(client.post(NEW, json={"type": "widget", "name": "kpi_tile", "check": True}, headers=AUTH))
        assert would["relative"] == "widgets/kpi_tile.widget.py" and would["made"] is False
        assert not (folder / "widgets" / "kpi_tile.widget.py").exists()
        made = ok(client.post(NEW, json={"type": "widget", "name": "kpi_tile"}, headers=AUTH))
        assert made["made"] is True and made["address"] == "widgets?name=kpi_tile"
        text = (folder / "widgets" / "kpi_tile.widget.py").read_text(encoding="utf-8")
        assert "swissarmybench-widget" in text
        assert client.post(NEW, json={"type": "widget", "name": "kpi_tile"}, headers=AUTH).status_code == 409
        assert client.post(NEW, json={"type": "widget", "name": "Not Valid"}, headers=AUTH).status_code == 400
        assert client.post(NEW, json={"type": "widget"}, headers=AUTH).json()["error"] == new_files.NO_NAME
        canvas = ok(client.post(NEW, json={"type": "canvas", "name": "Sales"}, headers=AUTH))
        assert canvas["relative"] == "sales.canvas.json" and (folder / "sales.canvas.json").is_file()
        assert canvas["address"].startswith("canvas?path=") and canvas["page"] == "canvas"
        assert client.post(NEW, json={"type": "canvas", "name": "Sales"}, headers=AUTH).status_code == 409


def test_an_extensions_type_is_read_loosely_and_never_takes_a_base_types_id() -> None:
    raw = {"id": "widget", "label": "Widget", "ending": ".widget.py", "page": "widgets"}
    made = new_files.from_extension(raw)
    assert made is not None and made.maker == "widget" and made.loose is False and made.asks == ("name",)
    for bad in (None, {}, {"id": "x"}, raw | {"id": "python"}, raw | {"ending": "widget"}):
        assert new_files.from_extension(bad) is None
    # With no project open only the loose ones are offered; a project-only one says to open a project.
    assert [t.id for t in new_files.offered([raw], project=False)] == [t.id for t in new_files.TYPES]
    assert new_files.offered([raw], project=True)[-1].id == "widget"
    with pytest.raises(new_files.NewFileError, match="Open a project first"):
        new_files.type_of("widget", [raw], project=False)


def test_the_agents_types_follow_the_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with make_client(tmp_path) as client:

        def call(method: str, path: str, body: Any = None, **_: Any) -> Any:
            return ok(client.request(method, path, json=body, headers=AGENT))

        monkeypatch.setattr("swissarmybench.cli.api.call", call)
        run = commands.REGISTRY["workbench_file"].run
        assert "widget" not in [t["id"] for t in run({"action": "types"})["types"]]
        folder = project(client, tmp_path, "streamlit")
        assert [t["id"] for t in run({"action": "types"})["types"]][-2:] == ["widget", "canvas"]
        made = run({"action": "new", "type": "diagram", "to": "flow", "variant": "sequence"})
        assert made["relative"] == "docs/diagrams/flow.mmd"
        assert (
            (folder / "docs" / "diagrams" / "flow.mmd")
            .read_text(encoding="utf-8")
            .startswith("sequenceDiagram\n")
        )
        assert run({"action": "new", "type": "widget"})["error"].startswith("Give the file a name")


# ===== the documentation starters =====


class _Html(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.open: list[str] = []
        self.seen: list[str] = []
        self.doctype = ""

    def handle_decl(self, decl: str) -> None:
        self.doctype = decl

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        self.seen.append(tag)
        if tag not in ("meta", "link", "br", "img", "hr"):
            self.open.append(tag)

    def handle_startendtag(self, tag: str, attrs: Any) -> None:
        self.seen.append(tag)

    def handle_endtag(self, tag: str) -> None:
        assert self.open and self.open[-1] == tag, f"</{tag}> closes {self.open[-1:]}"
        self.open.pop()


def test_the_html_starter_is_a_valid_small_page_that_loads_nothing() -> None:
    text = new_files.starter(new_files.type_of("html"), "sales & <more>.html")
    read = _Html()
    read.feed(text)
    read.close()
    assert read.doctype.lower() == "doctype html" and read.open == []
    assert read.seen[:3] == ["html", "head", "meta"] and {"title", "body", "h1"} <= set(read.seen)
    assert "<title>sales &amp; &lt;more&gt;</title>" in text
    assert (
        "http" not in text and "src=" not in text
    )  # nothing from outside: the preview's frame loads nothing


def test_each_diagram_kind_has_its_own_small_starter() -> None:
    kind = new_files.type_of("diagram")
    firsts = {
        "flowchart": "flowchart TD",
        "class": "classDiagram",
        "sequence": "sequenceDiagram",
        "state": "stateDiagram-v2",
        "er": "erDiagram",
        "gantt": "gantt",
    }
    assert [v for v, _ in kind.variants] == list(firsts) and "variant" in kind.asks
    for variant, first in firsts.items():
        text = new_files.starter(kind, "d.mmd", {"variant": variant})
        assert text.splitlines()[0] == first and text.endswith("\n") and len(text.splitlines()) >= 5
    assert new_files.variant_of(kind, None) == "flowchart"
    with pytest.raises(new_files.NewFileError, match="variant is one of"):
        new_files.variant_of(kind, "plantuml")
    assert (
        new_files.named(kind, "flow") == "flow.mmd"
        and new_files.named(kind, "flow.mermaid") == "flow.mermaid"
    )


def test_the_documentation_starters_write_real_named_files(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        folder = project(client, tmp_path)
        push(client, "orders", ORDERS)
        made = ok(client.post(NEW, json={"type": "decision", "name": "0001-use-duckdb"}, headers=AUTH))
        assert made["relative"] == "docs/decisions/0001-use-duckdb.md"
        text = (folder / made["relative"]).read_text(encoding="utf-8")
        assert text.startswith("# Use duckdb\n\n- Date: 20")
        assert [b.text for b in blocks.blocks(text) if b.kind == "heading"] == [
            "# Use duckdb",
            "## Context",
            "## Decision",
            "## Consequences",
        ]
        # The data dictionary: the open tables' columns by name and type, never a value.
        made = ok(client.post(NEW, json={"type": "dictionary", "name": "data-dictionary"}, headers=AUTH))
        text = (folder / "docs" / "data-dictionary.md").read_text(encoding="utf-8")
        assert (
            "## orders\n" in text
            and "| order_id | BIGINT |  |" in text
            and "| customer | VARCHAR |  |" in text
        )
        assert "Avery" not in text and "Birch" not in text and "3" not in text.replace("BIGINT", "")
        # README is there already (the project's scaffold): refused, never written over.
        taken = client.post(NEW, json={"type": "readme", "name": "README"}, headers=AUTH)
        assert taken.status_code == 409
        readme = ok(
            client.post(NEW, json={"type": "readme", "name": "README", "folder": "docs"}, headers=AUTH)
        )
        assert (folder / readme["relative"]).read_text(encoding="utf-8").startswith("# shop\n")
        page = ok(client.post(NEW, json={"type": "html", "name": "report"}, headers=AUTH))
        assert page["relative"] == "docs/report.html" and page["kind"] == "text"
        diagram = ok(
            client.post(NEW, json={"type": "diagram", "name": "model", "variant": "er"}, headers=AUTH)
        )
        assert (folder / diagram["relative"]).read_text(encoding="utf-8").startswith("erDiagram\n")
        bad = client.post(NEW, json={"type": "diagram", "name": "x", "variant": "plantuml"}, headers=AUTH)
        assert bad.status_code == 400
        # The agent makes docs the same way (the golden rule).
        agent = ok(
            client.post(NEW, json={"type": "markdown", "name": "handover", "folder": "docs"}, headers=AGENT)
        )
        assert agent["relative"] == "docs/handover.md"

        # The Docs group: every doc wherever it sits, README.md first.
        tree = ok(client.get("/scripts/tree", headers=AUTH))
        docs = next(g for g in tree["groups"] if g["id"] == "text")
        paths = [f["path"] for f in docs["files"]]
        assert docs["name"] == "Docs" and paths[0] == "README.md"
        assert {"docs/decisions/0001-use-duckdb.md", "docs/report.html", "docs/diagrams/model.mmd"} <= set(
            paths
        )

        # context.md lists the docs by path and title only: never their text.
        (folder / "docs" / "handover.md").write_text(
            "# Handover\n\nA made-up secret line.\n", encoding="utf-8"
        )
        listed = ok(client.get("/project/documents", headers=AUTH))["docs"]
        by_path = {d["path"]: d["title"] for d in listed}
        assert by_path["docs/handover.md"] == "Handover" and by_path["docs/diagrams/model.mmd"] == ""
        said = json.dumps(ok(client.get("/claude/context", headers=AGENT)))
        assert "docs/handover.md" in said and "Handover" in said and "made-up secret line" not in said


def test_context_md_lists_docs_by_path_and_title_only() -> None:
    state = context_md.State(
        version="0",
        project="shop",
        documents=(
            context_md.DocumentFacts("notebook", "data.ipynb"),
            context_md.DocumentFacts("doc", "README.md", "Shop"),
            context_md.DocumentFacts("doc", "docs/flow.mmd"),
        ),
    )
    lines = context_md.section_lines("Documents", state, set())
    assert lines[0] == "- `data.ipynb`: notebook"
    assert "- `README.md`: doc, `Shop`" in lines and "- `docs/flow.mmd`: doc" in lines
    assert any("path and title only" in line for line in lines)


def test_the_docs_group_puts_the_readme_and_the_outline_first() -> None:
    paths = ["notes/z.md", "ARCHITECTURE.md", "docs/a.mmd", "README.md", "x.py", ".sab/secret.md", "pic.svg"]
    assert code_tree.docs(paths) == ["README.md", "ARCHITECTURE.md", "pic.svg", "docs/a.mmd", "notes/z.md"]


# ===== text documents: which files, which preview =====


def test_text_documents_and_their_previews() -> None:
    previews = {
        "README.md": ("markdown", "preview"),
        "page.html": ("html", "source"),
        "old.HTM": ("html", "source"),
        "logo.svg": ("svg", "source"),
        "flow.mmd": ("mermaid", "source"),
        "flow.mermaid": ("mermaid", "source"),
        "sales.vl.json": ("vega", "source"),
        "sales.vg.json": ("vega", "source"),
        "todo.txt": ("", "source"),
    }
    for name, (preview, first) in previews.items():
        kind = text_documents.kind_of(f"docs/{name}")
        assert kind is not None and (kind.preview, kind.first) == (preview, first), name
        assert (
            workbench_pages.home_of_path(name) == "scripts" and workbench_pages.kind_of_path(name) == "text"
        )
    assert text_documents.kind_of("data.json") is None and text_documents.kind_of(".hidden.md") is None
    # A chart's spec is a text document, never a structure's tab; any other .json still is one.
    assert not workbench_pages.is_structure_path("sales.vl.json")
    assert workbench_pages.is_structure_path("sales.json")
    assert text_documents.view_of("Read") == "preview" and text_documents.view_of("split") == "split"
    with pytest.raises(ValueError, match="preview, split or source"):
        text_documents.view_of("both")
    said = workbench_pages.rules()["text"]
    assert said["views"] == ["preview", "split", "source"]
    assert {
        "ending": ".md",
        "language": "markdown",
        "preview": "markdown",
        "first": "preview",
    }.items() <= said["kinds"][0].items()


# ===== a Markdown file's blocks: the route and the agent's command =====

NOTES = "# Notes\r\n\r\nA first paragraph.\r\n\r\n- [ ] Check the totals\r\n- [x] Write it down\r\n"


def test_a_block_edit_through_the_route_and_the_agents_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path) as client:
        folder = project(client, tmp_path)
        path = folder / "docs" / "notes.md"
        path.parent.mkdir()
        path.write_bytes(NOTES.encode("utf-8"))
        # With the text sent (the page's unsaved text) nothing is written.
        typed = ok(
            client.post(
                "/workbench/markdown", json={"text": NOTES, "block": 1, "to": "Changed."}, headers=AUTH
            )
        )
        assert typed["written"] is False and typed["changed"] is True
        assert typed["text"] == NOTES.replace("A first paragraph.", "Changed.")
        assert path.read_bytes() == NOTES.encode("utf-8")
        assert [b["kind"] for b in typed["blocks"]] == ["heading", "paragraph", "list"]

        def call(method: str, route: str, body: Any = None, **_: Any) -> Any:
            return ok(client.request(method, route, json=body, headers=AGENT))

        monkeypatch.setattr("swissarmybench.cli.api.call", call)
        run = commands.REGISTRY["workbench_file"].run
        read = run({"action": "blocks", "path": str(path)})
        assert read["title"] == "Notes" and [b["index"] for b in read["blocks"]] == [0, 1, 2]
        assert read["blocks"][2]["tasks"] == 2
        done = run({"action": "edit_block", "path": str(path), "block": 1, "to": "The agent's paragraph."})
        assert done["written"] is True and done["changed"] is True
        after = path.read_bytes().decode("utf-8")
        assert after == NOTES.replace("A first paragraph.", "The agent's paragraph.")  # only there, CRLF kept
        ticked = run({"action": "edit_block", "path": str(path), "block": 2, "task": 0})
        assert ticked["written"] is True
        assert path.read_bytes().decode("utf-8") == after.replace("- [ ] Check", "- [x] Check")
        added = run({"action": "edit_block", "path": str(path), "block": 2, "to": "## More", "after": True})
        assert [b["kind"] for b in added["blocks"]] == ["heading", "paragraph", "list", "heading"]
        assert path.read_bytes().decode("utf-8").endswith("- [x] Write it down\r\n\r\n## More\r\n")
        same = run({"action": "edit_block", "path": str(path), "block": 3, "to": "## More"})
        assert same["written"] is False and same["changed"] is False
        # Refusals: one sentence each.
        for body in ({"path": str(path), "block": 9, "to": "x"}, {"path": str(folder / "data.ipynb")}, {}):
            assert client.post("/workbench/markdown", json=body, headers=AUTH).status_code == 400, body
        missing = client.post("/workbench/markdown", json={"path": str(folder / "no.md")}, headers=AUTH)
        assert missing.status_code == 404


def test_the_view_and_export_actions_go_to_the_scripts_window(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[Any] = []

    def call(method: str, path: str, body: Any = None, **_: Any) -> Any:
        sent.append((method, path, body))
        return {"result": {"view": "split"}}

    monkeypatch.setattr("swissarmybench.cli.api.call", call)
    run = commands.REGISTRY["workbench_file"].run
    assert run({"action": "view", "path": "/p/README.md", "to": "split"}) == {"view": "split"}
    run({"action": "export", "path": "/p/flow.mmd", "format": "png"})
    run({"action": "export", "path": "/p/flow.mmd"})
    window = "/workbench/window"
    assert sent == [
        ("POST", window, {"command": "view.split", "args": {"path": "/p/README.md"}, "page": "scripts"}),
        ("POST", window, {"command": "preview.savePng", "args": {"path": "/p/flow.mmd"}, "page": "scripts"}),
        ("POST", window, {"command": "preview.saveSvg", "args": {"path": "/p/flow.mmd"}, "page": "scripts"}),
    ]
    assert "action:" in run({"action": "nonsense"})["error"]


# ===== a preview's pictures =====

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def test_a_picture_beside_a_document_is_served_and_nothing_else(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        folder = project(client, tmp_path)
        (folder / "chart.png").write_bytes(PNG)
        (folder / "logo.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><script>x</script></svg>', "utf-8"
        )
        got = client.get("/workbench/picture", params={"path": str(folder / "chart.png")}, headers=AUTH)
        assert got.status_code == 200 and got.content == PNG and got.headers["content-type"] == "image/png"
        svg = client.get("/workbench/picture", params={"path": str(folder / "logo.svg")}, headers=AUTH)
        # An SVG opened at this address runs nothing: sandboxed, no script.
        assert (
            svg.headers["content-security-policy"] == "default-src 'none'; style-src 'unsafe-inline'; sandbox"
        )
        assert svg.headers["x-content-type-options"] == "nosniff"
        for other in ("README.md", "data.ipynb", ".sab/project.json"):
            refused = client.get("/workbench/picture", params={"path": str(folder / other)}, headers=AUTH)
            assert refused.status_code == 403, other
        assert (
            client.get(
                "/workbench/picture", params={"path": str(folder / "no.png")}, headers=AUTH
            ).status_code
            == 404
        )
        assert client.get("/workbench/picture", params={"path": str(folder / "chart.png")}).status_code in (
            401,
            403,
        )


def test_a_diagrams_preview_is_saved_beside_its_file(tmp_path: Path) -> None:
    drawn = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'
    )
    with make_client(tmp_path) as client:
        folder = project(client, tmp_path)
        made = ok(client.post(NEW, json={"type": "diagram", "name": "flow"}, headers=AUTH))
        body = {"path": made["path"], "format": "svg", "data": drawn}
        saved = ok(client.post("/workbench/export-picture", json=body, headers=AUTH))
        target = folder / "docs" / "diagrams" / "flow.svg"
        assert Path(saved["path"]) == target and saved["written"] is True
        assert target.read_text(encoding="utf-8") == drawn
        assert ok(client.post("/workbench/export-picture", json=body, headers=AUTH))["written"] is False
        png = {"path": made["path"], "format": "png", "data": base64.b64encode(PNG).decode()}
        assert (
            Path(ok(client.post("/workbench/export-picture", json=png, headers=AUTH))["path"]).read_bytes()
            == PNG
        )
        for bad in (
            body | {"format": "exe"},
            body | {"data": "not a picture"},
            png | {"data": base64.b64encode(b"not a png").decode()},
            body | {"path": str(folder / "data.ipynb")},
        ):
            assert client.post("/workbench/export-picture", json=bad, headers=AUTH).status_code == 400, bad
        # An .svg file's own preview never replaces the file.
        (folder / "logo.svg").write_text(drawn, encoding="utf-8")
        own = ok(
            client.post(
                "/workbench/export-picture", json=body | {"path": str(folder / "logo.svg")}, headers=AUTH
            )
        )
        assert Path(own["path"]).name == "logo.preview.svg"


# ===== ARCHITECTURE.md: the app's outline, kept when edited by hand =====


def test_an_outline_edited_by_hand_is_kept_and_said(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        folder = project(client, tmp_path)
        first = ok(client.post("/project/outline", json={}, headers=AUTH))
        assert first["written"] is True and first["edited"] is False
        outline = folder / "ARCHITECTURE.md"
        kept = json.loads((folder / ".sab" / "outline.json").read_text(encoding="utf-8"))
        assert list(kept) == ["sha256"] and len(kept["sha256"]) == 64  # a hash, never the text
        assert ok(client.post("/project/outline", json={}, headers=AUTH))["written"] is False
        # The project changes: the app's own file follows.
        push(client, "orders", ORDERS)
        ok(client.post("/project/save", json={}, headers=AUTH))
        again = ok(client.post("/project/outline", json={}, headers=AUTH))
        assert again["edited"] is False and outline.read_text(encoding="utf-8") == again["text"]
        # Edited by hand: kept, and said; Replace takes the new outline.
        mine = again["text"] + "\n## My own notes\n\nA made-up line I wrote.\n"
        outline.write_text(mine, encoding="utf-8")
        said = ok(client.post("/project/outline", json={}, headers=AGENT))
        assert said["written"] is False and said["edited"] is True
        assert "edited by hand" in said["said"] and "Replace" in said["said"]
        assert outline.read_text(encoding="utf-8") == mine
        taken = ok(client.post("/project/outline", json={"replace": True}, headers=AUTH))
        assert taken["written"] is True and outline.read_text(encoding="utf-8") == taken["text"]
        # An older project's outline (no hash kept) is taken as someone's: never written over silently.
        (folder / ".sab" / "outline.json").unlink()
        outline.write_text("# Older\n", encoding="utf-8")
        assert ok(client.post("/project/outline", json={}, headers=AUTH))["edited"] is True
        assert outline.read_text(encoding="utf-8") == "# Older\n"


# ===== the front end: the server's data, no copy of its own =====

BLAZOR = Path(__file__).resolve().parents[1] / "blazor" / "SwissArmyBench.Web"


def test_the_front_ends_text_kinds_are_the_servers() -> None:
    """Docs/TextFiles.cs is held to domain/text_documents.py KINDS: the same endings in the same order, each
    with its language, preview, first view and icon."""
    text = (BLAZOR / "Pages" / "Workbench" / "Docs" / "TextFiles.cs").read_text(encoding="utf-8")
    found = re.findall(r'new\("([^"]+)", "([^"]+)", "([^"]*)", (\w+), "([^"]+)"\)', text)
    assert [(e, lang, preview, first.lower(), icon) for e, lang, preview, first, icon in found] == [
        (k.ending, k.language, k.preview, k.first, k.icon) for k in text_documents.KINDS
    ]


def test_the_front_end_names_no_file_type() -> None:
    """The New file list and its dialog draw what GET /scripts/files/new says: no type's id or label is
    written in them (a project type's own least of all)."""
    from swissarmybench import extensions

    ids = {t.id for t in new_files.TYPES} | {"widget", "canvas", "workbook", "page"}
    for module in extensions.enabled():
        mode = extensions.manifest(module).MODE or {}
        ids |= {str(t.get("id")) for t in mode.get("new_files") or []}
    assert {"widget", "canvas"} <= ids
    workbench = BLAZOR / "Pages" / "Workbench"
    files = [*sorted((workbench / "Ide").glob("NewFile*")), workbench / "WorkbenchPage.NewFiles.cs"]
    assert len(files) >= 5
    for file in files:
        code = "\n".join(
            line
            for line in file.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith(("//", "@*", "///"))
        )
        code = code.replace('type="text"', "")  # an input's own attribute
        named = sorted(i for i in ids if re.search(rf'"{re.escape(i)}"', code))
        assert named == [], f"{file.name} names the file type(s) {named}"


def test_the_screen_says_which_view_a_text_documents_tab_is_in() -> None:
    from swissarmybench.domain import screen

    tab = {"title": "README.md", "path": "/p/README.md", "kind": "document", "dirty": False, "view": "split"}
    state = screen.clean({"page": "scripts", "tab": tab | {"text": "never kept"}, "tabs": [tab]})
    assert state["tab"]["view"] == "split" and state["tabs"][0]["view"] == "split"
    assert "text" not in state["tab"]  # names and states only: never a document's text
    assert "document /p/README.md, split view" in screen.shows(state)
