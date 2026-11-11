from typing import Any, Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# API endpointy Collection Designeru (GUI návrhář kolekcí a šablon).
# Vše vyžaduje system_admin. Designer nepracuje s YAML textem, ale s modelem
# (dict odpovídající YAML souboru); převod model ↔ YAML, validaci a bezpečný
# zápis řeší services/designer_service.py – routy jsou jen tenká HTTP vrstva.
#
# GET  /admin/designer/catalog                               – paleta (typy sekcí, polí…)
# GET  /admin/designer/collections                           – přehled kolekcí
# GET  /admin/designer/collections/{id}                      – model kolekce + šablony
# POST /admin/designer/collections                           – vytvoření kolekce z modelu
# PUT  /admin/designer/collections/{id}                      – uložení modelu kolekce
# POST /admin/designer/collections/{id}/check                – kontrola modelu (nic nezapisuje)
# GET  /admin/designer/collections/{id}/templates/{tid}      – model šablony
# POST /admin/designer/collections/{id}/templates            – vytvoření šablony z modelu
# PUT  /admin/designer/collections/{id}/templates/{tid}      – uložení modelu šablony
# POST /admin/designer/collections/{id}/check-template       – kontrola + náhled (nic nezapisuje)
#
# Audit: zápisy zaznamená AuditMiddleware (op = název funkce); routy doplňují
# identifikátory a výsledek (change, changed_keys…) přes request.state.audit –
# jen názvy, nikdy hodnoty. Kontrolní endpointy nic nemění, proto se neauditují.
# ---------------------------------------------------------------------------

from uniforms import config
from uniforms.core.database import get_db
from uniforms.core.security import require_admin
from uniforms.core.validation import require_slug
from uniforms.models.user import User
from uniforms.services import collection_service
from uniforms.services import designer_service as ds
from uniforms.services.settings_service import get_collections_dir, get_schemas_dir

router = APIRouter(prefix="/admin/designer", tags=["Admin – Collection Designer"])

_STATUS = {
    ds.DesignerNotFound: 404,
    ds.DesignerExists: 409,
    ds.DesignerStale: 409,
    ds.DesignerRewriteNotConfirmed: 409,
    ds.DesignerUnsupported: 422,
    ds.DesignerInvalid: 422,
}


# --- Modely ---

class CollectionCreateBody(BaseModel):
    collection_id: str = Field(min_length=1, max_length=64)
    model: dict[str, Any]


class ModelSaveBody(BaseModel):
    model: dict[str, Any]
    base_hash: Optional[str] = Field(default=None, max_length=64)
    confirm_rewrite: bool = False


class ModelCheckBody(BaseModel):
    model: dict[str, Any]


class TemplateCreateBody(BaseModel):
    filename: str = Field(min_length=1, max_length=128)  # slug bez pripony .yaml
    model: dict[str, Any]


# --- Pomocne funkce ---

def _http_error(exc: ds.DesignerError) -> HTTPException:
    """Prevede chybu sluzby na HTTP odpoved s jednotnym tvarem detailu {code, message, …}."""
    detail: dict[str, Any] = {"code": exc.code, "message": exc.message, **exc.extra}
    if isinstance(exc, ds.DesignerInvalid):
        detail["issues"] = exc.issues
    return HTTPException(status_code=_STATUS.get(type(exc), 400), detail=detail)


def _audit(request: Request, **fields: Any) -> None:
    """Doplni identifikatory do auditni udalosti (jen nazvy, nikdy hodnoty)."""
    current = getattr(request.state, "audit", None) or {}
    request.state.audit = {**current, **fields}


def _audit_result(request: Request, result: dict) -> None:
    _audit(
        request,
        change=result["change"],
        changed_keys=result["changed_keys"],
        comments_discarded=result["comments_discarded"],
        **({"backup": result["backup"]} if result["backup"] else {}),
    )


async def _collection_dirs(db: aiosqlite.Connection, collection_id: str):
    """Vrati (collections_dir, adresar sablon kolekce); 404, pokud kolekce neexistuje.

    Existence se overuje drive, nez se saha na adresar sablon – neznama kolekce
    tak nezalozi prazdny adresar ve schemas_dir.
    """
    require_slug(collection_id, "collection_id")
    collections_dir = await get_collections_dir(db)
    if not (collections_dir / f"{collection_id}.yaml").exists():
        raise HTTPException(404, detail={"code": "not_found",
                                         "message": f"Collection '{collection_id}' not found"})
    return collections_dir, (await get_schemas_dir(db)) / collection_id


def _field_keys(template_dir) -> set[str]:
    return {f["key"] for f in ds.collection_field_keys(template_dir)}


# --- Endpointy: katalog a prehled ---

@router.get("/catalog", summary="Designer palette: section/field types, colors, tokens")
# Vrati katalog typu sekci, poli, barev a tokenu, ze kterych designer sklada paletu
async def designer_catalog(current_user: User = Depends(require_admin)) -> dict:
    return ds.catalog(config.uniforms.terminology.model_dump())


