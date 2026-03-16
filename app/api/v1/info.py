from fastapi import APIRouter

from app.config import uniforms

# ---------------------------------------------------------------------------
# Veřejný informační endpoint – nevyžaduje autentizaci.
# Vrací základní metadata aplikace (název, podtitulek).
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/info", tags=["Info"])


@router.get("/", summary="Application info (public)")
async def get_info() -> dict[str, str]:
    """Returns app name and subtitle. No authentication required."""
    return {
        "app_name": uniforms.app.name,
        "app_subtitle": uniforms.app.subtitle,
    }
