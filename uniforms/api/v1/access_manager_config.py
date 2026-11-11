import asyncio
import ipaddress
import re
from typing import Literal, Optional
from urllib.parse import urlparse

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from uniforms.auth import access_manager_auth as am
from uniforms.core.database import get_db
from uniforms.core.security import require_admin
from uniforms.models.user import User

# ---------------------------------------------------------------------------
# Napojení na access-manager z GUI (Settings → Access-manager).
#
# Správce sem po instalaci zadá adresu serveru, realm a aplikační klíč, který
# mu vydala konzole access-manageru. UniForms v access-manageru NIC nezakládá
# ani nemění – jen se jím ptá (ověření kódu, adresář uživatelů a skupin).
#
# Hodnoty se ukládají do SQLite (settings, klíče "am.*") a mají přednost před
# .env. Aplikační klíč je jen pro zápis: API ho nikdy nevrací, ukazuje jen, že
# je nastaven, odkud (GUI / .env) a jeho veřejné key_id.
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/admin/access-manager", tags=["Access-manager"])

_PUBLIC = ("url", "realm", "ca", "admin_group", "user_group", "auth_provider")
_REALM_RE = re.compile(r"^[a-z0-9][a-z0-9.@_-]{0,252}$")
_GROUP_RE = re.compile(r"^[a-z0-9][a-z0-9._@-]{0,127}$")


class AmConfigUpdate(BaseModel):
    """Fields left out are unchanged; an empty string removes the GUI value
    (the .env value or the default applies again)."""
    url: Optional[str] = Field(None, max_length=512)
    realm: Optional[str] = Field(None, max_length=253)
    ca: Optional[str] = Field(None, max_length=512)
    admin_group: Optional[str] = Field(None, max_length=128)
    user_group: Optional[str] = Field(None, max_length=128)
    auth_provider: Optional[Literal["", "simple", "access_manager"]] = None
    key: Optional[str] = Field(None, max_length=512)   # write-only; "" removes the GUI key


def _view() -> dict:
    key = am.cfg("key")
    return {
        "configured": am.is_configured(),
        "fields": {f: {"value": am.cfg(f), "source": am.source(f)} for f in _PUBLIC},
        "key": {"set": bool(key), "source": am.source("key") if key else None,
                "key_id": am.key_id_of(key)},
        "local_mode": bool(am.cfg("home")),   # ACCESS_MANAGER_HOME (.env only)
    }


def _validate(body: AmConfigUpdate) -> None:
    if body.url:
        u = urlparse(body.url)
        if u.scheme not in ("https", "http") or not u.hostname:
            raise HTTPException(422, "Server URL must look like https://host[:port]")
        if u.scheme == "http":
            # Same rule as the client library: plain http only on loopback
            try:
                loopback = ipaddress.ip_address(u.hostname).is_loopback
            except ValueError:
                loopback = u.hostname == "localhost"
            if not loopback:
                raise HTTPException(422, "Plain http is allowed only for loopback – use https://")
    if body.realm and not _REALM_RE.match(body.realm.lower()):
        raise HTTPException(422, "Invalid realm name")
    for name in ("admin_group", "user_group"):
        v = getattr(body, name)
        if v and not _GROUP_RE.match(v):
            raise HTTPException(422, f"Invalid group name in {name}")
    if body.key and not am.key_id_of(body.key):
        raise HTTPException(422, "This does not look like an access-manager application key (am_k…_…)")


@router.get("/", summary="access-manager connection settings (system_admin; key never returned)")
async def get_config(current_user: User = Depends(require_admin)) -> dict:
    return _view()


@router.put("/", summary="Save access-manager connection settings (system_admin)")
async def save_config(
    request: Request,
    body: AmConfigUpdate,
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    _validate(body)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("realm"):
        changes["realm"] = changes["realm"].lower()

    # Lock-out guard: "everyone through access-manager" makes local passwords
    # useless – refuse it to an admin who would lose access by saving it.
    if changes.get("auth_provider") == "access_manager":
        async with db.execute(
            "SELECT auth_source FROM users WHERE username = ?", (current_user.username,)
        ) as cur:
            row = await cur.fetchone()
        if not row or row["auth_source"] != "access_manager":
            raise HTTPException(
                409,
                "You are signed in with a local password – switching every login to "
                "access-manager would lock you out. Sign in through access-manager (OTP) "
                "as an admin first, then change the mode.",
            )

    for field, value in changes.items():
        db_key = am.DB_PREFIX + field
        value = (value or "").strip()
        if value:
            await db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (db_key, value),
            )
        else:
            await db.execute("DELETE FROM settings WHERE key = ?", (db_key,))
    await db.commit()
    await am.load_overrides(db)   # also drops the cached client

    # Audit: which fields changed – names only (the key value never)
    request.state.audit = {"changed": sorted(changes)}
    return {"ok": True, "changed": sorted(changes), **_view()}


class AmTestRequest(AmConfigUpdate):
    """Values to try (e.g. not saved yet); missing ones fall back to the effective config."""


@router.post("/test", summary="Test the access-manager connection (system_admin)")
async def test_config(
    body: AmTestRequest,
    current_user: User = Depends(require_admin),
) -> dict:
    _validate(body)
    url = body.url if body.url is not None else am.cfg("url")
    key = body.key or am.cfg("key")
    realm = (body.realm if body.realm is not None else am.cfg("realm")).lower()
    ca = body.ca if body.ca is not None else am.cfg("ca")
    admin_group = body.admin_group or am.cfg("admin_group")
    user_group = body.user_group or am.cfg("user_group")
    home = am.cfg("home") if not body.url else ""

    def probe() -> dict:
        client = am.build_client(url=url, key=key, realm=realm, ca=ca, home=home)
        not_ready = client.ready()
        groups = client.groups()
        users = client.users()
        return {
            "ready": not_ready is None,
            "not_ready_reason": not_ready,
            "users": len(users),
            "groups": groups,
            "missing_groups": [g for g in (admin_group, user_group) if g not in groups],
        }

    try:
        info = await asyncio.wait_for(asyncio.to_thread(probe), timeout=40)
    except am.AccessManagerNotConfigured as exc:
        return {"ok": False, "message": str(exc)}
    except asyncio.TimeoutError:
        return {"ok": False, "message": "access-manager did not answer in time"}
    except Exception as exc:
        # The client raises descriptive errors (wrong realm, bad key, TLS, version)
        return {"ok": False, "message": f"{type(exc).__name__}: {str(exc)[:300]}"}

    ok = info["ready"] and not info["missing_groups"]
    if not info["ready"]:
        msg = f"Connected, but the realm is not ready: {info['not_ready_reason']}"
    elif info["missing_groups"]:
        msg = ("Connected to realm '%s', but these groups do not exist there: %s"
               % (realm, ", ".join(info["missing_groups"])))
    else:
        msg = f"Connected to realm '{realm}': {info['users']} users, groups OK."
    return {"ok": ok, "message": msg, **info, "realm": realm}
