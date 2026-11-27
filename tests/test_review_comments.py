"""Review comments (the owner, 2026-11-27): the one message the agent reads, and its send through the inbox.

Made-up code and a made-up secret only.
"""

from __future__ import annotations

from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.client.context_hook import sent
from swissarmybench.domain import review_comments as rules
from swissarmybench.domain.review_comments import Comment
from tests.conftest import AGENT, AUTH

SECRET = "hunter2-made-up-password"


def test_the_message_names_the_file_then_each_comment_in_line_order() -> None:
    made = rules.message(
        "scripts/load.py",
        [
            Comment(20, 20, "    return rows", "Return a DataFrame instead."),
            Comment(12, 15, "for row in rows:\n    total += row", "Use sum() here."),
        ],
    )
    assert made.title == "Review comments on scripts/load.py (2)"
    assert made.count == 2 and made.masked == 0
    assert made.text.startswith("Review comments on scripts/load.py: 2 comments. ")
    first, second = made.text.index("1. lines 12-15"), made.text.index("2. line 20")
    assert first < made.text.index("Comment: Use sum() here.") < second
    assert "```\nfor row in rows:\n    total += row\n```" in made.text
    assert made.text.index("    return rows") < made.text.index("Comment: Return a DataFrame instead.")


def test_a_notebooks_cells_stay_in_the_order_given_and_lines_within_a_cell() -> None:
    listed = [
        Comment(9, 9, "c", "third", "cell 4"),
        Comment(2, 2, "a", "first", "cell 4"),
        Comment(1, 1, "b", "fourth", "cell 2"),
    ]
    assert [c.comment for c in rules.ordered(listed)] == ["first", "third", "fourth"]
    assert "1. cell 4, line 2" in rules.message("sums.ipynb", listed).text


def test_one_comment_is_singular_and_an_agents_note_is_marked() -> None:
    assert ": 1 comment. " in rules.message("a.py", [Comment(1, 1, "x = 1", "Why one?")]).text
    made = rules.message(
        "a.py", [Comment(1, 1, "x = 1", "Why?"), Comment(3, 3, "y = 2", "Look here.", by_agent=True)]
    )
    assert "2 comments (1 from the user, 1 your own notes)" in made.text
    assert "Your own note: Look here." in made.text


def test_a_known_secret_is_masked_in_the_code_and_in_the_comment() -> None:
    made = rules.message(
        "connect.py",
        [Comment(3, 3, f'password = "{SECRET}"', f"Should {SECRET} be a variable?")],
        [SECRET, "dev"],  # a value under four characters masks nothing: it would hide ordinary code
    )
    assert SECRET not in made.text and made.masked == 2
    assert f'password = "{rules.MASK}"' in made.text
    assert "2 secret values were masked" in made.text
    assert rules.mask("dev = 1", ["dev"]) == ("dev = 1", 0)


def test_code_past_its_share_is_cut_and_the_cap_is_stated() -> None:
    made = rules.message("big.py", [Comment(1, 400, "x" * 5_000, "Too long?")])
    assert f"… (cut: {5_000 - rules.MAX_CODE:,} more characters)" in made.text
    assert rules.CAP_WORDS in made.text and len(made.text) <= rules.MAX_MESSAGE
    many = [Comment(n, n, "y" * 3_000, "Shorter?") for n in range(1, rules.MAX_COMMENTS + 1)]
    packed = rules.message("big.py", many)
    assert len(packed.text) <= rules.MAX_MESSAGE and packed.count == rules.MAX_COMMENTS
    assert "50. line 50" in packed.text


def test_what_cannot_be_sent_says_why() -> None:
    with pytest.raises(rules.ReviewError, match="no comments"):
        rules.read({"path": "a.py", "comments": []})
    with pytest.raises(rules.ReviewError, match="path is the document"):
        rules.read({"path": " ", "comments": [{"line": 1, "comment": "x"}]})
    with pytest.raises(rules.ReviewError, match="more than one send holds"):
        rules.read({"path": "a.py", "comments": [{"line": 1, "comment": "x"}] * (rules.MAX_COMMENTS + 1)})
    with pytest.raises(rules.ReviewError, match="Comment 1 says nothing"):
        rules.read({"path": "a.py", "comments": [{"line": 1, "comment": "  "}]})
    with pytest.raises(rules.ReviewError, match="end is its last line"):
        rules.read({"path": "a.py", "comments": [{"line": 4, "end": 2, "comment": "x"}]})
    long = [Comment(n, n, "", "w" * rules.MAX_COMMENT) for n in range(1, 21)]
    with pytest.raises(rules.ReviewError, match="send them in two goes"):
        rules.message("a.py", long)
    path, read = rules.read({"path": "a.py", "comments": [{"line": 2, "comment": " x ", "by": "agent"}]})
    assert path == "a.py" and read == [Comment(2, 2, "", "x", "", True)]


def test_a_fence_in_the_code_cannot_close_its_block() -> None:
    made = rules.message("notes.md", [Comment(1, 3, "```python\nx = 1\n```", "Keep?")])
    assert "````\n```python\nx = 1\n```\n````" in made.text


def body() -> dict[str, Any]:
    return {
        "path": "scripts/load.py",
        "comments": [
            {"line": 12, "end": 15, "code": "for row in rows:\n    total += row", "comment": "Use sum()."},
            {"line": 3, "end": 3, "code": "import os", "comment": "Is this used?"},
        ],
    }


def test_the_send_is_one_inbox_item_the_agent_reads_once(client: TestClient) -> None:
    answer = client.post("/agent/inbox/review", json=body(), headers=AUTH)
    assert answer.status_code == 200
    assert answer.json() == {"id": 1, "waiting": 1, "comments": 2, "masked": 0}
    taken = client.get("/agent/inbox?take=1", headers=AGENT).json()
    assert len(taken["items"]) == 1
    item = taken["items"][0]
    assert item["kind"] == "review" and item["title"] == "Review comments on scripts/load.py (2)"
    assert item["text"].index("1. line 3") < item["text"].index("2. lines 12-15")
    assert "Comment: Use sum()." in item["text"] and "import os" in item["text"]
    assert "Review comments on scripts/load.py (2)" in sent(taken)  # the prompt hook's text
    assert client.get("/agent/inbox?take=1", headers=AGENT).json() == {"items": [], "waiting": 0}


def test_only_the_user_sends_and_a_bad_send_keeps_nothing(client: TestClient) -> None:
    refused = client.post("/agent/inbox/review", json=body(), headers=AGENT)
    assert refused.status_code == 403 and "Only the user sends review comments" in refused.json()["error"]
    empty = client.post("/agent/inbox/review", json={"path": "a.py", "comments": []}, headers=AUTH)
    assert empty.status_code == 400 and "no comments" in empty.json()["error"]
    assert client.get("/agent/inbox?all=1", headers=AGENT).json() == {"items": [], "waiting": 0}


def test_the_inbox_masks_what_its_secrets_say() -> None:
    import asyncio

    from swissarmybench.services.inbox import Inbox

    class Quiet:
        def write(self, *a: Any, **k: Any) -> None: ...

        async def broadcast(self, notice: Any) -> None: ...

    class Ws:
        audit = Quiet()
        live = Quiet()

    inbox = Inbox(Ws(), lambda: [SECRET])  # type: ignore[arg-type]
    sent_now = asyncio.run(
        inbox.review(
            {"path": "c.py", "comments": [{"line": 1, "code": f'p = "{SECRET}"', "comment": "ok?"}]}, "user"
        )
    )
    assert sent_now["masked"] == 1
    assert SECRET not in inbox.read(False)["items"][0]["text"]
