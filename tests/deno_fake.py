# ruff: noqa: E501 (the recorded programs are written as the stand-ins run them)
"""A recorded stand-in for Deno and its Jupyter kernel, written by the tests onto a PATH of their own (as
tests/powerapps_fakes.py stands in for pa and pac).

`install(folder)` writes a `deno` program that answers the three things the Power Apps extension asks of
Deno: `deno --version` (2.9.6's line), `deno jupyter --kernel --conn <file>` (a real Jupyter kernel, so the
extension's adapter drives it exactly as it drives Deno's, answering with the outputs Deno 2.9.6 gave for
the same cells when run here: docs/verified.md, 2026-11-17) and `deno bundle ... -o <file>` (a small
script that writes the props it was given into the page). The kernel keeps a little state of its own: the
open tables' views (`sab.sync`, read back from their Parquet files by a SQL cell that names them), the
table results by their ids (`sab.save` writes one as Parquet), the names cells made. Made-up data only.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

KERNEL = r"""
import json
import re
import sys

from ipykernel.kernelapp import IPKernelApp
from ipykernel.kernelbase import Kernel

TABLE = "application/vnd.swissarmybench.table+json"
BY_REGION = {"columns": ["region", "total"], "types": ["VARCHAR", "DOUBLE"],
             "rows": [{"region": "North", "total": 12.5}, {"region": "South", "total": 7}]}


class FakeDeno(Kernel):
    implementation = "deno"
    implementation_version = "2.9.6"
    language = "typescript"
    language_version = "6.0.3"
    language_info = {"name": "typescript", "mimetype": "text/x.typescript", "file_extension": ".ts"}
    banner = "Deno 2.9.6 (a recorded stand-in)"

    views = {}
    results = {}
    made = set()
    count = 0

    def _send(self, kind, content):
        self.send_response(self.iopub_socket, kind, content)

    def _table(self, found):
        ident = f"r{len(self.results) + 1}"
        self.results[ident] = found
        bundle = dict(found, id=ident, total=len(found["rows"]))
        n = len(found["rows"])
        return {TABLE: bundle, "text/plain": f"{n} row{'' if n == 1 else 's'}, {len(found['columns'])} columns"}

    def _error(self, ename, evalue, traceback):
        self._send("error", {"ename": ename, "evalue": evalue, "traceback": traceback})
        return {"status": "error", "execution_count": self.execution_count, "ename": ename, "evalue": evalue,
                "traceback": traceback}

    def _view(self, name):
        import pyarrow.parquet as pq
        table = pq.read_table(self.views[name])
        columns = table.column_names
        types = ["DOUBLE" if str(t).startswith(("double", "int")) else "VARCHAR" for t in table.schema.types]
        return {"columns": columns, "types": types, "rows": table.to_pylist()}

    def do_execute(self, code, silent, store_history=True, user_expressions=None, allow_stdin=False):
        if code.startswith('import { DuckDBInstance'):
            return {"status": "ok", "execution_count": self.execution_count}
        data = None
        if code.startswith("await sab.sync("):
            self.views = json.loads(code[len("await sab.sync("):].rstrip(");"))
        elif code.startswith("await sab.save("):
            ident, path = json.loads("[" + code[len("await sab.save("):].rstrip(");") + "]")
            if ident not in self.results:
                return self._error("Error", f"There is no result {ident} in this kernel any more: run its cell again.", [])
            import pyarrow as pa
            import pyarrow.parquet as pq
            pq.write_table(pa.Table.from_pylist(self.results[ident]["rows"]), path)
        elif code.startswith("await sab.sql("):
            query = json.loads(code[len("await sab.sql("):-1])
            if "missing_table" in query:
                message = ('Catalog Error: Table with name missing_table does not exist!\nDid you mean "pg_tables"?\n\n'
                           'LINE 1: select * from missing_table\n                      ^^^^^^^^^^^^^')
                return self._error("Error", message, ["Error: " + line for line in message.splitlines()[:1]])
            named = next((n for n in self.views if re.search(rf"\b{n}\b", query)), None)
            data = self._table(self._view(named) if named else BY_REGION)
        elif "__sabProps" in code:
            data = {"application/json": {"rows": BY_REGION["rows"], "title": "Sales by region"}}
        elif "SabTable" in code and "application/json" in code:
            names = json.loads(code[code.index("for (const n of ") + 16:code.index(") { try")])
            data = {"application/json": {n: {"columns": BY_REGION["columns"], "types": BY_REGION["types"]}
                                         for n in names if n in self.made}}
        elif "nope" in code:
            return self._error("ReferenceError", "nope is not defined", ["ReferenceError: nope is not defined",
                                                                        "    at <anonymous>:1:22"])
        else:
            for name in re.findall(r"^(?:export\s+)?(?:const|let|function)\s+([A-Za-z_]\w*)", code, re.M):
                self.made.add(name)
            if "sab.sql`" in code:
                data = self._table(BY_REGION)
            else:
                printed = re.findall(r"console\.log\((['\"])(.*?)\1\)", code)
                for _, text in printed:
                    self._send("stream", {"name": "stdout", "text": text + "\n"})
                if not printed:
                    data = {"text/plain": "\x1b[33m42\x1b[39m"}
        if data is not None and not silent:
            self._send("execute_result", {"execution_count": self.execution_count, "data": data, "metadata": {}})
        return {"status": "ok", "execution_count": self.execution_count, "payload": [], "user_expressions": {}}

    def do_complete(self, code, cursor_pos):
        return {"status": "ok", "matches": ["version"], "cursor_start": max(0, cursor_pos - 3),
                "cursor_end": cursor_pos, "metadata": {}}


