"""Rebuild the Collaboration panel's emoji list from Unicode's own emoji-test.txt (standard library only).

    python tools/emoji_data.py                      # fetch Unicode's latest emoji-test.txt and write the file
    python tools/emoji_data.py --from emoji-test.txt   # the same from a copy already here
    python tools/emoji_data.py --check --from emoji-test.txt   # is the file current with that copy?

The file is blazor/SwissArmyBench.Web/wwwroot/data/emoji.json: Unicode's version and date, the source file's
SHA-256, the groups in Unicode's order, and every fully-qualified emoji as [character, name, group index] in the
file's order (the order Unicode's own keyboards use). Byte-stable: the same source gives the same bytes. No
package: the front end reads it as it is (the composer's `:` list, the reaction picker's grid and search).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

SOURCE = "https://unicode.org/Public/emoji/latest/emoji-test.txt"
OUT = (
    Path(__file__).resolve().parents[1] / "blazor" / "SwissArmyBench.Web" / "wwwroot" / "data" / "emoji.json"
)
LINE = re.compile(r"^([0-9A-F ]+?)\s*;\s*fully-qualified\s*#\s*(\S+)\s+E\d+\.\d+\s+(.+)$")
FORMAT = 1


def parse(text: str) -> dict[str, object]:
    """emoji-test.txt read: its version and date, the groups, each fully-qualified emoji with its name and
    group (components, minimally-qualified and unqualified forms left out)."""
    version = re.search(r"^# Version: (\S+)", text, re.M)
    date = re.search(r"^# Date: (\d{4}-\d{2}-\d{2})", text, re.M)
    groups: list[str] = []
    emoji: list[list[object]] = []
    for raw in text.splitlines():
        if raw.startswith("# group: "):
            groups.append(raw.removeprefix("# group: ").strip())
            continue
        found = LINE.match(raw)
        if not found:
            continue
        points, character, name = found.groups()
        made = "".join(chr(int(p, 16)) for p in points.split())
        if made != character:
            raise ValueError(f"The line for {name} names {points}, its character says otherwise.")
        emoji.append([made, name.strip(), len(groups) - 1])
    if not version or not groups or not emoji:
        raise ValueError("This is not Unicode's emoji-test.txt.")
    return {
        "format": FORMAT,
        "unicode": version.group(1),
        "date": date.group(1) if date else "",
        "source": SOURCE,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "groups": groups,
        "emoji": emoji,
    }


def text_of(data: dict[str, object]) -> str:
    """The file's text: its header on top, one emoji a line (a diff reads as the emoji that changed)."""
    head = {k: v for k, v in data.items() if k != "emoji"}
    rows = data["emoji"] if isinstance(data["emoji"], list) else []
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    body = ",\n".join(lines)
    header = json.dumps(head, ensure_ascii=False, sort_keys=True)[:-1]
    return f'{header},\n"emoji": [\n{body}\n]}}\n'


def fetch() -> str:
    with urllib.request.urlopen(SOURCE, timeout=60) as answer:
        data: bytes = answer.read()
    return data.decode("utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from", dest="source", help="a copy of emoji-test.txt (else Unicode's is fetched)")
    parser.add_argument("--check", action="store_true", help="only say whether the file is current")
    args = parser.parse_args(argv)
    text = Path(args.source).read_text(encoding="utf-8") if args.source else fetch()
    made = text_of(parse(text))
    if args.check:
        current = OUT.is_file() and OUT.read_text(encoding="utf-8") == made
        print(f"{OUT.name} is {'current' if current else 'not current: run python tools/emoji_data.py'}.")
        return 0 if current else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(made, encoding="utf-8", newline="\n")
    data = json.loads(made)
    print(f"Wrote {OUT.name}: {len(data['emoji'])} emoji, Unicode {data['unicode']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
