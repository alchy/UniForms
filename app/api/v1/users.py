import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# API endpointy pro správu uživatelů aplikace. Vyžadují roli system_admin.
# GET    /users/           – seznam všech uživatelů.
# POST   /users/           – vytvoření nového uživatele.
# PATCH  /users/{username} – změna role, hesla nebo stavu aktivace.
# DELETE /users/{username} – smazání uživatele.
# ---------------------------------------------------------------------------

from app.core.database import get_db
from app.core.security import hash_password, require_admin
from app.models.user import User, UserCreate, UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["Uživatelé"])


# Nacte radek uzivatele z DB podle username; vrati None, pokud neexistuje
async def _get_user_row(db: aiosqlite.Connection, username: str):
    async with db.execute(
        "SELECT id, username, role, is_active, created_at FROM users WHERE username = ?",
        (username,),
    ) as cursor:
        return await cursor.fetchone()


@router.get(
    "/",
    response_model=list[UserResponse],
    summary="Seznam uživatelů (admin)",
)
# Vrati seznam vsech uzivatelu; vyzaduje roli system_admin
async def list_users(
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[UserResponse]:
    async with db.execute(
        "SELECT id, username, role, is_active, created_at FROM users ORDER BY created_at"
    ) as cursor:
        rows = await cursor.fetchall()
    return [UserResponse(**dict(row)) for row in rows]


@router.post(
    "/",
    response_model=UserResponse,
    status_code=201,
    summary="Vytvoření uživatele (admin)",
)
# Vytvori noveho uzivatele s bcrypt heslem; vyzaduje roli system_admin
async def create_user(
    request: UserCreate,
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> UserResponse:
    existing = await _get_user_row(db, request.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Uživatel '{request.username}' již existuje",
        )
    await db.execute(
        "INSERT INTO users (username, hashed_password, role) VALUES (?, ?, ?)",
        (request.username, hash_password(request.password), request.role),
    )
    await db.commit()
    row = await _get_user_row(db, request.username)
    return UserResponse(**dict(row))


@router.get(
    "/{username}",
    response_model=UserResponse,
    summary="Detail uživatele (admin)",
)
# Vrati detail jednoho uzivatele; vyzaduje roli system_admin
async def get_user(
    username: str,
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> UserResponse:
    row = await _get_user_row(db, username)
    if not row:
        raise HTTPException(status_code=404, detail=f"Uživatel '{username}' nenalezen")
    return UserResponse(**dict(row))


@router.patch(
    "/{username}",
    response_model=UserResponse,
    summary="Aktualizace uživatele (admin)",
)
# Aktualizuje roli, stav nebo heslo uzivatele; vyzaduje roli system_admin
async def update_user(
    username: str,
    request: UserUpdate,
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> UserResponse:
    row = await _get_user_row(db, username)
    if not row:
        raise HTTPException(status_code=404, detail=f"Uživatel '{username}' nenalezen")

    if request.role is not None:
        await db.execute("UPDATE users SET role = ? WHERE username = ?", (request.role, username))
    if request.is_active is not None:
        await db.execute(
            "UPDATE users SET is_active = ? WHERE username = ?",
            (1 if request.is_active else 0, username),
        )
    if request.password is not None:
        await db.execute(
            "UPDATE users SET hashed_password = ? WHERE username = ?",
            (hash_password(request.password), username),
        )
    await db.commit()
    row = await _get_user_row(db, username)
    return UserResponse(**dict(row))


@router.get(
    "/{username}/collection-roles",
    summary="Collection roles for a user (admin)",
)
# Vrati slovnik {collection_id: role} pro vsechny kolekce, ke kterym ma uzivatel prirazenou roli
async def get_user_collection_roles(
    username: str,
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict[str, str]:
    row = await _get_user_row(db, username)
    if not row:
        raise HTTPException(status_code=404, detail=f"Uživatel '{username}' nenalezen")
    async with db.execute(
        "SELECT collection_id, role FROM collection_roles WHERE username = ?",
        (username,),
    ) as cursor:
        rows = await cursor.fetchall()
    return {r[0]: r[1] for r in rows}


# Model pro hromadnou aktualizaci collection_roles; role null = odebrani prirazeni
class CollectionRolesUpdate(BaseModel):
    roles: dict[str, str | None]  # {collection_id: "collection_admin"|"collection_user"|null → odebrat}


@router.patch(
    "/{username}/collection-roles",
    summary="Update collection roles for a user (admin)",
)
# Upsertuje nebo odebira prirazeni collection_roles pro jednoho uzivatele; vyzaduje system_admin
async def update_user_collection_roles(
    username: str,
    body: CollectionRolesUpdate,
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict[str, str]:
    row = await _get_user_row(db, username)
    if not row:
        raise HTTPException(status_code=404, detail=f"Uživatel '{username}' nenalezen")
    for collection_id, role in body.roles.items():
        if role:
            # Vlozi nebo prepise zaznam v tabulce collection_roles
            await db.execute(
                "INSERT OR REPLACE INTO collection_roles (username, collection_id, role) "
                "VALUES (?, ?, ?)",
                (username, collection_id, role),
            )
        else:
            # Role null = odebrání prirazeni
            await db.execute(
                "DELETE FROM collection_roles WHERE username = ? AND collection_id = ?",
                (username, collection_id),
            )
    await db.commit()
    async with db.execute(
        "SELECT collection_id, role FROM collection_roles WHERE username = ?",
        (username,),
    ) as cursor:
        rows = await cursor.fetchall()
    return {r[0]: r[1] for r in rows}


@router.delete(
    "/{username}",
    status_code=204,
    summary="Smazání uživatele (admin)",
)
# Smaze uzivatele; nelze smazat vlastni ucet; vyzaduje roli system_admin
async def delete_user(
    username: str,
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> None:
    if username == current_user.username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nelze smazat vlastní účet",
        )
    row = await _get_user_row(db, username)
    if not row:
        raise HTTPException(status_code=404, detail=f"Uživatel '{username}' nenalezen")
    await db.execute("DELETE FROM users WHERE username = ?", (username,))
    await db.commit()
