from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings


# ---------------------------------------------------------------------------
# uniforms.yaml – domain / UI configuration
# ---------------------------------------------------------------------------

class AppConfig(BaseModel):
    name: str = "UniForms"
    subtitle: str = "Universal Forms Engine"


class TerminologyConfig(BaseModel):
    # Core entity names
    record_id_label: str = "Record ID"

    # Page subtitles (shown under headings)
    records_subtitle: str = "All records"
    templates_subtitle: str = "Available templates"
    dashboard_subtitle: str = "Overview"

    # Action buttons
    new_record_btn: str = "New Record"
    record_owner_label: str = "Record Owner"
    take_over_btn: str = "Take Over"

    # Template / record status labels
    status_active: str = "Active"
    status_draft: str = "Draft"
    status_deprecated: str = "Deprecated"

    # Sidebar nav labels
    nav_dashboard: str = "Dashboard"
    nav_users: str = "Users"
    nav_settings: str = "Settings"
    nav_logout: str = "Log out"
    nav_sections: str = "Sections"
    nav_admin: str = "Admin"

    # Common action buttons
    btn_cancel: str = "Cancel"
    btn_delete: str = "Delete"
    btn_edit: str = "Edit"
    btn_clone: str = "Clone"
    btn_print: str = "Print"
    btn_open: str = "Open"
    btn_save: str = "Save"
    btn_create: str = "Create"

    # Table column headers
    col_status: str = "Status"
    col_title: str = "Title"
    col_lock: str = "Lock"
    col_username: str = "Username"
    col_role: str = "Role"
    col_created: str = "Created"

    # Filter bar
    filter_all: str = "All"

    # User management page
    users_title: str = "User Management"
    users_subtitle: str = "Create and manage application access"
    new_user_btn: str = "New user"

    # Settings page
    settings_title: str = "Application Settings"

    # Login page
    login_title: str = "Login"
    login_username_label: str = "USERNAME"
    login_username_placeholder: str = "Enter your username"
    login_password_label: str = "PASSWORD"
    login_password_placeholder: str = "Enter your password"
    login_btn: str = "Sign in"
    login_error_credentials: str = "Invalid credentials"
    login_error_failed: str = "Login failed"
    login_error_connection: str = "Server connection error"


class WorkflowState(BaseModel):
    id: str
    label: str
    color: str = "secondary"


class WorkflowConfig(BaseModel):
    default_states: list[WorkflowState] = [
        WorkflowState(id="new", label="New", color="secondary"),
        WorkflowState(id="open", label="Open", color="primary"),
        WorkflowState(id="in_progress", label="In Progress", color="warning"),
        WorkflowState(id="on_hold", label="On Hold", color="info"),
        WorkflowState(id="closed", label="Closed", color="success"),
    ]
    initial_state: str = "new"


class IdConfig(BaseModel):
    prefix: str = "REC"
    format: str = "{prefix}-{YYYYMM}-{rand:04d}"


class UniformsConfig(BaseModel):
    app: AppConfig = AppConfig()
    terminology: TerminologyConfig = TerminologyConfig()
    id: IdConfig = IdConfig()
    workflow: WorkflowConfig = WorkflowConfig()


def _load_uniforms_config() -> UniformsConfig:
    config_path = Path("uniforms.yaml")
    if config_path.exists():
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            return UniformsConfig(**raw)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to load uniforms.yaml: %s – using defaults", exc
            )
    return UniformsConfig()


uniforms = _load_uniforms_config()


# ---------------------------------------------------------------------------
# .env – secrets and infrastructure settings
# ---------------------------------------------------------------------------

class Settings(BaseSettings):
    # JWT
    jwt_secret_key: str = "change-me-in-production-use-strong-random-key"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480  # 8 hours

    # Auth provider: "simple" | "oauth" | "ldap"
    auth_provider: str = "simple"

    # Initial admin account (used on first run if no users exist)
    admin_username: str = "admin"
    admin_password: str = "admin"

    # Timezone for timestamp display (IANA name, e.g. Europe/Prague)
    timezone: str = "Europe/Prague"

    # Paths
    database_path: str = "data/uniforms.db"
    default_records_dir: str = "data/records"
    default_schemas_dir: str = "data/schemas"
    default_collections_dir: str = "data/collections"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
