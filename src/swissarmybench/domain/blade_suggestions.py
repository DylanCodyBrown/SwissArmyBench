"""A blade's settings' suggestions (domain/blades.py's settings): the values the user's other blades use for
the same setting, then the standard environment variables that commonly hold one. Never a password, never a
placeholder. Pure rules: no I/O."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from swissarmybench.domain.blades import BladeCodeError, Setting, detect_settings

# Environment variables that commonly hold a setting, per plain name. Never a password.
ENVIRONMENT: dict[str, tuple[str, ...]] = {
    "server": ("PGHOST", "MYSQL_HOST", "DB_HOST", "DATABASE_HOST", "SQLSERVER_HOST"),
    "port": ("PGPORT", "MYSQL_PORT", "DB_PORT"),
    "database": ("PGDATABASE", "MYSQL_DATABASE", "DB_NAME", "DATABASE_NAME"),
    "user": ("PGUSER", "MYSQL_USER", "DB_USER", "SNOWFLAKE_USER"),
    "account": ("SNOWFLAKE_ACCOUNT",),
    "warehouse": ("SNOWFLAKE_WAREHOUSE",),
    "role": ("SNOWFLAKE_ROLE",),
    "project": ("GOOGLE_CLOUD_PROJECT", "GCLOUD_PROJECT"),
    "region": ("AWS_REGION", "AWS_DEFAULT_REGION"),
    "vault address": ("AZURE_KEY_VAULT_URL", "VAULT_ADDR"),
    "address": ("VAULT_ADDR",),
}


def suggest_settings(
    settings: list[Setting],
    others: Iterable[tuple[str, str, str]],
    environ: Mapping[str, str] | None = None,
) -> list[Setting]:
    """Fill in each setting's suggestions: values the user's other blades use for the same setting
    (`others`: (blade name, dialect, code); the same dialect first, then by how often), then standard
    environment variables. Placeholders are never suggested, and neither is the value already there."""
    env: Mapping[str, str] = {} if environ is None else environ
    seen: dict[str, dict[str, list[tuple[str, str]]]] = {}  # name -> value -> [(blade, dialect)]
    for blade, dialect, code in others:
        try:
            found = detect_settings(code)
        except BladeCodeError:
            continue
        for other in found:
            if other.placeholder or (other.name == other.key and other.where == "name"):
                continue  # a placeholder, or a top-level name only that blade's code knows
            seen.setdefault(other.name, {}).setdefault(str(other.value), []).append((blade, dialect))
    for setting in settings:
        offered: list[dict[str, str]] = []
        current = str(setting.value)
        values = seen.get(setting.name, {})
        for value, users in sorted(values.items(), key=lambda kv: -len(kv[1])):
            if value != current:
                names = sorted({u[0] for u in users})
                offered.append({"value": value, "from": "your blade " + ", ".join(names[:3])})
        for variable in ENVIRONMENT.get(setting.name, ()):
            value = env.get(variable, "").strip()
            if value and value != current and all(o["value"] != value for o in offered) and len(value) < 300:
                offered.append({"value": value, "from": f"environment variable {variable}"})
        setting.suggestions = offered[:8]
    return settings
