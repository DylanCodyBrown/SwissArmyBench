"""One record per connection kind (domain/connection_kinds.py; the craft review of 2026-11-22, item 12).

A record with a part half filled is refused; every module's per-kind table is the record's view, under the
name it always had; a made-up kind added to the records arrives in every view with no other file edited.
Made-up names only."""

from __future__ import annotations

import dataclasses
import importlib
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from swissarmybench.domain import app_registrations, connection_tables, lakes, portability
from swissarmybench.domain import connection_kinds as kinds
from swissarmybench.domain.blade_templates import Template
from swissarmybench.domain.connection_kinds import Kind, Writable
from swissarmybench.server.blade_templates import TEMPLATES
from swissarmybench.services import connections

SRC = Path(kinds.__file__).resolve().parents[1]
# The groups whose starters are connections with tables (a vault, a blank blade and an analysis are not).
CONNECTION_GROUPS = (kinds.DATABASES, kinds.FILES, kinds.OWN_CODE, kinds.LAKES)


def test_every_record_is_whole() -> None:
    assert kinds.problems() == []


def test_the_module_imports_nothing_of_the_app() -> None:
    """The kind modules import the records, never the other way: no cycle can pass through them."""
    text = (SRC / "domain" / "connection_kinds.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(?:from|import)\s+swissarmybench", text, re.MULTILINE)


@pytest.mark.parametrize(
    "template", [t for t in TEMPLATES if t.group in CONNECTION_GROUPS], ids=lambda t: t.id
)
def test_every_connection_starter_has_its_record(template: Template) -> None:
    """A starter nobody declared is refused, and so is one whose label, group or dialect disagrees."""
    record = kinds.get(template.id)
    assert record is not None, "add its record to domain/connection_kinds.py"
    said = (record.label, record.group, record.dialect or kinds.OTHER)
    assert said == (template.label, template.group, template.dialect)


@pytest.mark.parametrize(
    ("change", "words"),
    [
        ({"label": ""}, "has no label"),
        ({"reads": ""}, "not both"),
        ({"reads_with": "magic"}, "reads_with is one of"),
        ({"naming": ""}, "naming is one of"),
        ({"naming": "single"}, "so its tables are paths"),
        ({"writes": None}, "exactly one of"),
        ({"read_only": "it is"}, "exactly one of"),
        ({"sqlglot": ""}, "its name in sqlglot"),
        ({"filters": ""}, "filters is one of"),
        ({"count": ""}, "count is one of"),
        ({"entra_scope": ""}, "all four"),
        ({"aliases": ("tsql",)}, "already"),
        ({"paramstyle": "qmark"}, "both its marks and its words"),
    ],
)
def test_a_record_with_a_missing_field_is_refused(change: dict[str, object], words: str) -> None:
    broken = dataclasses.replace(kinds.KINDS["onelake"], **change)  # type: ignore[arg-type]
    found = kinds.problems(kinds.KINDS | {"onelake": broken})
    assert any(line.startswith("onelake: ") and words in line for line in found), found


def test_a_later_record_of_a_dialect_does_not_say_it_again() -> None:
    again = dataclasses.replace(kinds.KINDS["azuresql"], sqlglot="postgres")
    found = kinds.problems(kinds.KINDS | {"azuresql": again})
    assert found == ["azuresql: sqlglot are said once, by its dialect's own record (sqlserver)"]


def test_a_kind_that_writes_as_another_needs_that_one_decided() -> None:
    lost = dataclasses.replace(kinds.KINDS["dataverse_web"], writes_as="nowhere")
    assert any(
        "writes as 'nowhere'" in line for line in kinds.problems(kinds.KINDS | {"dataverse_web": lost})
    )


def test_an_older_face_is_a_tables_kind_of_the_same_dialect() -> None:
    """Dataverse's record says the tables kind a saved connection listed by its Web API is (connection_tables
    tables_kind asks it: the kind module is not imported for it)."""
    assert kinds.KINDS["dataverse"].unless_sql == "dataverse_web"
    odd = dataclasses.replace(kinds.KINDS["dataverse"], unless_sql="postgres")
    assert any(
        "unless_sql names 'postgres'" in line for line in kinds.problems(kinds.KINDS | {"dataverse": odd})
    )


