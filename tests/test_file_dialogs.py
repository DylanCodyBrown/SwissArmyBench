"""The system's own file dialog (domain/file_dialogs.py, server/dialog_runner.py, services/file_dialogs.py)
and the page's own picker's server side (quick places, recent folders per kind, New folder, hidden files). No
real dialog opens: each system's plan is built and read, and the child process is a stand-in. Made-up
folders."""

from __future__ import annotations

import base64
import json
import subprocess
import threading
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from swissarmybench.domain import file_dialogs as rules
from swissarmybench.server import routes_file_dialogs
from swissarmybench.server.dialog_runner import DialogRunner, nearest_folder
from swissarmybench.server.http import guarded
from swissarmybench.services.file_dialogs import FileDialogs
from tests.conftest import AGENT, AUTH, make_client


def request(**body: Any) -> rules.DialogRequest:
    return rules.read_request({"title": "Open file", **body})


# ===== the request =====


def test_a_request_is_checked_and_named_by_its_kind() -> None:
    got = request(mode="file", suffixes=[".CSV", ".xlsx", ".csv"], start="/data")
    assert got.suffixes == (".csv", ".xlsx") and got.kind == "file:.csv,.xlsx" and got.name is None
    assert request(mode="folder", suffixes=[".csv"]).suffixes == ()
    assert request(mode="save", name="orders.csv", kind="workbench-save").kind == "workbench-save"
    for bad in (
        {"mode": "delete"},
        {"suffixes": ["csv"]},
        {"suffixes": [".c sv"]},
        {"mode": "save", "name": "../x"},
        {"title": "two\nlines"},
        {"kind": "Has Spaces"},
    ):
        with pytest.raises(ValueError):
            rules.read_request({"title": "x", **bad})


# ===== which tool on which system =====


def tool(
    platform: str, env: dict[str, str] | None = None, have: tuple[str, ...] = (), tk: bool = False
) -> Any:
    return rules.choose_tool(platform, env or {}, lambda c: c in have, lambda: tk)


def test_each_system_picks_its_tool() -> None:
    assert tool("win32", tk=True) == ("tk", "")
    assert tool("win32", have=("powershell",)) == ("powershell", "")
    assert tool("darwin", have=("osascript",), tk=True) == ("osascript", "")
    assert tool("darwin", tk=True) == ("tk", "")
    display = {"DISPLAY": ":0"}
    assert tool("linux", display, have=("zenity", "kdialog"), tk=True)[0] == "zenity"
    assert tool("linux", display | {"XDG_CURRENT_DESKTOP": "KDE"}, have=("zenity", "kdialog"))[0] == "kdialog"
    assert tool("linux", {"WAYLAND_DISPLAY": "wayland-0"}, tk=True)[0] == "tk"
    assert tool("linux", display) == (None, "No zenity, kdialog or Tk here.")


def test_no_display_or_switched_off_means_the_page_picker() -> None:
    none, why = tool("linux", {}, have=("zenity",), tk=True)
    assert none is None and "No display" in why
    for value in ("off", "0", "false"):
        assert tool("win32", {rules.OFF_VARIABLE: value}, tk=True)[0] is None


# ===== each tool's plan: the values never inside a script =====

TRICKY = "Pick \"it\"; $(rm -rf ~) `x` 'q'"


def test_tk_plan_passes_the_values_as_one_json_argument() -> None:
    plan = rules.plan(
        "tk", request(mode="save", title=TRICKY, name="a b.csv", suffixes=[".csv"]), "/home/me", "py"
    )
    assert plan.argv[:4] == ("py", "-I", "-c", rules.TK_SCRIPT)
    payload = json.loads(plan.argv[4])
    assert payload == {
        "mode": "save",
        "title": TRICKY,
        "folder": "/home/me",
        "name": "a b.csv",
        "types": [["Files (.csv)", "*.csv"], ["All files", "*"]],
    }
    assert TRICKY not in rules.TK_SCRIPT and "-topmost" in rules.TK_SCRIPT
    compile(rules.TK_SCRIPT, "tk", "exec")


def test_powershell_plan_is_encoded_and_reads_its_values_from_the_environment() -> None:
    plan = rules.plan("powershell", request(title=TRICKY, suffixes=[".csv", ".xlsx"]), r"C:\Data", "py")
    assert plan.argv[0] == "powershell" and "-STA" in plan.argv and plan.argv[-2] == "-EncodedCommand"
    script = base64.b64decode(plan.argv[-1]).decode("utf-16-le")
    assert script == rules.POWERSHELL_SCRIPT and TRICKY not in script
    assert "IFileDialog" in script and "FolderBrowserDialog" not in script and "TopMost" in script
    assert json.loads(plan.env["SAB_DIALOG"]) == {
        "mode": "file",
        "title": TRICKY,
        "folder": r"C:\Data",
        "name": "",
        "filter": "Files (.csv, .xlsx)|*.csv;*.xlsx|All files|*.*",
    }
    folder = rules.plan("powershell", request(mode="folder"), None, "py")
    assert json.loads(folder.env["SAB_DIALOG"])["filter"] == ""


