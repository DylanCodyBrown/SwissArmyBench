"""The Streamlit extension (the owner, 2026-11-17: "It's not an edition now it's the streamlit extension.
Preinstalled"): its package plugs into the base like the others, the base runs without it (the BI base: no
Apps area, no Streamlit canvas, a plain answer from its tools and its door), with it everything is as before,
the catalog shows it installed (preinstalled) with Remove, every update keeps it and the installers put it in.
The package keeps the layers. Made-up data only."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from starlette.testclient import TestClient

from swissarmybench import extensions
from swissarmybench.domain import extensions as rules
from swissarmybench.domain.extensions import Found
from swissarmybench.domain.updates import install_command
from swissarmybench.services.agent import Approvals
from swissarmybench.services.extensions import Extensions
from tests.conftest import AGENT, AUTH, make_client
from tests.test_architecture import DOMAIN_FORBIDDEN, SERVICES_FORBIDDEN, _imports

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "extensions" / "streamlit" / "src" / "swissarmybench_streamlit"


@pytest.fixture
def base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The BI base alone: the Streamlit extension turned off."""
    monkeypatch.setenv(extensions.VARIABLE, "-streamlit")
    with make_client(tmp_path) as test_client:
        yield test_client


# ===== the package =====


def test_the_extension_says_what_it_is_and_its_mode() -> None:
    from swissarmybench_streamlit import extension

    said = extension.describe()
    assert said["id"] == "streamlit" and said["package"] == "swissarmybench-streamlit"
    mode = said["mode"]
    assert mode["type"] == "streamlit" and mode["canvases"] == ["streamlit"]
    assert mode["families"] == ["Streamlit", "Components", "Controllers", "Text and layout"]
    assert mode["languages"] == ["python"] and mode["tools"] == ["canvas_", "widgets_"]
    assert mode["widget_framework"] == "streamlit"
    # The beginners' words for New project.
    assert all(isinstance(mode[k], str) and mode[k] for k in ("title", "for_whom", "explain", "example"))
    assert rules.describe("streamlit", extension.describe) == Found(
        "streamlit",
        extension.VERSION,
        "Streamlit",
        extension.DESCRIPTION,
        tuple(extension.ADDS),
        "swissarmybench-streamlit",
    )


def test_its_starters_moved_with_it() -> None:
    from swissarmybench_streamlit import extension

    families: dict[str, int] = {}
    for path in Path(extension.STARTERS).glob("*.blade.py"):
        family = next(
            line.split("=", 1)[1].strip().strip('"')
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith("# family = ")
        )
        families[family] = families.get(family, 0) + 1
    assert set(families) == {"Streamlit", "Components", "Controllers", "Text and layout"}
    base = ROOT / "src" / "swissarmybench" / "starters"
    assert not [
        p.name
        for p in base.glob("*.blade.py")
        if any(
            line in p.read_text(encoding="utf-8")
            for line in ('# family = "Streamlit"', '# family = "Components"', '# family = "Controllers"')
        )
    ]


def test_the_package_keeps_the_layers() -> None:
    """Cosmic Python inside the package, as in the base: its domain does no I/O and knows no service, its
    services touch nothing themselves, its adapters do not know its doors; nothing deeper than a folder."""
    assert all(len(p.relative_to(PACKAGE).parts) <= 2 for p in PACKAGE.rglob("*.py"))
    for path in (PACKAGE / "domain").glob("*.py"):
        found = _imports(path)
        assert not {m for m in found if m.split(".")[0] in DOMAIN_FORBIDDEN}, path.name
        assert not [
            m
            for m in found
            if m.startswith(("swissarmybench.", "swissarmybench_streamlit."))
            and m.split(".")[1] not in ("domain",)
        ], path.name
    for path in (PACKAGE / "services").glob("*.py"):
        found = _imports(path)
        assert not {m for m in found if m.split(".")[0] in SERVICES_FORBIDDEN}, path.name
        assert not [
            m
            for m in found
            if m.split(".")[0].startswith("swissarmybench")
            and m.split(".")[1] in ("adapters", "server", "cli")
        ], path.name
    for path in (PACKAGE / "adapters").glob("*.py"):
        assert not [
            m
            for m in _imports(path)
            if m.split(".")[0].startswith("swissarmybench") and m.split(".")[1] == "server"
        ], path.name
    # And the base knows none of it: no module of the base imports the package.
    base = ROOT / "src" / "swissarmybench"
    assert not [
        str(p.relative_to(base))
        for p in base.rglob("*.py")
        if any(m.startswith("swissarmybench_streamlit") for m in _imports(p))
    ]


