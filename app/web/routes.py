import aiosqlite
import jwt
from pathlib import Path
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import uniforms, settings as app_settings
from app.core.database import get_db
from app.core.security import COOKIE_NAME, WebAdminRequired, WebLoginRequired, decode_token
from app.models.user import TokenPayload
from app.services import collection_service
from app.services.settings_service import get_all_settings, get_setting
from app.services.template_service import TemplateService, get_template_service

router = APIRouter(tags=["Web"])
templates = Jinja2Templates(directory="app/templates")

# Vlozi globalni kontext z uniforms.yaml do vsech Jinja2 sablon
templates.env.globals.update({
    "app_name": uniforms.app.name,
    "app_subtitle": uniforms.app.subtitle,
    "term": uniforms.terminology.model_dump(),
})


# ---------------------------------------------------------------------------
# Pomocne funkce
# ---------------------------------------------------------------------------

# Dekoduje JWT cookie a vrati TokenPayload; vrati None, pokud cookie chybi nebo je neplatna
def _get_user_from_cookie(request: Request) -> TokenPayload | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        return decode_token(token)
    except jwt.PyJWTError:
        return None


# Prevede TokenPayload na slovnik pro Jinja2 kontext
def _user_ctx(user: TokenPayload) -> dict:
    return {"username": user.sub, "role": user.role}


# Vrati terminologii: globalni hodnoty z uniforms.yaml prekryty per-kolekci overrides
def _merge_term(collection=None) -> dict:
    base = uniforms.terminology.model_dump()
    if collection and collection.terminology:
        base.update(collection.terminology)
    return base


# Nacte kolekce pristupne uzivateli pro sidebar; volitelne rozlisi aktualni kolekci
async def _sidebar_ctx(
    db: aiosqlite.Connection,
    user: TokenPayload,
    collection_id: str | None = None,
) -> dict:
    collections_dir = Path(
        await get_setting(db, "collections_dir") or app_settings.default_collections_dir
    )
    accessible = await collection_service.get_accessible_collections(
        db, user.sub, user.role, collections_dir
    )
    ctx: dict = {"accessible_collections": accessible}
    if collection_id:
        collection = next((c for c in accessible if c.id == collection_id), None)
        if collection is None:
            # system_admin muze pristupovat ke kolekci, ktera neni ve filtrovane liste
            collection = await collection_service.get_collection(collection_id, collections_dir)
        ctx["collection"] = collection
    return ctx


# ---------------------------------------------------------------------------
# Webove auth dependencies
# ---------------------------------------------------------------------------

# Vyzaduje prihlaseneho uzivatele (platna JWT cookie); vyhodi WebLoginRequired, pokud chybi
async def require_web_user(request: Request) -> TokenPayload:
    user = _get_user_from_cookie(request)
    if not user:
        raise WebLoginRequired()
    return user


# Vyzaduje roli system_admin; vyhodi WebAdminRequired, pokud role nesouhlasi
async def require_web_admin(user: TokenPayload = Depends(require_web_user)) -> TokenPayload:
    if user.role != "system_admin":
        raise WebAdminRequired()
    return user


# ---------------------------------------------------------------------------
# Webove routy
# ---------------------------------------------------------------------------

# Koren aplikace – presmeruje prihlasene uzivatele na dashboard, ostatni na login
@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = _get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return RedirectResponse(url="/dashboard", status_code=302)


# Prihlasovaci stranka – presmeruje uz prihlasene uzivatele na dashboard
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if _get_user_from_cookie(request):
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})


# Odhlaseni – smaze JWT cookie a presmeruje na /login
@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


# Dashboard – prehled kolekcí dostupnych uzivateli
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: TokenPayload = Depends(require_web_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    sidebar = await _sidebar_ctx(db, user)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": _user_ctx(user),
        "collections": sidebar["accessible_collections"],
        "active_section": "dashboard",
        **sidebar,
    })