def test_osascript_plan_passes_arguments_and_activates() -> None:
    plan = rules.plan("osascript", request(title=TRICKY, suffixes=[".csv", ".xlsx"]), "/Users/me", "py")
    assert plan.argv == ("osascript", "-e", rules.OSASCRIPT, TRICKY, "/Users/me", "", "file", "csv", "xlsx")
    assert "activate" in rules.OSASCRIPT and "on error number -128" in rules.OSASCRIPT
    save = rules.plan("osascript", request(mode="save", name="out.zip"), None, "py")
    assert save.argv[3:] == ("Open file", "", "out.zip", "save")


def test_zenity_and_kdialog_plans() -> None:
    z = rules.plan("zenity", request(suffixes=[".csv"]), "/home/me/data", "py")
    assert z.argv[:3] == ("zenity", "--file-selection", "--title=Open file")
    assert "--filename=/home/me/data/" in z.argv and "--file-filter=Files (.csv) | *.csv *.CSV" in z.argv
    assert z.cancel_codes == frozenset({1})
    zs = rules.plan("zenity", request(mode="save", name="out.csv"), "/home/me", "py")
    assert "--save" in zs.argv and "--filename=/home/me/out.csv" in zs.argv
    zf = rules.plan("zenity", request(mode="folder"), "/home/me", "py")
    assert "--directory" in zf.argv
    k = rules.plan("kdialog", request(mode="save", name="out.csv", suffixes=[".csv"]), "/home/me", "py")
    assert k.argv[:5] == ("kdialog", "--title", "Open file", "--getsavefilename", "/home/me/out.csv")
    assert k.argv[5].startswith("*.csv *.CSV|Files (.csv)")
    kf = rules.plan("kdialog", request(mode="folder"), "/home/me", "py")
    assert kf.argv[3:] == ("--getexistingdirectory", "/home/me")


def test_answers_are_read() -> None:
    zen = rules.plan("zenity", request(), "/x", "py")
    assert rules.read_answer(zen, 0, "/home/me/orders.csv\n", "") == {"path": "/home/me/orders.csv"}
    assert rules.read_answer(zen, 1, "", "") == {"cancelled": True}
    with pytest.raises(rules.DialogFailed, match="code 5"):
        rules.read_answer(zen, 5, "", "Gtk-WARNING: cannot open display")
    tk = rules.plan("tk", request(), "/x", "py")
    assert rules.read_answer(tk, 0, '{"path": "C:\\\\Data\\\\a.csv"}', "") == {"path": "C:\\Data\\a.csv"}
    assert rules.read_answer(tk, 0, '{"cancelled": true}', "") == {"cancelled": True}
    with pytest.raises(rules.DialogFailed):
        rules.read_answer(tk, 0, "not json", "")
    mac = rules.plan("osascript", request(), "/x", "py")
    assert rules.read_answer(mac, 0, "\n", "") == {"cancelled": True}
    assert rules.read_answer(mac, 0, "/Users/me/a b.csv\n", "") == {"path": "/Users/me/a b.csv"}


# ===== the runner, its child process stood in =====


