"""The Collaboration panel's emoji list (blazor/.../wwwroot/data/emoji.json), made by tools/emoji_data.py
from Unicode's own emoji-test.txt (the owner, 2026-11-25: "add emojis", the full set, no new package): well
formed, written exactly as the tool writes it (so a hand edit shows), its parser on a few made-up lines."""

from __future__ import annotations

import json

import pytest
from tools import emoji_data

SAMPLE = """# emoji-test.txt
# Date: 2026-04-30, 22:40:18 GMT
# Version: 18.0
# group: Smileys & Emotion
# subgroup: face-smiling
1F600                                                  ; fully-qualified     # 😀 E1.0 grinning face
263A FE0F                                              ; fully-qualified     # ☺️ E0.6 smiling face
263A                                                   ; unqualified         # ☺ E0.6 smiling face
# group: Component
1F3FB                                                  ; component           # 🏻 E1.0 light skin tone
# group: People & Body
1F44D                                                  ; fully-qualified     # 👍 E0.6 thumbs up
1F44D 1F3FD            ; fully-qualified     # 👍🏽 E1.0 thumbs up: medium skin tone
"""


def test_the_parser_keeps_only_fully_qualified_emoji_with_their_groups() -> None:
    data = emoji_data.parse(SAMPLE)
    assert data["unicode"] == "18.0" and data["date"] == "2026-04-30"
    assert data["groups"] == ["Smileys & Emotion", "Component", "People & Body"]
    assert data["emoji"] == [
        ["😀", "grinning face", 0],
        ["☺️", "smiling face", 0],
        ["👍", "thumbs up", 2],
        ["👍🏽", "thumbs up: medium skin tone", 2],
    ]
    text = emoji_data.text_of(data)
    assert json.loads(text)["emoji"] == data["emoji"] and emoji_data.text_of(json.loads(text)) == text
    with pytest.raises(ValueError):
        emoji_data.parse("# not it\n")


def test_the_file_is_current_and_well_formed() -> None:
    text = emoji_data.OUT.read_text(encoding="utf-8")
    data = json.loads(text)
    assert emoji_data.text_of(data) == text  # exactly as tools/emoji_data.py writes it
    assert data["format"] == emoji_data.FORMAT and data["source"] == emoji_data.SOURCE
    assert float(data["unicode"]) >= 15.0 and len(data["sha256"]) == 64
    groups, rows = data["groups"], data["emoji"]
    assert "Smileys & Emotion" in groups and "Flags" in groups
    assert len(rows) > 3000
    assert len({row[0] for row in rows}) == len(rows)  # each emoji once
    for character, name, group in rows:
        assert isinstance(character, str) and 0 < len(character) <= 32
        assert isinstance(name, str) and name.strip() == name and name
        assert isinstance(group, int) and 0 <= group < len(groups)
    names = {name: character for character, name, _ in rows}
    assert names["thumbs up"] == "👍" and names["party popper"] == "🎉" and names["eyes"] == "👀"
