"""Every feature is built in (the owner, 2026-11-27: "Also I think all extensions should be built in now",
merged into the one package, with no Remove): the six that were packages of their own are always on, one wheel
holds them, nothing of them is installed or removed, and the Extensions page lists the user's own folder
extensions (and a built-in feature's own panel). The folder extension "ledger" is made up."""

from __future__ import annotations

import asyncio
import re
import tomllib
from pathlib import Path
from typing import Any, cast

import pytest

from swissarmybench import extensions as loader
from swissarmybench.adapters.extensions import built_in
from swissarmybench.cli.commands import REGISTRY, CommandError, execute_result
from swissarmybench.domain import extensions as rules
from swissarmybench.domain.extensions import BuiltIn, Found
from swissarmybench.services.agent import Approvals
from swissarmybench.services.extensions import Extensions
from swissarmybench.services.workspace import Conflict, NotFound
from tests.conftest import AGENT, AUTH, make_client

ROOT = Path(__file__).resolve().parents[1]
SIX = ["accounting", "copilot", "git", "powerapps", "powerbi", "streamlit"]
FEATURES = (
    BuiltIn("streamlit", "Streamlit", "Apps from widgets."),
    BuiltIn("copilot", "GitHub Copilot", "Ghost text.", ("Sign in with GitHub",), "/copilot/panel"),
)
LEDGER = Found("ledger", "0.1", "Ledger", "A made-up ledger.", ("Ledger pages",), path="/library/ledger")


# ===== always on =====


def test_the_six_are_built_in_and_always_on() -> None:
    assert sorted(loader.BUILT_IN) == SIX
    assert [loader.manifest(m).ID.lower() for m in loader.built_in()] == list(loader.BUILT_IN)  # each imports
    assert all(loader.extension_on(i) and loader.load(i) is not None for i in SIX)
    assert not loader.extension_on("ledger") and loader.load("ledger") is None
    assert [m.__name__ for m in loader.enabled()] == list(loader.BUILT_IN.values())


def test_no_switch_turns_one_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """SWISSARMYBENCH_EXTENSIONS turned an extension on or off before they were built in: it is not read."""
    monkeypatch.setenv("SWISSARMYBENCH_EXTENSIONS", "-streamlit,-git")
    assert loader.extension_on("streamlit") and len(loader.enabled()) == len(SIX)
    assert "SWISSARMYBENCH_EXTENSIONS" not in (ROOT / "src/swissarmybench/extensions.py").read_text()


def test_every_project_type_and_rail_area_is_there() -> None:
    types = [m["type"] for m in loader.modes()]
    assert types == ["bi", "streamlit", "accounting", "codeapp", "powerbi"]
    assert [(a["area"], a["name"]) for a in loader.areas()] == [("scm", "Git"), ("powerbi", "Power BI")]


def test_every_features_commands_are_the_agents() -> None:
    prefixes = ("canvas_", "widgets_", "workbook_", "powerapps_", "powerbi_", "github_", "scm_", "copilot_")
    for prefix in prefixes:
        assert any(name.startswith(prefix) for name in REGISTRY), prefix
    assert len(REGISTRY) == 477  # the base's 375 and every feature's: what every extension on gave before


# ===== one wheel =====


