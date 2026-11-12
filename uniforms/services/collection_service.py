import logging
from pathlib import Path
from typing import Optional

import aiosqlite
import yaml

from uniforms.models.collection import CollectionConfig

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


def parse_collection_yaml(content: str, collection_id: str) -> CollectionConfig:
    """Strictly validate collection YAML before it is written to disk.

    Raises ValueError with a human-readable message. Checks: valid YAML mapping,
    `id` equal to the file name (roles are keyed by id), model validity and
    workflow.initial_state being one of workflow.states.
    """
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML: {exc}")
    if not isinstance(data, dict):
        raise ValueError("Collection YAML must be a mapping")
    data.setdefault("id", collection_id)
    if data["id"] != collection_id:
        raise ValueError(f"Collection id '{data['id']}' must match the file name '{collection_id}'")
    wf = data.get("workflow") or {}
    state_ids = [s.get("id") for s in wf.get("states") or [] if isinstance(s, dict)]
    if state_ids and "initial_state" in wf and wf["initial_state"] not in state_ids:
        raise ValueError(
            f"workflow.initial_state '{wf['initial_state']}' is not one of: {', '.join(state_ids)}"
        )
    try:
        return CollectionConfig(**data)
    except Exception as exc:  # pydantic ValidationError
        raise ValueError(f"Invalid collection: {exc}")


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


# ---------------------------------------------------------------------------
# Ciselniky stanovene aplikaci – pole typu "user" (source: ...)
# ---------------------------------------------------------------------------

# Zdroje hodnot pro pole `type: user`; poradi = poradi v Designeru
USER_SOURCES = ("collection_members", "collection_admin", "collection_user")
DEFAULT_USER_SOURCE = "collection_members"


# Vrati aktivni uzivatele, kteri odpovidaji zdroji pole typu user, jako [{username, role}].
# Kopiruje pravidla require_collection_access / require_collection_admin:
#   collection_members – system_admin + kazdy s roli v kolekci
#   collection_admin   – system_admin + collection_admin
#   collection_user    – jen collection_user
async def get_collection_members(
    db: aiosqlite.Connection,
    collection_id: str,
    source: str = DEFAULT_USER_SOURCE,
) -> list[dict]:
    if source not in USER_SOURCES:
        raise ValueError(f"Unknown user source '{source}' – allowed: {', '.join(USER_SOURCES)}")
    members: dict[str, str] = {}
    if source != "collection_user":
        async with db.execute(
            "SELECT username FROM users WHERE role = 'system_admin' AND is_active = 1"
        ) as cursor:
            for row in await cursor.fetchall():
                members[row[0]] = "system_admin"
    roles = {"collection_members": ("collection_admin", "collection_user"),
             "collection_admin": ("collection_admin",),
             "collection_user": ("collection_user",)}[source]
    async with db.execute(
        "SELECT cr.username, cr.role FROM collection_roles cr "
        "JOIN users u ON u.username = cr.username AND u.is_active = 1 "
        f"WHERE cr.collection_id = ? AND cr.role IN ({','.join('?' * len(roles))})",
        (collection_id, *roles),
    ) as cursor:
        for row in await cursor.fetchall():
            members.setdefault(row[0], row[1])
    return [{"username": u, "role": r} for u, r in sorted(members.items())]
