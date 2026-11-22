"""An extension's manifest (swissarmybench/extensions.py manifest): every module attribute an extension may
declare, read once into one typed record; a misspelt name is reported, never quietly "not there"; and the
extensions keep their own services on their own place of the record (craft review 2026-11-22, item 9)."""

from __future__ import annotations

from types import ModuleType

from swissarmybench import extensions


def _module(**names: object) -> ModuleType:
    module = ModuleType("sab_ext_madeup")
    for name, value in names.items():
        setattr(module, name, value)
    return module


def test_the_manifest_reads_each_name_once_and_reports_a_misspelt_one() -> None:
    module = _module(
        ID="madeup",
        NAME="Made up",
        SECRET_PATH=("/madeup/run/",),
        AREAS=[("madeup", "Made up")],
        STARTERS=None,
    )
    found = extensions.manifest(module)
    assert (found.ID, found.NAME, found.AREAS) == ("madeup", "Made up", (("madeup", "Made up"),))
    assert found.SECRET_PATHS == () and found.STARTERS == ""
    assert found.unknown == ("SECRET_PATH",)
    assert extensions.manifest(module) is found  # read once


def test_each_bundled_extension_s_manifest_names_only_what_it_means() -> None:
    """The extensions on in the tests: each upper-case name the base does not read is one of its own
    constants (used inside it), never a manifest name misspelt."""
    fields = set(extensions.Manifest.__dataclass_fields__)
    for module in extensions.enabled():
        found = extensions.manifest(module)
        assert found.ID, module.__name__
        for name in found.unknown:
            near = [
                f
                for f in fields
                if f.rstrip("S") == name.rstrip("S") or f.replace("_", "") == name.replace("_", "")
            ]
            assert not near, f"{module.__name__}: {name} looks like {near}"
