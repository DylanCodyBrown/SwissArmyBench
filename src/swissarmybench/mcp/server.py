"""The Swiss Army Bench MCP server: `swissarmybench-mcp`. One typed tool per command.

A stdio launcher. Claude Code (or any MCP client) starts it. Every command in the registry
(`swissarmybench.cli.commands`) becomes an MCP tool of the same name, with its real arguments as the
tool's typed schema, so the model sees `steps_add(grid, kind, params, index?)` rather than composing
a generic call. Nothing is written by hand here: add a command to the registry and it is a tool.

Descriptions are kept lean on purpose, since every tool's description and schema sits in the
agent's context: the first sentence of the command's summary, and a short note only on arguments
whose shape cannot be guessed (the JSON ones). The guide carries the detail: a short index the agent
reads first (`swissarmybench://index`, or the `guide` tool with no arguments) and a page per topic
(`swissarmybench://guide/<topic>`, or `guide(topic=...)`), served as resources too.

Like every front end it calls the grid server over HTTP as the agent (`X-Actor: agent`); all the
rules (export approvals, the SQL guard, the audit log) live in that server. It never starts a server
or opens a browser: the user starts the server (the `swissarmybench` command, or VS Code's Open Swiss
Army Bench button).

Cell values are untrusted: they come back only inside an `<untrusted-data>` block.
"""

from __future__ import annotations

import inspect
import json
from typing import Annotated, Any

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.resources import TextResource
from mcp.types import Annotations
from pydantic import Field

from swissarmybench.cli.api import CommandError
from swissarmybench.cli.commands import (
    DATA_NOTE,
    GUIDE_TOPICS,
    OLD_NAMES,
    REGISTRY,
    Command,
    ImageResult,
    execute_result,
    guide_text,
)

INDEX_URI = "swissarmybench://index"
TOPIC_URI = "swissarmybench://guide/{topic}"

server = MCPServer(
    name="swissarmybench",
    title="Swiss Army Bench",
    instructions=f"Read {INDEX_URI} (or call guide) before any other tool. " + DATA_NOTE,
)

# The index first, for the assistant and marked most important; then each topic of the guide.
server.add_resource(
    TextResource(
        uri=INDEX_URI,
        name="index",
        title="Read first: Swiss Army Bench index",
        description="What the app is, how to start, the tools by prefix, the rules, where the detail lives.",
        mime_type="text/markdown",
        annotations=Annotations(audience=["assistant"], priority=1.0),
        text=guide_text(),
    )
)
for _topic, _title in GUIDE_TOPICS.items():
    server.add_resource(
        TextResource(
            uri=TOPIC_URI.format(topic=_topic),
            name=f"guide/{_topic}",
            title=_title,
            mime_type="text/markdown",
            annotations=Annotations(audience=["assistant"], priority=0.5),
            text=guide_text(_topic),
        )
    )


CONTEXT_URI = "swissarmybench://context"


@server.resource(
    CONTEXT_URI,
    name="context",
    title="context.md: Swiss Army Bench's live picture",
    description="Connections and their SQL names, open tables, the ERD, variables, documents, the guide.",
    mime_type="text/markdown",
    annotations=Annotations(audience=["assistant"], priority=0.9),
)
def open_now() -> str:
    """context.md's text, read fresh (app_context): Claude Desktop has no folder to find it in."""
    try:
        answer = json.loads(str(execute_result("app_context", {})))
    except (CommandError, ValueError) as error:
        return f"Swiss Army Bench did not answer: {error}"
    return str(answer.get("text", "")) if isinstance(answer, dict) else str(answer)


class GridServerError(ToolError):
    """A command was refused or failed. A ToolError, so the MCP library passes the plain-language
    reason ("The user declined (or did not answer) this export.") to the agent; any other exception
    type reaches it only as "Error executing tool <name>"."""


_TYPES: dict[str, Any] = {"str": str, "int": int, "bool": bool, "json": Any, "any": Any, "list": list[str]}
DESCRIPTION_LIMIT = 110
ARG_NOTE_LIMIT = 90


