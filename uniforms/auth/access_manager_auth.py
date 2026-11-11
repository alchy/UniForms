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
import inspect
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from uniforms import config

logger = logging.getLogger(__name__)

AUTH_SOURCE_LOCAL = "local"
AUTH_SOURCE_AM = "access_manager"
AUTH_SOURCES = (AUTH_SOURCE_LOCAL, AUTH_SOURCE_AM)


@dataclass(frozen=True)
class OtpResult:
    ok: bool
    outcome: str                      # ok | denied | need_factor | throttled | unavailable
    reason: Optional[str] = None      # detail for the audit (None if the service hides it)
    retry_after: Optional[int] = None
    principals: frozenset = frozenset()   # "user:x", "group:admin", … (only when ok)

    def role(self) -> Optional[str]:
        """UniForms system role derived from realm groups; None = no access."""
        s = config.settings
        if f"group:{s.access_manager_admin_group}" in self.principals:
            return "system_admin"
        if f"group:{s.access_manager_user_group}" in self.principals:
            return "system_reader"
        return None


class AccessManagerNotConfigured(RuntimeError):
    pass


def is_configured() -> bool:
    s = config.settings
    return bool((s.access_manager_url and s.access_manager_key)
                or (s.access_manager_home and s.access_manager_realm))


@lru_cache(maxsize=1)
def _access():
    """Build the client once (remote checks API version and realm at startup)."""
    try:
        from access_manager import Access
    except ImportError as exc:  # pragma: no cover
        raise AccessManagerNotConfigured(
            "access-manager client is not installed – pip install -r requirements-access-manager.txt"
        ) from exc
    s = config.settings
    if s.access_manager_home:
        if not s.access_manager_realm:
            raise AccessManagerNotConfigured("ACCESS_MANAGER_HOME requires ACCESS_MANAGER_REALM")
        return Access.local(s.access_manager_home, realm=s.access_manager_realm)
    if s.access_manager_url and s.access_manager_key:
        return Access.remote(
            s.access_manager_url, key=s.access_manager_key,
            realm=s.access_manager_realm or None, ca=s.access_manager_ca or None,
        )
    raise AccessManagerNotConfigured(
        "set ACCESS_MANAGER_URL + ACCESS_MANAGER_KEY (service) or ACCESS_MANAGER_HOME + ACCESS_MANAGER_REALM"
    )


def reset_client() -> None:
    """Forget the cached client (tests, config reload)."""
    _access.cache_clear()


def _authenticate(access, username: str, credentials: dict, **kwargs):
    """Access.authenticate, tolerant to the client's store signature.

    access-manager 0.1.0.dev0: Access.authenticate() always forwards key_id= and
    origin= to the store, but RemoteStore.authenticate() does not accept them →
    TypeError on every remote login. Call the store with only the keyword
    arguments it declares; drop this shim once the library is fixed.
    """
    store = getattr(access, "_store", None)
    if store is None:
        return access.authenticate(username, credentials, **kwargs)
    accepted = inspect.signature(store.authenticate).parameters
    return store.authenticate(
        username, credentials, **{k: v for k, v in kwargs.items() if k in accepted}
    )


def _verify_sync(username: str, code: str, client_origin: Optional[str]) -> OtpResult:
    verdict = _authenticate(
        _access(), username, {"totp": code.strip()}, purpose="login", client_origin=client_origin,
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
