import logging
from pathlib import Path
from typing import Optional

import aiosqlite
import yaml

from app.models.collection import CollectionConfig

# ---------------------------------------------------------------------------
# Služba pro správu kolekcí.
# Načítá definice kolekcí z YAML souborů v collections_dir, filtruje je dle
# přístupových práv uživatele (system_admin vidí vše, ostatní jen své kolekce)
# a poskytuje funkce pro čtení a zápis rolí uživatelů v kolekcích (SQLite).
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# Nacte jednu kolekci z YAML souboru; vrati None, pokud soubor nelze nacist nebo je prazdny
def _load_collection_from_path(path: Path) -> Optional[CollectionConfig]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not data:
            return None
        data.setdefault("id", path.stem)
        return CollectionConfig(**data)
    except Exception as exc:
        logger.warning("Cannot load collection '%s': %s", path.name, exc)
        return None


# Vrati seznam vsech kolekcí z adresare serazenych podle nazvu
async def list_collections(collections_dir: Path) -> list[CollectionConfig]:
    result = []
    if not collections_dir.exists():
        return result
    for yaml_file in sorted(collections_dir.glob("*.yaml")):
        col = _load_collection_from_path(yaml_file)
        if col:
            result.append(col)
    return result


# Vrati kolekci podle ID, nebo None, pokud soubor neexistuje
async def get_collection(collection_id: str, collections_dir: Path) -> Optional[CollectionConfig]:
    path = collections_dir / f"{collection_id}.yaml"
    if not path.exists():
        return None
    return _load_collection_from_path(path)


# ---------------------------------------------------------------------------
# Sprava collection_roles v SQLite
# ---------------------------------------------------------------------------

# Vrati roli uzivatele v kolekci ('collection_admin' nebo 'collection_user'); None = neni prirazen
async def get_user_collection_role(
    db: aiosqlite.Connection,
    username: str,
    collection_id: str,
) -> Optional[str]:
    async with db.execute(
        "SELECT role FROM collection_roles WHERE username = ? AND collection_id = ?",
        (username, collection_id),
    ) as cursor:
        row = await cursor.fetchone()
    return row[0] if row else None


# Vrati vsechna prirazeni roli pro kolekci jako seznam {username, role}
async def get_collection_roles(
    db: aiosqlite.Connection,
    collection_id: str,
) -> list[dict]:
    async with db.execute(
        "SELECT username, role FROM collection_roles WHERE collection_id = ? ORDER BY username",
        (collection_id,),
    ) as cursor:
        rows = await cursor.fetchall()
    return [{"username": row[0], "role": row[1]} for row in rows]


# Nahradi vsechna prirazeni roli pro kolekci novym seznamem; transakce je atomicka
async def set_collection_roles(
    db: aiosqlite.Connection,
    collection_id: str,
    assignments: list[dict],
) -> None:
    await db.execute(
        "DELETE FROM collection_roles WHERE collection_id = ?",
        (collection_id,),
    )
    for a in assignments:
        await db.execute(
            "INSERT INTO collection_roles (username, collection_id, role) VALUES (?, ?, ?)",
            (a["username"], collection_id, a["role"]),
        )
    await db.commit()


# Vrati kolekce pristupne uzivateli: system_admin vidi vse, ostatni jen prirazene v collection_roles
async def get_accessible_collections(
    db: aiosqlite.Connection,
    username: str,
    global_role: str,
    collections_dir: Path,
) -> list[CollectionConfig]:
    all_collections = await list_collections(collections_dir)
    if global_role == "system_admin":
        return all_collections
    async with db.execute(
        "SELECT collection_id FROM collection_roles WHERE username = ?",
        (username,),
    ) as cursor:
        rows = await cursor.fetchall()
    accessible = {row[0] for row in rows}
    return [c for c in all_collections if c.id in accessible]
