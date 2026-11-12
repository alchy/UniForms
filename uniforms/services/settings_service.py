from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiosqlite

from uniforms.config import settings

# ---------------------------------------------------------------------------
# Služba pro čtení a zápis runtime nastavení uložených v SQLite tabulce settings.
# Klíče: records_dir, schemas_dir, collections_dir, designer_enabled,
# time_zone, date_format, time_format (editovatelné za běhu přes GUI).
# Ostatní nastavení (JWT, hesla, cesty) jsou v .env a vyžadují restart.
# Helpery get_*_dir() jsou jediné místo, kde se runtime cesty rozhodují –
# hodnota z DB má přednost, jinak výchozí z konfigurace.
# ---------------------------------------------------------------------------

async def get_setting(db: aiosqlite.Connection, key: str) -> Optional[str]:
    """Vrátí hodnotu nastavení dle klíče nebo None."""
    async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
        row = await cursor.fetchone()
    return row[0] if row else None


async def set_setting(db: aiosqlite.Connection, key: str, value: str) -> None:
    """Uloží nebo aktualizuje nastavení."""
    await db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    await db.commit()


async def get_all_settings(db: aiosqlite.Connection) -> dict[str, str]:
    """All PUBLIC settings – access-manager configuration (am.*, incl. the
    application key) is excluded and only reachable through its own API."""
    return {k: v for k, v in (await _all_rows(db)).items() if not k.startswith("am.")}


async def _all_rows(db: aiosqlite.Connection) -> dict[str, str]:
    """Vrátí všechna nastavení jako slovník."""
    async with db.execute("SELECT key, value FROM settings") as cursor:
        rows = await cursor.fetchall()
    return {row[0]: row[1] for row in rows}


async def _get_dir(db: aiosqlite.Connection, key: str, default: str) -> Path:
    return Path(await get_setting(db, key) or default)


async def get_records_dir(db: aiosqlite.Connection) -> Path:
    return await _get_dir(db, "records_dir", settings.default_records_dir)


async def get_schemas_dir(db: aiosqlite.Connection) -> Path:
    return await _get_dir(db, "schemas_dir", settings.default_schemas_dir)


async def get_collections_dir(db: aiosqlite.Connection) -> Path:
    return await _get_dir(db, "collections_dir", settings.default_collections_dir)


# ---------------------------------------------------------------------------
# Feature switches (stored as "true" / "false" in the settings table)
# ---------------------------------------------------------------------------

#: Boolean settings and their defaults. Collection Designer is OFF unless enabled
#: in Settings – while off, its pages and API answer 404 as if they did not exist.
BOOL_SETTINGS = {"designer_enabled": False}


async def get_bool_setting(db: aiosqlite.Connection, key: str) -> bool:
    value = await get_setting(db, key)
    return BOOL_SETTINGS.get(key, False) if value is None else value == "true"


async def designer_enabled(db: aiosqlite.Connection) -> bool:
    return await get_bool_setting(db, "designer_enabled")


# ---------------------------------------------------------------------------
# Date & time display (stored in the settings table, editable in Settings)
#
# All instants are STORED in UTC. These settings only decide how they are shown:
# the IANA zone, the date format and 12/24h time. Defaults come from .env
# (TIMEZONE) so an existing deployment keeps its zone until changed in the GUI.
# ---------------------------------------------------------------------------

DATE_FORMATS = ("DD.MM.YYYY", "YYYY-MM-DD", "MM/DD/YYYY", "DD/MM/YYYY")
TIME_FORMATS = ("24h", "12h")
TIME_SETTING_KEYS = ("time_zone", "date_format", "time_format")

# Last known values – Jinja context processors are synchronous, so pages read this
# cache; it is loaded at startup and refreshed whenever the settings change.
_time_cache: dict[str, str] = {}


def time_defaults() -> dict[str, str]:
    return {"time_zone": settings.timezone, "date_format": DATE_FORMATS[0], "time_format": TIME_FORMATS[0]}


def valid_time_zone(name: str) -> bool:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return False
    return bool(name)


def validate_time_setting(key: str, value: str) -> Optional[str]:
    """Return an error message, or None when the value is acceptable."""
    if key == "time_zone" and not valid_time_zone(value):
        return f"Unknown time zone '{value}' – use an IANA name such as Europe/Prague or UTC."
    if key == "date_format" and value not in DATE_FORMATS:
        return f"Date format must be one of: {', '.join(DATE_FORMATS)}."
    if key == "time_format" and value not in TIME_FORMATS:
        return f"Time format must be one of: {', '.join(TIME_FORMATS)}."
    return None


async def load_time_settings(db: aiosqlite.Connection) -> dict[str, str]:
    """Read the date & time settings (falling back to defaults) and refresh the cache."""
    values = time_defaults()
    for key in TIME_SETTING_KEYS:
        stored = await get_setting(db, key)
        if stored and validate_time_setting(key, stored) is None:
            values[key] = stored
    _time_cache.clear()
    _time_cache.update(values)
    return dict(values)


def time_settings() -> dict[str, str]:
    """Cached date & time settings for page rendering (defaults until loaded)."""
    return dict(_time_cache) if _time_cache else time_defaults()
