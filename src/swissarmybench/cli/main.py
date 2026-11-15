"""`sab`: run any Swiss Army Bench command from a terminal (the same registry the MCP tool uses).

    sab commands --match export        # the catalog, filtered
    sab list_grids
    sab build_from_query top_clients "SELECT client, sum(balance) b FROM clients GROUP BY 1"
    sab add_step g1 filter '{"column": "balance", "op": "gt", "value": 100}'
    sab put_steps g1 --steps @steps.json
    sab events --types grid_updated --seconds 60
    sab pack new ./data-blades --marketplace data-blades --pack sales --owner "Sales team"

Required arguments can be given in order without a name; any argument can be `--name value`. A
value of `@file` reads the file and `-` reads standard input, which is the easy way to pass JSON or
long SQL. Output is the command's JSON on stdout; a failure is one line on stderr and exit code 1.

Standard library only, so it starts fast.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from swissarmybench.cli.api import CommandError
from swissarmybench.cli.commands import REGISTRY, ImageResult, catalog, execute_result


def parse(argv: list[str]) -> tuple[str, dict[str, Any]]:
    """`name [positional...] [--arg value]...` to (command, arguments)."""
    if not argv:
        raise CommandError("Give a command. `sab commands` lists them.")
    name, rest = argv[0], argv[1:]
    cmd = REGISTRY.get(name)
    required = [a.name for a in cmd.args if a.required] if cmd else []
    values: dict[str, Any] = {}
    positional: list[str] = []
    i = 0
    while i < len(rest):
        token = rest[i]
        if token.startswith("--") and len(token) > 2:
            key = token[2:].replace("-", "_")
            if "=" in key:
                key, _, value = key.partition("=")
                values[key] = _read(value)
            elif i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                values[key] = _read(rest[i + 1])
                i += 1
            else:
                values[key] = "true"  # a bare flag
        else:
            positional.append(token)
        i += 1
    unfilled = [r for r in required if r not in values]
    if cmd and len(positional) > len(unfilled):
        extra = positional[len(unfilled) :]
        raise CommandError(
            f"{name}: unexpected extra value(s) {extra!r}. Pass optional arguments as --name value."
        )
    for arg_name, token in zip(unfilled, positional, strict=False):
        values[arg_name] = _read(token)
    return name, values


def _read(value: str) -> str:
    if value == "-":
        return sys.stdin.read()
    if value.startswith("@"):
        try:
            return Path(value[1:]).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise CommandError(f"Could not read {value[1:]}: {error}") from error
    return value


def save_picture(data: bytes) -> Path:
    """A snapshot with no --out goes to the system temp folder, so a terminal agent can open the file
    by its printed path. The operating system clears that folder; Swiss Army Bench keeps nothing."""
    import tempfile
    import time

    folder = Path(tempfile.gettempdir()) / "swissarmybench-snapshots"
    folder.mkdir(exist_ok=True)
    path = folder / f"snapshot-{time.strftime('%Y%m%d-%H%M%S')}.png"
    path.write_bytes(data)
    return path


def pack_new(argv: list[str]) -> int:
    """`sab pack new <folder> [--marketplace name] [--pack name] [--owner name] [--description text]`:
    a new Claude Code plugin marketplace repository with one pack (blades/ and tangs/), on this
    computer, with no server needed. Push it to GitHub and teammates add it with /plugin."""
    from swissarmybench.domain.packs import PackError, scaffold

    options: dict[str, str] = {}
    rest: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv):
            options[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            rest.append(argv[i])
            i += 1
    if len(rest) != 1:
        print("sab: pack new <folder> [--marketplace name] [--pack name] [--owner name]", file=sys.stderr)
        return 1
    target = Path(rest[0]).expanduser().resolve()
    marketplace = options.get("marketplace") or target.name
    pack = options.get("pack") or "blades"
    try:
        files = scaffold(marketplace, options.get("owner", ""), pack, options.get("description", ""))
    except PackError as error:
        print(f"sab: {error}", file=sys.stderr)
        return 1
    if target.exists() and any(target.iterdir()):
        print(f"sab: {target} is not empty: pick a new folder.", file=sys.stderr)
        return 1
    for relative, text in files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(
        json.dumps(
            {
                "folder": str(target),
                "files": sorted(files),
                "next": [
                    f"Add {target} as a blade folder (blades page, Blade folders), save blades and "
                    f"tangs into packs/{pack}/blades and packs/{pack}/tangs, then push it to GitHub.",
                    "Teammates: /plugin marketplace add <owner>/<repository>, then "
                    f"/plugin install {pack}@{marketplace}",
                ],
            },
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args[:2] == ["pack", "new"]:
        return pack_new(args[2:])
    try:
        if args and args[0] in ("-h", "--help", "help"):
            print(json.dumps(catalog(None), indent=2))
            return 0
        name, values = parse(args)
        result = execute_result(name, values)
        if isinstance(result, ImageResult):
            print(
                json.dumps(
                    result.meta | {"saved": result.meta.get("saved") or str(save_picture(result.data))}
                )
            )
        else:
            print(result)
        return 0
    except CommandError as error:
        print(f"sab: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
