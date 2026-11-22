"""One way the agent asks for the user's Allow (the craft review's item 4, 2026-11-22): the port
`services/ports.py Approvals.allowed`, the user's request at once, the agent's waiting for the user's answer,
and one refusal sentence. The walk below fails on a hand-written `approvals.ask(` anywhere in the base or the
extensions, on a second declaration of the port, and on a call that does not say what stays as it is."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.domain.refusals import declined
from swissarmybench.services import agent as agent_module
from swissarmybench.services.agent import Approvals, NoOneToAsk
from swissarmybench.services.workspace import Refused

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [ROOT / "src" / "swissarmybench", *sorted((ROOT / "extensions").glob("*/src"))]
# The one place `ask` is called: the port's real implementation.
THE_PORT = ROOT / "src" / "swissarmybench" / "services" / "agent.py"
DECLARED = ROOT / "src" / "swissarmybench" / "services" / "ports.py"


def _files() -> list[Path]:
    return [p for root in SOURCES for p in sorted(root.rglob("*.py"))]


def _name_of(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _is_approvals(node: ast.expr) -> bool:
    return _name_of(node).lower().endswith("approvals")


def test_no_hand_written_ask_outside_the_port() -> None:
    found = []
    for path in _files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # approvals.ask(...) called, or approvals.ask handed on as a callable
            if isinstance(node, ast.Attribute) and node.attr == "ask" and _is_approvals(node.value):
                found.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert found == [], (
        "call approvals.allowed(who, subject=, action=, detail=, otherwise=) instead: " + ", ".join(found)
    )


def test_the_port_is_declared_once() -> None:
    declared = []
    for path in _files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef) and node.name in ("Approvals", "Asker"):
                bases = {_name_of(b) for b in node.bases}
                if "Protocol" in bases:
                    declared.append(f"{path.relative_to(ROOT)}:{node.name}")
    assert declared == ["src/swissarmybench/services/ports.py:Approvals"]


def test_every_approvals_argument_is_typed_by_the_port() -> None:
    loose = []
    for path in _files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                for arg in [*node.args.args, *node.args.kwonlyargs]:
                    if arg.arg == "approvals" and (
                        arg.annotation is None or "Approvals" not in ast.unparse(arg.annotation)
                    ):
                        loose.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.name}")
    assert loose == []


def _allowed_calls() -> list[tuple[str, ast.Call]]:
    calls = []
    for path in _files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "allowed"
                and _is_approvals(node.func.value)
            ):
                calls.append((f"{path.relative_to(ROOT)}:{node.lineno}", node))
    return calls


def test_every_allow_says_what_it_asks_and_what_stays() -> None:
    calls = _allowed_calls()
    # 31 in the base's services (one through each of three services' own _allow), 13 in the extensions.
    assert len(calls) >= 40
    bad = []
    for where, call in calls:
        given = {k.arg for k in call.keywords}
        if len(call.args) != 1 or not {"subject", "action", "detail", "otherwise"} <= given:
            bad.append(f"{where}: who, then subject=, action=, detail=, otherwise=")
            continue
        otherwise = next(k.value for k in call.keywords if k.arg == "otherwise")
        if isinstance(otherwise, ast.Constant | ast.JoinedStr):
            text = ast.unparse(otherwise)
            # The sentence's start is the port's: only what stays as it is is the site's.
            if "declined" in text or "did not answer" in text or text.rstrip("'\"").endswith("."):
                bad.append(f"{where}: otherwise names what stays as it is, no 'declined', no full stop")
    assert bad == []


def test_the_one_sentence() -> None:
    assert declined("nothing was exported") == "The user declined (or did not answer): nothing was exported."
    assert declined(" the sandbox stays. ") == "The user declined (or did not answer): the sandbox stays."


class Live:
    def __init__(self, answer: bool | None) -> None:
        self.answer = answer
        self.told: list[dict[str, Any]] = []
        self.approvals: Approvals | None = None

    async def broadcast(self, message: dict[str, Any]) -> None:
        self.told.append(message)
        if message["type"] == "approval_requested" and self.answer is not None:
            assert self.approvals is not None
            waiting = self.approvals.get(message["id"])
            assert waiting is not None
            asyncio.get_running_loop().call_soon(waiting.future.set_result, self.answer)


def _approvals(answer: bool | None) -> tuple[Approvals, Live]:
    live = Live(answer)
    approvals = Approvals(live)  # type: ignore[arg-type]
    live.approvals = approvals
    return approvals, live


ASK: dict[str, Any] = {
    "subject": "Shop",
    "action": "write_connection",
    "detail": "Write 2 rows to orders",
    "otherwise": "nothing",
}


def test_the_users_request_goes_ahead_without_a_question() -> None:
    approvals, live = _approvals(False)
    asyncio.run(approvals.allowed("user", **ASK))
    asyncio.run(approvals.allowed("app", **ASK))
    assert live.told == []


def test_the_agents_request_waits_for_the_users_allow() -> None:
    approvals, live = _approvals(True)
    asyncio.run(approvals.allowed("agent", **ASK))
    asked = live.told[0]
    assert asked["type"] == "approval_requested"
    assert (asked["dataset"], asked["action"], asked["detail"]) == (
        "Shop",
        "write_connection",
        "Write 2 rows to orders",
    )
    assert live.told[-1]["type"] == "approval_resolved" and approvals.pending() == []


def test_declined_or_unanswered_is_one_refusal() -> None:
    approvals, _ = _approvals(False)
    with pytest.raises(Refused) as no:
        asyncio.run(approvals.allowed("agent", **ASK | {"otherwise": "nothing was written to orders"}))
    assert str(no.value) == "The user declined (or did not answer): nothing was written to orders."


def test_unanswered_is_the_same_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent_module, "APPROVAL_TIMEOUT_SECONDS", 0.01)
    approvals, live = _approvals(None)
    with pytest.raises(Refused, match=r"^The user declined \(or did not answer\): the sandbox stays\.$"):
        asyncio.run(approvals.allowed("agent", **ASK | {"otherwise": "the sandbox stays"}))
    assert approvals.pending() == [] and live.told[-1]["type"] == "approval_resolved"


def test_even_the_user_is_asked_when_the_allow_is_remembered() -> None:
    approvals, live = _approvals(True)
    asyncio.run(approvals.allowed("user", **ASK, even_the_user=True))
    assert live.told[0]["type"] == "approval_requested"


def test_no_one_to_ask_declines_the_agent_only() -> None:
    nobody = NoOneToAsk()
    asyncio.run(nobody.allowed("user", **ASK))
    with pytest.raises(Refused, match="declined"):
        asyncio.run(nobody.allowed("agent", **ASK))
