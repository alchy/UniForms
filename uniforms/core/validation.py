import re

from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Sdílená validace identifikátorů, které se používají jako součást cest
# na souborovém systému (collection_id, record_id, template_id, názvy souborů).
# Chrání před path traversal – povoleny jsou jen bezpečné znaky bez lomítek
# a teček, takže hodnoty typu "../" nemohou opustit datový adresář.
# ---------------------------------------------------------------------------

# collection_id a názvy YAML souborů (kolekce, šablony) – lowercase slug
SLUG_RE = re.compile(r"^[a-z0-9_-]+$")

# record_id a template_id – generovaná/deklarovaná ID, povolena i velká písmena
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def is_safe_id(value: str) -> bool:
    return bool(SAFE_ID_RE.match(value))


def require_slug(value: str, name: str = "identifier") -> str:
    """Ověří slug pro HTTP vrstvu; při nevalidní hodnotě vyhodí HTTP 400."""
    if not SLUG_RE.match(value):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {name} – only lowercase letters, digits, '_' and '-' are allowed",
        )
    return value


def require_safe_id(value: str, name: str = "identifier") -> str:
    """Ověří ID pro HTTP vrstvu; při nevalidní hodnotě vyhodí HTTP 400."""
    if not SAFE_ID_RE.match(value):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {name} – only letters, digits, '_' and '-' are allowed",
        )
    return value
