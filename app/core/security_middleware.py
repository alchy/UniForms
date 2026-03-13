from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# HTTP metody, které nesou tělo a musejí mít správný Content-Type
_BODY_METHODS = {"POST", "PUT", "PATCH"}


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Bezpečnostní middleware – dvě funkce:

    1. Content-Type guard: POST/PUT/PATCH na /api/v1/* musejí
       mít Content-Type: application/json.
       Brání CSRF útokům přes HTML formuláře (ty posílají
       application/x-www-form-urlencoded nebo multipart/form-data).

    2. Security response headers: přidány ke každé odpovědi.
       - X-Content-Type-Options: nosniff  – zabrání MIME-type sniffingu
       - X-Frame-Options: DENY            – zabrání clickjackingu v <iframe>
       - Referrer-Policy                  – omezí únik URL v Referer hlavičce
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # ── Content-Type guard ────────────────────────────────────────────
        if (
            request.url.path.startswith("/api/v1/")
            and request.method in _BODY_METHODS
        ):
            ct = request.headers.get("content-type", "")
            if not ct.startswith("application/json"):
                return JSONResponse(
                    status_code=415,
                    content={"detail": "Content-Type must be application/json"},
                )

        response = await call_next(request)

        # ── Security headers ──────────────────────────────────────────────
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        return response
