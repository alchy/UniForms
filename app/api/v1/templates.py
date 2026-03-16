from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# API endpointy pro správu YAML šablon kolekce.
# GET    /templates/{col}/            – seznam šablon (bez abstraktních).
# GET    /templates/{col}/{id}         – detail šablony (normalizovaná struktura).
# GET    /templates/{col}/{id}/source  – zdrojový YAML text šablony.
# PUT    /templates/{col}/{id}         – uložení upraveného YAML (vyžaduje collection_admin).
# POST   /templates/{col}/             – vytvoření nové šablony (vyžaduje collection_admin).
# DELETE /templates/{col}/{id}         – smazání šablony (vyžaduje collection_admin).
# ---------------------------------------------------------------------------

from app.core.collection_deps import require_collection_access, require_collection_admin
from app.models.template import UniTemplate
from app.models.user import User
from app.services.template_service import TemplateService, get_template_service

router = APIRouter(prefix="/templates/{collection_id}", tags=["Templates"])


# Telo pozadavku pro ulozeni obsahu existujici sablony
class TemplateSaveBody(BaseModel):
    content: str


# Telo pozadavku pro vytvoreni nove sablony (nazev souboru + YAML obsah)
class TemplateCreateBody(BaseModel):
    filename: str
    content: str


@router.get("/", response_model=list[UniTemplate], summary="List templates in collection")
# Vrati seznam vsech sablon kolekce; vyzaduje pristup ke kolekci
async def list_templates(
    current_user: User = Depends(require_collection_access),
    svc: TemplateService = Depends(get_template_service),
) -> list[UniTemplate]:
    return await svc.list_templates()


@router.post("/", summary="Create template (collection admin)")
# Vytvori novy YAML soubor sablony; vyzaduje roli collection_admin nebo system_admin
async def create_template(
    body: TemplateCreateBody,
    current_user: User = Depends(require_collection_admin),
    svc: TemplateService = Depends(get_template_service),
):
    try:
        template_id = await svc.create(body.filename, body.content)
        return {"ok": True, "template_id": template_id, "filename": body.filename.rstrip(".yaml") + ".yaml"}
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {exc}")


@router.get("/{template_id}/source", summary="Template source YAML (collection admin)")
# Vrati zdrojovy YAML sablony pro editor; vyzaduje roli collection_admin nebo system_admin
async def get_template_source(
    template_id: str,
    current_user: User = Depends(require_collection_admin),
    svc: TemplateService = Depends(get_template_service),
):
    source = await svc.get_source(template_id)
    if not source:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return source


@router.get("/{template_id}", response_model=UniTemplate, summary="Get template")
# Vrati normalizovany JSON sablony; vyzaduje pristup ke kolekci
async def get_template_by_id(
    template_id: str,
    current_user: User = Depends(require_collection_access),
    svc: TemplateService = Depends(get_template_service),
) -> UniTemplate:
    template = await svc.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return template


@router.put("/{template_id}", summary="Save template (collection admin)")
# Ulozi upraveny YAML obsah sablony; vyzaduje roli collection_admin nebo system_admin
async def save_template(
    template_id: str,
    body: TemplateSaveBody,
    current_user: User = Depends(require_collection_admin),
    svc: TemplateService = Depends(get_template_service),
):
    try:
        filename = await svc.save(template_id, body.content)
        return {"ok": True, "filename": filename}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {exc}")


@router.delete("/{template_id}", status_code=204, summary="Delete template (collection admin)")
# Smaze soubor sablony; vyzaduje roli collection_admin nebo system_admin
async def delete_template(
    template_id: str,
    current_user: User = Depends(require_collection_admin),
    svc: TemplateService = Depends(get_template_service),
):
    try:
        await svc.delete(template_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
