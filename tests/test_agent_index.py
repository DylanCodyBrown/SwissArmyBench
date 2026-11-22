"""The agent's index: the short page an agent reads first, and the guide's topics behind it.

The index is checked against the registry, not against a list written here: a branch that adds a
command with a new prefix fails here until the index's table names that prefix, and a renamed command
cannot linger in the index or a topic. The resources are read over the MCP protocol itself, with the
library's in-process client.
"""

from __future__ import annotations

import asyncio
import json
import re
from importlib.resources import files
from typing import Any

from mcp import Client

from swissarmybench.cli.commands import (
    AREAS,
    GUIDE_TOPICS,
    HELP_COMMANDS,
    REGISTRY,
    area_of,
    execute,
    guide_text,
)
from swissarmybench.mcp import server as mcp_server

INDEX_LIMIT = 4_000
GUIDE = files("swissarmybench.mcp")


# Words shaped like a command that are an argument's name: Power Apps' environment_id (the Environment's one
# tool, `environment`, made its word a prefix, 2026-11-22).
ARGUMENTS = {"environment_id"}


def index() -> str:
    return GUIDE.joinpath("index.md").read_text(encoding="utf-8")


def named_commands(text: str) -> set[str]:
    """Every word in the text that is shaped like a command: an area's prefix and more, or a help command."""
    prefixes = "|".join(re.escape(area) for area, _ in AREAS if area != "help")
    named = set(re.findall(rf"\b((?:{prefixes})_[a-z_]+)\b", text))
    named |= {word for word in HELP_COMMANDS if re.search(rf"`{word}[`(]", text)}
    return {name for name in named if not name.endswith("_")} - ARGUMENTS


def test_the_index_is_short() -> None:
    assert len(index()) < INDEX_LIMIT, f"the index is {len(index())} characters; keep it under {INDEX_LIMIT}"


def test_the_index_names_every_tool_prefix_in_the_registry() -> None:
    prefixes = sorted({area_of(name) for name in REGISTRY} - {"help"})
    missing = [prefix for prefix in prefixes if f"`{prefix}_`" not in index()]
    assert missing == [], (
        f"tool prefixes {missing} are in the registry but not in the index: add a row for each to the "
        "table in src/swissarmybench/mcp/index.md (the prefix, its area, two or three key tools)"
    )
    for word in HELP_COMMANDS:
        assert f"`{word}`" in index()


def test_the_index_and_the_topics_name_only_commands_that_exist() -> None:
    pages = {"index.md": index()} | {f"guide/{topic}.md": guide_text(topic) for topic in GUIDE_TOPICS}
    for page, text in pages.items():
        unknown = sorted(named_commands(text) - set(REGISTRY))
        assert unknown == [], f"{page} names commands that do not exist: {unknown}"
    first = {"agent_context", "tabs_list", "datasets_list", "row_read", "steps_run_sql"}
    assert first <= named_commands(index())


def test_every_topic_resolves_and_the_index_lists_them_all() -> None:
    on_disk = {
        path.name.removesuffix(".md")
        for path in GUIDE.joinpath("guide").iterdir()
        if path.name.endswith(".md")
    }
    assert on_disk == set(GUIDE_TOPICS), "every guide/<topic>.md is in GUIDE_TOPICS, and the other way round"
    for topic in GUIDE_TOPICS:
        text = guide_text(topic)
        assert text.startswith("# ") and not text.startswith("No guide topic")
        assert guide_text(f" {topic.upper()} ") == text  # a topic is read loosely
        assert topic in index().split("## More", 1)[1], f"the index's More section does not list {topic}"


def test_guide_returns_the_index_a_topic_or_the_topics() -> None:
    assert execute("guide") == index()
    assert execute("guide", {"topic": "privacy"}) == guide_text("privacy")
    unknown = execute("guide", {"topic": "nope"})
    assert "No guide topic 'nope'" in unknown
    assert all(f"- {topic}:" in unknown for topic in GUIDE_TOPICS)


def test_the_resources_list_and_read_over_mcp() -> None:
    async def talk() -> tuple[str | None, list[Any], dict[str, str]]:
        async with Client(mcp_server.server) as client:
            listed = (await client.list_resources()).resources
            texts: dict[str, str] = {}
            for resource in listed:
                [content] = (await client.read_resource(str(resource.uri))).contents
                contracts = str(resource.uri) == mcp_server.CONTRACTS_URI
                assert content.mime_type == ("application/json" if contracts else "text/markdown")
                texts[str(resource.uri)] = getattr(content, "text", "")
            return client.instructions, listed, texts

    instructions, listed, texts = asyncio.run(talk())
    by_uri = {str(resource.uri): resource for resource in listed}
    first = by_uri[mcp_server.INDEX_URI]
    assert first.title == "Read first: Swiss Army Bench index" and first.mime_type == "text/markdown"
    assert texts[mcp_server.INDEX_URI] == index()
    for topic in GUIDE_TOPICS:
        uri = f"swissarmybench://guide/{topic}"
        assert texts[uri] == guide_text(topic) and by_uri[uri].title == GUIDE_TOPICS[topic]
    guide = {f"swissarmybench://guide/{t}" for t in GUIDE_TOPICS}
    assert set(by_uri) == {mcp_server.INDEX_URI, mcp_server.CONTEXT_URI, mcp_server.CONTRACTS_URI} | guide
    # Each analysis's data contract (the owner, 2026-11-19: "then present that to the agent"): with no app
    # running, the built-in ones, each with its made-up sample.
    contracts = json.loads(texts[mcp_server.CONTRACTS_URI])
    assert contracts["format"] == 1 and len(contracts["contracts"]) >= 14
    assert all(c["slots"] is not None and c["sample"]["rows"] for c in contracts["contracts"])
    assert mcp_server.CONTRACTS_URI in index() and "analyze_contracts" in guide_text("analyze")
    # What is open now (Launch Claude's summary, for Claude Desktop): read fresh, said plainly with no app.
    assert texts[mcp_server.CONTEXT_URI]
    # The instructions send the agent to the index first, and keep the data note.
    assert instructions is not None and "swissarmybench://index" in instructions and "guide" in instructions
    assert "<untrusted-data>" in instructions


def test_the_guide_tool_stays_lean() -> None:
    [tool] = [t for t in asyncio.run(mcp_server.server.list_tools()) if t.name == "guide"]
    assert len(tool.description or "") <= mcp_server.DESCRIPTION_LIMIT
    assert set(tool.input_schema["properties"]) == {"topic"} and not tool.input_schema.get("required")
    assert len(json.dumps(tool.input_schema)) < 120