@router.get("/collections", summary="List collections for the designer")
# Vrati prehled kolekci vcetne poctu sablon; vyzaduje system_admin
async def designer_list_collections(
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[dict]:
    collections_dir = await get_collections_dir(db)
    schemas_dir = await get_schemas_dir(db)
    result = []
    for col in await collection_service.list_collections(collections_dir):
        result.append({
            "collection_id": col.id,
            "name": col.name,
            "description": col.description,
            "states": [s.model_dump() for s in col.workflow.states],
            "templates": len(ds.list_templates(schemas_dir / col.id)),
        })
    return result


# --- Endpointy: kolekce ---

@router.get("/collections/{collection_id}", summary="Load a collection model")
# Vrati model kolekce (dict z YAML), informace o zdroji, seznam sablon a klice poli
async def designer_get_collection(
    collection_id: str,
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    collections_dir, template_dir = await _collection_dirs(db, collection_id)
    try:
        loaded = ds.load_collection(collections_dir, collection_id)
    except ds.DesignerError as exc:
        raise _http_error(exc)
    loaded["templates"] = ds.list_templates(template_dir)
    loaded["field_keys"] = ds.collection_field_keys(template_dir)
    return loaded


@router.post("/collections/{collection_id}/check", summary="Validate a collection model (no write)")
# Overi model kolekce a vrati vysledny YAML + nalezy; nic nezapisuje, neaudituje se
async def designer_check_collection(
    collection_id: str,
    body: ModelCheckBody,
    request: Request,
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    request.state.audit_skip = True
    require_slug(collection_id, "collection_id")
    template_dir = (await get_schemas_dir(db)) / collection_id
    return ds.check_collection(body.model, collection_id, _field_keys(template_dir))


@router.post("/collections", status_code=201, summary="Create a collection from a model")
# Vytvori novy soubor kolekce z modelu; validace jako u POST /admin/collections/
async def designer_create_collection(
    body: CollectionCreateBody,
    request: Request,
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    require_slug(body.collection_id, "collection_id")
    _audit(request, via="designer", collection_id=body.collection_id)
    collections_dir = await get_collections_dir(db)
    try:
        result = ds.save_collection(collections_dir, body.collection_id, body.model, create=True)
    except ds.DesignerError as exc:
        _audit(request, reject_code=exc.code)
        raise _http_error(exc)
    _audit_result(request, result)
    return result


@router.put("/collections/{collection_id}", summary="Save a collection model")
# Ulozi model existujici kolekce; hlida soubeznou zmenu (base_hash) a ztratu komentaru
async def designer_update_collection(
    collection_id: str,
    body: ModelSaveBody,
    request: Request,
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    _audit(request, via="designer")
    collections_dir, template_dir = await _collection_dirs(db, collection_id)
    try:
        result = ds.save_collection(
            collections_dir, collection_id, body.model,
            base_hash=body.base_hash, confirm_rewrite=body.confirm_rewrite,
            known_field_keys=_field_keys(template_dir),
        )
    except ds.DesignerError as exc:
        _audit(request, reject_code=exc.code)
        raise _http_error(exc)
    _audit_result(request, result)
    return result


# --- Endpointy: sablony ---

@router.get("/collections/{collection_id}/templates/{template_id}", summary="Load a template model")
# Vrati model sablony (nenormalizovany dict z YAML) a zdedene sekce rodicu
async def designer_get_template(
    collection_id: str,
    template_id: str,
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    _collections_dir, template_dir = await _collection_dirs(db, collection_id)
    try:
        loaded = await ds.load_template(template_dir, template_id)
    except ds.DesignerError as exc:
        raise _http_error(exc)
    if not loaded:
        raise HTTPException(404, detail={"code": "not_found",
                                         "message": f"Template '{template_id}' not found"})
    return loaded


@router.post("/collections/{collection_id}/check-template",
             summary="Validate a template model and build its preview (no write)")
# Overi model sablony a vrati YAML, nalezy, nahled sekci a zdedene sekce; nic nezapisuje
async def designer_check_template(
    collection_id: str,
    body: ModelCheckBody,
    request: Request,
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    request.state.audit_skip = True
    _collections_dir, template_dir = await _collection_dirs(db, collection_id)
    result = ds.check_template(template_dir, body.model)
    result["inherited"] = ds.inherited_sections(
        template_dir, body.model.get("extends"), body.model.get("template_id"))
    return result


@router.post("/collections/{collection_id}/templates", status_code=201,
             summary="Create a template from a model")
# Vytvori novou sablonu z modelu; validace jako u POST /templates/{collection_id}/
async def designer_create_template(
    collection_id: str,
    body: TemplateCreateBody,
    request: Request,
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    new_id = body.model.get("template_id")
    _audit(request, via="designer",
           **({"template_id": new_id[:128]} if isinstance(new_id, str) and ds.SAFE_ID_RE.match(new_id) else {}))
    _collections_dir, template_dir = await _collection_dirs(db, collection_id)
    try:
        result = await ds.save_template(template_dir, body.model, filename=body.filename)
    except ds.DesignerError as exc:
        _audit(request, reject_code=exc.code)
        raise _http_error(exc)
    _audit_result(request, result)
    return result


@router.put("/collections/{collection_id}/templates/{template_id}", summary="Save a template model")
# Ulozi model existujici sablony; template_id nelze zmenit, hlida base_hash a komentare
async def designer_update_template(
    collection_id: str,
    template_id: str,
    body: ModelSaveBody,
    request: Request,
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    _audit(request, via="designer")
    _collections_dir, template_dir = await _collection_dirs(db, collection_id)
    try:
        result = await ds.save_template(
            template_dir, body.model, template_id=template_id,
            base_hash=body.base_hash, confirm_rewrite=body.confirm_rewrite,
        )
    except ds.DesignerError as exc:
        _audit(request, reject_code=exc.code)
        raise _http_error(exc)
    _audit_result(request, result)
    return result
