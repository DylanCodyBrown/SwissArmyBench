"""What a blade's save may change (the craft review's item 7, 2026-11-22): the rules as pure functions in
domain/blade_tables.py, one sentence each, and the store's write paths (Properties' set_header, the IDE's
set_code, save) asking them the same way. A rename moves the saved secrets by one rule on both paths: a secret
the renamed blade still names follows it; one another blade still reads under the old name stays there."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from swissarmybench.adapters.blades import KEYRING_SERVICE, BladeSecrets, BladeStore
from swissarmybench.domain import blades as rules
from swissarmybench.domain.blade_tables import (
    SecretsMove,
    may_change,
    may_take,
    name_taken,
    secret_blade_no_code,
    secrets_after_rename,
    starter_read_only,
)
from swissarmybench.domain.blades import BladeError
from tests.fake_keyring import MemoryKeyring, memory_keyring

CODE = "password = secret('password')\ntoken = secret('token')\n"

# ===== the rules =====


def test_one_sentence_each() -> None:
    assert (
        starter_read_only("Excel")
        == "Excel is a starter (read-only): Copy as your own (blades_copy) to change it."
    )
    assert (
        secret_blade_no_code("Keys") == "Keys is a secret blade: it has no code, only its variables' names."
    )
    assert name_taken("Bakery") == "A blade named 'Bakery' already exists. Pick another name."


def test_what_may_change() -> None:
    may_change("Mine", None, "other", code=True)
    may_change("Keys", None, "secret")  # its header may change, its code may not
    with pytest.raises(BladeError, match=r"^Keys is a secret blade"):
        may_change("Keys", None, "secret", code=True)
    with pytest.raises(BladeError, match=r"^Excel is a starter \(read-only\)"):
        may_change("Excel", rules.STARTERS, "other")
    may_take("New name", None)
    with pytest.raises(BladeError, match="A blade named 'Bakery' already exists"):
        may_take("bakery", "Bakery")


def test_secrets_after_a_rename() -> None:
    # Named still: it follows. Named no more: removed. Read by a blade that keeps the old name: kept there.
    assert secrets_after_rename(["password", "token"], ["password"]) == SecretsMove(
        follow=("password",), drop=("password", "token")
    )
    assert secrets_after_rename(["password", "token"], ["password", "token"], still_read=["token"]) == (
        SecretsMove(follow=("password", "token"), drop=("password",))
    )
    assert secrets_after_rename([], ["password"]) == SecretsMove((), ())


# ===== the store's paths, the same =====


def _rename_by_header(store: BladeStore, old: str, new: str, code: str) -> None:
    store.set_header(old, {"name": new})


def _rename_by_save(store: BladeStore, old: str, new: str, code: str) -> None:
    store.save({"name": new, "kind": "other", "code": code}, previous_name=old)


PATHS = [pytest.param(_rename_by_header, id="properties"), pytest.param(_rename_by_save, id="save")]
Rename = Callable[[BladeStore, str, str, str], None]


def _saved(vault: MemoryKeyring) -> dict[str, str]:
    return {user: value for (service, user), value in vault.values.items() if service == KEYRING_SERVICE}


@pytest.mark.parametrize("rename", PATHS)
def test_a_rename_moves_its_secrets_the_same_way_on_both_paths(tmp_path: Path, rename: Rename) -> None:
    with memory_keyring() as vault:
        store = BladeStore(tmp_path / "library")
        store.save({"name": "Bakery", "kind": "other", "code": CODE})
        store.set_secrets("Bakery", {"password": "made-up-1", "token": "made-up-2"})
        rename(store, "Bakery", "Cakes", CODE)
        assert _saved(vault) == {"blade/cakes/password": "made-up-1", "blade/cakes/token": "made-up-2"}
        assert store.secret_status("Cakes") == {"password": True, "token": True}


def test_a_secret_the_renamed_code_no_longer_names_goes(tmp_path: Path) -> None:
    with memory_keyring() as vault:
        store = BladeStore(tmp_path / "library")
        store.save({"name": "Bakery", "kind": "other", "code": CODE})
        store.set_secrets("Bakery", {"password": "made-up-1", "token": "made-up-2"})
        store.save({"name": "Cakes", "kind": "other", "code": "password = secret('password')\n"}, "Bakery")
        assert _saved(vault) == {"blade/cakes/password": "made-up-1"}


@pytest.mark.parametrize("rename", PATHS)
def test_a_secret_another_blade_still_reads_is_never_lost(tmp_path: Path, rename: Rename) -> None:
    """A saved blade shadows a blade folder's of the same name (a saved one comes first). Renaming the saved
    one shows the folder's again, and it reads the same keyring entries: they stay, and the renamed one
    takes copies."""
    folder = tmp_path / "team blades"
    folder.mkdir()
    shared = {"name": "Bakery", "kind": "other", "code": "password = secret('password')\n"}
    (folder / "bakery.blade.py").write_text(rules.write_blade(shared), encoding="utf-8")
    with memory_keyring() as vault:
        store = BladeStore(tmp_path / "library", folders_file=tmp_path / "folders.json")
        store.save({"name": "Bakery", "kind": "other", "code": CODE})
        store.set_folders([str(folder)])  # a team's folder added later, with a blade of the same name
        assert store.get("Bakery").path is None  # the saved one first
        store.set_secrets("Bakery", {"password": "made-up-1", "token": "made-up-2"})
        rename(store, "Bakery", "Cakes", CODE)
        assert store.get("Bakery").path == str(folder / "bakery.blade.py")
        assert _saved(vault) == {
            "blade/bakery/password": "made-up-1",  # the folder's blade still reads it
            "blade/cakes/password": "made-up-1",
            "blade/cakes/token": "made-up-2",
        }
        assert store.secret_status("Bakery") == {"password": True}


@pytest.mark.parametrize("rename", PATHS)
def test_a_rename_onto_a_taken_name_says_one_sentence(tmp_path: Path, rename: Rename) -> None:
    with memory_keyring():
        store = BladeStore(tmp_path / "library")
        store.save({"name": "Bakery", "kind": "other", "code": CODE})
        store.save({"name": "Cakes", "kind": "other", "code": "x = 1\n"})
        with pytest.raises(BladeError) as said:
            rename(store, "Bakery", "cakes", CODE)
        assert str(said.value) == name_taken("Cakes")


def test_a_starter_is_read_only_on_every_path(tmp_path: Path) -> None:
    starters = tmp_path / "starters"
    starters.mkdir()
    (starters / "excel.blade.py").write_text(
        rules.write_blade({"name": "Excel", "kind": "other", "code": "x = 1\n"}), encoding="utf-8"
    )
    store = BladeStore(tmp_path / "library", starters=starters)
    said = []
    changes: list[Callable[[], object]] = [
        lambda: store.set_header("Excel", {"description": "mine"}),
        lambda: store.set_code("Excel", "x = 2\n"),
        lambda: store.save({"name": "Excel", "kind": "other", "code": "x = 2\n"}, previous_name="Excel"),
    ]
    for change in changes:
        with pytest.raises(BladeError) as refused:
            change()
        said.append(str(refused.value))
    assert said == [starter_read_only("Excel")] * 3


def test_a_secret_blade_takes_no_code(tmp_path: Path) -> None:
    store = BladeStore(tmp_path / "library")
    store.save({"name": "Keys", "kind": "secret", "env_names": ["MY_KEY"]})
    with pytest.raises(BladeError) as refused:
        store.set_code("Keys", "x = 1\n")
    assert str(refused.value) == secret_blade_no_code("Keys")


def test_the_secrets_half_on_its_own() -> None:
    with memory_keyring() as vault:
        secrets = BladeSecrets(BladeSecrets.system_keyring)
        secrets.set("Bakery", "password", "made-up")
        assert secrets.status("Bakery", ["password", "token"]) == {"password": True, "token": False}
        secrets.move("Bakery", "Cakes", SecretsMove(follow=("password",), drop=("password",)))
        assert _saved(vault) == {"blade/cakes/password": "made-up"}
        assert secrets.values("Cakes", ["password"]) == {"password": "made-up"}
        secrets.delete("Cakes", "password")
        secrets.delete("Cakes", "password")  # nothing saved: nothing to forget
        assert _saved(vault) == {}
