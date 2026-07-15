import logging
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings

from uniforms.models.collection import IdFormatConfig, WorkflowState

# ---------------------------------------------------------------------------
# Konfigurace aplikace načítaná ze dvou zdrojů:
#   uniforms.yaml – doménová a UI konfigurace (branding, terminologie, workflow)
#   .env          – tajné hodnoty a infrastrukturní nastavení (JWT, cesty, hesla)
# Oba zdroje jsou načteny při startu a dostupné jako singletony `uniforms`
# a `settings`. Při použití UniForms jako knihovny lze oba singletony
# přenastavit voláním configure() PŘED vytvořením aplikace (create_app).
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

DEFAULT_JWT_SECRET = "change-me-in-production-use-strong-random-key"
DEFAULT_ADMIN_PASSWORD = "admin"


# ---------------------------------------------------------------------------
# uniforms.yaml – domain / UI configuration
# ---------------------------------------------------------------------------

class AppConfig(BaseModel):
    name: str = "UniForms"
    subtitle: str = "Universal Forms Engine"


class TerminologyConfig(BaseModel):
    """
    Katalog všech UI textů s výchozími hodnotami.

    V uniforms.yaml stačí přepsat jen doménové pojmy (record_id_label,
    record_owner_label, new_record_btn, take_over_btn, *_subtitle…);
    zbytek jsou obecné texty aplikace, které přepisovat netřeba.
    Kolekce mohou libovolný klíč přepsat per-kolekce v `terminology:`.
    """

    # Doménové pojmy – tohle typicky přepisuješ v uniforms.yaml
    record_id_label: str = "Record ID"
    record_owner_label: str = "Record Owner"
    new_record_btn: str = "New Record"
    take_over_btn: str = "Take Over"
    records_subtitle: str = "All records"
    templates_subtitle: str = "Available templates"
    dashboard_subtitle: str = "Overview"

    # Stavy šablon
    status_active: str = "Active"
    status_draft: str = "Draft"
    status_deprecated: str = "Deprecated"

    # Navigace
    nav_dashboard: str = "Dashboard"
    nav_users: str = "Users"
    nav_settings: str = "Settings"
    nav_logout: str = "Log out"
    nav_sections: str = "Sections"
    nav_admin: str = "Admin"

    # Obecná tlačítka
    btn_cancel: str = "Cancel"
    btn_delete: str = "Delete"
    btn_edit: str = "Edit"
    btn_clone: str = "Clone"
    btn_print: str = "Print"
    btn_open: str = "Open"
    btn_save: str = "Save"
    btn_create: str = "Create"

    # Hlavičky tabulek
    col_status: str = "Status"
    col_title: str = "Title"
    col_lock: str = "Lock"
    col_username: str = "Username"
    col_role: str = "Role"
    col_created: str = "Created"

    # Filtr
    filter_all: str = "All"

    # Správa uživatelů
    users_title: str = "User Management"
    users_subtitle: str = "Create and manage application access"
    new_user_btn: str = "New user"

    # Nastavení
    settings_title: str = "Application Settings"

    # Login
    login_title: str = "Login"
    login_username_label: str = "USERNAME"
    login_username_placeholder: str = "Enter your username"
    login_password_label: str = "PASSWORD"
    login_password_placeholder: str = "Enter your password"
    login_btn: str = "Sign in"
    login_error_credentials: str = "Invalid credentials"
    login_error_failed: str = "Login failed"
    login_error_connection: str = "Server connection error"


class WorkflowConfig(BaseModel):
    states: list[WorkflowState] = [
        WorkflowState(id="new", label="New", color="secondary"),
        WorkflowState(id="open", label="Open", color="primary"),
        WorkflowState(id="in_progress", label="In Progress", color="warning"),
        WorkflowState(id="on_hold", label="On Hold", color="info"),
        WorkflowState(id="closed", label="Closed", color="success"),
    ]
    initial_state: str = "new"


class UniformsConfig(BaseModel):
    app: AppConfig = AppConfig()
    terminology: TerminologyConfig = TerminologyConfig()
    id: IdFormatConfig = IdFormatConfig()
    workflow: WorkflowConfig = WorkflowConfig()


def load_uniforms_config(path: str | Path = "uniforms.yaml") -> UniformsConfig:
    """Načte uniforms.yaml; při chybě nebo chybějícím souboru vrátí výchozí konfiguraci."""
    config_path = Path(path)
    if config_path.exists():
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            return UniformsConfig(**raw)
        except Exception as exc:
            logger.warning("Failed to load %s: %s – using defaults", config_path, exc)
    return UniformsConfig()


uniforms = load_uniforms_config()


# ---------------------------------------------------------------------------
# .env – secrets and infrastructure settings
# ---------------------------------------------------------------------------

class Settings(BaseSettings):
    # JWT
    jwt_secret_key: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480  # 8 hours

    # Cookie: v produkci za HTTPS nastav COOKIE_SECURE=true
    cookie_secure: bool = False

    # Auth provider: "simple" | "oauth" | "ldap"
    auth_provider: str = "simple"

    # Initial admin account (used on first run if no users exist)
    admin_username: str = "admin"
    admin_password: str = DEFAULT_ADMIN_PASSWORD

    # Timezone for timestamp display (IANA name, e.g. Europe/Prague)
    timezone: str = "Europe/Prague"

    # Paths
    database_path: str = "data/uniforms.db"
    default_records_dir: str = "data/records"
    default_schemas_dir: str = "data/schemas"
    default_collections_dir: str = "data/collections"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()


# ---------------------------------------------------------------------------
# Embedding API – použití UniForms jako knihovny
# ---------------------------------------------------------------------------

def configure(
    new_settings: Optional[Settings] = None,
    new_uniforms: Optional[UniformsConfig] = None,
    uniforms_path: Optional[str | Path] = None,
) -> None:
    """
    Přenastaví globální konfiguraci in-place (singletony `settings` a `uniforms`).

    Určeno pro hostitelské aplikace, které UniForms vkládají jako knihovnu –
    volej PŘED create_app(). Aktualizace probíhá in-place, takže platí i pro
    moduly, které si singletony už naimportovaly.
    """
    if uniforms_path is not None and new_uniforms is None:
        new_uniforms = load_uniforms_config(uniforms_path)
    if new_settings is not None:
        for field in Settings.model_fields:
            setattr(settings, field, getattr(new_settings, field))
    if new_uniforms is not None:
        for field in UniformsConfig.model_fields:
            setattr(uniforms, field, getattr(new_uniforms, field))
