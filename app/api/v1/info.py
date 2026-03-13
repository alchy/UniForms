from fastapi import APIRouter

from app.config import uniforms

router = APIRouter(prefix="/info", tags=["Info"])


@router.get("/", summary="Application info (public)")
async def get_info() -> dict[str, str]:
    """Returns app name, subtitle, and terminology. No authentication required."""
    return {
        "app_name": uniforms.app.name,
        "app_subtitle": uniforms.app.subtitle,
        "terminology_record": uniforms.terminology.record,
        "terminology_records": uniforms.terminology.records,
    }
