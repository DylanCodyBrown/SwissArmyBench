"""Connections and blades when the app is not running: a saved notebook runs top to bottom anywhere.

A notebook made in the Workbench reads its tables through `sab.sql("Shop", ...)`, `sab.dax(...)`,
`sab.connection(...)`, `sab.blade(...)` and `sab.read(...)`. With the app running, the app hands over
each connection's code. Without it (a scheduled run on this computer, an Azure Function, a CI job) the
same calls find the connection here, so the notebook runs as it is, with no export step (the owner,
2026-11-15: "no export feature"):

    1. this computer's library (Plans/library.plan.md: ~/.swissarmybench/library, or the folder Settings
       named), when the app is installed here but not running;
    2. the blade folders: those the app lists, those in SWISSARMYBENCH_BLADE_FOLDERS (separated by the
       system's path separator), the current folder and its blades/ folder. A connection's portable file
       (its Export, `Shop.blade.py`) put beside the notebook is found there;
    3. the starter pack, shipped inside the package (`sab.blade("Excel copy template")`).

Passwords: a value saved on this computer (the keyring, when this Python has the keyring package and
the computer a vault), else an environment variable named after the connection and the secret
(Shop's secret("password") reads SHOP_PASSWORD), else one named as the code names it (PASSWORD,
password), else this computer's variable of that name (the library's variables.toml: a password saved
in the connection form is the keyring variable its code names, `secret("SHOP_PASSWORD")`; the app gives
the variables to what it starts while it runs, and a run with the app closed reads them here). A plain
variable the code reads through os.environ (a setting's `${NAME}`) is set in this process's environment
the same way, when the environment does not set it already.

A password that comes from a key vault in the app is the variable the vault would set: an
Azure Function's Key Vault reference sets it, and the vault's own code runs only when it is not set.
Standard library only, like the rest of the client.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from swissarmybench.adapters.blades import KEYRING_SERVICE, BladeStore
from swissarmybench.domain import dataverse, lakes, library, python_connections
from swissarmybench.domain.blades import Blade, VaultUnavailableError, is_blade, read_blade
from swissarmybench.domain.connections import connection_kind, env_name_for

_PACKAGE = Path(__file__).resolve().parents[1]


class NotFoundHereError(LookupError):
    """No saved connection, blade folder or starter has this name."""


class _Store(BladeStore):
    """The app's blade store, read from this Python: a computer with no keyring package (an Azure
    Function, a CI runner) has no saved passwords rather than an import error."""

    @staticmethod
    def _keyring() -> Any:
        try:
            return BladeStore._keyring()
        except ImportError:
            raise VaultUnavailableError("This Python has no keyring package.") from None


def _state() -> Path:
    override = os.environ.get("SWISSARMYBENCH_STATE", "")
    return Path(override) if override else (Path.home() / ".swissarmybench")


def _library() -> Path:
    """The library folder the app uses: the one Settings named (library.json), else the default."""
    state = _state()
    try:
        chosen = json.loads((state / "library.json").read_text(encoding="utf-8")).get("folder")
    except (OSError, ValueError, AttributeError):
        chosen = None
    return Path(chosen) if isinstance(chosen, str) and chosen.strip() else state / "library"


def store() -> BladeStore:
    """The library's blades, the blade folders and the starter pack, as the app would read them."""
    state = _state()
    return _Store(
        _library(),
        folders_file=state / "blade_folders.json",
        pins_file=state / "blade_pins.json",
        starters=_PACKAGE / "starters",
    )


def _here() -> list[Blade]:
    """The blade files in the current folder and its blades/ folder (only those two: the current folder
    of a scheduled run may be anywhere)."""
    found: list[Blade] = []
    for folder in (Path.cwd(), Path.cwd() / "blades"):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.py")):
            try:
                size = path.stat().st_size
            except OSError:
                continue
            blade, _ = BladeStore._load_file(path, size, is_blade, read_blade)
            if blade is not None:
                found.append(blade)
    return found


def find(name: str, blades: BladeStore | None = None) -> Blade:
    """The blade or connection of this name (any case), from the places above, in that order."""
    blades = blades or store()
    try:
        return blades.get(name)
    except KeyError:
        pass
    for blade in _here():
        if blade.name.casefold() == name.casefold():
            return blade
    places = f"{_library()}, the blade folders, the current folder or the starter pack"
    raise NotFoundHereError(
        f"Swiss Army Bench is not running, and no connection or blade named {name!r} is in {places}. "
        "Start the app, or put the connection's exported file (its Export, a .blade.py file) beside the "
        "notebook."
    )


def _from_environment(blade: Blade, wanted: list[str]) -> dict[str, str]:
    """The secrets set as environment variables: the connection's own name first (SHOP_PASSWORD), then
    the name as the code writes it (secret() reads that one itself, too)."""
    found: dict[str, str] = {}
    for secret in wanted:
        for variable in (env_name_for(blade.name, secret), secret):
            if os.environ.get(variable):
                found[secret] = os.environ[variable]
                break
    return found