class FakeRun:
    """subprocess.run stood in: Tk's check answers yes; the dialog answers what it is told."""

    def __init__(self, answer: Any) -> None:
        self.answer = answer
        self.calls: list[list[str]] = []
        self.envs: list[dict[str, str]] = []
        self.gate: threading.Event | None = None

    def __call__(self, argv: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        if argv[-1].startswith("import tkinter"):
            return subprocess.CompletedProcess(argv, 0, "", "")
        self.envs.append(kw.get("env") or {})
        assert kw["timeout"] == 600 and kw["stdin"] == subprocess.DEVNULL
        if self.gate:
            self.gate.wait(5)
        if isinstance(self.answer, BaseException):
            raise self.answer
        code, out = self.answer
        return subprocess.CompletedProcess(argv, code, out, "")


def runner(
    answer: Any, platform: str = "win32", env: dict[str, str] | None = None
) -> tuple[DialogRunner, FakeRun]:
    fake = FakeRun(answer)
    return DialogRunner(env=env or {}, platform=platform, which=lambda c: None, python="py", run=fake), fake


def test_the_runner_answers_a_path_a_cancel_and_a_timeout(tmp_path: Path) -> None:
    run, fake = runner((0, json.dumps({"path": str(tmp_path / "a.csv")})))
    assert run.status() == {"system": True, "tool": "tk"}
    assert run.choose(request(start=str(tmp_path / "missing" / "deeper"))) == {
        "path": str(tmp_path / "a.csv")
    }
    assert json.loads(fake.calls[-1][4])["folder"] == str(tmp_path)  # the nearest folder that is there
    fake.answer = (0, '{"cancelled": true}')
    assert run.choose(request()) == {"cancelled": True}
    fake.answer = subprocess.TimeoutExpired("py", 600)
    assert run.choose(request()) == {"cancelled": True, "timedOut": True}
    fake.answer = FileNotFoundError(2, "No such file")
    with pytest.raises(rules.DialogFailed):
        run.choose(request())
    # Tk was asked about once, however many dialogs.
    assert sum(1 for c in fake.calls if c[-1].startswith("import tkinter")) == 1


def test_one_dialog_at_a_time() -> None:
    run, fake = runner((0, '{"cancelled": true}'))
    fake.gate = threading.Event()
    first: list[Any] = []
    thread = threading.Thread(target=lambda: first.append(run.choose(request())))
    thread.start()
    while len(fake.envs) < 1:
        threading.Event().wait(0.01)
    assert run.choose(request()) == {"busy": True}
    fake.gate.set()
    thread.join(5)
    assert first == [{"cancelled": True}]


def test_no_display_opens_nothing() -> None:
    run, fake = runner((0, "/x"), platform="linux", env={})
    assert run.status()["system"] is False
    with pytest.raises(rules.DialogFailed, match="No display"):
        run.choose(request())
    assert fake.calls == []


def test_nearest_folder(tmp_path: Path) -> None:
    assert nearest_folder(str(tmp_path / "a" / "b.csv")) == str(tmp_path)
    assert nearest_folder(None) == str(Path.home())


# ===== recent folders, per kind =====


def test_recent_folders_are_kept_per_kind() -> None:
    data: Any = None
    for i in range(10):
        data = rules.remember(data, "file:.csv", f"/data/{i}")
    data = rules.remember(data, "folder", "/projects")
    data = rules.remember(data, "file:.csv", "/data/3")
    assert rules.recent(data, "file:.csv")[:3] == ["/data/3", "/data/9", "/data/8"]
    assert len(rules.recent(data, "file:.csv")) == rules.RECENT_PER_KIND
    assert rules.recent(data, "folder") == ["/projects"]
    assert rules.recent({"recent": "junk"}, "folder") == []
    assert rules.folder_of("/data/a.csv", "file") == "/data"
    assert rules.folder_of(r"C:\a.csv", "save") == "C:\\"
    assert rules.folder_of("/data/x", "folder") == "/data/x"


class Memory:
    def __init__(self) -> None:
        self.data: Any = None

    def read(self) -> Any:
        return self.data

    def write(self, data: Any) -> None:
        self.data = data


def test_a_pick_is_remembered_and_shown_as_a_place(tmp_path: Path) -> None:
    run, _ = runner((0, json.dumps({"path": str(tmp_path / "orders.csv")})))
    state = Memory()
    service = FileDialogs(run, state, lambda: [{"name": "Home", "path": "/home/me", "kind": "home"}])
    import asyncio

    got = asyncio.run(service.choose({"title": "Open file", "suffixes": [".csv"]}))
    assert got == {"path": str(tmp_path / "orders.csv")}
    assert rules.recent(state.data, "file:.csv") == [str(tmp_path)]
    places = service.places("file:.csv")
    assert places[-1] == {"name": str(tmp_path), "path": str(tmp_path), "kind": "recent"}
    assert [p["kind"] for p in service.places("folder")] == ["home"]
    service.remember({"kind": "folder", "path": "/somewhere", "mode": "folder"})
    assert rules.recent(state.data, "folder") == ["/somewhere"]


# ===== the door =====


def door(answer: Any, platform: str = "win32", env: dict[str, str] | None = None) -> TestClient:
    run, _ = runner(answer, platform, env)
    return TestClient(Starlette(routes=guarded(routes_file_dialogs.routes(FileDialogs(run, Memory())))))


def test_the_agent_is_refused_and_the_user_gets_the_path() -> None:
    client = door((0, json.dumps({"path": "C:\\Data\\orders.csv"})))
    body = {"mode": "file", "title": "Open file"}
    assert client.post("/dialogs/choose", json=body, headers={"X-Actor": "agent"}).status_code == 403
    assert client.post("/dialogs/choose", json=body).json() == {"path": "C:\\Data\\orders.csv"}
    assert client.get("/dialogs").json() == {"system": True, "tool": "tk"}
    assert client.post("/dialogs/choose", json={"mode": "x"}).status_code == 400


def test_no_display_answers_unavailable_so_the_page_falls_back() -> None:
    client = door((0, "/x"), platform="linux", env={})
    assert client.get("/dialogs").json()["system"] is False
    assert "unavailable" in client.post("/dialogs/choose", json={"title": "Open"}).json()


def test_the_app_has_system_dialogs_off_in_tests_and_refuses_the_agent(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        status = client.get("/dialogs", headers=AUTH).json()
        assert status["system"] is False and "turned off" in status["reason"]
        assert client.post("/dialogs/choose", json={"title": "x"}, headers=AGENT).status_code == 403
        assert client.post("/dialogs/choose", json={"title": "x"}, headers=AUTH).json()["unavailable"]
        assert client.post("/dialogs/choose", json={"title": "x"}).status_code in (401, 403)


# ===== the page's own picker: places, recent, New folder, hidden =====


def test_the_page_picker_lists_places_recent_new_folder_and_hidden(tmp_path: Path) -> None:
    root = tmp_path / "work"
    (root / "data").mkdir(parents=True)
    (root / ".secret").mkdir()
    (root / "orders.csv").write_text("a\n1\n", encoding="utf-8")
    (tmp_path / "home" / "Swiss Army Bench Projects").mkdir(parents=True)
    with make_client(tmp_path) as client:
        listed = client.get("/folders", params={"path": str(root), "kind": "file:.csv"}, headers=AUTH).json()
        assert [f["name"] for f in listed["folders"]] == ["data"] and "modified" in listed["folders"][0]
        kinds = [p["kind"] for p in listed["places"]]
        assert kinds[0] == "home"
        assert "projects" in kinds
        hidden = client.get("/folders", params={"path": str(root), "hidden": "1"}, headers=AUTH).json()
        assert [f["name"] for f in hidden["folders"]] == [".secret", "data"] and "places" not in hidden
        made = client.post("/folders/new", json={"path": str(root), "name": "Q3 reports"}, headers=AUTH)
        assert made.json() == {"path": str(root / "Q3 reports")} and (root / "Q3 reports").is_dir()
        again = client.post("/folders/new", json={"path": str(root), "name": "Q3 reports"}, headers=AUTH)
        assert again.status_code == 409
        for bad in ("a/b", "..", "con", "x:y", ""):
            response = client.post("/folders/new", json={"path": str(root), "name": bad}, headers=AUTH)
            assert response.status_code == 400, bad
        client.post(
            "/dialogs/recent",
            json={"kind": "file:.csv", "path": str(root / "orders.csv"), "mode": "file"},
            headers=AUTH,
        )
        again_listed = client.get(
            "/folders", params={"path": str(root), "kind": "file:.csv"}, headers=AUTH
        ).json()
        assert {"name": str(root), "path": str(root), "kind": "recent"} in again_listed["places"]
        other = client.get("/folders", params={"path": str(root), "kind": "folder"}, headers=AUTH).json()
        assert all(p["kind"] != "recent" for p in other["places"])
        saved = json.loads((tmp_path / "state" / "dialogs.json").read_text(encoding="utf-8"))
        assert saved == {"recent": {"file:.csv": [str(root)]}}


def test_every_pick_in_the_page_goes_through_choose_file() -> None:
    """One door for every path the user picks: only fileChooser.ts lists folders or asks for a system dialog,
    and it asks for the system's own first; the callers (Open file, projects, the Workbench, Settings, Add
    API, connections, imports, exports) all import chooseFile from it."""
    web = Path(__file__).resolve().parents[1] / "web" / "src"
    sources = {p.name: p.read_text(encoding="utf-8") for p in web.rglob("*.ts")}
    doors = ('"/folders', "`/folders", "/dialogs/choose")
    assert [n for n, s in sources.items() if any(d in s for d in doors)] == ["fileChooser.ts"]
    chooser = sources["fileChooser.ts"]
    assert chooser.index('"/dialogs/choose"') < chooser.index("return choosePage(options)")
    callers = sorted(n for n, s in sources.items() if "chooseFile(" in s and n != "fileChooser.ts")
    assert len(callers) >= 15
    for name in callers:
        assert 'import { chooseFile } from "./fileChooser"' in sources[name], name
