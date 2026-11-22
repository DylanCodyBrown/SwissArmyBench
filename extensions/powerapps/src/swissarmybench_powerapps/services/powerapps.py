"""The Power Apps extension's use cases: the tools, signing in, environments, the code app project, its
data sources, the environment's connectors, Run live, Push and custom connectors.

The Power Apps CLI and the Power Platform CLI do the work (domain/cli_lines.py builds each command line);
this runs them, streams each line to the pages (`powerapps_output`), keeps the run in this session's
memory (`runs`: the command's words, never a value it carried twice), and writes each to the audit log, so
the Session page shows it. Everything that talks to Power Platform runs on the user's action or the agent's
command, never in the background. Push and a custom connector change the environment: the agent's wait
for the user's Allow. A missing tool is the base's missing-package answer (422), installed on the user's
word.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from swissarmybench.domain.packages import MissingPackagesError
from swissarmybench.services.ports import Approvals
from swissarmybench.services.workspace import Conflict, NotFound, Refused
from swissarmybench_powerapps.domain import cli_lines, connectors, pages, project, shown, tools

TIMEOUTS: dict[str, float] = {
    "quick": 120.0,
    "sign_in": 300.0,
    "install": 900.0,
    "push": 900.0,
}
MAX_RUNS = 60
MAX_OUTPUT_SHOWN = 20_000


# ===== the ports =====


class RanLike(Protocol):
    argv: list[str]
    code: int | None
    output: str
    seconds: float
    timed_out: bool


Line = Callable[[str], Awaitable[None] | None]


class Runner(Protocol):
    def which(self, program: str) -> str | None: ...

    def system(self) -> str: ...

    async def run(
        self, argv: list[str], cwd: str | None, timeout: float, on_line: Line | None = None
    ) -> RanLike: ...

    async def start(self, argv: list[str], cwd: str | None, on_line: Line | None = None) -> Any: ...


class Stop(Protocol):
    async def __call__(self, process: Any) -> None: ...


class Files(Protocol):
    def exists(self, folder: str) -> bool: ...

    def resolve(self, folder: str) -> str: ...

    def parent_of(self, folder: str) -> str: ...

    def join(self, folder: str, *parts: str) -> str: ...

    def read(self, folder: str, relative: str) -> str | None: ...

    def write(self, folder: str, relative: str, text: str) -> str: ...

    def listing(self, folder: str) -> list[str]: ...

    def empty_or_missing(self, folder: str) -> bool: ...

    def state(self) -> dict[str, Any]: ...

    def save_state(self, data: dict[str, Any]) -> None: ...


class ConnectorService(Protocol):
    """The environment's connectivity service (a connector's definition, with pac's sign-in)."""

    def __call__(self, name: str, environment_id: str, token: str) -> dict[str, Any]: ...


class Audit(Protocol):
    def write(self, actor: str, action: str, dataset: str | None = None, **details: Any) -> None: ...


class Live(Protocol):
    async def broadcast(self, message: dict[str, Any]) -> None: ...


class ApiDocuments(Protocol):
    """The library's APIs (the APIs page): an API's OpenAPI document and its sign-in (never a secret)."""

    def __call__(self, name: str) -> tuple[dict[str, Any], dict[str, Any]]: ...


@dataclass
class Run:
    id: str
    words: str
    who: str
    started: float
    lines: list[str] = field(default_factory=list)
    code: int | None = None
    seconds: float = 0.0
    done: bool = False
    timed_out: bool = False

    def to_json(self, full: bool = False) -> dict[str, Any]:
        text = "\n".join(self.lines)
        return {
            "id": self.id,
            "command": self.words,
            "who": self.who,
            "started": self.started,
            "code": self.code,
            "ok": self.done and self.code == 0,
            "done": self.done,
            "timed_out": self.timed_out,
            "seconds": round(self.seconds, 2),
            "output": text if full else text[-MAX_OUTPUT_SHOWN:],
        }


def words_of(argv: list[str]) -> str:
    """A command line in words, without its values: the program and its verbs ("pa app push")."""
    verbs = []
    for part in argv:
        if part in ("--yes", "--"):  # a switch that carries nothing
            continue
        if part.startswith("-"):
            break
        verbs.append(part)
    return " ".join(verbs[:4])


@dataclass
class LiveApp:
    key: str
    port: int
    base: str
    folder: str
    handle: Any
    local_url: str
    play_url: str | None = None
    ready: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "running": bool(self.handle.running),
            "ready": self.ready,
            "pane": f"{self.base}",
            "local_url": self.local_url,
            "play_url": self.play_url,
            "port": self.port,
        }