def test_a_streamlit_project_is_its_scaffold(client: TestClient, tmp_path: Path) -> None:
    made = client.post(
        "/projects", json={"folder": str(tmp_path), "name": "Sales", "type": "streamlit"}, headers=AUTH
    )
    assert made.status_code == 200, made.text
    folder = Path(made.json()["folder"])
    assert json.loads((folder / ".sab" / "project.json").read_text()) == {"type": "streamlit"}
    # data.ipynb and an empty canvas, nothing else (2026-11-21: app notebooks were replaced by widgets).
    assert not (folder / "app.ipynb").exists() and (folder / "data.ipynb").exists()
    assert [p.name for p in folder.glob("*.canvas.json")] == ["sales.canvas.json"]  # one canvas, not two
    assert not list(folder.glob("*.stapp.json"))
    assert "streamlit>=1.43" in (folder / "requirements.txt").read_text()
    mode = client.get("/app/mode", headers=AUTH).json()
    assert mode["project_type"] == "streamlit" and mode["mode"]["families"][0] == "Streamlit"


# ===== with it on: as before =====


def test_on_the_base_project_still_has_its_app_and_the_canvas(client: TestClient, tmp_path: Path) -> None:
    modes = client.get("/app/modes", headers=AUTH).json()["modes"]
    assert [m["type"] for m in modes] == ["bi", "streamlit"] and modes[0]["canvases"] == ["streamlit"]
    made = client.post("/projects", json={"folder": str(tmp_path), "name": "Orchard"}, headers=AUTH).json()
    folder = Path(made["folder"])
    assert [p.name for p in folder.glob("*.canvas.json")] == ["orchard.canvas.json"]
    assert not (folder / ".sab" / "project.json").exists()
    assert client.get(f"/streamlit/canvases?folder={folder}", headers=AUTH).json()["canvases"] == [
        {"name": "orchard", "path": str(folder / "orchard.canvas.json")}
    ]
    listed = {e["id"]: e for e in client.get("/extensions", headers=AUTH).json()["extensions"]}
    assert listed["streamlit"]["status"] == "installed" and listed["streamlit"]["preinstalled"] is True


# ===== the BI base without it =====


def test_off_the_base_has_no_canvas_and_says_which_extension(base: TestClient, tmp_path: Path) -> None:
    modes = base.get("/app/modes", headers=AUTH).json()["modes"]
    assert [m["type"] for m in modes] == ["bi"] and modes[0]["canvases"] == []
    # Its door answers plainly, naming the extension, for the user and the agent alike.
    for headers in (AUTH, AGENT):
        door = base.get("/streamlit/canvases", headers=headers)
        assert door.status_code == 404 and door.json()["extension"] == "streamlit"
        assert "Streamlit extension" in door.json()["error"]
    assert base.post("/streamlit/canvases", headers=AUTH, json={}).status_code == 404
    # A new project is the base's: data and notebooks, no canvas, no Streamlit to install.
    made = base.post("/projects", json={"folder": str(tmp_path), "name": "Orchard"}, headers=AUTH)
    assert made.status_code == 200, made.text
    folder = Path(made.json()["folder"])
    assert not list(folder.glob("*.canvas.json")) and (folder / "data.ipynb").exists()
    assert "streamlit" not in (folder / "requirements.txt").read_text()
    # A Streamlit project is refused plainly.
    refused = base.post(
        "/projects", json={"folder": str(tmp_path), "name": "Sales", "type": "streamlit"}, headers=AUTH
    )
    assert refused.status_code == 400 and "No installed extension makes a streamlit project" in refused.text
    # An app's file says which extension opens it.
    canvas = tmp_path / "old.stapp.json"
    canvas.write_text('{"swissarmybench": "streamlit-app", "version": 1, "pages": []}', encoding="utf-8")
    opened = base.post("/workbench/open", headers=AUTH, json={"path": str(canvas)})
    assert opened.status_code == 404 and "Streamlit extension" in opened.text
    # A notebook opens, its Streamlit-calling cell a plain Python cell (nothing shown live).
    notebook = tmp_path / "plain.ipynb"
    from swissarmybench.domain import notebooks

    notebook.write_text(
        notebooks.write_notebook([notebooks.Cell("code", 'import streamlit as st\nst.write("hi")')])
    )
    cells = base.post("/workbench/open", headers=AUTH, json={"path": str(notebook)}).json()["cells"]
    assert "live" not in cells[0]
    # The Extensions page offers it again (one click: Install).
    listed = {e["id"]: e for e in base.get("/extensions", headers=AUTH).json()["extensions"]}
    assert listed["streamlit"]["status"] == "available" and listed["streamlit"]["preinstalled"] is True


