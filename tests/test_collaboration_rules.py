"""The Collaboration panel's rules (domain/collaboration.py): the files' format round trip and byte stability,
reactions and resolves folded from their own small files, two authors never writing the same file, references
found and their addresses, people mentioned, the activity's 90 days, and who may edit or delete.
Made-up people only."""

from __future__ import annotations

import pytest

from swissarmybench.domain import collaboration as rules

AVERY = rules.person("Avery Lin")
SAM = rules.person("Sam Ortiz", "sam-ortiz")


def _message(**over: object) -> rules.Message:
    made = rules.Message(
        id="1a2b3c4d",
        thread="t-0001",
        author=AVERY,
        time="2026-11-25T10:15:00Z",
        body="Sam, look at [@data.ipynb cell 7](sab:cell/data.ipynb#7) please @sam-ortiz",
        mentions=["sam-ortiz"],
        references=[rules.Reference("cell", "data.ipynb", "7", "data.ipynb cell 7")],
        reactions={"👍": ["sam-ortiz"]},
    )
    for key, value in over.items():
        setattr(made, key, value)
    return made


def test_a_message_file_round_trips_and_is_byte_stable() -> None:
    text = rules.message_text(_message())
    assert text.startswith('+++\nid = "1a2b3c4d"\n')
    back = rules.parse_message(text)
    assert back.body == _message().body
    assert back.references == _message().references
    assert back.reactions == {"👍": ["sam-ortiz"]}
    assert back.author == AVERY
    assert rules.message_text(back) == text  # the same bytes for the same message
    assert '"👍" = ["sam-ortiz"]' in text


def test_a_message_name_sorts_by_time_and_names_its_author() -> None:
    assert _message().file == "20261125T101500Z-avery-lin-1a2b3c4d.md"


def test_text_that_looks_like_toml_stays_text() -> None:
    body = '+++\nid = "evil"\n+++\n"quoted" \\ back'
    back = rules.parse_message(rules.message_text(_message(body=body)))
    assert back.body == body and back.id == "1a2b3c4d"


def test_a_thread_and_an_event_round_trip() -> None:
    thread = rules.Thread(
        "t-0001",
        "Returns",
        AVERY,
        "2026-11-25T10:00:00Z",
        anchor=rules.Reference("table", "orders", "", "orders"),
    )
    text = rules.thread_text(thread)
    assert rules.parse_thread(text) == thread
    assert rules.thread_text(rules.parse_thread(text)) == text
    event = rules.Event("e1", "t-0001", SAM, "2026-11-25T10:20:00Z", "react", "1a2b3c4d", "🎉")
    assert rules.parse_event(rules.event_text(event)) == event
    assert event.file == "20261125T102000Z-sam-ortiz-e1.toml"


def test_two_people_reacting_at_once_write_two_files() -> None:
    a = rules.Event("e1", "t-0001", AVERY, "2026-11-25T10:20:00Z", "react", "1a2b3c4d", "👍")
    b = rules.Event("e2", "t-0001", SAM, "2026-11-25T10:20:00Z", "react", "1a2b3c4d", "👍")
    assert a.file != b.file
    one = _message(author=AVERY, id="aaaa1111", reactions={})
    two = _message(author=SAM, id="aaaa1111", reactions={})
    assert one.file != two.file  # the same moment and id: still each author's own file