class PowerApps:
    def __init__(
        self,
        runner: Runner,
        stop: Stop,
        files: Files,
        connector_service: ConnectorService,
        audit: Audit,
        live: Live,
        approvals: Approvals,
        api_documents: ApiDocuments,
        free_port: Callable[[], int],
        prefix: str,
        opened: Callable[[str | None], None] = lambda folder: None,
    ) -> None:
        self._runner = runner
        self._stop = stop
        self._files = files
        self._connector_service = connector_service
        self._audit = audit
        self._live = live
        self._approvals = approvals
        self._api_documents = api_documents
        self._free_port = free_port
        self._prefix = prefix
        self._runs: OrderedDict[str, Run] = OrderedDict()
        self._tools: dict[str, dict[str, Any]] | None = None
        self._folder: str | None = None
        self._account: dict[str, Any] | None = None
        self._environments: list[dict[str, Any]] | None = None
        self._connectors: list[dict[str, Any]] | None = None
        self._live_app: LiveApp | None = None
        self._pushes: list[dict[str, Any]] = []
        self._busy: set[str] = set()
        # The open project is told (the base's mode follows the open code app's type).
        self._told = opened

    def use_api_documents(self, api_documents: ApiDocuments) -> None:
        """An API's OpenAPI document and sign-in read through `api_documents` from now on (a test's stand-in
        for the library's APIs)."""
        self._api_documents = api_documents

    @property
    def folder(self) -> str | None:
        return self._folder

    def _recent(self) -> str | None:
        """The code app last opened (Open it again offers it; it is not opened by itself)."""
        remembered = self._files.state().get("folder")
        return remembered if isinstance(remembered, str) and self._files.exists(remembered) else None

    # ===== running a command =====

    async def _run(
        self, argv: list[str], who: str, timeout: float, cwd: str | None = None, keep: bool = True
    ) -> RanLike:
        """Run one command: its lines streamed to the pages, the run kept for this session and written to
        the audit log (its words only). `keep=False`: a run whose output is a secret (pac auth token):
        neither streamed, kept nor logged beyond its words."""
        cli_lines.check_argv(argv)
        run = Run(secrets.token_hex(4), words_of(argv), who, time.time())
        if keep:
            self._runs[run.id] = run
            while len(self._runs) > MAX_RUNS:
                self._runs.popitem(last=False)
            await self._live.broadcast({"type": "powerapps_run", "run": run.to_json()})

        async def line(text: str) -> None:
            if not keep:
                return
            shown = cli_lines.plain(text)
            run.lines.append(shown)
            await self._live.broadcast({"type": "powerapps_output", "run": run.id, "line": shown})

        try:
            ran = await self._runner.run(argv, cwd, timeout, line)
        except FileNotFoundError:
            run.done, run.code = True, 127
            raise self._missing_for(argv[0]) from None
        run.code, run.seconds, run.done, run.timed_out = ran.code, ran.seconds, True, ran.timed_out
        if keep:
            await self._live.broadcast({"type": "powerapps_run", "run": run.to_json()})
        self._audit.write(
            who,
            "powerapps_run",
            None,
            command=run.words,
            code=ran.code,
            ok=ran.code == 0 and not ran.timed_out,
        )
        return ran

    def _missing_for(self, program: str) -> MissingPackagesError:
        """A program that was not there after all: the missing-package answer for it."""
        tool = program if program in tools.TOOLS else "node"
        spec = tools.TOOLS[tool]
        self._tools = None  # looked for again next time
        return MissingPackagesError(
            {
                "feature": f"{spec.name[0].upper()}{spec.name[1:]} ({spec.purpose})",
                "packages": [spec.name],
                "python": "tool",
                "command": spec.installs[tools.system_of(self._runner.system())],
                "tool": tool,
            }
        )

    def _failed(self, ran: RanLike, what: str) -> Exception:
        if ran.timed_out:
            return Conflict(f"{what} took too long and was stopped.")
        said = cli_lines.plain_error(ran.output, self._environment_name())
        tail = "\n".join(ran.output.splitlines()[-8:])
        return Conflict(said or f"{what} failed (exit {ran.code}): {tail}".strip())

    def runs(self, run_id: str | None = None) -> dict[str, Any]:
        if run_id:
            run = self._runs.get(run_id)
            if run is None:
                raise NotFound(f"There is no run {run_id} this session.")
            return {"run": run.to_json(full=True)}
        return {"runs": [r.to_json() for r in reversed(self._runs.values())]}

    # ===== tools =====

    async def tools_state(self, refresh: bool = False) -> dict[str, Any]:
        if self._tools is None or refresh:
            system = tools.system_of(self._runner.system())
            found: dict[str, dict[str, Any]] = {}
            for ident, spec in tools.TOOLS.items():
                path = self._runner.which(ident)
                version = None
                if path:
                    try:
                        ran = await self._runner.run([ident, *spec.version_args], None, 30.0)
                        version = tools.parse_version(ident, ran.output)
                    except (FileNotFoundError, OSError):
                        path = None
                found[ident] = tools.tool_state(ident, path, version, system)
            self._tools = found
        return {"system": tools.system_of(self._runner.system()), "tools": list(self._tools.values())}

    async def _need(self, action: str) -> None:
        await self.tools_state()
        found = tools.missing(action, self._tools or {})
        if found is None:
            return
        # Looked again (the user may have installed it since).
        await self.tools_state(refresh=True)
        found = tools.missing(action, self._tools or {})
        if found is not None:
            raise MissingPackagesError(found["missing"])

    async def install_tool(self, tool: Any, who: str) -> dict[str, Any]:
        """Install a tool with this system's command, on the user's word (the agent's waits for Allow)."""
        if tool not in tools.TOOLS:
            raise NotFound(f"{tool} is not one of the tools ({', '.join(tools.TOOLS)}).")
        system = tools.system_of(self._runner.system())
        argv = tools.install_argv(str(tool), system)
        command = tools.TOOLS[str(tool)].installs[system]
        if argv is None:
            raise Conflict(f"Run this in a terminal (it asks for your password): {command}")
        await self._approvals.allowed(
            who,
            subject=str(tool),
            action="install",
            detail=f"Install {tools.TOOLS[str(tool)].name} with: {command}",
            otherwise=f"{tools.TOOLS[str(tool)].name} was not installed",
        )
        ran = await self._run(argv, who, TIMEOUTS["install"])
        await self.tools_state(refresh=True)
        if ran.code != 0:
            raise self._failed(ran, f"Installing {tools.TOOLS[str(tool)].name}")
        return await self.tools_state()

    # ===== signing in and environments =====

    async def account(self, refresh: bool = True) -> dict[str, Any]:
        await self._need("auth")
        if self._account is None or refresh:
            ran = await self._run(cli_lines.auth_status(), "user", TIMEOUTS["quick"])
            if ran.code != 0:
                raise self._failed(ran, "pa auth status")
            self._account = cli_lines.accounts(ran.output)
        return self._account

    async def sign_in(self, account: Any, who: str) -> dict[str, Any]:
        await self._need("auth")
        ran = await self._run(cli_lines.auth_login(account), who, TIMEOUTS["sign_in"])
        if ran.code != 0:
            raise self._failed(ran, "Signing in")
        return await self.account()

    async def switch_account(self, account: Any, who: str) -> dict[str, Any]:
        await self._need("auth")
        ran = await self._run(cli_lines.auth_switch(account), who, TIMEOUTS["quick"])
        if ran.code != 0:
            raise self._failed(ran, "Switching the account")
        return await self.account()

    async def environments(self, who: str = "user") -> dict[str, Any]:
        """The environments this sign-in reaches (`pac env list`), the project's marked."""
        await self._need("environments")
        ran = await self._run(cli_lines.pac_env_list(), who, TIMEOUTS["quick"])
        if ran.code != 0:
            raise self._failed(ran, "pac env list")
        self._environments = cli_lines.environments(ran.output)
        return {"environments": self._mark_project(self._environments)}

    def state_environments(self) -> list[dict[str, Any]]:
        """The environments last listed this session (none listed yet: empty), nothing run."""
        return list(self._environments or [])

    def _mark_project(self, found: list[dict[str, Any]]) -> list[dict[str, Any]]:
        current = self._summary().get("environment_id") if self._folder else None
        return [e | {"project": bool(current) and e["id"].lower() == str(current).lower()} for e in found]

    def _environment_name(self) -> str:
        current = self._summary().get("environment_id") if self._folder else ""
        for e in self._environments or []:
            if current and e["id"].lower() == str(current).lower():
                return str(e["name"])
        return str(current or "")

    async def profiles(self, who: str = "user") -> dict[str, Any]:
        await self._need("environments")
        ran = await self._run(cli_lines.pac_auth_list(), who, TIMEOUTS["quick"])
        if ran.code != 0:
            raise self._failed(ran, "pac auth list")
        return {"profiles": cli_lines.profiles(ran.output)}

    async def create_profile(self, environment: Any, who: str) -> dict[str, Any]:
        await self._need("environments")
        ran = await self._run(cli_lines.pac_auth_create(environment), who, TIMEOUTS["sign_in"])
        if ran.code != 0:
            raise self._failed(ran, "pac auth create")
        return await self.profiles(who)

    async def select_profile(self, index: Any, who: str) -> dict[str, Any]:
        await self._need("environments")
        ran = await self._run(cli_lines.pac_auth_select(index), who, TIMEOUTS["quick"])
        if ran.code != 0:
            raise self._failed(ran, "pac auth select")
        self._environments = None
        return await self.profiles(who)

    # ===== the project =====

    def _config(self) -> dict[str, Any]:
        if not self._folder:
            raise Conflict("No code app is open: New code app makes one, Open code app opens one.")
        return project.config(self._files.read(self._folder, project.CONFIG))

    def _summary(self) -> dict[str, Any]:
        try:
            return project.summary(self._config())
        except (Conflict, project.ProjectError):
            return {}

    def project_state(self) -> dict[str, Any]:
        if not self._folder:
            return {"open": False, "recent": self._recent()}
        try:
            cfg = self._config()
        except project.ProjectError as error:
            return {"open": True, "folder": self._folder, "problem": str(error)}
        listing = self._files.listing(self._folder)
        return {
            "open": True,
            "folder": self._folder,
            "type": project.PROJECT_TYPE,
            "app": project.summary(cfg),
            "environment": self._environment_name(),
            "sources": project.sources(cfg),
            "generated": project.generated(listing),
            "vite_plugin": project.uses_vite_plugin(
                self._files.read(self._folder, "vite.config.ts")
                or self._files.read(self._folder, "vite.config.js")
            ),
        }

    def files_tree(self, every: bool = False) -> dict[str, Any]:
        """The files a person edits (domain/shown.py: .ts and .tsx under src/, not generated), or with
        `every` all of them. The others are in the folder all the same; a hidden one is read by its path."""
        if not self._folder:
            raise Conflict("No code app is open.")
        listing = self._files.listing(self._folder)
        files = shown.shown_files(listing)
        return {
            "folder": self._folder,
            "tree": project.tree(listing if every else files),
            "files": listing if every else files,
            "all": every,
            "hidden": len(listing) - len(files),
        }

    # ===== pages: each page a folder of its own (domain/pages.py) =====

    def _service_for(self, folder: str, source: str) -> tuple[str, str] | None:
        """A data source's generated service file and its text (None: none, or no such source)."""
        wanted = pages.names_of(source)["folder"].lower() if source else ""
        for path in self._files.listing(folder):
            if path.startswith(project.GENERATED + "/services/") and path.endswith("Service.ts"):
                if pages.service_of(path).removesuffix("Service").lower() == wanted:
                    return path, self._files.read(folder, path) or ""
        return None

    def pages_state(self) -> dict[str, Any]:
        """The app's pages (each folder under src/pages with its index.ts) and which src/pages.ts lists."""
        folder = self._open_folder()
        listing = self._files.listing(folder)
        found = sorted(
            {
                p.split("/")[2]
                for p in listing
                if p.startswith(pages.PAGES + "/") and p.endswith("/index.ts") and p.count("/") == 3
            }
        )
        listed = pages.registered(self._files.read(folder, pages.REGISTRY))
        return {
            "pages": [{"name": f, "folder": f"{pages.PAGES}/{f}", "listed": f in listed} for f in found],
            "registry": pages.REGISTRY,
        }

    async def new_page(self, body: Any, who: str) -> dict[str, Any]:
        """New page: its folder (page, components, hooks, state, types, index) and its line in src/pages.ts;
        its hook reads a data source's generated service when one is named."""
        body = body if isinstance(body, dict) else {}
        folder = self._open_folder()
        try:
            names = pages.names_of(body.get("name"))
        except pages.PageError as error:
            raise ValueError(str(error)) from None
        page_folder = f"{pages.PAGES}/{names['folder']}"
        if any(p.startswith(page_folder + "/") for p in self._files.listing(folder)):
            raise Conflict(f"{page_folder} is there already: choose another name.")
        source = str(body.get("source") or "")
        service = self._service_for(folder, source) if source else None
        if source and service is None:
            raise NotFound(f"The app has no generated service for {source} (add it as a data source first).")
        made = pages.page_files(names["title"], *(service or (None, "")))
        for path, text in made.items():
            self._files.write(folder, path, text)
        self._files.write(
            folder, pages.REGISTRY, pages.register(self._files.read(folder, pages.REGISTRY), names["title"])
        )
        self._audit.write(who, "powerapps_new_page", None, page=names["title"])
        await self._live.broadcast({"type": "powerapps_project", "open": True})
        return {
            "page": names["title"],
            "files": sorted(made),
            "open": f"{page_folder}/{names['component']}.tsx",
        }

    async def scaffold(self, who: str) -> dict[str, Any]:
        """The starter files on the template: what pages share, the Accounts page (its hook over the generated
        Accounts service when there is one), src/pages.ts and App.tsx: each only where no file is."""
        folder = self._open_folder()
        existing = {p: self._files.read(folder, p) for p in pages.scaffold_paths()}
        service = self._service_for(folder, "Accounts")
        planned = pages.scaffold_plan(existing, *(service or (None, "")))
        for path, text in planned.items():
            self._files.write(folder, path, text)
        if planned:
            self._audit.write(who, "powerapps_scaffold", None, files=len(planned))
            await self._live.broadcast({"type": "powerapps_project", "open": True})
        return {"written": sorted(planned), "kept": sorted(p for p in existing if p not in planned)}

    def lint(self, body: Any) -> dict[str, Any]:
        """The pages rule (a page never imports another page's code) over one file as sent, or every shown
        file of the app."""
        body = body if isinstance(body, dict) else {}
        folder = self._open_folder()
        path, text = body.get("path"), body.get("text")
        if isinstance(path, str) and isinstance(text, str):
            return {"problems": [p | {"path": path} for p in pages.cross_page_imports(path, text)]}
        found = []
        for rel in shown.shown_files(self._files.listing(folder)):
            found += [
                p | {"path": rel} for p in pages.cross_page_imports(rel, self._files.read(folder, rel) or "")
            ]
        return {"problems": found}

    def read_file(self, path: Any) -> dict[str, Any]:
        if not self._folder:
            raise Conflict("No code app is open.")
        relative = str(path or "").replace("\\", "/").lstrip("/")
        try:
            text = self._files.read(self._folder, relative)
        except PermissionError as error:
            raise Refused(str(error)) from None
        if text is None:
            raise NotFound(f"{relative} is not in the code app (or is too large to open).")
        return {
            "path": relative,
            "full_path": self._files.join(self._folder, relative),
            "language": project.language_of(relative),
            "text": text,
            "generated": relative.startswith(project.GENERATED + "/"),
        }

    async def write_file(self, path: Any, text: Any, who: str) -> dict[str, Any]:
        if not self._folder:
            raise Conflict("No code app is open.")
        relative = str(path or "").replace("\\", "/").lstrip("/")
        if not relative or not isinstance(text, str):
            raise ValueError('Send {"path": "src/App.tsx", "text": "..."}.')
        try:
            self._files.write(self._folder, relative, text)
        except PermissionError as error:
            raise Refused(str(error)) from None
        self._audit.write(who, "powerapps_save_file", None, file=relative.rsplit("/", 1)[-1])
        return {"path": relative, "saved": True}

    async def _opened(self, folder: str, who: str) -> dict[str, Any]:
        self._folder = folder
        marker = self._files.read(folder, project.MARKER)
        if project.project_type(marker) != project.PROJECT_TYPE:
            self._files.write(folder, project.MARKER, project.marker(marker))
        self._files.save_state(self._files.state() | {"folder": folder})
        self._told(folder)
        await self._live.broadcast({"type": "powerapps_project", "open": True})
        await self._live.broadcast({"type": "mode_changed"})
        return self.project_state()

    async def open_app(self, folder: Any, who: str) -> dict[str, Any]:
        where = str(folder or "").strip()
        if not where or not self._files.exists(where):
            raise NotFound(f"There is no folder {where}.")
        where = self._files.resolve(where)
        project.config(self._files.read(where, project.CONFIG))  # a code app, or said plainly
        await self.stop_live(who)
        state = await self._opened(where, who)
        self._audit.write(who, "powerapps_open", None, app=state["app"]["name"])
        return state

    async def close_app(self, who: str) -> dict[str, Any]:
        await self.stop_live(who)
        self._told(None)
        self._folder = None
        await self._live.broadcast({"type": "powerapps_project", "open": False})
        await self._live.broadcast({"type": "mode_changed"})
        return {"open": False}

    async def new_app(self, body: Any, who: str) -> dict[str, Any]:
        """New code app: Microsoft's Vite template into <parent>/<name>, `npm install`, then `pa app init`
        with its name and environment, and the project's type recorded."""
        body = body if isinstance(body, dict) else {}
        name = cli_lines.value("The app's name", body.get("name"))
        environment = cli_lines.value("The environment", body.get("environment_id"), guid=True)
        parent = str(body.get("parent") or "").strip()
        if not parent or not self._files.exists(parent):
            raise NotFound("Choose the folder the code app goes in (it must exist).")
        slug = project.folder_name(name)
        folder = self._files.join(self._files.resolve(parent), slug)
        if not self._files.empty_or_missing(folder):
            raise Conflict(f"{folder} is there already and not empty: choose another name or folder.")
        await self._need("init")
        if "init" in self._busy:
            raise Conflict("A code app is being made already.")
        self._busy.add("init")
        try:
            ran = await self._run(
                cli_lines.template(slug), who, TIMEOUTS["install"], cwd=self._files.resolve(parent)
            )
            if ran.code != 0:
                raise self._failed(ran, "Copying Microsoft's code app template")
            ran = await self._run(cli_lines.npm_install(), who, TIMEOUTS["install"], cwd=folder)
            if ran.code != 0:
                raise self._failed(ran, "npm install")
            argv = cli_lines.app_init(name, environment, body.get("description"))
            ran = await self._run(argv, who, TIMEOUTS["sign_in"], cwd=folder)
            if ran.code != 0:
                raise self._failed(ran, "pa app init")
        finally:
            self._busy.discard("init")
        await self.stop_live(who)
        await self._opened(folder, who)
        await self.scaffold(who)
        self._audit.write(who, "powerapps_new", None, app=name)
        return self.project_state()

    # ===== data sources =====

    async def add_source(self, body: Any, who: str) -> dict[str, Any]:
        body = body if isinstance(body, dict) else {}
        folder = self._open_folder()
        await self._need("sources")
        kind = body.get("kind") or (
            "dataverse" if body.get("connector") in (None, "", "dataverse") else "connector"
        )
        if kind == "dataverse":
            argv = cli_lines.add_dataverse_table(body.get("table"), body.get("org_url"))
        else:
            argv = cli_lines.add_connector(
                body.get("connector"),
                body.get("connection_id"),
                body.get("connection_ref"),
                body.get("solution_id"),
                body.get("dataset"),
                body.get("tables") or body.get("table"),
                body.get("as"),
            )
        ran = await self._run(argv, who, TIMEOUTS["install"], cwd=folder)
        if ran.code != 0:
            raise self._failed(ran, "Adding the data source")
        self._audit.write(
            who, "powerapps_add_source", None, source=str(body.get("table") or body.get("connector"))
        )
        await self._live.broadcast({"type": "powerapps_project", "open": True})
        return self.project_state()

    async def remove_source(self, body: Any, who: str) -> dict[str, Any]:
        body = body if isinstance(body, dict) else {}
        folder = self._open_folder()
        await self._need("sources")
        name = str(body.get("name") or "")
        listed = {s["name"]: s for s in project.sources(self._config())}
        source = listed.get(name)
        if source is None:
            raise NotFound(f"The app has no data source {name} (powerapps_project lists them).")
        argv = cli_lines.remove_source(body.get("connector") or source["connector"], name)
        ran = await self._run(argv, who, TIMEOUTS["quick"], cwd=folder)
        if ran.code != 0:
            raise self._failed(ran, "Removing the data source")
        self._audit.write(who, "powerapps_remove_source", None, source=name)
        await self._live.broadcast({"type": "powerapps_project", "open": True})
        return self.project_state()

    def _open_folder(self) -> str:
        if not self._folder:
            raise Conflict("No code app is open: New code app makes one, Open code app opens one.")
        return self._folder

    # ===== connectors =====

    async def connector_list(
        self, search: Any = None, refresh: bool = False, who: str = "user"
    ) -> dict[str, Any]:
        await self._need("connectors")
        if self._connectors is None or refresh:
            ran = await self._run(cli_lines.connector_list(), who, TIMEOUTS["quick"], cwd=self._folder)
            if ran.code != 0:
                raise self._failed(ran, "pa connector list")
            self._connectors = cli_lines.connectors(ran.output)
        in_app = {s["connector"] for s in project.sources(self._config())} if self._folder else set()
        listed = [
            c | {"in_app": c["name"] in in_app}
            for c in connectors.search(self._connectors, str(search or ""))
        ]
        return {"connectors": listed, "total": len(self._connectors)}

    async def connection_list(self, connector: Any = None, who: str = "user") -> dict[str, Any]:
        await self._need("connectors")
        ran = await self._run(cli_lines.connection_list(), who, TIMEOUTS["quick"], cwd=self._folder)
        if ran.code != 0:
            raise self._failed(ran, "pa connection list")
        found = cli_lines.connections(ran.output)
        if connector:
            found = [c for c in found if c["connector"] == str(connector)]
        return {"connections": found}

    def _project_definition(self, name: str) -> tuple[dict[str, Any], str] | None:
        if not self._folder:
            return None
        for path in self._files.listing(self._folder):
            if not path.startswith(project.SCHEMAS + "/") or not path.endswith(".json"):
                continue
            if name.lower().removeprefix("shared_") not in path.lower():
                continue
            text = self._files.read(self._folder, path)
            try:
                found = connectors.find_swagger(json.loads(text or "null"))
            except ValueError:
                continue
            if found and found.get("paths"):
                return found, f"the code app's {path}"
        return None

    async def connector(self, name: Any, who: str = "user") -> dict[str, Any]:
        """One connector in the APIs explorer's model: from the app's downloaded schema, else the
        environment's connectivity service (with the Power Platform CLI's sign-in)."""
        ident = cli_lines.value("The connector", name)
        display = next((c["display_name"] for c in self._connectors or [] if c["name"] == ident), ident)
        found = self._project_definition(ident)
        if found is None:
            environment = self._summary().get("environment_id") or next(
                (e["id"] for e in self._environments or [] if e.get("active")), ""
            )
            if not environment:
                raise Conflict(
                    "Open a code app (or list the environments) first: a connector is read in an environment."
                )
            await self._need("environments")
            ran = await self._run(cli_lines.pac_auth_token(), who, TIMEOUTS["quick"], keep=False)
            token = _token_of(cli_lines.plain(ran.output)) if ran.code == 0 else None
            if not token:
                raise Conflict("The Power Platform CLI is not signed in: pac auth create signs in.")
            try:
                answer = await asyncio.to_thread(self._connector_service, ident, environment, token)
            except Exception as error:
                raise Conflict(str(error)) from None
            finally:
                token = None
            given = answer.get("properties")
            props: dict[str, Any] = given if isinstance(given, dict) else {}
            display = str(props.get("displayName") or display)
            swagger = connectors.find_swagger(answer)
            if swagger is None:
                raise Conflict(f"{display} has no definition the service gives out.")
            found = (swagger, "the environment's connectivity service")
        return connectors.explored(ident, display, found[0], found[1])

    # ===== Run live =====

    def live_port_of(self, key: str) -> int | None:
        """The proxy's lookup: the dev server's port for this run's key (None: refuse)."""
        app = self._live_app
        if app is None or app.handle is None or not app.handle.running:
            return None
        return app.port if secrets.compare_digest(key.encode(), app.key.encode()) else None

    def live_state(self) -> dict[str, Any]:
        app = self._live_app
        if app is None:
            return {"running": False}
        return app.to_json()

    async def start_live(self, who: str) -> dict[str, Any]:
        folder = self._open_folder()
        if self._live_app is not None and self._live_app.handle.running:
            return self.live_state()
        await self._need("run")
        state = self.project_state()
        if not state.get("vite_plugin"):
            raise Conflict(
                "Run live needs the Power Apps Vite plugin in vite.config (Microsoft's current template has "
                "it). Without it, run `pa app run` in a terminal."
            )
        key = secrets.token_urlsafe(18)
        base = f"{self._prefix}{key}/"
        port = self._free_port()
        environment = str(state["app"].get("environment_id") or "")
        local_url = f"http://localhost:{port}{base}"
        app = LiveApp(
            key,
            port,
            base,
            folder,
            None,
            local_url,
            cli_lines.local_play(environment, local_url) if environment else None,
        )
        run = Run(secrets.token_hex(4), "npm run dev", who, time.time())
        self._runs[run.id] = run

        async def line(text: str) -> None:
            shown = cli_lines.plain(text)
            run.lines.append(shown)
            urls = cli_lines.dev_urls(shown)
            if "play" in urls:
                app.play_url = urls["play"]
            if "local" in urls:
                app.ready = True
            await self._live.broadcast({"type": "powerapps_output", "run": run.id, "line": shown})
            if urls:
                await self._live.broadcast({"type": "powerapps_live", **app.to_json()})

        argv = cli_lines.check_argv(cli_lines.dev_server(port, base))
        try:
            app.handle = await self._runner.start(argv, folder, line)
        except FileNotFoundError:
            raise self._missing_for("npm") from None
        self._live_app = app
        self._audit.write(who, "powerapps_run_live", None, app=state["app"].get("name"))
        await self._live.broadcast({"type": "powerapps_run", "run": run.to_json()})
        for _ in range(100):  # up to ten seconds for its first answer
            if app.ready or not app.handle.running:
                break
            await asyncio.sleep(0.1)
        if not app.handle.running:
            self._live_app = None
            run.done, run.code = True, getattr(app.handle.process, "returncode", None)
            raise Conflict("The dev server stopped: " + " ".join(run.lines[-6:]))
        await self._live.broadcast({"type": "powerapps_live", **app.to_json()})
        return self.live_state()

    async def stop_live(self, who: str) -> dict[str, Any]:
        app = self._live_app
        self._live_app = None
        if app is not None and app.handle is not None:
            await self._stop(app.handle.process)
            self._audit.write(who, "powerapps_stop_live", None)
            await self._live.broadcast({"type": "powerapps_live", "running": False})
        return {"running": False}

    # ===== Push =====

    async def push(self, body: Any, who: str) -> dict[str, Any]:
        """`npm run build`, then `pa app push`: a new version in the environment. The agent's waits for
        the user's Allow. `dry_run`: what would run, nothing run."""
        body = body if isinstance(body, dict) else {}
        folder = self._open_folder()
        state = self.project_state()
        app = state["app"]
        steps = [cli_lines.npm_build(), cli_lines.app_push(body.get("solution_id"))]
        plan = {
            "app": app["name"],
            "environment": self._environment_name() or app["environment_id"],
            "commands": [" ".join(s) for s in steps],
        }
        if body.get("dry_run"):
            return {"dry_run": True, **plan}
        await self._need("push")
        await self._approvals.allowed(
            who,
            subject=app["name"],
            action="push",
            detail=f"Push {app['name']} to {plan['environment']}: a new version there.",
            otherwise=f"{app['name']} was not pushed",
        )
        if "push" in self._busy:
            raise Conflict("A push is running already.")
        self._busy.add("push")
        try:
            for argv in steps:
                ran = await self._run(argv, who, TIMEOUTS["push"], cwd=folder)
                if ran.code != 0:
                    raise self._failed(ran, words_of(argv))
        finally:
            self._busy.discard("push")
        link = cli_lines.push_link(ran.output)
        pushed = {"at": time.time(), "link": link, "who": who, "app_id": self._summary().get("app_id")}
        self._pushes.insert(0, pushed)
        self._audit.write(who, "powerapps_push", None, app=app["name"])
        await self._live.broadcast({"type": "powerapps_project", "open": True})
        return {"pushed": True, "link": link, **plan}

    async def versions(self, who: str = "user") -> dict[str, Any]:
        """What the CLI reports: the environment's code apps (pa app list) with this one marked, and this
        session's pushes. The CLI lists no versions of an app; its link opens the app's details."""
        await self._need("push")
        ran = await self._run(cli_lines.app_list(), who, TIMEOUTS["quick"], cwd=self._folder)
        if ran.code != 0:
            raise self._failed(ran, "pa app list")
        mine = self._summary().get("app_id")
        apps = [a | {"this": bool(mine) and a["id"] == mine} for a in cli_lines.code_apps(ran.output)]
        return {"apps": apps, "pushes": self._pushes}

    # ===== custom connectors =====

    async def custom_connector(self, body: Any, who: str) -> dict[str, Any]:
        """From an API in the library: its two files (a dry run shows them, writes and runs nothing), then
        written into the code app's connectors/<api>/ (or a folder the user named) and `pac connector
        create` (or update, with a connector id). The agent's create waits for the user's Allow."""
        body = body if isinstance(body, dict) else {}
        api_name = cli_lines.value("The API", body.get("api"))
        try:
            doc, auth = self._api_documents(api_name)
        except LookupError as error:
            raise NotFound(str(error)) from None
        made = connectors.custom_connector_files(
            doc, auth, str(body.get("publisher") or ""), str(body.get("brand_color") or "#007ee5")
        )
        if body.get("dry_run", True):
            return {"dry_run": True, "api": api_name, **made}
        folder = str(body.get("folder") or "").strip()
        if not folder:
            folder = self._files.join(self._open_folder(), "connectors", project.folder_name(api_name))
        await self._need("custom_connector")
        update = body.get("connector_id")
        environment = body.get("environment") or self._summary().get("environment_id") or None
        await self._approvals.allowed(
            who,
            subject=api_name,
            action="custom connector",
            detail=f"{'Update' if update else 'Make'} the custom connector {made['title']} in "
            f"{self._environment_name() or environment or 'the selected environment'}.",
            otherwise=f"no custom connector was made from {api_name}",
        )
        written = {name: self._files.write(folder, name, text) for name, text in made["files"].items()}
        argv = cli_lines.pac_connector_create(
            written[connectors.DEFINITION_FILE], written[connectors.PROPERTIES_FILE], environment, update
        )
        ran = await self._run(argv, who, TIMEOUTS["quick"], cwd=folder)
        if ran.code != 0:
            raise self._failed(ran, "pac connector " + ("update" if update else "create"))
        self._connectors = None
        self._audit.write(who, "powerapps_custom_connector", None, api=api_name, update=bool(update))
        return {"made": True, "api": api_name, "files": list(written.values()), "output": ran.output[-4000:]}

    # ===== the page's picture =====

    async def state(self) -> dict[str, Any]:
        tools_now = await self.tools_state()
        return {
            "tools": tools_now,
            "account": self._account,
            "environments": self._mark_project(self._environments)
            if self._environments is not None
            else None,
            "project": self.project_state(),
            "live": self.live_state(),
            "runs": [r.to_json() for r in reversed(self._runs.values())][:10],
        }

    async def stop_all(self) -> None:
        await self.stop_live("user")


def _token_of(output: str) -> str | None:
    for line in reversed((output or "").splitlines()):
        word = line.strip()
        if len(word) > 40 and " " not in word:
            return word
    return None
