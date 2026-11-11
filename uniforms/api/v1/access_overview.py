import logging

import aiosqlite
from fastapi import APIRouter, Depends

from uniforms import config
from uniforms.auth import access_manager_auth as am
from uniforms.core.database import get_db
from uniforms.core.security import require_admin
from uniforms.models.user import User

# ---------------------------------------------------------------------------
# Přehled přístupu: kdo se do UniForms dostane a v jaké roli – bez ohledu na
# to, kdo je autentizační (heslo / access-manager) a kdo autorizační autorita
# (lokální DB / skupiny realmu). Jen pro system_admin, jen čtení.
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/access", tags=["Uživatelé"])


async def _local_rows(db: aiosqlite.Connection) -> dict[str, dict]:
    async with db.execute(
        "SELECT username, role, is_active, auth_source, created_at FROM users ORDER BY username"
    ) as cur:
        return {r["username"]: dict(r) for r in await cur.fetchall()}


@router.get("/", summary="Effective access overview: local accounts + access-manager realm")
async def access_overview(
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    s = config.settings
    global_am = s.auth_provider == "access_manager"
    rows = await _local_rows(db)

    # ── Local accounts: password login, role from the local DB ────────────
    local = []
    for r in rows.values():
        if r["auth_source"] != "local":
            continue
        if global_am:
            access, reason = None, "password login disabled (AUTH_PROVIDER=access_manager)"
        elif not r["is_active"]:
            access, reason = None, "inactive"
        else:
            access, reason = r["role"], None
        local.append({**r, "is_active": bool(r["is_active"]), "access": access, "reason": reason})

    result = {
        "auth_provider": s.auth_provider,
        "local": local,
        "access_manager": {
            "configured": am.is_configured(),
            "realm": s.access_manager_realm or None,
            "admin_group": s.access_manager_admin_group,
            "user_group": s.access_manager_user_group,
            "error": None,
            "users": [],
        },
    }
    amr = result["access_manager"]
    if not amr["configured"]:
        return result

    try:
        directory = await am.realm_directory()
    except Exception as exc:
        logger.error("access-manager directory unavailable: %s", exc)
        amr["error"] = f"access-manager unavailable: {type(exc).__name__}"
        directory = []

    # ── Realm users: OTP login, role from realm groups ────────────────────
    in_realm = set()
    for d in directory:
        in_realm.add(d["username"])
        row = rows.get(d["username"])
        if row and row["auth_source"] == "local" and not global_am:
            # Local password account shadows the realm identity of the same name
            access, reason = None, "name taken by a local password account"
        elif not d["enabled"]:
            access, reason = None, "disabled in realm"
        elif d["role"] is None:
            access, reason = None, f"not in {s.access_manager_user_group} / {s.access_manager_admin_group}"
        elif row and not row["is_active"]:
            access, reason = None, "blocked locally (inactive)"
        else:
            access, reason = d["role"], None
        amr["users"].append({
            **d,
            "in_realm": True,
            "local": ({"role": row["role"], "is_active": bool(row["is_active"]),
                       "auth_source": row["auth_source"], "created_at": row["created_at"]}
                      if row else None),
            "access": access,
            "reason": reason,
        })

    # ── Local OTP accounts whose identity is gone from the realm ──────────
    if not amr["error"]:
        for r in rows.values():
            if r["auth_source"] == "access_manager" and r["username"] not in in_realm:
                amr["users"].append({
                    "username": r["username"], "enabled": False, "groups": [], "role": None,
                    "in_realm": False,
                    "local": {"role": r["role"], "is_active": bool(r["is_active"]),
                              "auth_source": r["auth_source"], "created_at": r["created_at"]},
                    "access": None, "reason": "not in realm – cannot sign in",
                })
    amr["users"].sort(key=lambda u: u["username"])
    return result