def _first_sentence(text: str, limit: int) -> str:
    """The text up to its first full stop followed by a space, cut to `limit` characters."""
    head = text.split(". ")[0].rstrip(".")
    return head if len(head) <= limit else head[: limit - 1].rstrip() + "…"


def tool_description(cmd: Command) -> str:
    return _first_sentence(cmd.summary, DESCRIPTION_LIMIT)


def _signature(cmd: Command) -> inspect.Signature:
    """The command's arguments as a typed Python signature, required ones first. Only JSON
    arguments carry a note: their shape is the one thing a name and a type can't say."""
    params: list[inspect.Parameter] = []
    for arg in sorted(cmd.args, key=lambda a: not a.required):
        base = _TYPES[arg.type]
        kind = base if arg.required else base | None
        if arg.type == "json":
            kind = Annotated[kind, Field(description=_first_sentence(arg.help, ARG_NOTE_LIMIT))]
        params.append(
            inspect.Parameter(
                arg.name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=inspect.Parameter.empty if arg.required else None,
                annotation=kind,
            )
        )
    return inspect.Signature(params, return_annotation=Any if cmd.image else str)


def _make_tool(cmd: Command) -> Any:
    def run(**kwargs: Any) -> Any:
        try:
            result = execute_result(cmd.name, {k: v for k, v in kwargs.items() if v is not None})
        except CommandError as error:
            raise GridServerError(str(error)) from error
        except Exception as error:  # a reply the command did not expect: say what, not just "Error"
            raise GridServerError(f"{cmd.name} failed: {type(error).__name__}: {error}") from error
        if isinstance(result, ImageResult):
            # The model gets the picture itself, plus its size and where it was saved, if it was.
            return [Image(data=result.data, format="png"), json.dumps(result.meta)]
        return result

    signature = _signature(cmd)
    run.__name__ = cmd.name
    run.__qualname__ = cmd.name
    run.__signature__ = signature  # type: ignore[attr-defined]
    run.__annotations__ = {p.name: p.annotation for p in signature.parameters.values()} | {
        "return": Any if cmd.image else str
    }
    return run


def _slim(schema: dict[str, Any]) -> dict[str, Any]:
    """The library's generated schema, without what a model doesn't need: a "title" on every argument
    (it only repeats the name) and the "or null" wrapper on optional ones (optional already means the
    argument is not in `required`). About a quarter of the tool list."""
    slim: dict[str, Any] = {k: v for k, v in schema.items() if k != "title"}
    properties: dict[str, Any] = {}
    for name, prop in schema.get("properties", {}).items():
        prop = {k: v for k, v in prop.items() if k not in ("title", "default")}
        options = prop.get("anyOf")
        if isinstance(options, list):
            real = [o for o in options if o != {"type": "null"}]
            if len(real) == 1 and len(options) == 2:
                prop = {k: v for k, v in prop.items() if k != "anyOf"} | real[0]
            elif not real:
                prop = {k: v for k, v in prop.items() if k != "anyOf"}
        properties[name] = prop
    slim["properties"] = properties
    return slim


for _command in REGISTRY.values():
    server.add_tool(
        _make_tool(_command),
        name=_command.name,
        description=tool_description(_command),
        structured_output=False if _command.image else None,
    )
    # The library keeps each tool's schema as a plain dict; slim it in place. If a future version
    # stores it elsewhere, the tools still work, just with the longer schema.
    _registered = getattr(getattr(server, "_tool_manager", None), "_tools", {}).get(_command.name)
    if _registered is not None and isinstance(getattr(_registered, "parameters", None), dict):
        _registered.parameters = _slim(_registered.parameters)

# The old command names (sandbox_* is visualizations_* now, one release): a call by an old name reaches the
# new tool, which the list does not repeat (if the library keeps its tools elsewhere, old names are refused).
_manager = getattr(server, "_tool_manager", None)
if _manager is not None and callable(getattr(_manager, "get_tool", None)):
    _get_tool = _manager.get_tool

    def _get_tool_by_any_name(name: str) -> Any:
        return _get_tool(OLD_NAMES.get(name, name))

    _manager.get_tool = _get_tool_by_any_name


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
