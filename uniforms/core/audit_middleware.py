"""ASGI middleware that writes one audit event per state-changing API call.

Every POST/PUT/PATCH/DELETE under /api/v1/ is recorded – including the ones
that were refused (401/403/423/4xx) – so the trail answers "who tried what,
from where, and did it work", without each route having to remember to log.

Routes can enrich or suppress their event through ``request.state``:

    request.state.audit = {"subject": "user:x", "status_to": "closed", …}
    request.state.audit_skip = True      # e.g. lock heartbeat refresh

Only identifiers are logged (path parameters, usernames, field keys) – never
request bodies, passwords, tokens or field values.
"""
from __future__ import annotations

import json
from http.cookies import SimpleCookie

from uniforms import config
from uniforms.core import audit

_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_TARGET_PARAMS = ("collection_id", "record_id", "template_id", "username")
_MAX_ERROR_BODY = 4096


def _outcome(status: int) -> str:
    if status < 400:
        return "ok"
    if status in (401, 403, 423):
        return "denied"
    if status < 500:
        return "rejected"
    return "error"


def _actor_from_cookie(scope) -> str | None:
    # Lazy import: security imports config only, but keep middleware import-light
    from uniforms.core.security import COOKIE_NAME, decode_token

    raw = next((v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"cookie"), "")
    if not raw:
        return None
    try:
        morsel = SimpleCookie(raw).get(COOKIE_NAME)
        return audit.principal(decode_token(morsel.value).sub) if morsel else None
    except Exception:
        return None  # expired / invalid token – the route answers 401 itself


def _error_detail(body: bytes) -> str | None:
    try:
        detail = json.loads(body).get("detail")
    except Exception:
        return None
    if isinstance(detail, dict):
        detail = detail.get("message") or json.dumps(detail, ensure_ascii=False)
    elif isinstance(detail, list):  # pydantic validation errors
        detail = "; ".join(str(d.get("msg", d)) for d in detail[:3] if isinstance(d, dict))
    return str(detail)[:300] if detail else None


class AuditMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] not in _METHODS
            or not scope["path"].startswith("/api/v1/")
        ):
            await self.app(scope, receive, send)
            return

        scope.setdefault("state", {})
        status_code = 500
        error_body = b""

        async def send_wrapper(message):
            nonlocal status_code, error_body
            if message["type"] == "http.response.start":
                status_code = message["status"]
            elif message["type"] == "http.response.body" and status_code >= 400:
                if len(error_body) < _MAX_ERROR_BODY:
                    error_body += message.get("body", b"")[: _MAX_ERROR_BODY - len(error_body)]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            state = scope.get("state", {})
            if not state.get("audit_skip"):
                self._write(scope, state, status_code, error_body)

    @staticmethod
    def _write(scope, state: dict, status_code: int, error_body: bytes) -> None:
        endpoint = scope.get("endpoint")
        op = getattr(endpoint, "__name__", None) or f"{scope['method']} {scope['path']}"
        params = scope.get("path_params") or {}
        event = {
            "kind": "auth" if op in ("login", "logout") else "write",
            "op": op,
            "actor": _actor_from_cookie(scope),
            "origin": (scope.get("client") or (None,))[0],
            "method": scope["method"],
            "path": scope["path"],
            "status": status_code,
            "outcome": _outcome(status_code),
            **{k: params[k] for k in _TARGET_PARAMS if params.get(k)},
            **(state.get("audit") or {}),
        }
        if status_code >= 400:
            event.setdefault("error", _error_detail(error_body))
        audit.append_event(config.settings.audit_dir, event, config.settings.audit_retention_days)
