import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from uniforms import config
from uniforms.config import DEFAULT_ADMIN_PASSWORD, DEFAULT_JWT_SECRET, Settings, UniformsConfig
from uniforms.core.database import init_db
from uniforms.core.security import WebAdminRequired, WebLoginRequired
from uniforms.core.security_middleware import SecurityMiddleware

# ---------------------------------------------------------------------------
# Vstupní bod aplikace / knihovny.
# create_app() je tovární funkce: vytvoří FastAPI instanci, zaregistruje
# API routery (prefix /api/v1), webové routy (Jinja2) a statické soubory.
# Modulová instance `app` slouží pro samostatné spuštění (uvicorn uniforms.main:app);
# hostitelské aplikace volají create_app() – viz README, sekce
# „Použití jako knihovna".
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

_PKG_DIR = Path(__file__).resolve().parent


def _warn_insecure_defaults() -> None:
    """Upozorní do logu na výchozí (nebezpečné) hodnoty konfigurace."""
    if config.settings.jwt_secret_key == DEFAULT_JWT_SECRET:
        logger.warning(
            "JWT_SECRET_KEY is the built-in default – set a strong random key in .env "
            "(openssl rand -hex 32) before exposing the app"
        )
    if config.settings.admin_password == DEFAULT_ADMIN_PASSWORD:
        logger.warning(
            "ADMIN_PASSWORD is the built-in default ('%s') – change it in .env "
            "or via Admin → Users", DEFAULT_ADMIN_PASSWORD,
        )
    if not config.settings.cookie_secure:
        logger.info("COOKIE_SECURE is off – enable it in production behind HTTPS")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    _warn_insecure_defaults()
    await init_db()
    yield


def create_app(
    settings: Optional[Settings] = None,
    uniforms_config: Optional[UniformsConfig] = None,
    *,
    include_web: bool = True,
    docs_url: Optional[str] = "/api/docs",
) -> FastAPI:
    """
    Vytvoří nakonfigurovanou FastAPI aplikaci UniForms.

    settings / uniforms_config – volitelné přepsání globální konfigurace
        (ekvivalent config.configure(); hodí se při embeddingu).
    include_web – False vypne HTML UI (zůstane jen REST API pod /api/v1);
        hostitel pak může UI nahradit vlastním frontendem.
    docs_url – None skryje OpenAPI dokumentaci.
    """
    if settings is not None or uniforms_config is not None:
        config.configure(new_settings=settings, new_uniforms=uniforms_config)

    # Importy routerů až po případné konfiguraci (moduly čtou config při importu)
    from uniforms.api.v1 import (
        admin_collections, auth, collection_roles, collections,
        info, records, settings as settings_api, templates, users,
    )
    from uniforms.web import routes as web_routes

    app = FastAPI(
        title=config.uniforms.app.name,
        version="1.0.0",
        description=f"{config.uniforms.app.subtitle} – REST API",
        lifespan=_lifespan,
        docs_url=docs_url,
        redoc_url="/api/redoc" if docs_url else None,
        openapi_url="/api/openapi.json" if docs_url else None,
    )

    app.add_middleware(SecurityMiddleware)

    @app.exception_handler(WebLoginRequired)
    async def _login_required(request: Request, exc: WebLoginRequired) -> RedirectResponse:
        return RedirectResponse(url="/login", status_code=302)

    @app.exception_handler(WebAdminRequired)
    async def _admin_required(request: Request, exc: WebAdminRequired) -> RedirectResponse:
        return RedirectResponse(url="/dashboard", status_code=302)

    # Staticke soubory jsou soucasti balicku – cesta nezavisi na CWD hostitele
    app.mount("/static", StaticFiles(directory=str(_PKG_DIR / "static")), name="static")

    api_v1 = "/api/v1"
    for router_module in (
        auth, info, collections, templates, records,
        collection_roles, settings_api, users, admin_collections,
    ):
        app.include_router(router_module.router, prefix=api_v1)

    if include_web:
        app.include_router(web_routes.router)

    return app


# Samostatné spuštění: uvicorn uniforms.main:app
app = create_app()
