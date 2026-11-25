"""What a project needs installed, found as it opens (domain/project_needs.py): every source read without
running anything, what its Python already meets, and an install's progress read from uv's and pip's own lines
(captured, made-up output). Made-up data only."""

from __future__ import annotations

import json

from swissarmybench.domain import project_needs as rules


def notebook(*cells: str) -> str:
    return json.dumps({"cells": [{"cell_type": "code", "source": c} for c in cells] + [
        {"cell_type": "markdown", "source": "import nothing_here"}
    ]})  # fmt: skip


def test_a_notebooks_code_cells_are_its_python_its_magics_made_python() -> None:
    text = notebook("%pip install tabulate\nimport tabulate", "%%sql Sales\nSELECT 1", "!ls\nimport rich")
    code = rules.code_of("data.ipynb", text)
    assert len(code) == 2  # the %%sql cell is not Python
    assert [rules.imports_in(c) for c in code] == [["tabulate"], ["rich"]]
    assert rules.code_of("load.py", "import polars") == ["import polars"]
    assert rules.code_of("broken.ipynb", "{not json") == []
    assert rules.imports_in("def broken(:") == []


def test_every_source_gives_its_packages_once_with_why() -> None:
    found = rules.needs(
        "polars==1.36.0  # pinned\n-r more.txt\n./local/path\nrequests\n",
        for_type=[("streamlit", "the Streamlit project")],
        code=[
            rules.Code("data.ipynb", "import pandas as pd\nimport yaml\nimport os, json\nfrom . import x"),
            rules.Code(
                "scripts/load.py", "import pandas\nimport etl.clean\nimport swissarmybench\nimport sklearn"
            ),
            rules.Code("widgets/kpi.widget.py", "import streamlit as st\nimport polars"),
        ],
        packages=[("connection Sales (SQL Server)", ["mssql-python", "pandas"])],
        local=rules.local_modules(["data.ipynb", "scripts/etl/clean.py", "scripts/load.py"]),
    )
    by = {n.name: n for n in found}
    assert by["polars"].why == ["requirements.txt", "widgets/kpi.widget.py"]
    assert by["polars"].written and by["polars"].spec == "==1.36.0"
    assert by["pandas"].why == ["data.ipynb", "scripts/load.py", "connection Sales (SQL Server)"]
    assert by["PyYAML"].why == ["data.ipynb"]  # yaml installs as PyYAML (domain/packages.py's table)
    assert by["scikit-learn"].why == ["scripts/load.py"]
    assert by["streamlit"].why == ["the Streamlit project", "widgets/kpi.widget.py"]
    assert by["mssql-python"].why == ["connection Sales (SQL Server)"]
    assert by["ipykernel"].machinery and by["openpyxl"].machinery
    # The standard library, the app's own, a relative import and the project's own module are no library.
    assert not {"os", "json", "swissarmybench", "etl", "x", "scripts"} & {rules.key(n) for n in by}
    assert "more.txt" not in " ".join(by)  # an option's line is left for the user's own install


def test_what_the_python_already_meets_is_left_out_a_pin_not_met_is_needed() -> None:
    found = rules.needs("polars==1.36.0\npandas>=2\n", code=[rules.Code("a.py", "import Tabulate")])
    installed = {"Polars": "1.30.0", "pandas": "2.3.3", "ipykernel": "6.29.5", "openpyxl": "3.1.5"}
    missing = [n.name for n in rules.missing(found, installed)]
    assert missing == ["polars", "xlrd", "Tabulate"]
    assert rules.satisfied(">=2,<3", "2.3.3") and not rules.satisfied("<2", "2.3.3")
    assert rules.satisfied("==2.*", "2.3.3") and not rules.satisfied("!=2.3.3", "2.3.3")
    assert rules.satisfied("", "0.1") and not rules.satisfied("", None)


def test_what_is_written_to_requirements_is_what_it_did_not_name_never_the_machinery() -> None:
    found = rules.needs("polars\n", code=[rules.Code("a.py", "import tabulate\nimport polars")])
    keys = {"polars", "tabulate", "ipykernel"}
    assert rules.to_write(found, keys) == ["tabulate"]


# uv's own output (made-up names and sizes).
UV = """Using Python 3.12.7 environment at: .venv
Resolved 9 packages in 412ms
Downloading pandas (11.8MiB)
Downloading numpy (15.9MiB)
 Downloaded numpy
 Downloaded pandas
Prepared 4 packages in 2.31s
Installed 4 packages in 38ms
 + numpy==2.1.3
 + pandas==2.3.3
 + python-dateutil==2.9.0
 + tabulate==0.9.0
""".splitlines()

