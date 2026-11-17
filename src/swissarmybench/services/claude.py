"""Launch Claude (domain/claude.py): Claude Code in the user's own terminal, or Claude Desktop, each with
what it needs to understand Swiss Army Bench.

- **Claude Code:** a folder of its own in the state folder (claude/<project>/) with CLAUDE.md (what the app
  is, and context.md imported), context.md (the app's live picture, kept current by services/context_md.py:
  metadata only), .mcp.json and .claude/settings.json (the prompt hook),
  then the user's terminal running `claude` there, the project's working folder added. Bypass permissions
  mode only when the user turned it on in Settings.
- **Claude Desktop:** it takes no folder, so its context comes through its MCP config: the `swissarmybench`
  server is set in that install's claude_desktop_config.json (a backup first, every other entry kept; the
  user is asked once per file), then the app is started. The index, the guide and context.md's text are
  the MCP server's resources.

Only the user's click launches anything, and only the user changes which Claude is launched: the agent
reads what was found and the summary, and is refused the rest (an agent starting another agent).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Protocol

from swissarmybench.domain import claude as rules
from swissarmybench.domain.claude import CODE, DESKTOP, Context, Install, TableFacts
from swissarmybench.services.context_md import ContextMd
from swissarmybench.services.workspace import Refused, Workspace

AGENT_REFUSED = (
    "Launching Claude, and choosing which Claude is launched, is the user's alone: an agent does not start "
    "another agent."
)


class Finder(Protocol):
    platform: str

    def find(self) -> list[Install]: ...

    def terminals(self) -> dict[str, str]: ...


class Starter(Protocol):
    def start(self, argv: list[str], cwd: str | None, new_console: bool) -> None: ...


class Files(Protocol):
    def prepare(self, name: str, files: dict[str, str]) -> str: ...

    def index(self) -> str: ...

    def load(self) -> dict[str, Any]: ...

    def save(self, data: dict[str, Any]) -> None: ...

    def exists(self, path: str) -> bool: ...

    def runnable(self, path: str) -> bool: ...

    def read(self, path: str) -> str | None: ...

    def write_config(self, path: str, text: str) -> str | None: ...


class Claude:
    def __init__(
        self,
        ws: Workspace,
        finder: Finder,
        starter: Starter,
        files: Files,
        *,
        version: str,
        home: str,
        environ: dict[str, str],
        commands: Callable[[str], str],
        project: Callable[[], dict[str, Any] | None],
        connections: Callable[[], list[dict[str, Any]]],
        documents: Callable[[], list[dict[str, Any]]],
        context_md: ContextMd | None = None,
    ) -> None:
        self.ws = ws
        self._finder = finder
        self._starter = starter
        self._files = files
        self._version = version
        self._home = home
        self._environ = environ
        self._commands = commands  # swissarmybench-mcp, swissarmybench-context: their full paths
        self._project = project
        self._connections = connections
        self._documents = documents
        self._found: list[Install] | None = None
        self.context_md = context_md  # context.md: the folder's live picture

    # ===== what was found, and the user's choices =====

    async def _installs(self, refresh: bool = False) -> list[Install]:
        if self._found is None or refresh:
            self._found = await asyncio.to_thread(self._finder.find)
        found = list(self._found)
        # An install the user picked with Other… (one the search missed) is listed too.
        for kind in rules.KINDS:
            path = (self._choices().get("chosen") or {}).get(kind)
            if path and not any(i.path == path for i in found) and self._files.runnable(path):
                found.insert(0, rules.user_install(kind, path, self._finder.platform))
        return found

    def _choices(self) -> dict[str, Any]:
        return self._files.load()

    def _pick(self, installs: list[Install], kind: str) -> Install | None:
        return rules.chosen(installs, kind, (self._choices().get("chosen") or {}).get(kind))

    def _config_of(self, install: Install) -> dict[str, Any]:
        """Where this Desktop install keeps its config: the user's own pick, else the first place that
        exists, else the official app's own place; unknown for an unofficial build with none there."""
        own = (self._choices().get("configs") or {}).get(install.path)
        places = rules.config_places(install, self._finder.platform, self._home, self._environ)
        if own:
            return {"path": own, "known": True, "places": places}
        for place in places:
            if self._files.exists(place):
                return {"path": place, "known": True, "places": places}
        if install.official:
            return {"path": install.config or places[-1], "known": True, "places": places}
        return {"path": places[0], "known": False, "places": places}

    async def state(self, refresh: bool = False) -> dict[str, Any]:
        """What was found (Claude Code, Claude Desktop), which is chosen, bypass permissions mode, and where
        the chosen Desktop keeps its config."""
        installs = await self._installs(refresh)
        choices = self._choices()
        out: dict[str, Any] = {"platform": self._finder.platform, "bypass": choices.get("bypass") is True}
        for kind in rules.KINDS:
            pick = self._pick(installs, kind)
            out[kind] = {
                "found": [i.to_json() for i in installs if i.kind == kind],
                "chosen": pick.path if pick else None,
                "help": None if pick else rules.install_help(kind, self._finder.platform),
            }
        desktop = self._pick(installs, DESKTOP)
        if desktop is not None:
            config = self._config_of(desktop)
            allowed = choices.get("allowed") or []
            out[DESKTOP]["config"] = config | {"allowed": config["path"] in allowed}
        return out

    async def choose(self, body: Any, who: str) -> dict[str, Any]:
        """Settings, Claude: {"code"?: path, "desktop"?: path, "bypass"?: bool, "config"?: {"desktop path":
        "config path"}}. The user's only."""
        if who == "agent":
            raise Refused(AGENT_REFUSED)
        if not isinstance(body, dict):
            raise ValueError("Send an object: code, desktop, bypass or config.")
        choices = self._choices()
        chosen = dict(choices.get("chosen") or {})
        for kind in rules.KINDS:
            if kind not in body:
                continue
            path = body[kind]
            if path is None:
                chosen.pop(kind, None)
                continue
            known = any(i.path == path and i.kind == kind for i in self._found or [])
            if not isinstance(path, str) or not (known or self._files.runnable(path)):
                raise ValueError(f"{path!r} is not a file that can be started.")
            chosen[kind] = path
        if "bypass" in body:
            if not isinstance(body["bypass"], bool):
                raise ValueError("bypass is true or false.")
            choices["bypass"] = body["bypass"]
        if "config" in body:
            configs = dict(choices.get("configs") or {})
            raw = body["config"]
            if not isinstance(raw, dict) or not all(isinstance(v, str) and v for v in raw.values()):
                raise ValueError('config is {"<Claude Desktop path>": "<its claude_desktop_config.json>"}.')
            configs |= raw
            choices["configs"] = configs
        choices["chosen"] = chosen
        self._files.save(choices)
        self.ws.audit.write(who, "claude_settings", f"bypass {'on' if choices.get('bypass') else 'off'}")
        return await self.state()

    # ===== the summary of what is open =====

    def context(self) -> Context:
        ws = self.ws
        tables = []
        for info in sorted(ws.store.all(), key=lambda i: i.name):
            grids = ws.grids.for_dataset(info.name)
            tables.append(
                TableFacts(
                    info.name,
                    info.row_count,
                    [(c.name, c.type) for c in info.columns],
                    list(grids[0].steps) if grids else [],
                )
            )
        project = self._project() or {}
        connections = [
            (str(c.get("name")), str(c.get("type") or c.get("connection") or "")) for c in self._connections()
        ]
        documents = [(str(d.get("kind")), str(d.get("path"))) for d in self._documents()]
        return Context(
            self._version,
            project.get("name"),
            project.get("path"),
            project.get("folder"),
            tables,
            connections,
            documents,
        )

    async def summary(self, who: str = "user") -> dict[str, Any]:
        """context.md's text and path (the MCP resource swissarmybench://context, app_context)."""
        if self.context_md is None:
            return {"text": rules.context_markdown(self.context()), "path": None}
        return await self.context_md.read(who)

    # ===== launching =====

    async def launch(self, body: Any, who: str) -> dict[str, Any]:
        """The user's click: {"app"?: "code" | "desktop", "confirmed"?: true}. With no app, the one found."""
        if who == "agent":
            raise Refused(AGENT_REFUSED)
        body = body if isinstance(body, dict) else {}
        installs = await self._installs()
        platform = self._finder.platform
        app = body.get("app")
        if app is None:
            kinds = [k for k in rules.KINDS if self._pick(installs, k)]
            if len(kinds) > 1:
                return {"launched": None, "choose": kinds}
            app = kinds[0] if kinds else None
        if app is None:
            return {"launched": None, "missing": [rules.install_help(k, platform) for k in rules.KINDS]}
        if app not in rules.KINDS:
            raise ValueError("app is code or desktop.")
        install = self._pick(installs, app)
        if install is None:
            return {"launched": None, "missing": [rules.install_help(app, platform)]}
        if app == CODE:
            return await self._launch_code(install, who)
        return await self._launch_desktop(install, body.get("confirmed") is True, who)

    async def _launch_code(self, install: Install, who: str) -> dict[str, Any]:
        context = self.context()
        files = {
            "CLAUDE.md": rules.claude_md(self._version),
            ".mcp.json": rules.mcp_json(self._commands("swissarmybench-mcp")),
            ".claude/settings.json": rules.settings_json(self._commands("swissarmybench-context")),
        }
        folder = await asyncio.to_thread(self._files.prepare, rules.folder_name(context.project), files)
        if self.context_md is not None:
            await self.context_md.launched()  # context.md beside it, taken as read
        bypass = self._choices().get("bypass") is True
        argv = rules.claude_argv(install.path, [context.folder] if context.folder else [], bypass)
        plan = rules.terminal(self._finder.platform, self._finder.terminals(), folder, argv)
        if plan is None:
            return {"launched": None, "error": rules.NO_TERMINAL, "folder": folder, "argv": argv}
        try:
            await asyncio.to_thread(self._starter.start, plan.argv, plan.cwd, plan.new_console)
        except OSError as error:
            return {
                "launched": None,
                "error": f"{plan.name} did not start: {error.strerror or error}",
                "folder": folder,
            }
        self.ws.audit.write(
            who, "claude_launch", f"Claude Code in {plan.name}{' (bypass permissions)' if bypass else ''}"
        )
        return {"launched": CODE, "folder": folder, "terminal": plan.name, "bypass": bypass}

    async def _launch_desktop(self, install: Install, confirmed: bool, who: str) -> dict[str, Any]:
        config = self._config_of(install)
        if not config["known"] and not confirmed:
            # An unofficial build with no config file where one would be: the user names it (or agrees).
            return {"launched": None, "config_unknown": config}
        choices = self._choices()
        allowed = list(choices.get("allowed") or [])
        if config["path"] not in allowed and not confirmed:
            return {"launched": None, "confirm": config}
        text, changed = rules.merge_config(
            await asyncio.to_thread(self._files.read, config["path"]),
            rules.mcp_entry(self._commands("swissarmybench-mcp")),
        )
        backup = await asyncio.to_thread(self._files.write_config, config["path"], text) if changed else None
        if config["path"] not in allowed:
            choices["allowed"] = [*allowed, config["path"]]
            self._files.save(choices)
        try:
            await asyncio.to_thread(
                self._starter.start, rules.desktop_argv(install, self._finder.platform), None, False
            )
        except OSError as error:
            return {"launched": None, "error": f"{install.name} did not start: {error.strerror or error}"}
        self.ws.audit.write(who, "claude_launch", "Claude Desktop")
        return {"launched": DESKTOP, "config": config["path"], "changed": changed, "backup": backup}