def test_one_wheel_holds_every_package() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    packages = project["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    homes = sorted(p.name for p in (ROOT / "src").iterdir() if (p / "__init__.py").is_file())
    assert sorted(Path(p).name for p in packages) == homes
    assert homes == ["swissarmybench", *(f"swissarmybench_{i}" for i in SIX)]
    assert not (ROOT / "extensions").exists()
    assert not list((ROOT / "src").rglob("pyproject.toml"))
    assert "entry-points" not in (ROOT / "pyproject.toml").read_text()
    # Power BI's two packages are the app's now; the plain install still needs nothing.
    server = project["project"]["optional-dependencies"]["server"]
    assert "pbixray==0.15.5" in server and "pythonnet==3.0.5; sys_platform == 'win32'" in server
    assert project["project"]["dependencies"] == []


def test_every_package_is_on_the_apps_version() -> None:
    base = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    for ident in SIX:
        init = (ROOT / "src" / f"swissarmybench_{ident}" / "__init__.py").read_text()
        assert re.search(rf'__version__(: str)? = "{re.escape(base)}"', init), ident


def test_the_installers_install_the_one_wheel() -> None:
    for name in ("install.sh", "install.ps1"):
        text = (ROOT / "installer" / name).read_text(encoding="utf-8")
        assert "--with" not in text and "streamlit" not in text.lower(), name
    build = (ROOT / "build.py").read_text(encoding="utf-8")
    assert 'glob("*/pyproject.toml")' not in build


def test_an_older_installs_update_still_finds_each_packages_name(tmp_path: Path, monkeypatch: Any) -> None:
    """An install of 0.0.42 or older updates with its own updater, which asks for each installed extension's
    wheel at the new version: build.py makes an empty one of each name (no code, the app its only need)."""
    import importlib.util
    import zipfile

    spec = importlib.util.spec_from_file_location("sab_build", ROOT / "build.py")
    assert spec is not None and spec.loader is not None
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    monkeypatch.setattr(build, "HERE", tmp_path)
    (tmp_path / "dist").mkdir()
    made = build.transition_wheels("9.9.9")
    assert [p.name for p in made] == [f"swissarmybench_{i}-9.9.9-py3-none-any.whl" for i in SIX]
    with zipfile.ZipFile(made[-1]) as wheel:
        names = wheel.namelist()
        said = wheel.read("swissarmybench_streamlit-9.9.9.dist-info/METADATA").decode()
    assert all(n.startswith("swissarmybench_streamlit-9.9.9.dist-info/") for n in names)  # no code
    assert "Name: swissarmybench-streamlit\n" in said
    assert "Requires-Dist: swissarmybench[server]==9.9.9\n" in said


# ===== the Extensions page =====


def test_the_page_lists_folder_extensions_and_a_built_in_panel() -> None:
    listed = rules.listed(FEATURES, {"ledger": LEDGER}, "1.2.3")
    assert [(e["id"], e["status"]) for e in listed] == [("copilot", "builtin"), ("ledger", "installed")]
    copilot, ledger = listed
    assert copilot["panel"] == "/copilot/panel" and copilot["version"] == "1.2.3"
    assert "source" not in copilot and "preinstalled" not in copilot
    assert ledger["source"] == "folder" and ledger["on"] is True and ledger["path"] == "/library/ledger"
    assert rules.listed(FEATURES, {}, "1.2.3")[0]["name"] == "GitHub Copilot"
    assert rules.listed((FEATURES[0],), {}, "1.2.3") == []  # no panel, no card: nothing to do on it


def test_the_apps_own_features_say_what_they_are() -> None:
    found = {f.id: f for f in built_in()}
    assert list(found) == list(loader.BUILT_IN) and all(f.name for f in found.values())
    assert [f.id for f in found.values() if f.panel] == ["copilot"]
    assert found["copilot"].panel == "/copilot/panel"


class Fakes(Approvals):
    def __init__(self) -> None:
        self.asked: list[tuple[str, str, str]] = []

    async def ask(self, dataset: str, action: str, detail: str) -> bool:
        self.asked.append((dataset, action, detail))
        return True

    async def broadcast(self, message: dict[str, Any]) -> None:
        pass

    def write(self, who: str, action: str, dataset: str | None, **details: Any) -> None:
        pass


def made(fakes: Fakes) -> Extensions:
    return Extensions(
        current="1.2.3",
        built_in=FEATURES,
        approvals=cast(Any, fakes),
        audit=cast(Any, fakes),
        live=cast(Any, fakes),
    )


def test_a_built_in_feature_is_never_installed_or_removed() -> None:
    fakes = Fakes()
    extensions = made(fakes)
    assert extensions.state() == {"extensions": rules.listed(FEATURES, {}, "1.2.3")}
    assert extensions.names() == []
    for who in ("user", "agent"):
        with pytest.raises(Conflict, match=r"^Streamlit is built in: .* nothing to install\.$"):
            asyncio.run(extensions.install({"id": "streamlit"}, who))
        with pytest.raises(Conflict, match=r"^GitHub Copilot is built in: .* cannot be removed\.$"):
            asyncio.run(extensions.remove({"id": "copilot", "confirmed": True}, who))
    assert fakes.asked == []  # no Allow asked for: nothing would happen
    with pytest.raises(NotFound, match="no extension 'nope'"):
        asyncio.run(extensions.remove({"id": "nope"}, "user"))
    with pytest.raises(NotFound, match="Only a folder extension"):
        extensions.show({"id": "streamlit"}, "user")
    with pytest.raises(ValueError, match="streamlit"):  # New extension never takes a built-in feature's id
        asyncio.run(extensions.new({"id": "streamlit"}, "user"))


# ===== the routes and the agent =====


def test_the_routes_list_and_say_built_in(tmp_path: Path) -> None:
    with make_client(tmp_path, update_feeds=()) as client:
        said = client.get("/extensions", headers=AUTH).json()
        assert list(said) == ["extensions"]  # no installable, no change under way
        assert [(e["id"], e["status"]) for e in said["extensions"]] == [("copilot", "builtin")]
        for ident in SIX:
            refused = client.post("/extensions/install", headers=AGENT, json={"id": ident})
            assert refused.status_code == 409 and "is built in" in refused.json()["error"], ident
            refused = client.post("/extensions/remove", headers=AUTH, json={"id": ident, "confirmed": True})
            assert refused.status_code == 409 and "cannot be removed" in refused.json()["error"], ident
        assert client.post("/extensions/remove", headers=AUTH, json={"id": "nope"}).status_code == 404
        assert client.get("/extensions").status_code == 401  # the token, as on every route
        # Each feature's door answers (none says "not installed here").
        modes = [m["type"] for m in client.get("/app/modes", headers=AUTH).json()["modes"]]
        assert modes == ["bi", "streamlit", "accounting", "codeapp", "powerbi"]
        areas = [a["area"] for a in client.get("/app/areas", headers=AUTH).json()["areas"]]
        assert areas == ["scm", "powerbi"]
        assert client.get("/streamlit/canvases", headers=AUTH).status_code == 200
        assert client.get("/copilot/panel", headers=AUTH).status_code == 200
        assert client.get("/git/mark", headers=AUTH).status_code == 200


def test_a_command_that_is_none_says_so_and_names_no_extension() -> None:
    with pytest.raises(CommandError, match=r"^No command 'ledger_post'"):
        execute_result("ledger_post", {})