def test_a_dialect_is_found_by_any_of_its_names() -> None:
    assert kinds.engine(" TSQL ") is kinds.KINDS["sqlserver"]
    assert kinds.engine("azuresql") is kinds.KINDS["sqlserver"]
    assert kinds.engine("dax") is kinds.engine("Power BI") is kinds.KINDS["powerbi"]
    assert kinds.engine("other") is None and kinds.engine(None) is None and kinds.engine("nobody") is None
    assert kinds.get("sybase") is not None and kinds.get(None) is None


# ===== a made-up kind: one entry, every view =====

MADE_UP = Kind(
    "lakefront",
    "Lakefront (made up)",
    kinds.LAKES,
    lists="its made-up shelves",
    reads="its made-up read",
    reads_with="code",
    naming="path",
    versions=True,
    query_tab=True,
    dialect="lakefront",
    aliases=("lf",),
    sqlglot="duckdb",
    filters="structured",
    adapter=True,
    count="query",
    paramstyle="qmark",
    sql_words="Lakefront SQL",
    by_code=True,
    writes=Writable(("append",), "its made-up write"),
    local_only="odbc",
    reads_files=True,
    entra_area="Lakefront",
    entra_scope="https://lakefront.example/.default",
    entra_place=(("shore",), ""),
    entra_refusals="storage",
    env_prefix="LAKEFRONT",
)


@pytest.fixture
def with_made_up() -> dict[str, Kind]:
    return kinds.KINDS | {MADE_UP.name: MADE_UP}


def test_a_made_up_kind_is_whole(with_made_up: dict[str, Kind]) -> None:
    assert kinds.problems(with_made_up) == []


VIEWS = {
    "tables_contract": ("its made-up shelves", "its made-up read"),
    "path_kinds": None,
    "versioned": None,
    "dialects": None,
    "sqlglot_names": "duckdb",
    "structured_filters": None,
    "adapter_dialects": None,
    "paramstyles": "qmark",
    "sql_words": "Lakefront SQL",
    "writable": MADE_UP.writes,
    "local_only": "odbc",
    "file_kinds": None,
    "entra_scopes": "https://lakefront.example/.default",
    "entra_areas": "Lakefront",
    "env_prefixes": "LAKEFRONT",
}


@pytest.mark.parametrize("view", sorted(VIEWS))
def test_a_made_up_kind_arrives_in_every_view(view: str, with_made_up: dict[str, Kind]) -> None:
    """One entry in the records, and the table each module keeps has it: no other file is edited."""
    before, after = getattr(kinds, view)(), getattr(kinds, view)(with_made_up)
    assert "lakefront" not in before and "lakefront" in after
    if VIEWS[view] is not None:
        assert after["lakefront"] == VIEWS[view]
    assert [name for name in after if name != "lakefront"] == list(before) or set(after) - {
        "lakefront"
    } == set(before)


def test_a_made_up_kind_is_found_by_its_names_and_its_group(with_made_up: dict[str, Kind]) -> None:
    assert kinds.aliases(with_made_up)["lf"] == "lakefront"
    assert kinds.engine("LF", with_made_up) is MADE_UP
    assert kinds.in_group(kinds.LAKES, with_made_up)[-1] == "lakefront"
    assert kinds.labels(["lakefront"], with_made_up) == {"lakefront": "Lakefront (made up)"}
    assert kinds.dialects(with_made_up)[-2:] == ("lakefront", "other")


# ===== every module's table is its record's view, under the name it always had =====