if __name__ == "__main__":
    IPKernelApp.launch_instance(kernel_class=FakeDeno, argv=["-f", sys.argv[1]])
"""

DENO = r"""
import os
import subprocess
import sys

args = sys.argv[1:]
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "deno_calls.log"), "a", encoding="utf-8") as log:
    log.write(" ".join(args[:2]) + "\n")
if args[:1] == ["--version"]:
    print("deno 2.9.6 (stable, release, x86_64-unknown-linux-gnu)\nv8 15.0.245.2-rusty\ntypescript 6.0.3")
elif args[:2] == ["jupyter", "--kernel"]:
    conn = args[args.index("--conn") + 1]
    os.execv(sys.executable, [sys.executable, os.path.join(here, "fake_deno_kernel.py"), conn])
elif args[:1] == ["bundle"]:
    out = args[args.index("-o") + 1]
    entry = args[-1]
    component = open(os.path.join(os.path.dirname(entry), "component.tsx"), encoding="utf-8").read()
    if "does-not-compile" in component:
        print("error: The module's source code could not be parsed: Expected ';'", file=sys.stderr)
        sys.exit(1)
    with open(out, "w", encoding="utf-8") as f:
        f.write('const p = globalThis.__SAB_PROPS__ || {};\n'
                'document.getElementById("root").innerHTML = "<h2>" + (p.title || "Component") + "</h2>"'
                ' + "<ul>" + (p.rows || []).map(r => "<li>" + r.region + ": " + r.total + "</li>").join("") + "</ul>";\n')
    print("Bundled 1 module")
else:
    print("deno (recorded stand-in): " + " ".join(args), file=sys.stderr)
    sys.exit(2)
"""


def install(folder: Path) -> Path:
    """Write the stand-in into `folder` and return it, for the front of PATH."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "fake_deno_kernel.py").write_text(KERNEL, encoding="utf-8")
    (folder / "fake_deno.py").write_text(DENO, encoding="utf-8")
    script = folder / "deno"
    script.write_text(
        f"#!{sys.executable}\nimport runpy, sys\nsys.argv[0] = {str(folder / 'fake_deno.py')!r}\n"
        f"runpy.run_path({str(folder / 'fake_deno.py')!r}, run_name='__main__')\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    if os.name == "nt":
        (folder / "deno.cmd").write_text(f'@"{sys.executable}" "%~dp0deno" %*\n', encoding="utf-8")
    return folder


def calls(folder: Path) -> list[str]:
    log = folder / "deno_calls.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []
