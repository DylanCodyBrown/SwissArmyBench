"""Export: workbook.py, the automation that builds the design's workbook without the app (the Accounting
extension's domain; no I/O: the runtime's text is handed in).

The design is data; the Python is generated from it: workbook.py holds the design (a Python literal),
the builder (sab_excel's own text, the one builder Play runs too: only the parts this design uses), and
reads its tables from data.py, the data notebook's export. It runs anywhere with openpyxl and duckdb:

    python workbook.py                  writes <title>.xlsx beside it
    python workbook.py out/April.xlsx   writes there
"""

from __future__ import annotations

import pprint
import re
from collections.abc import Mapping
from typing import Any

FILE = "workbook.py"
DESIGN_FILE = "workbook.design.json"
FUTURE = "from __future__ import annotations\n"


def variable(name: str) -> str:
    """A table's name as data.py's variable (the data notebook's rule: letters, digits, _)."""
    text = re.sub(r"\W+", "_", name.strip()).strip("_").lower() or "table"
    return f"t_{text}" if text[0].isdigit() else text


def output_name(design: Mapping[str, Any]) -> str:
    stem = (
        re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", str(design.get("title") or "workbook")).strip(" .")
        or "workbook"
    )
    return f"{stem}.xlsx"


MARK = "# ===== "
ALWAYS = ("cells", "data", "tables", "design")  # the parts every design's workbook is built with
BY_BLOCK = {"pivot": "pivots", "chart": "charts"}  # a block kind's own part


def parts_used(design: Mapping[str, Any]) -> list[str]:
    """The builder's parts this design needs: the core, and a part for each kind of block it has."""
    kinds = {b.get("kind") for s in design.get("sheets") or [] for b in s.get("blocks") or []}
    return [*ALWAYS, *(part for kind, part in BY_BLOCK.items() if kind in kinds)]


def _body(runtime: str, design: Mapping[str, Any]) -> str:
    """The builder's code after its docstring and `from __future__` line: what comes before its first part
    (the imports and settings), then only the parts this design uses, in the builder's own order."""
    at = runtime.index(FUTURE)
    head, *parts = runtime[at + len(FUTURE) :].lstrip("\n").split("\n" + MARK)
    wanted = parts_used(design)
    kept = [MARK + p for p in parts if p.split(":", 1)[0].strip() in wanted]
    return "\n".join([head.rstrip() + "\n\n", *kept])


def workbook_py(design: Mapping[str, Any], runtime: str, tables: list[str]) -> str:
    """workbook.py's text: the design, the builder, the tables read from data.py, main()."""
    names = {t: variable(t) for t in tables}
    literal = pprint.pformat(dict(design), width=100, sort_dicts=False)
    return (
        f'"""workbook.py: builds {output_name(design)} from the data.\n\n'
        "Swiss Army Bench's Accounting export of workbook.design.json. It runs anywhere with openpyxl and\n"
        "duckdb, the app not needed: `python workbook.py [where.xlsx]`. Its tables come from data.py, the\n"
        "data notebook's export. Made again by Export: edit the design, not this file.\n"
        '"""\n\n'
        f"{FUTURE}\n"
        f"DESIGN = {literal}\n\n"
        f"# The tables the workbook reads, and their names in data.py.\nTABLES = {pprint.pformat(names, width=100)}\n\n"
        "# ===== the builder (Swiss Army Bench's sab_excel: the parts this design uses) =====\n\n"
        f"{_body(runtime, design).rstrip()}\n\n\n"
        "# ===== the data and the run =====\n\n\n"
        "def load_tables() -> dict[str, Any]:\n"
        '    """The tables, by the names the design reads, from data.py (the data notebook\'s export)."""\n'
        "    import data\n\n"
        "    missing = [v for v in TABLES.values() if not hasattr(data, v)]\n"
        "    if missing:\n"
        "        raise SystemExit(f\"data.py does not make {', '.join(missing)}: make it in data.ipynb, then Export data.py.\")\n"
        "    return {name: getattr(data, v) for name, v in TABLES.items()}\n\n\n"
        "def main(argv: list[str] | None = None) -> str:\n"
        "    import sys\n\n"
        "    args = sys.argv[1:] if argv is None else argv\n"
        f"    out = Path(args[0]) if args else Path(__file__).with_name({output_name(design)!r})\n"
        "    build_workbook(DESIGN, load_tables(), out)\n"
        '    print(f"Wrote {out}")\n'
        "    return str(out)\n\n\n"
        'if __name__ == "__main__":\n'
        "    main()\n"
    )