# Seznam zaznamu dane kolekce
@router.get("/records/{collection_id}", response_class=HTMLResponse)
async def records_list(
    request: Request,
    collection_id: str,
    user: TokenPayload = Depends(require_web_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    sidebar = await _sidebar_ctx(db, user, collection_id)
    return templates.TemplateResponse("records.html", {
        "request": request,
        "user": _user_ctx(user),
        "term": _merge_term(sidebar.get("collection")),
        "collection_id": collection_id,
        "active_section": "records",
        **sidebar,
    })


# Tiskovy nahled zaznamu (print_mode=True skryje navigaci)
@router.get("/records/{collection_id}/{record_id}/print", response_class=HTMLResponse)
async def record_print(
    request: Request,
    collection_id: str,
    record_id: str,
    user: TokenPayload = Depends(require_web_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    sidebar = await _sidebar_ctx(db, user, collection_id)
    return templates.TemplateResponse("record_detail.html", {
        "request": request,
        "user": _user_ctx(user),
        "term": _merge_term(sidebar.get("collection")),
        "collection_id": collection_id,
        "record_id": record_id,
        "print_mode": True,
        "active_section": "records",
        **sidebar,
    })


# Detail zaznamu – hlavni stranka pro editaci a zobrazeni zaznamu
@router.get("/records/{collection_id}/{record_id}", response_class=HTMLResponse)
async def record_detail(
    request: Request,
    collection_id: str,
    record_id: str,
    user: TokenPayload = Depends(require_web_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    sidebar = await _sidebar_ctx(db, user, collection_id)
    return templates.TemplateResponse("record_detail.html", {
        "request": request,
        "user": _user_ctx(user),
        "term": _merge_term(sidebar.get("collection")),
        "collection_id": collection_id,
        "record_id": record_id,
        "active_section": "records",
        **sidebar,
    })


# Stranka nastaveni – cestova nastaveni (editovatelna) a init-time nastaveni (read-only); vyzaduje system_admin
@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    user: TokenPayload = Depends(require_web_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    sidebar = await _sidebar_ctx(db, user)
    current_settings = await get_all_settings(db)
    # Init-time nastaveni ze souboru .env – pouze ke cteni, meni se restartem s novym .env
    init_settings = {
        "admin_username": app_settings.admin_username,
        "database_path": app_settings.database_path,
        "auth_provider": app_settings.auth_provider,
        "jwt_algorithm": app_settings.jwt_algorithm,
        "jwt_expire_minutes": app_settings.jwt_expire_minutes,
        "jwt_secret_safe": "*** (default – change in .env!)" if app_settings.jwt_secret_key == "change-me-in-production-use-strong-random-key" else "*** (custom key set)",
    }
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "user": _user_ctx(user),
        "settings": current_settings,
        "init_settings": init_settings,
        "active_section": "settings",
        **sidebar,
    })


# Admin stranka spravce uzivatelu; vyzaduje roli system_admin
@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(
    request: Request,
    user: TokenPayload = Depends(require_web_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    sidebar = await _sidebar_ctx(db, user)
    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "user": _user_ctx(user),
        "active_section": "users",
        **sidebar,
    })


# Seznam sablon kolekce; vyzaduje prihlaseneho uzivatele
@router.get("/templates/{collection_id}", response_class=HTMLResponse)
async def templates_list(
    request: Request,
    collection_id: str,
    user: TokenPayload = Depends(require_web_user),
    svc: TemplateService = Depends(get_template_service),
    db: aiosqlite.Connection = Depends(get_db),
):
    sidebar = await _sidebar_ctx(db, user, collection_id)
    tmpl_list = await svc.list_templates()
    return templates.TemplateResponse("templates_list.html", {
        "request": request,
        "user": _user_ctx(user),
        "term": _merge_term(sidebar.get("collection")),
        "collection_id": collection_id,
        "templates": tmpl_list,
        "active_section": "templates",
        **sidebar,
    })


# Editor pro vytvoreni nove sablony; vyzaduje roli system_admin
@router.get("/templates/{collection_id}/new", response_class=HTMLResponse)
async def template_editor_new(
    request: Request,
    collection_id: str,
    user: TokenPayload = Depends(require_web_admin),
    clone: str | None = None,
    db: aiosqlite.Connection = Depends(get_db),
):
    sidebar = await _sidebar_ctx(db, user, collection_id)
    return templates.TemplateResponse("template_editor.html", {
        "request": request,
        "user": _user_ctx(user),
        "term": _merge_term(sidebar.get("collection")),
        "collection_id": collection_id,
        "mode": "new",
        "template_id": None,
        "clone_from": clone,
        "active_section": "templates",
        **sidebar,
    })


# Editor pro upravu existujici sablony; vyzaduje roli system_admin
@router.get("/templates/{collection_id}/{template_id}/edit", response_class=HTMLResponse)
async def template_editor_edit(
    request: Request,
    collection_id: str,
    template_id: str,
    user: TokenPayload = Depends(require_web_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    sidebar = await _sidebar_ctx(db, user, collection_id)
    return templates.TemplateResponse("template_editor.html", {
        "request": request,
        "user": _user_ctx(user),
        "term": _merge_term(sidebar.get("collection")),
        "collection_id": collection_id,
        "mode": "edit",
        "template_id": template_id,
        "active_section": "templates",
        **sidebar,
    })


# Admin stranka spravce kolekcí; vyzaduje roli system_admin
@router.get("/admin/collections", response_class=HTMLResponse)
async def admin_collections_page(
    request: Request,
    user: TokenPayload = Depends(require_web_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    sidebar = await _sidebar_ctx(db, user)
    return templates.TemplateResponse("admin_collections.html", {
        "request": request,
        "user": _user_ctx(user),
        "active_section": "collections",
        **sidebar,
    })


# Editor pro vytvoreni nove kolekce; vyzaduje roli system_admin
@router.get("/admin/collections/new", response_class=HTMLResponse)
async def admin_collection_editor_new(
    request: Request,
    user: TokenPayload = Depends(require_web_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    sidebar = await _sidebar_ctx(db, user)
    return templates.TemplateResponse("admin_collection_editor.html", {
        "request": request,
        "user": _user_ctx(user),
        "mode": "new",
        "collection_id": None,
        "active_section": "collections",
        **sidebar,
    })


# Editor pro upravu existujici kolekce; vyzaduje roli system_admin
@router.get("/admin/collections/{collection_id}/edit", response_class=HTMLResponse)
async def admin_collection_editor_edit(
    request: Request,
    collection_id: str,
    user: TokenPayload = Depends(require_web_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    sidebar = await _sidebar_ctx(db, user)
    return templates.TemplateResponse("admin_collection_editor.html", {
        "request": request,
        "user": _user_ctx(user),
        "mode": "edit",
        "collection_id": collection_id,
        "active_section": "collections",
        **sidebar,
    })
