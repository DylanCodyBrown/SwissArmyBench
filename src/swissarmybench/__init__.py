"""Swiss Army Bench: a local server that shows tabular data in live grids in the browser.

From a notebook, nothing to write beyond the import:

    import swissarmybench       # starts the watcher when IPython is running
    SOD = trino.execute("SELECT ...")

The grid's Open list shows SOD. Click it and it opens; run the cell again and the open tab refreshes.
In a plain script call `sab.watch()` once. `push` still works, for what the watcher cannot see
(a script about to exit, a table made inside a function):

    sab.push(orders)

The client needs only the standard library (pyarrow, when present, keeps column types), so it goes into
any project's environment. It only connects: the grid server (installed once per machine with the
[server] extra, a uv tool) is started by the `swissarmybench` command and shows the grids.
The design is Plans/swissarmybench-build-plan.md and Plans/autodetect-and-reload.plan.md.

The client is loaded on first use (a module-level `__getattr__`, PEP 562), so `import swissarmybench`
costs nothing until `push` or `watch` is touched. That is what keeps the `sab` agent command, which
lives in this package and never pushes, fast to start.
"""

from __future__ import annotations

import sys
from importlib import import_module
from typing import TYPE_CHECKING, Any

from swissarmybench.renamed import env

if TYPE_CHECKING:
    from swissarmybench.client.blades_client import blade, blades, load, read
    from swissarmybench.client.blades_client import blade as connection
    from swissarmybench.client.completion import complete
    from swissarmybench.client.push_client import DatasetTooLargeError, ServerNotRunningError, push
    from swissarmybench.client.sandbox_client import sandbox
    from swissarmybench.client.sql_cell import dax, sql
    from swissarmybench.client.watcher import start as watch
    from swissarmybench.client.watcher import stop as unwatch

__version__: str = "0.0.3"
__all__ = [
    "DatasetTooLargeError",
    "ServerNotRunningError",
    "__version__",
    "blade",
    "blades",
    "complete",
    "connection",
    "dax",
    "load",
    "push",
    "read",
    "sandbox",
    "sql",
    "unwatch",
    "watch",
]

# Public name -> (module, attribute), imported when first asked for.
_LAZY: dict[str, tuple[str, str]] = {
    "push": ("swissarmybench.client.push_client", "push"),
    "load": ("swissarmybench.client.blades_client", "load"),
    "blade": ("swissarmybench.client.blades_client", "blade"),
    "blades": ("swissarmybench.client.blades_client", "blades"),
    # A connection (a database or file, added in the app's Connections) is run the way a blade is.
    "connection": ("swissarmybench.client.blades_client", "blade"),
    # A table by a connection's own Read a table box (a connection made of your own Python).
    "read": ("swissarmybench.client.blades_client", "read"),
    "sql": ("swissarmybench.client.sql_cell", "sql"),
    # DAX on one dataset of a Power BI workspace connection: sab.dax("Finance/Sales model", ...).
    "dax": ("swissarmybench.client.sql_cell", "dax"),
    "sandbox": ("swissarmybench.client.sandbox_client", "sandbox"),
    "complete": ("swissarmybench.client.completion", "complete"),
    "DatasetTooLargeError": ("swissarmybench.client.push_client", "DatasetTooLargeError"),
    "ServerNotRunningError": ("swissarmybench.client.push_client", "ServerNotRunningError"),
    "watch": ("swissarmybench.client.watcher", "start"),
    "unwatch": ("swissarmybench.client.watcher", "stop"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module 'swissarmybench' has no attribute {name!r}")
    value = getattr(import_module(target[0]), target[1])
    globals()[name] = value  # later lookups skip this function
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY})


# Start the watcher on import in a notebook or the interactive window, where importing the package is
# already the decision to use the grid. The watcher's own autostart makes the final call (and honors
# SWISSARMYBENCH_WATCH=0); this only avoids loading it when it cannot start: IPython has to be
# loaded already for it to be running, so a plain script, the server and the MCP never pay for the import.
if env("SWISSARMYBENCH_WATCH", "") == "1" or "IPython" in sys.modules:
    from swissarmybench.client.watcher import autostart

    autostart()
# Catalog completion inside SQL strings, and SQL cells on a connection: only in Jupyter and IPython.
if "IPython" in sys.modules:
    from swissarmybench.client.completion import autostart as complete_on_tab
    from swissarmybench.client.sql_cell import autostart as sql_cells

    complete_on_tab()
    # %%sql <connection> cells (and %%sab, %sql_connect, %sql_connections): SWISSARMYBENCH_SQL_CELL=0 is off.
    sql_cells()
