"""A blade's settings found in its code (domain/blade_settings.py)."""

from swissarmybench.domain.blade_settings import detect_settings


def test_a_chained_assignment_is_not_a_setting_and_does_not_hide_the_others() -> None:
    # As the code's first line it used to raise, and the connection showed no settings at all.
    found = detect_settings('host = backup = "db.example.test"\nport = 5432\n')
    names = [s.name for s in found]
    assert "port" in names
    assert "backup" not in names
