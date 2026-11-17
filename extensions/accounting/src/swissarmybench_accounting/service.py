"""The Accounting extension's use cases: the Excel canvas's designs, Play, Export, templates and their
bindings, building statements and invoices, the register. For the page and the agent alike (the golden
rule): every action here is a route and a command.

  designs   open (workbook.design.json), new, the design as it stands; sheets (add, change, remove) and
            blocks (place, change, move, remove), each edit checked by design.py; save (the file: no data)
  play      the workbook built from the open tables (each one's grid with its steps), in the app's own
            runtime; its preview (each sheet as shown) and its bytes for Download
  export    workbook.py beside the design: the automation that builds the same workbook from data.py
  templates import an existing workbook into the project (templates/<name>.xlsx, its bind.json beside
            it); its preview and bindings; bind and unbind a place
  build     statements or invoices from a template and two open tables (the groups and their lines):
            the dry run first, always (the plan: files, rows, totals; nothing written). The real build is
            the same request after its dry run; the agent's waits for the user's Allow in the page (the
            files are written only when the user said so)
  register  what was built in a folder (register.csv), as rows or opened as a grid

The design never holds rows; the preview and the workbook's bytes live in memory only.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain.datasets import quote
from swissarmybench.domain.grids import POS
from swissarmybench.services.ports import INTERACTIVE
from swissarmybench.services.workspace import Conflict, NotFound, Refused, Workspace
from swissarmybench_accounting import design as rules
from swissarmybench_accounting import exporter, files
from swissarmybench_accounting import templates as binding_rules
from swissarmybench_accounting.design import DesignError

MAX_OPEN = 20


@dataclass
class OpenDesign:
    id: str
    design: dict[str, Any]
    path: str | None = None
    built: bytes | None = None
    preview: dict[str, Any] | None = None
    played_key: str | None = None
    problem: str | None = None
    kept: str = ""  # the design as last saved or opened (unsaved: it differs)
    extra: dict[str, Any] = field(default_factory=dict)


def _key(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16]


class Accounting:
    def __init__(
        self,
        ws: Workspace,
        ask: Callable[[str, str, str], Any],
        store_table: Callable[..., Any],
        project_folder: Callable[[], str | None],
    ) -> None:
        self.ws = ws
        self._ask = ask  # the user's Allow (services/agent.py Approvals.ask)
        self._store_table = store_table  # a table opened as a grid (services/datasets.py)
        self._project = project_folder  # the open project's folder, if any
        self._open: dict[str, OpenDesign] = {}
        self._dry: dict[str, list[dict[str, Any]]] = {}  # each dry run's plan, by its request's key

    # ===== designs =====

    def _get(self, design_id: str) -> OpenDesign:
        found = self._open.get(design_id)
        if found is None:
            raise NotFound("That workbook is not open (the server restarted?): open its design again.")
        return found

    def state(self, design_id: str) -> dict[str, Any]:
        d = self._get(design_id)
        tables = rules.tables_read(d.design)
        open_names = {i.name for i in self.ws.store.all()}
        problems = [
            f"{a} and {b} overlap on {s['name']}" for s in d.design["sheets"] for a, b in rules.overlaps(s)
        ]
        return {
            "id": d.id,
            "path": d.path,
            "title": d.design.get("title") or "",
            "design": d.design,
            "tables": tables,
            "missing": [t for t in tables if t not in open_names],
            "problems": problems,
            "played": d.built is not None,
            "out_of_date": d.built is not None and d.played_key != _key(d.design),
            "problem": d.problem,
            "unsaved": _key(d.design) != d.kept,
        }

    def _keep(self, made: OpenDesign) -> dict[str, Any]:
        if len(self._open) >= MAX_OPEN:
            oldest = next(iter(self._open))
            self._open.pop(oldest)
        self._open[made.id] = made
        return self.state(made.id)

    async def open(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"path": a workbook.design.json} or {"title", "design"?}: a design open on the server."""
        body = body if isinstance(body, dict) else {}
        path = body.get("path")
        if isinstance(path, str) and path.strip():
            for d in self._open.values():
                if d.path == path:
                    return self.state(d.id)
            try:
                raw = await asyncio.to_thread(files.read_json, path)
            except FileNotFoundError:
                raise NotFound(f"There is no design at {path}.") from None
            except ValueError:
                raise DesignError(f"{path} is not a workbook design (its JSON does not read).") from None
            checked = rules.check(raw)
            made = OpenDesign(secrets.token_hex(6), checked, path=path, kept=_key(checked))
        else:
            checked = (
                rules.check(body["design"])
                if body.get("design")
                else rules.new_design(str(body.get("title") or ""))
            )
            made = OpenDesign(
                secrets.token_hex(6), checked, kept="" if not body.get("design") else _key(checked)
            )
        self.ws.audit.write(who, "workbook_open", made.path or checked.get("title") or "")
        return self._keep(made)

    def close(self, design_id: str) -> dict[str, Any]:
        self._open.pop(design_id, None)
        return {"closed": design_id}

    def _edit(
        self, design_id: str, change: Callable[[dict[str, Any]], dict[str, Any]], who: str, what: str
    ) -> dict[str, Any]:
        d = self._get(design_id)
        d.design = change(d.design)
        self.ws.audit.write(who, what, d.path or d.design.get("title") or "")
        return self.state(design_id)

    def put(self, design_id: str, body: Any, who: str = "user") -> dict[str, Any]:
        """The whole design replaced (Undo, Redo, the agent's design written at once)."""
        design = body.get("design") if isinstance(body, dict) and "design" in body else body
        return self._edit(design_id, lambda _: rules.check(design), who, "workbook_design")

    def add_sheet(self, design_id: str, body: Any, who: str = "user") -> dict[str, Any]:
        name = body.get("name") if isinstance(body, dict) else None
        made: dict[str, str] = {}

        def change(design: dict[str, Any]) -> dict[str, Any]:
            new, made["sheet"] = rules.add_sheet(design, name)
            return new

        return self._edit(design_id, change, who, "workbook_sheet_add") | made

    def change_sheet(self, design_id: str, sheet: str, body: Any, who: str = "user") -> dict[str, Any]:
        if not isinstance(body, dict):
            raise DesignError("Send {name?, freeze?, tab_colour?, print?, index?}.")
        return self._edit(
            design_id, lambda d: rules.change_sheet(d, sheet, body), who, "workbook_sheet_change"
        )

    def remove_sheet(self, design_id: str, sheet: str, who: str = "user") -> dict[str, Any]:
        return self._edit(design_id, lambda d: rules.remove_sheet(d, sheet), who, "workbook_sheet_remove")

    def add_block(self, design_id: str, sheet: str, body: Any, who: str = "user") -> dict[str, Any]:
        made: dict[str, str] = {}

        def change(design: dict[str, Any]) -> dict[str, Any]:
            new, made["block"] = rules.add_block(design, sheet, body if isinstance(body, dict) else {})
            return new

        return self._edit(design_id, change, who, "workbook_block_add") | made

    def change_block(self, design_id: str, block: str, body: Any, who: str = "user") -> dict[str, Any]:
        if not isinstance(body, dict):
            raise DesignError("Send the block's fields to change: {cell, w, h, text, source, ...}.")
        return self._edit(
            design_id, lambda d: rules.change_block(d, block, body), who, "workbook_block_change"
        )

    def remove_block(self, design_id: str, block: str, who: str = "user") -> dict[str, Any]:
        return self._edit(design_id, lambda d: rules.remove_block(d, block), who, "workbook_block_remove")

    async def save(self, design_id: str, body: Any, who: str = "user") -> dict[str, Any]:
        """The design's file written (its path, or {"path"}: Save as). Code and layout only: no rows."""
        d = self._get(design_id)
        path = body.get("path") if isinstance(body, dict) and body.get("path") else d.path
        if not isinstance(path, str) or not path.strip():
            raise DesignError('Send {"path": where workbook.design.json goes}.')
        if not path.lower().endswith(".json"):
            path += ".design.json"
        d.path = await asyncio.to_thread(files.write_json, path, d.design)
        d.kept = _key(d.design)
        self.ws.audit.write(who, "workbook_save", d.path)
        return self.state(design_id) | {"modified": files.mtime(d.path)}

    # ===== the data: the open tables, each with its grid's steps =====

    async def tables(self, names: list[str]) -> dict[str, Any]:
        """The named open tables as Arrow tables, each through its first grid's steps (as it is shown)."""
        ws = self.ws
        found = {i.name.lower(): i for i in ws.store.all()}
        missing = [n for n in names if n.lower() not in found]
        if missing:
            listed = ", ".join(sorted(i.name for i in ws.store.all())) or "none"
            raise NotFound(
                f"{', '.join(missing)} {'is' if len(missing) == 1 else 'are'} not open: open it as a grid (or run data.ipynb). Open: {listed}."
            )

        def job(cursor: Any) -> dict[str, Any]:
            out: dict[str, Any] = {}
            for name in names:
                info = found[name.lower()]
                grid = ws.grids.first_for(info.name)
                if grid is not None:
                    sql, columns = ws.views.positioned_sql(cursor, info, grid.steps, grid.settings)
                    picks = ", ".join(quote(c.name) for c in columns)
                    query = f"SELECT {picks} FROM ({sql}) ORDER BY {POS}"
                else:
                    query = f"SELECT * FROM {info.table}"
                with warnings.catch_warnings():  # DuckDB 2 notes the copy an Arrow fetch makes
                    warnings.simplefilter("ignore")
                    result = cursor.execute(query)
                    out[name] = (getattr(result, "to_arrow_table", None) or result.fetch_arrow_table)()
            return out

        return await ws.workers.run(INTERACTIVE, job, ws.store.cursor())

    # ===== Play, Download, Export =====

    async def play(self, design_id: str, who: str = "user") -> dict[str, Any]:
        """The workbook built from the open tables: its preview, and its bytes for Download."""
        d = self._get(design_id)
        design = d.design
        try:
            data = await self.tables(rules.tables_read(design))
            built = await asyncio.to_thread(files.build, design, data)
            d.preview = await asyncio.to_thread(files.preview, built)
        except (NotFound, ValueError) as error:
            d.problem = str(error)
            raise
        d.built, d.played_key, d.problem = built, _key(design), None
        self.ws.audit.write(who, "workbook_play", d.path or design.get("title") or "")
        return self.state(design_id) | {"preview": d.preview}

    def preview(self, design_id: str) -> dict[str, Any]:
        d = self._get(design_id)
        if d.preview is None:
            raise NotFound("Play the workbook first: the preview is the workbook it builds.")
        return self.state(design_id) | {"preview": d.preview}

    def download(self, design_id: str) -> tuple[bytes, str]:
        d = self._get(design_id)
        if d.built is None:
            raise NotFound("Play the workbook first: Download gives the workbook it built.")
        return d.built, exporter.output_name(d.design)

    async def export(self, design_id: str, body: Any, who: str = "user") -> dict[str, Any]:
        """workbook.py written beside the design (or into {"folder"}): the automation, run anywhere."""
        d = self._get(design_id)
        folder = body.get("folder") if isinstance(body, dict) and body.get("folder") else None
        if folder is None:
            folder = files.folder_of(d.path) if d.path else self._project()
        if not folder or not files.is_folder(folder):
            raise DesignError('Save the design first (workbook.py goes beside it), or send {"folder"}.')
        tables = rules.tables_read(d.design)
        text = exporter.workbook_py(d.design, files.runtime_text(), tables)
        path = await asyncio.to_thread(files.write_text, files.join(folder, exporter.FILE), text)
        self.ws.audit.write(who, "workbook_export", path)
        return {
            "path": path,
            "tables": tables,
            "run": f"python {exporter.FILE}",
            "needs": ["openpyxl", "duckdb"],
            "output": exporter.output_name(d.design),
        }

    # ===== templates =====

    def _folder(self, body: Any) -> str:
        folder = body.get("folder") if isinstance(body, dict) else None
        folder = folder or self._project()
        if not isinstance(folder, str) or not folder.strip():
            raise DesignError('No project is open: send {"folder": the project\'s folder}.')
        if not files.is_folder(folder):
            raise NotFound(f"There is no folder {folder}.")
        return folder

    def _template_paths(self, folder: str, name: str) -> tuple[str, str]:
        name = binding_rules.check_name(name)
        return files.join(folder, "templates", f"{name}.xlsx"), files.join(
            folder, "templates", f"{name}.bind.json"
        )

    async def import_template(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"source": an existing .xlsx, "name"?, "folder"?}: copied in as templates/<name>.xlsx, its layout,
        formats, merged cells and named ranges kept; an empty bind.json beside it."""
        if not isinstance(body, dict) or not isinstance(body.get("source"), str):
            raise DesignError('Send {"source": the workbook to import, "name"?: the template\'s name}.')
        folder = self._folder(body)
        source = body["source"]
        stem = source.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
        xlsx, bind = self._template_paths(folder, body.get("name") or stem)
        if files.exists(xlsx) and not body.get("overwrite"):
            raise Conflict(
                f"There is a template {binding_rules.check_name(body.get('name') or stem)} already."
            )
        try:
            await asyncio.to_thread(files.copy_template, source, xlsx)
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        except Exception as error:
            if isinstance(error, ValueError):
                raise
            raise DesignError(f"{stem} does not open as a workbook: {str(error)[:200]}") from None
        if not files.exists(bind) or body.get("overwrite"):
            await asyncio.to_thread(
                files.write_json, bind, {"format": 1, "template": f"{stem}.xlsx", "bindings": []}
            )
        self.ws.audit.write(who, "template_import", xlsx)
        return await self.template({"folder": folder, "name": body.get("name") or stem})

    def templates(self, body: Any) -> dict[str, Any]:
        folder = self._folder(body)
        return {"folder": folder, "templates": files.templates_in(folder)}

    async def template(self, body: Any) -> dict[str, Any]:
        """A template: its preview (sheets, cells, merged, named ranges), its bindings, what they need."""
        if not isinstance(body, dict) or not body.get("name"):
            raise DesignError('Send {"name": the template\'s name}.')
        folder = self._folder(body)
        xlsx, bind = self._template_paths(folder, str(body["name"]))
        if not files.exists(xlsx):
            raise NotFound(f"There is no template {body['name']} in {folder}.")
        bindings = (
            binding_rules.check_bindings(files.read_json(bind))
            if files.exists(bind)
            else {"format": 1, "template": "", "bindings": []}
        )
        shown = await asyncio.to_thread(files.preview, xlsx)
        data, lines = binding_rules.columns_needed(bindings)
        return {
            "name": binding_rules.check_name(str(body["name"])),
            "folder": folder,
            "path": xlsx,
            "bindings": bindings["bindings"],
            "preview": shown,
            "needs": {"data": data, "lines": lines},
        }

    async def bind(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"name", "binding": {kind, place, ...}} binds a place; {"name", "unbind": place} frees one."""
        if not isinstance(body, dict) or not body.get("name"):
            raise DesignError(
                'Send {"name": the template, "binding": {"kind", "place", ...}} or {"unbind": place}.'
            )
        folder = self._folder(body)
        xlsx, bind = self._template_paths(folder, str(body["name"]))
        if not files.exists(xlsx):
            raise NotFound(f"There is no template {body['name']}.")
        current = (
            binding_rules.check_bindings(files.read_json(bind))
            if files.exists(bind)
            else {"format": 1, "template": "", "bindings": []}
        )
        if body.get("unbind"):
            changed = binding_rules.unbind(current, str(body["unbind"]))
        else:
            changed = binding_rules.bind(current, body.get("binding"))
            # The place is the template's: a named range or a cell on one of its sheets.
            await asyncio.to_thread(_check_place, xlsx, changed["bindings"][-1]["place"])
        await asyncio.to_thread(files.write_json, bind, changed)
        self.ws.audit.write(who, "template_bind", xlsx)
        return await self.template({"folder": folder, "name": body["name"]})

    # ===== statements and invoices =====

    async def build(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Statements or invoices: {template, data, lines?, group_by, key?, name, number?, date?,
        one_workbook?, out_folder?, dry_run (default true)}. A dry run gives the plan and writes nothing;
        the build is the same request after its dry run (the agent's waits for the user's Allow)."""
        dry_run = not (isinstance(body, dict) and body.get("dry_run") is False)
        args = binding_rules.check_build(body)
        folder = self._folder(body)
        xlsx, bind = self._template_paths(folder, args["template"])
        if not files.exists(xlsx):
            raise NotFound(f"There is no template {args['template']}: import one first.")
        bindings = (
            binding_rules.check_bindings(files.read_json(bind)) if files.exists(bind) else {"bindings": []}
        )
        if not bindings["bindings"]:
            raise DesignError(f"{args['template']} has no bindings yet: bind its places to the data first.")
        args["out_folder"] = args.get("out_folder") or files.join(folder, "statements")
        key = _key({k: v for k, v in args.items() if k != "overwrite"} | {"bindings": bindings["bindings"]})
        tables = await self.tables([args["data"], *([args["lines"]] if args.get("lines") else [])])
        if not dry_run:
            planned = self._dry.get(key)
            if planned is None:
                raise Conflict("Dry run first: the same build with dry_run true lists the files it makes.")
            if who == "agent":
                detail = "\n".join(
                    [
                        f"Build {len(planned)} {'sheets' if args['one_workbook'] else 'workbooks'} from {args['template']} into:",
                        f"  {args['out_folder']}",
                        *(f"  {p['sheet'] or p['file']}" for p in planned[:20]),
                        *(["  ..."] if len(planned) > 20 else []),
                    ]
                )
                if not await self._ask(args["template"], "build statements", detail):
                    raise Refused("The user declined (or did not answer): nothing was built.")
        plan = await asyncio.to_thread(
            files.build_statements,
            xlsx,
            tables[args["data"]],
            tables.get(args["lines"]) if args.get("lines") else None,
            args,
            bindings["bindings"],
            dry_run,
        )
        if dry_run:
            self._dry[key] = plan
            if len(self._dry) > 50:
                self._dry.pop(next(iter(self._dry)))
        else:
            self._dry.pop(key, None)
            self.ws.audit.write(who, "statements_build", args["out_folder"], files=len(plan))
        totals: dict[str, float] = {}
        for p in plan:
            for column, value in p["totals"].items():
                totals[column] = round(totals.get(column, 0.0) + value, 2)
        return {
            "dry_run": dry_run,
            "folder": args["out_folder"],
            "files": plan,
            "count": len(plan),
            "totals": totals,
        }

    async def register(self, body: Any, who: str = "user") -> dict[str, Any]:
        """What was built in a folder ({"folder"}: default the project's statements/): register.csv's
        rows; {"open": true} opens it as a grid named register."""
        body = body if isinstance(body, dict) else {}
        target = body.get("out_folder") or files.join(self._folder(body), "statements")
        header, rows = await asyncio.to_thread(files.read_register, target)
        out: dict[str, Any] = {"folder": target, "columns": header, "rows": [list(r) for r in rows]}
        if body.get("open"):
            if not rows:
                raise NotFound(f"Nothing was built in {target} yet.")
            import pyarrow as pa

            table = pa.table({c: [r[i] for r in rows] for i, c in enumerate(header)})
            opened = await self._store_table("register", table, "file", True, who)
            out["grid"] = opened.get("grid") if isinstance(opened, dict) else None
        return out


def _check_place(xlsx: str, place: str) -> None:
    from openpyxl import load_workbook

    from swissarmybench_accounting import runtime

    runtime.place_of(load_workbook(xlsx), place)