PIP = """Collecting pandas
  Downloading pandas-2.3.3-cp312-cp312-manylinux_2_17_x86_64.whl.metadata (89 kB)
Collecting Tabulate
  Downloading tabulate-0.9.0-py3-none-any.whl (35 kB)
Collecting numpy>=1.26.0 (from pandas)
Requirement already satisfied: openpyxl in ./.venv/lib/python3.12/site-packages (3.1.5)
Installing collected packages: tabulate, numpy, pandas
Successfully installed numpy-2.1.3 pandas-2.3.3 tabulate-0.9.0
""".splitlines()


def test_uvs_lines_say_each_package_as_it_goes_a_dependency_not_counted() -> None:
    asked = ["pandas", "tabulate==0.9.0"]
    start = rules.read_progress(UV[:2], asked)
    assert start.phase == "downloading" and set(start.statuses.values()) == {"waiting"} and start.share == 0
    busy = rules.read_progress(UV[:4], asked)
    assert busy.statuses == {"pandas": "installing", "tabulate": "waiting"} and busy.current == "pandas"
    assert busy.share == 0.25
    end = rules.read_progress(UV, asked)
    assert end.statuses == {"pandas": "installed", "tabulate": "installed"} and end.share == 1
    assert end.current is None and end.phase == "finished"
    assert "numpy" not in end.statuses  # pulled in by pandas: not counted
    already = rules.read_progress(["Audited 2 packages in 3ms"], asked)
    assert set(already.statuses.values()) == {"installed"}


def test_pips_lines_say_each_package_as_it_goes() -> None:
    asked = ["pandas", "tabulate", "openpyxl"]
    middle = rules.read_progress(PIP[:4], asked)
    assert middle.statuses == {"pandas": "installing", "tabulate": "installing", "openpyxl": "waiting"}
    assert middle.current == "Tabulate" or middle.current == "tabulate"
    satisfied = rules.read_progress(PIP[:6], asked)
    assert satisfied.statuses["openpyxl"] == "installed"
    end = rules.read_progress(PIP, asked)
    assert set(end.statuses.values()) == {"installed"} and end.share == 1


def test_each_state_says_one_line() -> None:
    packages = [{"name": n, "why": "data.ipynb", "status": s} for n, s in
                [("pandas", "installed"), ("tabulate", "installing"), ("rich", "waiting")]]  # fmt: skip
    state = rules.State("installing", "Sales Recon", packages, current="tabulate")
    assert state.words == "Setting up Sales Recon: installing 2 of 3 · tabulate"
    assert state.to_json()["total"] == 3 and state.to_json()["done"] == 1
    assert (
        rules.State("checking", "Sales Recon").words == "Setting up Sales Recon: looking for what it needs…"
    )
    done = rules.State(
        "done", "Sales Recon", [p | {"status": "installed"} for p in packages], written=["rich"]
    )
    assert done.words == "Installed 3 libraries · added to requirements.txt"
    done.restart = True
    assert done.words.endswith("restart the Python session to use them")
    failed = rules.State("failed", "S", [packages[0], packages[1] | {"status": "failed"}])
    assert failed.words == "1 library could not be installed (tabulate); 1 library installed"
    assert rules.State("none").words == "Everything this project needs is installed."
    waiting = rules.State("none", "S", packages[:1], own=False)
    assert "not made yet" in waiting.words
    problem = rules.failure(["tabulate"], "a\n" * 30 + "error: No solution found", 1)
    assert problem["error"] == "These could not be installed: tabulate."
    assert problem["fixes"] == [{"label": "Try again", "action": "try_again"}]
    assert problem["details"].endswith("No solution found") and problem["details"].count("\n") == 14
    assert rules.why_words(["a", "b", "c", "d"]) == "a, b and 2 more"


def test_the_apps_own_modules_are_never_libraries_to_fetch() -> None:
    """The owner, 2026-11-25: a project opened said "These could not be installed: sab_api": API.py's
    `from sab_api import ...` is the app's own module, as are the scaffold's adapter and a built app's
    runtime."""
    api = "from sab_api import ApiError, connection, endpoint, records\nimport adapter\nimport api_adapter\n"
    app = "import sab_canvas\nimport sab_widgets\nfrom sab_excel import build\nimport pandas\n"
    found = rules.needs(
        "sab_api\nsab-api\nrich\n",  # written there by mistake: not a library either
        code=[rules.Code("API.py", api), rules.Code("builds/app/1/app.py", app)],
    )
    names = {n.name for n in found if not n.machinery}
    assert names == {"rich", "pandas"}