def test_folding_reactions_resolves_and_pins() -> None:
    thread = rules.Thread("t-0001", "Returns", AVERY, "2026-11-25T10:00:00Z", channel="general")
    first = _message(reactions={})
    reply = _message(id="2b3c4d5e", time="2026-11-25T10:30:00Z", author=SAM, kind="reply", body="Done.")
    events = [
        rules.Event("e1", "t-0001", SAM, "2026-11-25T10:20:00Z", "react", "1a2b3c4d", "👍"),
        rules.Event("e2", "t-0001", AVERY, "2026-11-25T10:21:00Z", "react", "1a2b3c4d", "👍"),
        rules.Event("e3", "t-0001", SAM, "2026-11-25T10:22:00Z", "unreact", "1a2b3c4d", "👍"),
        rules.Event("e4", "t-0001", AVERY, "2026-11-25T10:40:00Z", "resolve"),
        rules.Event("e5", "t-0001", SAM, "2026-11-25T10:41:00Z", "pin"),
    ]
    now, messages = rules.fold(thread, [reply, first], events)
    assert [m.id for m in messages] == ["1a2b3c4d", "2b3c4d5e"]
    assert messages[0].reactions == {"👍": ["avery-lin"]}
    assert now.resolved == {"by": "avery-lin", "time": "2026-11-25T10:40:00Z"} and now.pinned
    assert thread.resolved is None  # the file's thread is left as written
    reopened, _ = rules.fold(
        thread, [first], [*events, rules.Event("e6", "t-0001", SAM, "2026-11-25T11:00:00Z", "reopen")]
    )
    assert reopened.resolved is None


def test_references_and_mentions_in_a_body() -> None:
    body = (
        "See [@orders.customer_id](sab:column/orders#customer_id) and "
        "[@scripts/load data.py](sab:script/scripts/load%20data.py), @sam-ortiz and @nobody; "
        "`@sam-ortiz` in code"
    )
    found = rules.references_in(body)
    assert [r.key for r in found] == ["column:orders#customer_id", "script:scripts/load data.py"]
    assert rules.mentions_in(body, ["sam-ortiz", "avery-lin"]) == ["sam-ortiz"]
    made = rules.Reference("script", "scripts/load data.py", "", "load data.py")
    assert rules.references_in(made.link()) == [made]


def test_a_reference_names_a_kind_and_never_climbs_out() -> None:
    with pytest.raises(rules.CollaborationError):
        rules.reference({"kind": "password", "path": "x"})
    with pytest.raises(rules.CollaborationError):
        rules.reference({"kind": "script", "path": "../secrets.py"})


def test_where_a_reference_opens() -> None:
    folder = "/home/avery/Projects/Returns"
    assert rules.href(rules.Reference("cell", "data.ipynb", "7"), folder) == (
        "notebooks?path=%2Fhome%2Favery%2FProjects%2FReturns%2Fdata.ipynb&cell=7"
    )
    assert str(rules.href(rules.Reference("function", "load.py", "clean"), folder, 12)).endswith("&line=12")
    assert rules.href(rules.Reference("table", "orders"), folder) == "tables?table=orders"
    assert (
        rules.href(rules.Reference("connection", "Finance Captive"), folder)
        == "connections?name=Finance%20Captive"
    )
    assert rules.href(rules.Reference("analysis", ".sab/visualizations/q3.json"), folder) == "analyze"
    with pytest.raises(rules.CollaborationError):
        rules.reference({"kind": "change", "path": "avery-lin", "id": "abc"})  # the change log stays out


def test_news_counts_what_others_wrote_since_you_read() -> None:
    thread = rules.Thread("t-0001", "Returns", AVERY, "2026-11-25T09:00:00Z", channel="general")
    agent = rules.agent_for(AVERY)
    messages = [
        _message(id="aaaa0001", author=AVERY, time="2026-11-25T09:00:00Z", body="mine"),
        _message(id="aaaa0002", author=SAM, time="2026-11-25T10:00:00Z", body="one"),
        _message(id="aaaa0003", author=agent, time="2026-11-25T11:00:00Z", body="two"),
        _message(id="aaaa0004", author=SAM, time="2026-11-25T12:00:00Z", body="three"),
    ]
    first = rules.news([(thread, messages)], {}, AVERY.login)
    assert (first.count, first.first_time, first.words) == (3, True, "3 new messages")
    later = rules.news([(thread, messages)], {"t-0001": "2026-11-25T10:30:00Z"}, AVERY.login)
    assert later.count == 2 and later.thread == "t-0001"  # your own never; the agent's count
    assert later.words == "2 new messages from Sam Ortiz and Claude for Avery Lin"
    many = rules.News(150, ("Sam Ortiz", "Avery Lin", "Kai Moss", "Lee Park"), "t-1", False)
    assert many.words == "99+ new messages from Sam Ortiz, Avery Lin and 2 others"
    assert rules.News(1, ("Sam Ortiz",), "t-1", False).words == "1 new message from Sam Ortiz"
    assert rules.news([(thread, messages)], {"t-0001": "2026-11-25T12:00:00Z"}, AVERY.login).words == ""


