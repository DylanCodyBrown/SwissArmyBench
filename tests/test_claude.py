"""Launch Claude (the owner, 2026-11-16): "a launch claude command on the home page in the bottom footer ...
start a claude code cli session in the proper folder so the claude agent inherits the context it needs to
understand SAB"; "with a setting in the settings go launch it with bypass permissions"; and "a launcher that
checks the machine for the installed claude desktop app and launch it the same way. alot of the users will
have a 3p claude install so dynamically finding it will be the key".

Nothing here probes this computer or opens a terminal: the probes' answers are made up, and the launches
are recorded by a stand-in."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pyarrow as pa
import pytest

from swissarmybench.domain import claude as rules
from swissarmybench.domain.claude import CODE, DESKTOP, Context, Install, TableFacts
from swissarmybench.domain.steps import Step
from swissarmybench.server.claude_finder import Finder
from tests.conftest import AGENT, AUTH, grid_id, make_client, push

# A made-up table whose cell value must never reach Claude's files.
SECRET_VALUE = "Zanzibar-Quokka-7731"


# ===== finding Claude: loosely, by name, wherever it is =====


def test_names_are_matched_loosely_but_not_uninstallers() -> None:
    assert (
        rules.is_claude("Claude")
        and rules.is_claude("Claude (Acme Corp)")
        and rules.is_claude("claude-desktop")
    )
    assert not rules.is_claude("Uninstall Claude") and not rules.is_claude("Update.exe claude")
    assert not rules.is_claude("Slack")


def test_the_registry_finds_the_official_app_and_a_company_build() -> None:
    entries = [
        {
            "key": "AnthropicClaude",
            "DisplayName": "Claude",
            "Publisher": "Anthropic, PBC",
            "DisplayIcon": r"C:\Users\pat\AppData\Local\AnthropicClaude\claude.exe,0",
        },
        {
            "key": "{1234}",
            "DisplayName": "Claude for Acme",
            "Publisher": "Acme IT",
            "InstallLocation": r"D:\Apps\AcmeClaude",
        },
        {"key": "claude.exe", "Default": r'"C:\Program Files\Acme Claude\claude.exe"'},
        {"key": "Slack", "DisplayName": "Slack", "DisplayIcon": r"C:\Slack\slack.exe"},
        {"key": "AnthropicClaudeUninstall", "DisplayName": "Claude", "DisplayIcon": r"C:\x\Uninstall.exe"},
    ]
    found = rules.from_registry(entries)
    assert [(i.kind, i.path, i.official) for i in found] == [
        (DESKTOP, r"C:\Users\pat\AppData\Local\AnthropicClaude\claude.exe", True),
        (DESKTOP, r"D:\Apps\AcmeClaude\claude.exe", False),
        (DESKTOP, r"C:\Program Files\Acme Claude\claude.exe", False),
    ]


def test_store_packages_start_by_their_app_id_and_keep_settings_in_their_folder() -> None:
    packages = [
        {
            "Name": "Claude",
            "PackageFamilyName": "Claude_pzs8sxrjxfjjc",
            "Publisher": "CN=Anthropic",
            "InstallLocation": r"C:\Program Files\WindowsApps\Claude_1.0",
            "AppIds": ["Claude"],
        }
    ]
    (install,) = rules.from_store(packages, r"C:\Users\pat\AppData\Local")
    assert install.launch == ("explorer.exe", r"shell:AppsFolder\Claude_pzs8sxrjxfjjc!Claude")
    assert install.official and install.config.endswith(
        r"Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json"
    )


def test_start_menu_shortcuts_tell_the_app_from_the_cli() -> None:
    shortcuts = [
        {"lnk": r"C:\Start Menu\Programs\Acme AI\Claude.lnk", "target": r"E:\Tools\AcmeAI\Claude.exe"},
        {"lnk": r"C:\Start Menu\Programs\Claude Code.lnk", "target": r"C:\Users\pat\.local\bin\claude.exe"},
        {"lnk": r"C:\Start Menu\Programs\Word.lnk", "target": r"C:\Office\winword.exe"},
    ]
    found = rules.from_shortcuts(shortcuts)
    assert [(i.kind, i.path) for i in found] == [
        (DESKTOP, r"E:\Tools\AcmeAI\Claude.exe"),
        (CODE, r"C:\Users\pat\.local\bin\claude.exe"),
    ]


def test_mac_bundles_by_bundle_id_or_name() -> None:
    official = rules.from_bundle(
        "/Applications/Claude.app", {"CFBundleIdentifier": rules.OFFICIAL_BUNDLE}, "Applications"
    )
    renamed = rules.from_bundle(
        "/Applications/Acme Assistant.app",
        {"CFBundleIdentifier": "com.acme.claude-desktop", "CFBundleName": "Acme Assistant"},
        "Spotlight",
    )
    assert official and official.official and official.launch == ("open", "-a", "/Applications/Claude.app")
    assert renamed and not renamed.official and renamed.name == "Acme Assistant"
    assert (
        rules.from_bundle("/Applications/Safari.app", {"CFBundleIdentifier": "com.apple.Safari"}, "x") is None
    )


def test_desktop_files_give_their_exec_line_as_arguments() -> None:
    text = (
        "[Desktop Entry]\nType=Application\nName=Claude\nName[de]=Claude DE\n"
        'Exec="/opt/Claude Desktop/claude-desktop" --no-sandbox %U\nIcon=claude\n'
        "[Desktop Action new]\nExec=/bin/false\n"
    )
    install = rules.from_desktop_file("/usr/share/applications/claude-desktop.desktop", text)
    assert install and install.kind == DESKTOP
    assert install.launch == ("/opt/Claude Desktop/claude-desktop", "--no-sandbox")
    terminal = "[Desktop Entry]\nType=Application\nName=Claude Code\nExec=claude\nTerminal=true\n"
    assert rules.from_desktop_file("/x/claude-code.desktop", terminal) is None


def test_ranked_once_each_official_first() -> None:
    a = Install(DESKTOP, r"C:\A\claude.exe", "Claude", "Start menu", False)
    b = Install(DESKTOP, r"c:\a\CLAUDE.exe", "Claude", "registry", True)
    c = Install(DESKTOP, "/x/acme", "Acme", "registry", False)
    assert rules.ranked([c, a, b]) == [b, c]
    assert rules.chosen([b, c], DESKTOP, "/x/acme") == c
    assert rules.chosen([b, c], DESKTOP, "/gone") == b and rules.chosen([b, c], CODE, None) is None


def test_the_finder_reads_linux_desktop_files_and_the_cli_without_running_anything(tmp_path: Path) -> None:
    apps = tmp_path / "share" / "applications"
    apps.mkdir(parents=True)
    (apps / "acme-claude.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Acme Claude\nExec=/opt/acme/claude %u\n"
    )
    (apps / "gimp.desktop").write_text("[Desktop Entry]\nType=Application\nName=GIMP\nExec=gimp\n")
    local = tmp_path / ".claude" / "local"
    local.mkdir(parents=True)
    (local / "claude").write_text("#!/bin/sh\n")
    ran: list[Any] = []
    finder = Finder(
        "linux",
        tmp_path,
        {"XDG_DATA_HOME": str(tmp_path / "share"), "XDG_DATA_DIRS": str(tmp_path / "none")},
        run=lambda *a, **k: ran.append(a),
        which=lambda name: None,
    )
    found = finder.find()
    assert [(i.kind, i.name) for i in found] == [(CODE, "Claude Code"), (DESKTOP, "Acme Claude")]
    assert found[1].launch == ("/opt/acme/claude",) and ran == []


def test_the_finder_reads_windows_answers(tmp_path: Path) -> None:
    exe = tmp_path / "AcmeClaude" / "claude.exe"
    exe.parent.mkdir()
    exe.write_text("")
    answer = {
        "packages": {"Name": "Claude", "PackageFamilyName": "Claude_x", "AppIds": "App"},
        "shortcuts": [{"lnk": r"C:\menu\Claude.lnk", "target": str(exe)}],
    }
    finder = Finder(
        "windows",
        tmp_path,
        {"LOCALAPPDATA": str(tmp_path)},
        run=lambda *a, **k: SimpleNamespace(stdout=json.dumps(answer), returncode=0),
        which=lambda name: None,
    )
    found = finder.find()
    assert {(i.source, i.path) for i in found} >= {("Store", ""), ("Start menu", str(exe))} - {("Store", "")}
    assert any(i.source == "Store" and i.launch[1].endswith("Claude_x!App") for i in found)


# ===== Claude Desktop's config: ours set, everything else kept, no token =====


def test_the_config_merge_keeps_every_other_entry() -> None:
    before = json.dumps({"mcpServers": {"files": {"command": "npx", "args": ["fs"]}}, "theme": "dark"})
    text, changed = rules.merge_config(before, rules.mcp_entry("/opt/sab/swissarmybench-mcp"))
    data = json.loads(text)
    assert (
        changed
        and data["theme"] == "dark"
        and data["mcpServers"]["files"] == {"command": "npx", "args": ["fs"]}
    )
    assert data["mcpServers"]["swissarmybench"] == {"command": "/opt/sab/swissarmybench-mcp"}
    assert "token" not in text.casefold()
    again, changed_again = rules.merge_config(text, rules.mcp_entry("/opt/sab/swissarmybench-mcp"))
    assert not changed_again and json.loads(again) == data
    assert json.loads(rules.merge_config(None, rules.mcp_entry("m"))[0]) == {
        "mcpServers": {"swissarmybench": {"command": "m"}}
    }
    with pytest.raises(rules.ConfigError, match="not valid JSON"):
        rules.merge_config("{oops", rules.mcp_entry("m"))
    with pytest.raises(rules.ConfigError, match="mcpServers"):
        rules.merge_config('{"mcpServers": []}', rules.mcp_entry("m"))


def test_config_places_follow_the_app_name_and_the_official_place() -> None:
    company = Install(DESKTOP, "/Applications/Acme Assistant.app", "Acme Assistant", "Spotlight")
    assert rules.config_places(company, "darwin", "/Users/pat", {}) == [
        "/Users/pat/Library/Application Support/Acme Assistant/claude_desktop_config.json",
        "/Users/pat/Library/Application Support/Claude/claude_desktop_config.json",
    ]
    assert rules.official_config(
        "windows", r"C:\Users\pat", {"APPDATA": r"C:\Users\pat\AppData\Roaming"}
    ) == (r"C:\Users\pat\AppData\Roaming\Claude\claude_desktop_config.json")
    assert (
        rules.official_config("linux", "/home/pat", {})
        == "/home/pat/.config/Claude/claude_desktop_config.json"
    )


# ===== Claude Code's folder: context, no values =====


def _context() -> Context:
    steps = [
        Step("filter", {"column": "region", "op": "eq", "value": SECRET_VALUE}),
        Step("filter", {"column": "city", "op": "in", "values": [SECRET_VALUE, "Oslo"]}),
        Step("sql", {"sql": f"SELECT * FROM grid WHERE note = '{SECRET_VALUE}'"}),  # noqa: S608 (made-up text, never run)
        Step("sort", {"keys": [["amount", "desc"]]}),
    ]
    return Context(
        "9.9.9",
        'Q3 "close" pack',
        "/home/pat/Q3.sab",
        "/var/sab-1/Q3",
        [TableFacts("orders", 1200, [("region", "VARCHAR"), ("amount", "DOUBLE")], steps)],
        [("Warehouse", "PostgreSQL")],
        [("notebook", "data.ipynb"), ("app", "sales.stapp.json")],
    )


def test_claude_md_is_stable_and_imports_context_md() -> None:
    text = rules.claude_md("9.9.9")
    assert text == rules.claude_md("9.9.9") and "# Swiss Army Bench 9.9.9: your context" in text
    assert text.rstrip().endswith("@context.md") and "swissarmybench://context" in text


def test_the_summary_has_the_context_and_no_value() -> None:
    text = rules.context_markdown(_context())
    assert SECRET_VALUE not in text and "Oslo" not in text and "SELECT" not in text
    for part in (
        'Q3 "close" pack',
        "/home/pat/Q3.sab",
        "/var/sab-1/Q3",
        "`orders`: 1,200 rows",
        "region (VARCHAR)",
        "Keep rows where region equals a value",
        "A SQL step",
        "Sort by amount descending",
        "Warehouse (PostgreSQL)",
        "`data.ipynb`",
    ):
        assert part in text, part


def test_mcp_and_settings_files_have_no_token_and_grant_nothing() -> None:
    assert json.loads(rules.mcp_json("/opt/x/swissarmybench-mcp")) == {
        "mcpServers": {"swissarmybench": {"command": "/opt/x/swissarmybench-mcp"}}
    }
    settings = json.loads(rules.settings_json("/Program Files/x/swissarmybench-context"))
    assert "permissions" not in settings and settings["enabledMcpjsonServers"] == ["swissarmybench"]
    hook = settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    assert hook["command"] == '"/Program Files/x/swissarmybench-context" --folder'


def test_folder_names_are_safe() -> None:
    assert rules.folder_name(None) == "no-project"
    assert rules.folder_name('Q3 "close"; rm -rf /') == "Q3 -close- rm -rf"
    assert rules.folder_name("../..") == "no-project" and rules.folder_name("CON") == "CON-project"


# ===== the terminal: argument lists, a name with quotes and spaces is safe =====

NASTY = '/var/sab work/Q3 "close"; $(touch x) `id`'


def test_the_terminal_per_platform_is_an_argument_list() -> None:
    argv = rules.claude_argv("/usr/bin/claude", [NASTY], bypass=False)
    assert argv == ["/usr/bin/claude", "--add-dir", NASTY]
    linux = rules.terminal(
        "linux", {"gnome-terminal": "/usr/bin/gnome-terminal", "xterm": "/usr/bin/xterm"}, "/f", argv
    )
    assert linux and linux.argv == ["/usr/bin/gnome-terminal", "--working-directory=/f", "--", *argv]
    konsole = rules.terminal("linux", {"konsole": "/k"}, "/f", argv)
    assert konsole and konsole.argv == ["/k", "--workdir", "/f", "-e", *argv]
    first = rules.terminal("linux", {"x-terminal-emulator": "/x", "xterm": "/xt"}, "/f", argv)
    assert first and first.argv == ["/x", "-e", *argv] and first.cwd == "/f"
    assert rules.terminal("linux", {}, "/f", argv) is None
    wt = rules.terminal("windows", {"wt": r"C:\wt.exe"}, r"C:\f", ["claude.exe", "--add-dir", r"C:\a;b"])
    assert wt and wt.argv == [r"C:\wt.exe", "-d", r"C:\f", "claude.exe", "--add-dir", r"C:\a\;b"]
    console = rules.terminal("windows", {}, r"C:\f", ["claude.exe"])
    assert console and console.new_console and console.argv == ["claude.exe"]


def test_macos_terminal_quotes_every_part() -> None:
    argv = rules.claude_argv("/Users/pat/.local/bin/claude", [NASTY], bypass=True)
    plan = rules.terminal("darwin", {}, "/Users/pat/.swissarmybench/claude/Q3 close", argv)
    assert plan and plan.argv[0] == "/usr/bin/osascript" and "do script (item 1 of argv)" in plan.argv
    line = plan.argv[-1]
    # The shell reads the line back into exactly the folder and the arguments.
    words = shlex.split(line)
    assert words[:3] == ["cd", "/Users/pat/.swissarmybench/claude/Q3 close", "&&"]
    assert words[4:] == [*argv]
    assert argv[-1] == rules.BYPASS_FLAG


def test_not_installed_says_how_to_install() -> None:
    code = rules.install_help(CODE, "windows")
    assert code["message"] == "Claude Code is not installed on this computer."
    assert code["commands"][0] == "irm https://claude.ai/install.ps1 | iex"
    assert (
        rules.install_help(CODE, "linux")["commands"][0] == "curl -fsSL https://claude.ai/install.sh | bash"
    )
    assert rules.install_help(DESKTOP, "darwin")["url"] == "https://claude.ai/download"


# ===== HTTP: the agent reads, the user launches =====


def _standin(tmp_path: Path, installs: list[dict[str, Any]], platform: str = "linux") -> Path:
    path = tmp_path / "claude-standin.json"
    path.write_text(
        json.dumps(
            {
                "platform": platform,
                "installs": installs,
                "terminals": {"x-terminal-emulator": "/usr/bin/x-terminal-emulator"},
            }
        )
    )
    return path


def _launches(standin: Path) -> list[dict[str, Any]]:
    path = standin.with_suffix(".launches.jsonl")
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_the_agent_reads_but_cannot_launch_or_choose(tmp_path: Path) -> None:
    standin = _standin(tmp_path, [{"kind": "code", "path": "/usr/local/bin/claude"}])
    with make_client(tmp_path, claude_standin=standin) as client:
        found = client.get("/claude", headers=AGENT).json()
        assert found["code"]["chosen"] == "/usr/local/bin/claude" and found["desktop"]["chosen"] is None
        assert found["desktop"]["help"]["url"] == "https://claude.ai/download"
        assert client.post("/claude/launch", json={}, headers=AGENT).status_code == 403
        assert client.put("/claude", json={"bypass": True}, headers=AGENT).status_code == 403
        assert _launches(standin) == []


def test_launching_claude_code_writes_the_folder_and_opens_the_terminal(tmp_path: Path) -> None:
    standin = _standin(tmp_path, [{"kind": "code", "path": "/usr/local/bin/claude"}])
    with make_client(tmp_path, claude_standin=standin) as client:
        table = pa.table({"region": ["North", SECRET_VALUE], "amount": [1.5, 2.0]})
        grid = grid_id(push(client, "orders", table))
        step = {"kind": "filter", "params": {"column": "region", "op": "eq", "value": SECRET_VALUE}}
        assert client.post(f"/grids/{grid}/steps", json={"steps": [step]}, headers=AUTH).status_code == 200
        answer = client.post("/claude/launch", json={}, headers=AUTH).json()
        assert answer["launched"] == "code" and answer["bypass"] is False
        folder = Path(answer["folder"])
        assert folder == tmp_path / "state" / "claude" / "no-project"
        text = (folder / "context.md").read_text()
        assert "`orders`: 2 rows" in text and "`Keep rows where region equals a value`" in text
        assert SECRET_VALUE not in text and "North" not in text
        assert "swissarmybench" in json.loads((folder / ".mcp.json").read_text())["mcpServers"]
        assert "UserPromptSubmit" in (folder / ".claude" / "settings.json").read_text()
        (launch,) = _launches(standin)
        assert launch["argv"] == ["/usr/bin/x-terminal-emulator", "-e", "/usr/local/bin/claude"]
        assert launch["cwd"] == str(folder)
        context = client.get("/claude/context", headers=AGENT).json()["text"]
        assert "orders" in context and SECRET_VALUE not in context
        # Settings' bypass permissions mode: the user's switch.
        assert client.put("/claude", json={"bypass": True}, headers=AUTH).json()["bypass"] is True
        client.post("/claude/launch", json={"app": "code"}, headers=AUTH)
        assert _launches(standin)[-1]["argv"][-1] == rules.BYPASS_FLAG


def test_nothing_found_is_the_plain_message(tmp_path: Path) -> None:
    standin = _standin(tmp_path, [])
    with make_client(tmp_path, claude_standin=standin) as client:
        answer = client.post("/claude/launch", json={}, headers=AUTH).json()
        assert answer["launched"] is None
        assert [m["kind"] for m in answer["missing"]] == ["code", "desktop"]
        assert _launches(standin) == []


def test_both_found_asks_which(tmp_path: Path) -> None:
    standin = _standin(tmp_path, [{"kind": "code", "path": "/c"}, {"kind": "desktop", "path": "/d"}])
    with make_client(tmp_path, claude_standin=standin) as client:
        assert client.post("/claude/launch", json={}, headers=AUTH).json()["choose"] == ["code", "desktop"]


def test_claude_desktop_asks_once_then_writes_its_config_with_a_backup(tmp_path: Path) -> None:
    config = tmp_path / "AcmeClaude" / "claude_desktop_config.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"mcpServers": {"files": {"command": "npx"}}, "keep": 1}))
    standin = _standin(
        tmp_path,
        [
            {
                "kind": "desktop",
                "path": "/opt/acme/claude",
                "name": "Acme Claude",
                "official": False,
                "launch": ["/opt/acme/claude", "--x"],
                "config": str(config),
            }
        ],
    )
    with make_client(tmp_path, claude_standin=standin) as client:
        asked = client.post("/claude/launch", json={"app": "desktop"}, headers=AUTH).json()
        assert asked["launched"] is None and asked["confirm"]["path"] == str(config)
        assert _launches(standin) == [] and len(list(config.parent.iterdir())) == 1
        done = client.post("/claude/launch", json={"app": "desktop", "confirmed": True}, headers=AUTH).json()
        assert done["launched"] == "desktop" and done["changed"] and Path(done["backup"]).exists()
        data = json.loads(config.read_text())
        assert data["keep"] == 1 and data["mcpServers"]["files"] == {"command": "npx"}
        assert set(data["mcpServers"]["swissarmybench"]) == {"command"}
        assert _launches(standin)[-1]["argv"] == ["/opt/acme/claude", "--x"]
        # Asked once: the next launch goes straight on (and writes nothing: it is already there).
        again = client.post("/claude/launch", json={"app": "desktop"}, headers=AUTH).json()
        assert again["launched"] == "desktop" and not again["changed"] and again["backup"] is None
        assert client.get("/claude", headers=AUTH).json()["desktop"]["config"]["allowed"] is True


def test_a_company_build_with_no_config_anywhere_is_said(tmp_path: Path) -> None:
    standin = _standin(
        tmp_path, [{"kind": "desktop", "path": "/opt/acme/acme-ai", "name": "Acme AI", "official": False}]
    )
    with make_client(tmp_path, claude_standin=standin) as client:
        answer = client.post("/claude/launch", json={"app": "desktop"}, headers=AUTH).json()
        assert answer["launched"] is None and "Acme AI" in answer["config_unknown"]["path"]
        mine = tmp_path / "mine.json"
        chosen = client.put("/claude", json={"config": {"/opt/acme/acme-ai": str(mine)}}, headers=AUTH).json()
        assert chosen["desktop"]["config"]["path"] == str(mine)


def test_other_must_be_a_real_file(tmp_path: Path) -> None:
    standin = _standin(tmp_path, [])
    mine = tmp_path / "bin" / "claude"
    mine.parent.mkdir()
    mine.write_text("#!/bin/sh\n")
    with make_client(tmp_path, claude_standin=standin) as client:
        assert client.put("/claude", json={"code": str(tmp_path / "nope")}, headers=AUTH).status_code == 400
        state = client.put("/claude", json={"code": str(mine)}, headers=AUTH).json()
        assert state["code"]["chosen"] == str(mine) and state["code"]["found"][0]["source"] == "your choice"
