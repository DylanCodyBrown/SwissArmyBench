"""Export as one Python script (docs/ideas.md, 2026-11-15; the rules in domain/script_export.py). For
the Workbench window and the agent alike (the golden rule: `workbench_export_script`).

  export    a notebook or script (the open one as it stands, or a file) as ONE .py that runs with
            plain `python <file>` anywhere: its tables' cells as the grid has them now, each
            connection, vault and blade it uses written out, its settings named. Checked before it
            is written: it compiles, it holds no saved password's value and no row, and (when ruff is
            in the app's Python) Python's own checks find no undefined name. Something that cannot be
            exported is said by its cell; with `stub`, each such cell is a stub that raises FILL IN
            and the rest is written. An API_<name>.py beside the document that its code imports (one
            Add API made: services/apis.py `inline`) is written inside it, so the import still works

The script holds code only (no rows, no passwords), so the agent's export asks nothing; the file goes
where it is sent, as a Save as does. Its answer names each connection it uses that leans on this computer
(`local`, `local_words`: domain/portability.py), so the page warns before it writes ("Only works on your
machine"; the owner, 2026-11-17: "this is meant to scale to a function app or up to a hosted streamlit
application").
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from typing import Any, Protocol

from swissarmybench.domain import dataverse, notebooks, portability
from swissarmybench.domain import sandbox as sandbox_rules
from swissarmybench.domain import script_export as rules
from swissarmybench.domain import script_runtime as runtime
from swissarmybench.domain.blades import Blade
from swissarmybench.domain.connections import code_names, connection_kind, opens_in_code
from swissarmybench.domain.script_export import ExportCell, Piece
from swissarmybench.services.workspace import Conflict, NotFound, Refused, Workspace

ASK_STUB: str = (
    "Export the rest, with a stub that raises FILL IN for each of these? Send stub: true "
    "(the page asks the user)."
)


class Blades(Protocol):
    def get(self, name: str) -> Blade: ...

    def all(self) -> list[Blade]: ...

    def saved_secrets(self, blade: Blade) -> dict[str, str]: ...


class ScriptExports:
    def __init__(
        self,
        ws: Workspace,
        blades: Blades,
        read_document: Callable[[str], tuple[str, str, float]],
        write_document: Callable[[str, str], tuple[str, float]],
        arrange: Callable[[Any], Awaitable[dict[str, Any]]],
        lint: Callable[[str], list[dict[str, Any]] | None],
        folder_of: Callable[[str], str],
        join: Callable[[str, str], str],
        inline: Callable[[str, Iterable[str]], list[dict[str, str]]] = lambda folder, codes: [],
    ) -> None:
        self.ws = ws
        self._blades = blades
        self._read = read_document
        self._write = write_document
        self._arrange = arrange  # the document's tables' cells as the grid has them (services/table_cells.py)
        self._lint = lint  # ruff's findings (None: no ruff in the app's Python)
        self._folder_of = folder_of
        self._join = join
        self._inline = inline  # the API clients the code imports, from beside the document

    # ===== the document =====

    async def _cells(self, body: dict[str, Any]) -> tuple[list[ExportCell], str | None]:
        """The document's cells as they stand: sent (the open one, saved or not), else read from its
        file; each open table's read-only cell as the grid has it now."""
        path = body.get("path") if isinstance(body.get("path"), str) and body["path"].strip() else None
        kind = body.get("kind")
        cells_sent, text_sent = body.get("cells"), body.get("text")
        if cells_sent is None and text_sent is None:
            if path is None:
                raise ValueError('Send {"path": the notebook or script} (or its "cells" or "text").')
            try:
                text, path, _ = self._read(path)
            except FileNotFoundError as error:
                raise NotFound(str(error)) from None
            kind = notebooks.kind_of(path)
            if kind == "notebook":
                cells_sent = [c.to_json() for c in notebooks.read_document(text)[0]]
            elif kind == "script":
                text_sent = text
            else:
                raise ValueError("Export a notebook (.ipynb) or a script (.py).")
        if kind is None:
            kind = "notebook" if cells_sent is not None else "script"
        if kind == "notebook":
            cells = notebooks.read_cells(cells_sent)
            tables = [c.table for c in cells if c.role == "transformations" and c.table]
            if tables:
                sent = {"kind": "notebook", "cells": [c.to_json() for c in cells], "tables": tables}
                arranged = await self._arrange(sent | {"move": False})
                # The arrangement is about the tables' cells: each cell's connection and name stay.
                kept = {c.number: c for c in cells if c.number is not None}
                cells = notebooks.read_cells(arranged["cells"])
                for cell in cells:
                    held = kept.get(cell.number) if cell.number is not None else None
                    if held is not None and held.kind == cell.kind:
                        cell.connection, cell.name = held.connection, held.name
            return [
                ExportCell(c.kind, c.source, c.connection, c.role, c.table, c.number, c.name) for c in cells
            ], path
        if not isinstance(text_sent, str):
            raise ValueError("Send the script's text.")
        found = rules.script_cells(text_sent)
        tables = [c.table for c in found if c.role == "transformations" and c.table]
        if tables:
            arranged = await self._arrange(
                {"kind": "script", "text": text_sent, "tables": tables, "move": False}
            )
            found = rules.script_cells(arranged["text"])
        return found, path

    # ===== the connections, vaults and blades =====

    def _piece(self, blade: Blade, everything: list[Blade]) -> tuple[Piece, dict[str, str]]:
        """A blade as the script writes it out, and its saved values (to prove none is written)."""
        saved = self._blades.saved_secrets(blade)
        kind = connection_kind(blade.kind, blade.template)
        if kind == "python":
            secrets = rules.python_sources(blade.name, blade.variables, blade.env_reads)
        else:
            vaults = [(b.name, dict(b.vault_mapping), b.vault_all) for b in everything if b.kind == "vault"]
            vaults = [v for v in vaults if v[0] != blade.name]
            typed = {env: b.name for b in everything if b.kind == "secret" for env in b.env_names}
            secrets = rules.secret_sources(blade.name, blade.secrets, saved, vaults, typed)
        piece = Piece(
            blade.name,
            blade.kind,
            kind,
            blade.code,
            blade.variable or "",
            blade.dialect,
            read=dataverse.READ if dataverse.is_dataverse(blade.dialect) else blade.read_command,
            secrets=tuple(secrets),
            vault_mapping=dict(blade.vault_mapping),
            vault_all=blade.vault_all,
            env_names=tuple(blade.env_names),
        )
        return piece, saved

    def _pieces(self, wanted: list[str]) -> tuple[dict[str, Piece], list[str]]:
        everything = self._blades.all()
        chosen: dict[str, Blade] = {}
        for name in wanted:
            try:
                blade = self._blades.get(name)
            except KeyError:
                continue  # said by the export: not a connection or blade the app has
            chosen[blade.name] = blade
        for blade in everything:  # the vaults and secret blades a password may come from
            if blade.kind in ("vault", "secret"):
                chosen.setdefault(blade.name, blade)
        pieces: dict[str, Piece] = {}
        values: list[str] = []
        for blade in chosen.values():
            piece, saved = self._piece(blade, everything)
            pieces[blade.name] = piece
            values += saved.values()
        return pieces, values

    def local_notes(self, wanted: Iterable[str]) -> list[dict[str, Any]]:
        """Each connection named in `wanted` that will not run on a Function App or a hosted Streamlit
        app, with why (domain/portability.py): its kind, its sign-in, a password saved in this
        computer's keyring and in no vault it reads."""
        everything = self._blades.all()
        vaults = [b for b in everything if b.kind == "vault"]
        found = []
        for name in dict.fromkeys(wanted):
            try:
                blade = self._blades.get(name)
            except KeyError:
                continue
            saved = self._blades.saved_secrets(blade)
            passwords = [
                "keyring"
                for secret in saved
                if not any(v.vault_all or secret in v.vault_mapping for v in vaults)
            ]
            found.append((blade.name, blade.code, blade.template, passwords))
        return portability.export_notes(found)

    def connections_code(self, wanted: list[str]) -> dict[str, Any]:
        """The connections a local sandbox API's export uses (services/api_export.py), each as its own code
        (as a script export writes it: settings from the environment, a vault by managed identity), then
        their registry and connection(name): {text, requirements, variables, notes}. Checked as an export
        is: no saved password's value in it (Refused otherwise)."""
        # The project's Sandbox is never exported as a connection: it is local test data, never live.
        wanted = [w for w in wanted if not sandbox_rules.is_sandbox(w)]
        if not wanted:
            return {"text": "", "requirements": [], "variables": [], "notes": []}
        source = "import swissarmybench as sab\n" + "\n".join(
            f"_c{i} = sab.connection({name!r})" for i, name in enumerate(wanted)
        )
        cells = [ExportCell("code", source)]
        names = self._code_names()
        pieces, values = self._pieces(wanted)
        made = rules.plan("API", "API.py", cells, pieces, names)
        shared = rules.shared_parts(made)
        text = "\n\n".join(
            [
                runtime.IMPORTS,
                'log = logging.getLogger("connections")',
                shared.settings_text,
                shared.helpers,
                *shared.pieces,
                shared.registry,
            ]
        )
        stopped = rules.check(text, values)
        if stopped:
            raise Refused("connections.py was not written: " + "; ".join(dict.fromkeys(stopped)) + ".")
        _, listed = runtime.settings_block(made.settings)
        return {
            "text": text,
            "requirements": list(shared.requirements.values()),
            "variables": [str(v.get("variable")) for v in listed],
            "notes": self.local_notes(wanted),
        }

    def _code_names(self) -> dict[str, str]:
        """Each connection's variable in the Workbench (shop -> Shop), as services/blades.py names them."""
        opened = [b.name for b in self._blades.all() if opens_in_code(connection_kind(b.kind, b.template))]
        return {code: name for name, code in code_names(sorted(opened, key=str.casefold)).items()}

    # ===== the export =====

    async def export(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Export as one Python script, or (format "notebook") as one self-contained notebook.

        {"path": the notebook or script, "cells"? | "text"?: as it stands in the window,
         "kind"?: notebook or script, "format"?: script (default) or notebook, "to"?: where it
         goes (default: beside it, as <name>_automation.py or .ipynb), "stub"?: true to export the
         rest with a stub for what cannot be, "check"?: true to write nothing (what would be
         written, and what stops it)}
        """
        if not isinstance(body, dict):
            raise ValueError('Send {"path": the notebook or script, "to": the script to write}.')
        notebook = body.get("format", "script") == "notebook"
        if body.get("format", "script") not in ("script", "notebook"):
            raise ValueError('format is "script" (one .py) or "notebook" (one .ipynb).')
        suffix = ".ipynb" if notebook else ".py"
        cells, path = await self._cells(body)
        stub = body.get("stub") is True
        names = self._code_names()
        wanted = rules.references(cells, names)
        pieces, values = self._pieces(wanted)
        local = self.local_notes(wanted)
        title = (path or body.get("name") or "notebook").replace("\\", "/").rsplit("/", 1)[-1]
        title = title.rsplit(".", 1)[0] if "." in title else title
        to = body.get("to") if isinstance(body.get("to"), str) and body["to"].strip() else None
        if to is not None and not to.lower().endswith(suffix):
            to += suffix
        if to is None:
            if path is None:
                raise ValueError(f'Name where it goes: {{"to": ".../orders_automation{suffix}"}}.')
            named = rules.file_name(path, rules.NOTEBOOK_SUFFIX if notebook else rules.SUFFIX)
            to = self._join(self._folder_of(path), named)
        file = to.replace("\\", "/").rsplit("/", 1)[-1]
        codes = [c.source for c in cells if c.kind == "code"]
        clients = (
            [(c["module"], c["code"]) for c in self._inline(self._folder_of(path), codes)] if path else []
        )
        render = rules.export_notebook if notebook else rules.export
        made = render(
            title, path or f"{title}.ipynb", cells, pieces, names, stub=stub, file=file, clients=clients
        )
        stopped = rules.check(made.python, values)
        if notebook:  # its file as a whole too (its Markdown): a value or a row anywhere in it
            stopped += [s for s in rules.check(made.text, values) if not s.startswith("line ")]
        if stopped:
            # Never written: a password's value or a row would leave, or it does not compile.
            what = "notebook" if notebook else "script"
            raise Refused(f"The {what} was not written: " + "; ".join(dict.fromkeys(stopped)) + ".")
        linted = self._lint(made.python)
        findings = linted or []
        lint = [f"{rules.place_of(made.places, f['line'])}: {f['message']} ({f['code']})" for f in findings]
        answer: dict[str, Any] = {
            "path": None,
            "file": file,
            "requirements": list(made.requirements),
            "settings": list(made.settings),
            "stubs": list(made.stubs),
            "skipped": list(made.skipped),
            "problems": [str(p) for p in made.problems],
            "lint": lint,
            "linted": linted is not None,  # ruff checked it (False: no ruff in the app's Python)
            # Each connection it uses that only runs on this computer: the page asks before it writes.
            "local": local,
            "local_words": portability.export_words(local),
        }
        if body.get("check") is True:
            return answer | {"text": made.text}
        if (made.problems or lint) and not stub:
            return answer | {"ask": ASK_STUB}
        try:
            written, _ = self._write(to, made.text)
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        except PermissionError as error:
            raise Conflict(str(error)) from None
        self.ws.audit.write(
            who, "export_notebook" if notebook else "export_script", written, stubs=len(made.stubs)
        )
        run = f"jupyter nbconvert --to notebook --execute {file}" if notebook else f"python {file}"
        return answer | {"path": written, "format": "notebook" if notebook else "script", "run": run}