def test_off_the_agents_streamlit_tools_name_the_extension() -> None:
    """A fresh `sab` (the MCP server's registry): its tools are not listed, and a call says where to get them."""
    code = (
        "from swissarmybench.cli import commands as c\n"
        "print(sorted(n for n in c.REGISTRY if n.startswith('canvas_')))\n"
        "try:\n    c.execute('canvas_play', {'canvas': 'a1'})\nexcept c.CommandError as e:\n    print(e)\n"
        "try:\n    c.execute('widgets_list', {})\nexcept c.CommandError as e:\n    print(e)\n"
    )
    env = os.environ | {extensions.VARIABLE: "-streamlit"}
    said = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    lines = said.stdout.splitlines()
    assert lines[0] == "[]"
    assert (
        "canvas_play is the Streamlit extension's" in lines[1]
        and "extensions_install id=streamlit" in lines[1]
    )
    assert "widgets_list is the Streamlit extension's" in lines[2]
    # With it on, the same names are tools.
    on = subprocess.run(
        [sys.executable, "-c", code.split("try:")[0]],
        env=os.environ,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "canvas_play" in on.stdout


def test_the_base_mode_takes_what_an_on_extension_adds() -> None:
    class Module:
        BASE_MODE_ADDS = {"canvases": ["streamlit"], "nonsense": ["x"]}

    mode = extensions.base_mode(cast(Any, [Module()]))
    assert mode["canvases"] == ["streamlit"] and "nonsense" not in mode
    assert extensions.base_mode([])["canvases"] == [] == extensions.BASE_MODE["canvases"]


# ===== preinstalled: the catalog, updates, the installers =====


class Fakes(Approvals):
    def __init__(self) -> None:
        self.changes: list[tuple[list[str], list[str]]] = []
        self.stopped: list[bool] = []
        self.record: Any = None

    def installable(self) -> bool:
        return True

    def launch_change(self, wheels: list[str], before: list[str]) -> None:
        self.changes.append((wheels, before))

    async def ask(self, *_: Any) -> bool:
        return True

    async def broadcast(self, message: dict[str, Any]) -> None:
        pass

    def write(self, *args: Any, **details: Any) -> None:
        if len(args) == 1:  # the record's write
            self.record = args[0]

    def read(self) -> Any:
        return self.record


def service(fakes: Fakes, found: dict[str, Found]) -> Extensions:
    return Extensions(
        current="1.2.3",
        found=found,
        helper=fakes,
        approvals=cast(Any, fakes),
        audit=cast(Any, fakes),
        live=cast(Any, fakes),
        stop=lambda: fakes.stopped.append(True),
        record=fakes,
    )


STREAMLIT_WHEEL = rules.wheel_url("swissarmybench-streamlit", "1.2.3")


def test_an_update_keeps_it_with_its_wheel() -> None:
    kept = service(Fakes(), {"streamlit": Found("streamlit", "1.2.3")})
    assert kept.installed_ids() == ["streamlit"]
    assert kept.kept_wheels("1.3.0") == [rules.wheel_url("swissarmybench-streamlit", "1.3.0")]
    command = install_command("uv", "1.3.0", "pypi", "3.12", wheels=tuple(kept.kept_wheels("1.3.0")))
    assert command[-2:] == ["--with", rules.wheel_url("swissarmybench-streamlit", "1.3.0")]


def test_removed_by_the_user_it_stays_out_and_install_brings_it_back() -> None:
    fakes = Fakes()
    installed = service(fakes, {"streamlit": Found("streamlit", "1.2.3")})
    asked = asyncio.run(installed.remove({"id": "streamlit"}, "user"))
    assert "removes Streamlit" in asked["confirm"] and fakes.changes == []  # asked first

    async def remove() -> dict[str, Any]:
        return await installed.remove({"id": "streamlit", "confirmed": True}, "user")

    assert asyncio.run(remove())["changing"] == {"id": "streamlit", "action": "remove"}
    assert fakes.changes == [([], [STREAMLIT_WHEEL])] and fakes.record["removed"] == ["streamlit"]
    # Started again without it: never brought back by itself, offered on the page.
    after = service(fakes, {})
    assert after.bring_back() is None
    assert {e["id"]: e["status"] for e in after.listing()}["streamlit"] == "available"

    async def install() -> dict[str, Any]:
        return await after.install({"id": "streamlit"}, "user")

    assert asyncio.run(install())["changing"]["action"] == "install"
    assert fakes.changes[-1] == ([STREAMLIT_WHEEL], []) and fakes.record["removed"] == []


def test_an_update_from_a_built_in_version_brings_it_back_once() -> None:
    """0.0.17 had Streamlit built in and knew nothing of the package: the new version's first start installs
    it (the app restarts with it), once a version, never against the user's Remove."""
    fakes = Fakes()

    async def first_start() -> dict[str, Any] | None:
        said = service(fakes, {}).bring_back()
        await asyncio.sleep(0.6)
        return said

    assert asyncio.run(first_start()) == {"id": "streamlit", "action": "install"}
    assert fakes.changes == [([STREAMLIT_WHEEL], [])] and fakes.stopped == [True]
    assert fakes.record["tried"] == {"streamlit": "1.2.3"}
    assert service(fakes, {}).bring_back() is None  # a failed install is not tried again at this version
    assert rules.to_bring_back(rules.CATALOG, {}, fakes.record, "1.2.4")[0].id == "streamlit"
    assert rules.to_bring_back(rules.CATALOG, {}, {"removed": ["streamlit"]}, "1.2.4") == []
    assert rules.to_bring_back(rules.CATALOG, {"streamlit": Found("streamlit")}, None, "1.2.4") == []


def test_the_installers_put_it_in_beside_the_base() -> None:
    sh = (ROOT / "installer" / "install.sh").read_text(encoding="utf-8")
    assert 'STREAMLIT_WHEEL="swissarmybench_streamlit-${VERSION}-py3-none-any.whl"' in sh
    assert 'uv tool install --force --python 3.12 "${wheel_path}[server]" --with "$streamlit_path"' in sh
    assert "releases/download/v$VERSION/$STREAMLIT_WHEEL" in sh
    ps1 = (ROOT / "installer" / "install.ps1").read_text(encoding="utf-8")
    assert '$StreamlitWheelName = "swissarmybench_streamlit-$Version-py3-none-any.whl"' in ps1
    assert 'uv tool install --force --python 3.12 "$WheelPath[server]" --with "$StreamlitPath"' in ps1
    assert (
        rules.wheel_name("swissarmybench-streamlit", "0.0.18")
        == "swissarmybench_streamlit-0.0.18-py3-none-any.whl"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="sh")
def test_install_sh_finds_the_extension_beside_a_wheel(tmp_path: Path) -> None:
    """install.sh with a made-up uv on PATH: the command it runs carries the extension's wheel beside the
    base's, and installs the base alone (said) when none is there."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "uv.log"
    (bin_dir / "uv").write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n', encoding="utf-8")
    (bin_dir / "uv").chmod(0o755)
    script = (ROOT / "installer" / "install.sh").read_text(encoding="utf-8").replace("__VERSION__", "9.9.9")
    (tmp_path / "install.sh").write_text(script, encoding="utf-8")
    wheel = tmp_path / "swissarmybench-9.9.9-py3-none-any.whl"
    wheel.write_bytes(b"made up")
    env = os.environ | {
        "PATH": f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "HOME": str(tmp_path),
        "CI": "1",
    }

    def run() -> tuple[str, str]:
        log.unlink(missing_ok=True)
        done = subprocess.run(
            ["sh", str(tmp_path / "install.sh"), str(wheel), "--no-autostart", "--no-start"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        installs = [line for line in log.read_text().splitlines() if line.startswith("tool install")]
        return installs[0], done.stdout

    alone, said = run()
    assert "--with" not in alone and "without the Streamlit extension" in said
    (tmp_path / "swissarmybench_streamlit-9.9.9-py3-none-any.whl").write_bytes(b"made up")
    both, _ = run()
    assert both.endswith(f"--with {tmp_path / 'swissarmybench_streamlit-9.9.9-py3-none-any.whl'}")