def _variables(names: list[str]) -> dict[str, str]:
    """This computer's variables among these names, as the app gives them to what it starts
    (services/variables.py apply): a plain value, or a keyring variable's value saved here. Nothing
    readable (no library, no keyring package, no vault): nothing found."""
    if not names:
        return {}
    folder = _library()

    def read(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8") if path.is_file() else ""
        except (OSError, UnicodeError):
            return ""

    # The two files as domain/variables.py read_defined reads them (that module needs the server's packages).
    shared = library.read_variables_toml(read(folder / library.VARIABLES_FILE)) or {}
    local = (library.read_local_toml(read(folder / library.LOCAL_VARIABLES_FILE)) or {}).get("values") or {}
    found: dict[str, str] = {}
    for row in shared.get("variables") or []:
        name, origin = row.get("name"), row.get("from")
        if name not in names or name in found:
            continue
        if origin == "value":
            value = local.get(name) if row.get("local") in ("yes", "true", "True") else row.get("value")
        elif origin == "keyring":
            try:
                value = _Store._keyring().get_password(KEYRING_SERVICE, f"variable/{name}")
            except Exception:  # noqa: S112 (no keyring here: nothing saved)
                continue
        else:
            continue
        if isinstance(value, str):
            found[name] = value
    return found


def spec(name: str) -> dict[str, Any]:
    """What `sab.blade()` runs, in the shape the app's /blades/{name}/python gives it
    (services/blades.py for_python), read from this computer and the environment."""
    blades = store()
    blade = find(name, blades)
    saved = blades.saved_secrets(blade)
    secrets = saved | _from_environment(blade, [s for s in blade.secrets if s not in saved])
    secrets |= _variables([s for s in blade.secrets if s not in secrets])
    # The variables its code reads through os.environ (a setting's ${NAME}), as a running app gives them.
    # (secret()'s names are the secrets above, never put in the environment.)
    reads = python_connections.env_names(blade.code)
    unread = [n for n in reads if n not in os.environ and n not in blade.secrets]
    os.environ.update(_variables(unread))
    vaults, typed = blades.providers(blade)
    if all(s in secrets for s in blade.secrets):
        vaults, typed = [], {}  # every value is here: no vault needs to run, nobody is asked
    python: dict[str, Any] | None = None
    jobs: list[dict[str, Any]] = []
    if connection_kind(blade.kind, blade.template) == "python":
        python = {
            "tables": blade.catalog_command,
            "read": blade.read_command,
            "set": python_connections.plain_values(blade.variables),
            "keyring": python_connections.keyring_names(blade.variables),
        }
        # A variable a vault gives runs that vault only when the variable is not set already.
        unset = {n: s for n, s in blade.variables.items() if not os.environ.get(n)}
        jobs = python_connections.vault_jobs(unset, blades.get, blades.saved_secrets)
    elif lakes.is_kind(blade.dialect):  # a lake's or SharePoint's own read (sab.read)
        python = {"tables": None, "read": lakes.READ, "set": {}, "keyring": []}
    elif dataverse.is_dataverse(blade.dialect):  # its Web API read (sab.read)
        python = {"tables": None, "read": dataverse.READ, "set": {}, "keyring": []}
    return {
        "python": python,
        "name": blade.name,
        "kind": blade.kind,
        "code": blade.code,
        "variable": blade.variable,
        "table": blade.table,  # its table's name (sab.blade registers its result under it)
        "secrets": secrets,
        "vault_mapping": blade.vault_mapping,
        "vault_all": blade.vault_all,
        "env_names": blade.env_names,
        "typed": typed,
        "vaults": [
            {
                "label": v.name,
                "code": v.code,
                "variable": v.variable,
                "mapping": v.vault_mapping,
                "every": v.vault_all,
                "secrets": blades.saved_secrets(v),
            }
            for v in vaults
        ]
        + jobs,
    }


def record(name: str) -> dict[str, Any]:
    """The connection as the app's connections list describes it (no code, no secrets)."""
    blade = find(name)
    return {
        "name": blade.name,
        "kind": blade.kind,
        "dialect": blade.dialect,
        "variable": blade.variable,
        "template": blade.template,
        "connection": connection_kind(blade.kind, blade.template),
    }


def records() -> list[dict[str, Any]]:
    """Every connection found here (saved and in the blade folders), as record() describes each."""
    found = {b.name.casefold(): b for b in [*_here(), *store().all()]}
    return [
        record(b.name)
        for b in sorted(found.values(), key=lambda b: b.name.casefold())
        if connection_kind(b.kind, b.template) not in (None, "vault")
    ]


# ===== a notebook run headless =====
#
#     python -m swissarmybench.client.standalone sales.ipynb
#
# Each code cell runs top to bottom in one namespace, in the notebook's own folder (so `from data
# import ...` finds the project's data.py), under IPython when this Python has it (SQL and DAX cells,
# magics) and as plain Python otherwise. A cell that fails stops the run. The exit code is 0 when every
# cell ran, 1 otherwise.


def _shell() -> Any:
    """A headless IPython shell with the SQL and DAX cells, or None when this Python has no IPython."""
    try:
        from IPython.core.interactiveshell import InteractiveShell
    except ImportError:
        return None
    shell = InteractiveShell.instance()
    shell.reset(new_session=False)  # type: ignore[no-untyped-call]
    from swissarmybench.client import sql_cell

    sql_cell.register(shell)
    return shell


def _shown(shell: Any, value: Any) -> dict[str, Any]:
    """The value a cell ends with, as the kernel would send it (an execute_result's data)."""
    if shell is not None:
        data, _ = shell.display_formatter.format(value)
        return dict(data)
    data = {"text/plain": repr(value)}
    html = getattr(value, "_repr_html_", None)
    if callable(html):
        try:
            made = html()
        except Exception:
            made = None
        if isinstance(made, str):
            data["text/html"] = made
    return data


def run_cell(code: str, namespace: dict[str, Any], shell: Any, label: str) -> list[dict[str, Any]]:
    """One cell's code, run as a kernel would: its outputs as nbformat's records (stdout, displays,
    the value it ends with, an error)."""
    import ast
    import io
    from contextlib import ExitStack, redirect_stderr, redirect_stdout

    displays: list[dict[str, Any]] = []
    out, err = io.StringIO(), io.StringIO()
    shows: list[Any] = []
    with ExitStack() as stack:
        if shell is not None:
            from IPython.utils.capture import capture_output

            shows = stack.enter_context(capture_output(stdout=False, stderr=False, display=True)).outputs
        stack.enter_context(redirect_stdout(out))
        stack.enter_context(redirect_stderr(err))
        try:
            python = shell.transform_cell(code) if shell is not None else code
            tree = ast.parse(python)
            last = tree.body.pop() if tree.body and isinstance(tree.body[-1], ast.Expr) else None
            assert last is None or isinstance(last, ast.Expr)  # noqa: S101 (for the type checker)
            exec(compile(ast.Module(tree.body, []), label, "exec"), namespace)  # noqa: S102 (the user's own notebook)
            value = (
                eval(compile(ast.Expression(last.value), label, "eval"), namespace)  # noqa: S307
                if last is not None
                else None
            )
            if value is not None:
                displays.append(
                    {"output_type": "execute_result", "data": _shown(shell, value), "metadata": {}}
                )
        except Exception as error:
            displays.append(
                {"output_type": "error", "ename": type(error).__name__, "evalue": str(error), "traceback": []}
            )
    shown = [{"output_type": "display_data", "data": dict(s.data), "metadata": {}} for s in shows]
    outputs: list[dict[str, Any]] = []
    if out.getvalue():
        outputs.append({"output_type": "stream", "name": "stdout", "text": out.getvalue()})
    if err.getvalue():
        outputs.append({"output_type": "stream", "name": "stderr", "text": err.getvalue()})
    return outputs + shown + displays


def _where(cell: Any) -> str:
    return f"@cell{cell.number}" + (f" ({cell.name})" if cell.name else "")


def run_notebook(path: str | Path, say: Callable[[str], Any] = print) -> int:
    """Run a saved notebook top to bottom, headless. The exit code: 0 when every cell ran, 1 otherwise.
    `say` gets the report's lines."""
    import sys

    from swissarmybench.domain import notebooks

    notebook = Path(path).expanduser().resolve()
    try:
        cells = notebooks.read_notebook(notebook.read_text(encoding="utf-8"))
    except (OSError, notebooks.NotebookError) as error:
        say(f"{notebook.name}: {error}")
        return 1
    shell = _shell()
    namespace: dict[str, Any] = shell.user_ns if shell is not None else {"__name__": "__main__"}
    here, before_path = Path.cwd(), list(sys.path)
    os.chdir(notebook.parent)
    sys.path.insert(0, str(notebook.parent))
    ran = 0
    failed: str | None = None
    try:
        for cell in cells:
            code = notebooks.code_of(cell)
            if cell.kind == "markdown" or not code.strip():
                continue
            outputs = run_cell(code, namespace, shell, f"<{notebook.name} {_where(cell)}>")
            ran += 1
            broke = next((o for o in outputs if o["output_type"] == "error"), None)
            if broke is not None:
                failed = f"{_where(cell)} failed: {broke['ename']}: {broke['evalue']}"
                break
    finally:
        os.chdir(here)
        sys.path[:] = before_path
        if shell is not None:
            shell.clear_instance()
    said = f"{notebook.name}: {ran} cell{'' if ran == 1 else 's'} run"
    say(said)
    if failed:
        say(failed)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m swissarmybench.client.standalone",
        description="Run a notebook top to bottom without the app.",
    )
    parser.add_argument("notebook", help="the .ipynb file")
    found = parser.parse_args(argv)
    return run_notebook(found.notebook)


if __name__ == "__main__":
    raise SystemExit(main())