# (module, the table's name, the view it is assigned from)
TABLES = (
    ("connection_tables", "TABLE_KINDS", "tables_contract"),
    ("connection_tables", "PATH_KINDS", "path_kinds"),
    ("connection_tables", "VERSIONED", "versioned"),
    ("connection_sql", "_STRUCTURED", "structured_filters"),
    ("catalogs", "DIALECTS", "dialects"),
    ("catalogs", "_DIALECT_ALIASES", "aliases"),
    ("catalogs", "_SQLGLOT_NAMES", "sqlglot_names"),
    ("catalogs", "NO_SQLGLOT", "no_sqlglot"),
    ("sandbox_dialects", "PARAMSTYLE", "paramstyles"),
    ("sandbox_dialects", "WORDS", "sql_words"),
    ("write_capability", "WRITABLE", "writable"),
    ("write_capability", "READ_ONLY", "read_only"),
    ("write_capability", "BY_TEMPLATE", "writes_by_template"),
    ("write_capability", "_SAME", "writes_same"),
    ("portability", "FILE_KINDS", "file_kinds"),
    ("app_registrations", "CHECKED_KINDS", "entra_scopes"),
    ("app_registrations", "AREAS", "entra_areas"),
    ("lakes", "ENV_PREFIX", "env_prefixes"),
)


@pytest.mark.parametrize(("module", "table", "view"), TABLES, ids=lambda v: str(v))
def test_a_table_is_its_records_view(module: str, table: str, view: str) -> None:
    """A table that disagrees with the records is refused, and so is one written out by hand again."""
    found = importlib.import_module(f"swissarmybench.domain.{module}")
    assert getattr(found, table) == getattr(kinds, view)()
    text = (SRC / "domain" / f"{module}.py").read_text(encoding="utf-8")
    assigned = rf"^{table}: [^=\n]+ = (?:connection_kinds|kinds)\.{view}\(\)"
    assert re.search(assigned, text, re.MULTILINE), table


def test_the_tables_with_a_shape_of_their_own_follow_the_records() -> None:
    assert lakes.KINDS == kinds.in_group(kinds.LAKES) and lakes.GROUP == kinds.LAKES
    assert lakes.LABELS == kinds.labels(lakes.KINDS)
    assert {kind: note.key for kind, note in portability.KINDS.items()} == kinds.local_only()
    for kind in app_registrations.CHECKED_KINDS:  # each checked kind's place and refusals: its record's
        record = kinds.KINDS[kind]
        settings = dict.fromkeys(record.entra_place[0], "x") | {"url": "https://made-up.example/"}
        assert app_registrations.place_words(kind, settings)
        assert app_registrations.scope_for(kind, settings).endswith("/.default")
        assert "{" not in app_registrations.scope_for(kind, settings)
        assert all(app_registrations.refused_words(kind, 403, "refused"))
    settings = {"url": "https://made-up.example/", "database": "sales", "server": "made-up"}
    assert app_registrations.scope_for("dataverse", settings) == "https://made-up.example/.default"
    assert app_registrations.place_words("sqlserver", settings) == "sales on made-up"


def test_a_tables_kind_is_decided_from_the_records() -> None:
    """A dialect whose own record is a tables kind is that kind; a plain SQL dialect is a database."""
    for word, record in kinds.engines().items():
        if word == "dataverse":
            continue  # its Web API or its SQL endpoint: the catalog's language decides
        expected = record.name if record.tables else "database"
        assert connection_tables.tables_kind("sql", record.name, word) == expected, word
    assert connection_tables.tables_kind("sql", "dataverse", "dataverse", "sql") == "dataverse"
    assert connection_tables.tables_kind("sql", "dataverse", "dataverse", "python") == "dataverse_web"
    assert connection_tables.tables_kind("sql", "odbc", "other") == "database"


def test_no_domain_file_names_the_path_kinds_by_hand() -> None:
    """context.md's naming and the tree's folders ask the records; a literal tuple of the lake kinds is the
    drift the review found (context_md.py repeated PATH_KINDS)."""
    literal = re.compile(r"""\(\s*["']onelake["']\s*,\s*["']datalake["']\s*,\s*["']delta["']""")
    found = [
        path.name
        for path in sorted((SRC / "domain").glob("*.py"))
        if path.name != "connection_kinds.py" and literal.search(path.read_text(encoding="utf-8"))
    ]
    assert not found, found


# ===== the adapter and the connections service ask the records =====


