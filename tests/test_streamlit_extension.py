"""Streamlit, built in (the owner, 2026-11-27; a preinstalled extension of its own package before): its package
sits in the one wheel and declares what it adds like the others, the BI project still has its canvas, its tools
are always the agent's, and the installers install the one wheel. The package keeps the layers. Made-up data
only."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from starlette.testclient import TestClient

from swissarmybench import extensions
from tests.conftest import AUTH

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "swissarmybench_streamlit"


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
    assert extensions.manifest(extension).NAME == "Streamlit"


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


# Its layers (domain, services, adapters, the base knowing none of it) are held with every other extension's:
# tests/test_extension_layers.py.


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
    assert modes[0]["type"] == "bi" and modes[0]["canvases"] == ["streamlit"]
    assert "streamlit" in [m["type"] for m in modes]
    made = client.post("/projects", json={"folder": str(tmp_path), "name": "Orchard"}, headers=AUTH).json()
    folder = Path(made["folder"])
    assert [p.name for p in folder.glob("*.canvas.json")] == ["orchard.canvas.json"]
    assert not (folder / ".sab" / "project.json").exists()
    (listed_canvas,) = client.get(f"/streamlit/canvases?folder={folder}", headers=AUTH).json()["canvases"]
    assert listed_canvas["name"] == "orchard" and listed_canvas["path"] == str(folder / "orchard.canvas.json")
    # Its card's facts ride along (the Canvas landing page's cards).
    assert listed_canvas["pages"] == 1 and listed_canvas["layouts"] == ["desktop", "phone"]
    # Built in: nothing of it is listed to install or remove.
    listed = {e["id"]: e for e in client.get("/extensions", headers=AUTH).json()["extensions"]}
    assert "streamlit" not in listed


# ===== built in: no switch, its tools always the agent's =====


def test_its_tools_are_always_the_agents() -> None:
    """A fresh `sab` (the MCP server's registry) has its tools, whatever the old switch says."""
    code = (
        "from swissarmybench.cli import commands as c\n"
        "print(sorted(n for n in c.REGISTRY if n.startswith(('canvas_', 'widgets_')))[:2])\n"
    )
    env = os.environ | {"SWISSARMYBENCH_EXTENSIONS": "-streamlit"}
    said = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    assert "canvas_" in said.stdout and said.stdout.strip() != "[]"


def test_the_base_mode_takes_what_an_on_extension_adds() -> None:
    class Module:
        BASE_MODE_ADDS = {"canvases": ["streamlit"], "nonsense": ["x"]}

    mode = extensions.base_mode(cast(Any, [Module()]))
    assert mode["canvases"] == ["streamlit"] and "nonsense" not in mode
    assert extensions.base_mode([])["canvases"] == [] == extensions.BASE_MODE["canvases"]


# ===== the installers: one wheel =====


@pytest.mark.skipif(sys.platform == "win32", reason="sh")
def test_install_sh_installs_the_one_wheel(tmp_path: Path) -> None:
    """install.sh with a made-up uv on PATH: the command it runs is the app's wheel alone (Streamlit is in
    it), whatever sits beside it."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "uv.log"
    (bin_dir / "uv").write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n', encoding="utf-8")
    (bin_dir / "uv").chmod(0o755)
    script = (ROOT / "installer" / "install.sh").read_text(encoding="utf-8").replace("__VERSION__", "9.9.9")
    (tmp_path / "install.sh").write_text(script, encoding="utf-8")
    wheel = tmp_path / "swissarmybench-9.9.9-py3-none-any.whl"
    wheel.write_bytes(b"made up")
    (tmp_path / "swissarmybench_streamlit-9.9.9-py3-none-any.whl").write_bytes(b"made up")
    env = os.environ | {
        "PATH": f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "HOME": str(tmp_path),
        "CI": "1",
    }
    done = subprocess.run(
        ["sh", str(tmp_path / "install.sh"), str(wheel), "--no-autostart", "--no-start"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    installs = [line for line in log.read_text().splitlines() if line.startswith("tool install")]
    assert installs[0] == f"tool install --force --python 3.12 {wheel}[server]"
    assert "Streamlit" not in done.stdout
