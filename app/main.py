from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import admin_collections, auth, collection_roles, collections, info, records, settings, templates, users
from app.config import settings as app_settings, uniforms
from app.core.database import init_db
from app.core.security import WebAdminRequired, WebLoginRequired
from app.core.security_middleware import SecurityMiddleware
from app.web import routes as web_routes

# ---------------------------------------------------------------------------
# Vstupní bod aplikace.
# Inicializuje FastAPI instanci, registruje všechny API routery (prefix /api/v1)
# a webové routy pro server-side rendering (Jinja2). Zajišťuje startup databáze,
# připojení statických souborů a přesměrování při chybějícím přihlášení nebo
# nedostatečném oprávnění.
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    await init_db()
    yield


app = FastAPI(
    title=uniforms.app.name,
    version="1.0.0",
    description=f"{uniforms.app.subtitle} – REST API",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(SecurityMiddleware)


@app.exception_handler(WebLoginRequired)
async def web_login_required_handler(request: Request, exc: WebLoginRequired) -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=302)


@app.exception_handler(WebAdminRequired)
async def web_admin_required_handler(request: Request, exc: WebAdminRequired) -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=302)


# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# API v1
_API_V1 = "/api/v1"
app.include_router(auth.router, prefix=_API_V1)
app.include_router(info.router, prefix=_API_V1)
app.include_router(collections.router, prefix=_API_V1)
app.include_router(templates.router, prefix=_API_V1)
app.include_router(records.router, prefix=_API_V1)
app.include_router(collection_roles.router, prefix=_API_V1)
app.include_router(settings.router, prefix=_API_V1)
app.include_router(users.router, prefix=_API_V1)
app.include_router(admin_collections.router, prefix=_API_V1)

# Web routes (Jinja2 server-side rendering)
app.include_router(web_routes.router)