def test_the_adapters_own_dialects_are_kinds_the_records_know() -> None:
    """adapter.py keeps its own DIALECTS (an export carries it alone); this ties the two: every dialect it
    folds a plan into is a declared kind, and the ones the app reads through it are the records' `adapter`."""
    from swissarmybench.adapters import adapter

    for word in adapter.DIALECTS:
        assert kinds.get(word) is not None, f"{word}: add its record to domain/connection_kinds.py"
    read_here = set(kinds.adapter_dialects())
    assert read_here == set(connections.ADAPTER_DIALECTS)
    assert read_here - {"duckdb"} <= set(adapter.DIALECTS)  # DuckDB is the adapter's own source
    # Every dialect the adapter knows is read through it (Databricks' starter names its own since 2026-11-22).
    assert {w for w in adapter.DIALECTS if w not in read_here} == set()
    assert connections.NOT_ADAPTED == kinds.own_sql() == ("sybase",)


def _blade(template: str, dialect: str, language: str | None = "sql", kind: str = "sql") -> Any:
    return SimpleNamespace(
        name="Made up",
        kind=kind,
        template=template,
        dialect=dialect,
        catalog_language=language,
        tags=(),
        code="",
    )


def test_the_service_asks_the_record_how_a_table_is_counted_and_named() -> None:
    """The read path's questions are fields of the kind's record, not comparisons with its name."""
    sqlserver, postgres = _blade("sqlserver", "sqlserver"), _blade("postgres", "postgres")
    assert "sys.partitions" in connections._count_sql(sqlserver, "", "dbo", "orders")
    assert (
        "COUNT(*)" in connections._count_sql(sqlserver, "sales", "dbo", "orders").upper()
    )  # named with its database
    assert "sys.partitions" not in connections._count_sql(postgres, "", "public", "orders")
    workspace = _blade("powerbi", "dax")
    assert connections._origin(workspace, "Sales model") == "Made up/Sales model"
    assert connections._origin(postgres, "public") == "Made up"
    reads = {
        "sql": [postgres, sqlserver, _blade("dataverse", "dataverse")],
        "dax": [workspace],
        "code": [
            _blade("dataverse", "dataverse", "python"),
            _blade("onelake", "onelake"),
            _blade("sharepoint", "sharepoint"),
            _blade("python", "other", kind="other"),
        ],
        "file": [_blade("csv", "other", kind="other"), _blade("folder", "other", kind="other")],
    }
    for how, blades in reads.items():
        for blade in blades:
            assert connections._tables(blade).reads_with == how, (how, blade.template)
    assert not connections._tables(_blade("dataverse", "dataverse", "python")).names_schema
    assert connections._tables(_blade("azure_key_vault", "other", kind="vault")).name == ""


def test_what_a_tree_calls_a_group_is_the_records() -> None:
    said = {name: kinds.group_word(name) for name in kinds.tables_contract()}
    assert said["powerbi"] == "dataset" and said["sharepoint"] == "list" and said["database"] == "schema"
    assert {name for name, word in said.items() if word == "folder"} == set(kinds.path_kinds())
    assert kinds.group_word("nobody") == "schema"


# ===== how many files a new kind touches =====

# The domain and service files that still name a lake or SharePoint kind by its quoted word, and why. Before
# the records (the merge base of 2026-11-22) there were ten: catalogs, connection_tables (domain and service),
# context_md, write_capability, app_registrations (domain and service), lakes, lake_code and
# local_api_wizard. A file added here is a table or a branch that should have been a record's field.
NAMES_A_LAKE_KIND = {
    "domain/connection_kinds.py": "the record: the one entry a new kind writes",
    "domain/lakes.py": "its code module: each kind's own code, sign-ins and words",
    "domain/lake_code.py": "the lakes' shared code (\"delta\" is a table's format there)",
    "domain/app_registrations.py": "its app-registration code, and the path an Azure lake's check lists",
    "services/local_api_wizard.py": "a sandbox table mocked as a SharePoint list reads by the list's client",
}


def test_a_new_kind_is_one_record_and_its_code_module() -> None:
    quoted = re.compile(r"""["'](?:onelake|datalake|delta|sharepoint|sharepoint_docs)["']""")
    found = {
        f"{folder}/{path.name}"
        for folder in ("domain", "services")
        for path in sorted((SRC / folder).glob("*.py"))
        if quoted.search(path.read_text(encoding="utf-8"))
    }
    assert found == set(NAMES_A_LAKE_KIND), sorted(found ^ set(NAMES_A_LAKE_KIND))
