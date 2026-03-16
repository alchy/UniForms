import aiosqlite
from fastapi import Depends, HTTPException, status

# ---------------------------------------------------------------------------
# FastAPI dependencies pro řízení přístupu k jednotlivým kolekcím.
# require_collection_access – povolí přístup system_adminovi nebo uživateli
#   s jakoukoli rolí v dané kolekci (collection_admin nebo collection_user).
# require_collection_admin  – povolí přístup pouze system_adminovi nebo
#   uživateli s rolí collection_admin v dané kolekci.
# collection_id se automaticky rozlišuje z URL path parametru.
# ---------------------------------------------------------------------------

from app.core.database import get_db
from app.core.security import require_auth
from app.models.user import User
from app.services import collection_service


# Povoli pristup uzivateli se system_admin nebo s jakoukoli roli v collection_roles pro danou kolekci
async def require_collection_access(
    collection_id: str,
    current_user: User = Depends(require_auth),
    db: aiosqlite.Connection = Depends(get_db),
) -> User:
    if current_user.role == "system_admin":
        return current_user
    role = await collection_service.get_user_collection_role(
        db, current_user.username, collection_id
    )
    if not role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No access to collection '{collection_id}'",
        )
    return current_user


# Povoli pristup uzivateli se system_admin nebo s roli collection_admin v dane kolekci
async def require_collection_admin(
    collection_id: str,
    current_user: User = Depends(require_auth),
    db: aiosqlite.Connection = Depends(get_db),
) -> User:
    if current_user.role == "system_admin":
        return current_user
    role = await collection_service.get_user_collection_role(
        db, current_user.username, collection_id
    )
    if role != "collection_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Collection admin role required for '{collection_id}'",
        )
    return current_user
