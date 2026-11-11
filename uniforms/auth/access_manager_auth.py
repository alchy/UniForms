"""OTP login through access-manager (github.com/alchy/access-manager).

UniForms keeps its own session (JWT cookie) and its own roles; access-manager
only answers "is this person who they claim to be" for one login attempt:

    verdict = access.authenticate(name, {"totp": code}, purpose="login",
                                  client_origin=ip)

Only outcome "ok" lets the person in. The detailed reason (bad_code, replay,
unknown_user …) goes to the audit trail, never to the login form – the user
always sees one generic message (except "throttled", which says when to retry).

The client library is optional: ``pip install -r requirements-access-manager.txt``.
It is synchronous, so calls run in a worker thread.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from uniforms import config

logger = logging.getLogger(__name__)

AUTH_SOURCE_LOCAL = "local"
AUTH_SOURCE_AM = "access_manager"
AUTH_SOURCES = (AUTH_SOURCE_LOCAL, AUTH_SOURCE_AM)


# ── Effective configuration: GUI (Settings → access-manager, SQLite) over .env ──
# The GUI values live in the settings table under "am.<field>" and are loaded
# into memory at startup and after every save, so the sync code below can read
# them without a DB round-trip. Empty / missing GUI value → .env / default.
FIELDS = {
    "url": "access_manager_url",
    "key": "access_manager_key",
    "realm": "access_manager_realm",
    "ca": "access_manager_ca",
    "home": "access_manager_home",
    "admin_group": "access_manager_admin_group",
    "user_group": "access_manager_user_group",
    "auth_provider": "auth_provider",
}
DB_PREFIX = "am."
_overrides: dict[str, str] = {}


def cfg(name: str) -> str:
    return _overrides.get(name) or getattr(config.settings, FIELDS[name]) or ""


def source(name: str) -> str:
    if _overrides.get(name):
        return "gui"
    return "env" if getattr(config.settings, FIELDS[name]) else "default"


def auth_provider() -> str:
    return cfg("auth_provider") or "simple"


def set_overrides(values: dict[str, str]) -> None:
    """Replace the GUI overrides (keys without prefix) and drop the cached client."""
    global _overrides
    _overrides = {k: v for k, v in values.items() if k in FIELDS and v}
    reset_client()


async def load_overrides(db) -> None:
    async with db.execute("SELECT key, value FROM settings WHERE key LIKE 'am.%'") as cur:
        rows = await cur.fetchall()
    set_overrides({r[0][len(DB_PREFIX):]: r[1] for r in rows})


def key_id_of(key: str) -> str | None:
    """Public part of an application key ("am_k6_<secret>" → "k6"); never the secret."""
    parts = (key or "").split("_")
    return parts[1] if len(parts) >= 3 and parts[0] == "am" else None


@dataclass(frozen=True)
class OtpResult:
    ok: bool
    outcome: str                      # ok | denied | need_factor | throttled | unavailable
    reason: Optional[str] = None      # detail for the audit (None if the service hides it)
    retry_after: Optional[int] = None
    principals: frozenset = frozenset()   # "user:x", "group:admin", … (only when ok)

    def role(self) -> Optional[str]:
        """UniForms system role derived from realm groups; None = no access."""
        if f"group:{cfg('admin_group')}" in self.principals:
            return "system_admin"
        if f"group:{cfg('user_group')}" in self.principals:
            return "system_reader"
        return None


class AccessManagerNotConfigured(RuntimeError):
    pass


def is_configured() -> bool:
    return bool((cfg("url") and cfg("key")) or (cfg("home") and cfg("realm")))


def build_client(url: str = "", key: str = "", realm: str = "", ca: str = "", home: str = ""):
    """Construct an access-manager client. Remote construction already checks the
    API version and that the key belongs to `realm` (fails loudly otherwise)."""
    try:
        from access_manager import Access
    except ImportError as exc:  # pragma: no cover
        raise AccessManagerNotConfigured(
            "access-manager client is not installed – pip install -r requirements-access-manager.txt"
        ) from exc
    if home:
        if not realm:
            raise AccessManagerNotConfigured("ACCESS_MANAGER_HOME requires a realm")
        return Access.local(home, realm=realm)
    if url and key:
        return Access.remote(url, key=key, realm=realm or None, ca=ca or None)
    raise AccessManagerNotConfigured("access-manager server URL and application key are not set")


@lru_cache(maxsize=1)
def _access():
    """The client for the effective configuration, built once."""
    return build_client(cfg("url"), cfg("key"), cfg("realm"), cfg("ca"), cfg("home"))


def reset_client() -> None:
    """Forget the cached client (tests, config reload)."""
    _access.cache_clear()


def _verify_sync(username: str, code: str, client_origin: Optional[str]) -> OtpResult:
    verdict = _access().authenticate(
        username, {"totp": code.strip()}, purpose="login", client_origin=client_origin,
    )
    return OtpResult(
        ok=bool(verdict), outcome=verdict.outcome,
        reason=verdict.reason, retry_after=verdict.retry_after,
        principals=frozenset(verdict.principals or ()),
    )


async def verify_otp(username: str, code: str, client_origin: Optional[str] = None) -> OtpResult:
    """Ask access-manager to verify a TOTP code. Never raises: an unreachable or
    misconfigured service is a refused login ("unavailable"), logged loudly."""
    try:
        return await asyncio.to_thread(_verify_sync, username, code, client_origin)
    except AccessManagerNotConfigured as exc:
        logger.error("access-manager login unavailable: %s", exc)
        return OtpResult(ok=False, outcome="unavailable", reason="not_configured")
    except Exception as exc:
        logger.error("access-manager login failed for %r: %s", username, exc)
        reset_client()  # rebuild on next attempt (service restarted, key rotated …)
        return OtpResult(ok=False, outcome="unavailable", reason=type(exc).__name__)


def role_for_principals(principals) -> Optional[str]:
    """Same mapping as OtpResult.role(), for directory listings."""
    return OtpResult(ok=True, outcome="ok", principals=frozenset(principals)).role()


def _directory_sync() -> list[dict]:
    access = _access()
    out = []
    for name in access.users():
        user = access.user(name)
        if user is None:  # removed between the two calls
            continue
        principals = frozenset(user.principals)
        out.append({
            "username": name,
            "enabled": bool(user.enabled),
            "groups": sorted(p.removeprefix("group:") for p in principals
                             if p.startswith("group:") and p != "group:public"),
            "role": role_for_principals(principals),
        })
    return out


async def realm_directory() -> list[dict]:
    """All realm users with their groups and the UniForms role the groups give.
    Raises AccessManagerNotConfigured / transport errors – the caller reports them."""
    try:
        return await asyncio.to_thread(_directory_sync)
    except AccessManagerNotConfigured:
        raise
    except Exception:
        reset_client()
        raise