def test_links_inside_the_project_are_written_relative() -> None:
    body = "See [@cell 2](sab:cell//home/avery/Shop/data.ipynb#2) and [@orders](sab:table/orders)"
    made = rules.in_project_links(body, "/home/avery/Shop")
    assert made == "See [@cell 2](sab:cell/data.ipynb#2) and [@orders](sab:table/orders)"
    assert rules.page_paths('["/home/avery/Shop/data.ipynb", "orders"]') == [
        "/home/avery/Shop/data.ipynb",
        "orders",
    ]
    assert rules.page_paths("orders") == ["orders"]


def test_who_may_edit_and_delete() -> None:
    mine = _message()
    rules.may_change(mine, AVERY)
    with pytest.raises(PermissionError, match="Only its author"):
        rules.may_change(mine, SAM)
    with pytest.raises(PermissionError):
        rules.may_change(_message(author=rules.agent_for(AVERY)), AVERY)  # the agent's: nobody edits it
    assert "collaboration_post" in rules.agent_may_not("editing a message")


def test_unread_filters_and_search() -> None:
    thread = rules.Thread("t-0001", "Returns", AVERY, "2026-11-25T10:00:00Z", channel="general")
    messages = [_message(), _message(id="2b3c4d5e", author=SAM, time="2026-11-25T11:00:00Z", body="ok")]
    assert rules.unread_of(messages, "2026-11-25T10:30:00Z", "avery-lin") == 1
    assert rules.unread_of(messages, "", "sam-ortiz") == 1
    assert rules.kept("mentions", thread, messages, "sam-ortiz")
    assert not rules.kept("mentions", thread, messages, "avery-lin")
    assert rules.kept("page", thread, messages, "avery-lin", ["/home/avery/Returns/data.ipynb"])
    assert not rules.kept("page", thread, messages, "avery-lin", ["orders"])
    with pytest.raises(rules.CollaborationError):
        rules.check_filter("activity")
    assert rules.matches("CELL look", messages[0].body)
    assert "@data.ipynb cell 7" in rules.snippet(messages[0].body, "cell")
    assert rules.title_of("## [@orders](sab:table/orders) looks off\nmore") == "orders looks off"


def test_cell_numbers_and_widgets_for_the_picker() -> None:
    notebook = {
        "cells": [
            {"source": ["orders = load()\n"], "metadata": {"swissarmybench": {"number": 7}}},
            {"source": "x", "metadata": {}},
        ]
    }
    assert rules.cell_numbers(notebook) == {7: "orders = load()"}
    canvas = {"pages": [{"children": [{"kind": "widget", "id": "w1", "widget": "kpi_card"}]}]}
    assert rules.widget_ids(canvas) == {"w1": "kpi_card"}


def test_the_first_note_stays_first_when_a_reply_shares_its_moment() -> None:
    thread = rules.Thread("t-0001", "Returns", AVERY, "2026-11-25T10:00:00Z", channel="general")
    note = _message(id="ffff0000", reactions={})
    reply = _message(id="0000ffff", kind="reply", author=SAM, reactions={})
    _, shown = rules.fold(thread, [reply, note], [])
    assert [m.id for m in shown] == ["ffff0000", "0000ffff"]


def test_a_file_inside_the_project_is_kept_relative() -> None:
    made = rules.in_project(
        rules.Reference("cell", "/home/avery/Shop/data.ipynb", "7", "cell 7"), "/home/avery/Shop"
    )
    assert made.path == "data.ipynb" and made.key == "cell:data.ipynb#7"
    table = rules.Reference("table", "orders")
    assert rules.in_project(table, "/home/avery/Shop") == table
