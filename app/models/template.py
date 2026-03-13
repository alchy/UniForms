from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class UniTemplate(BaseModel):
    model_config = ConfigDict(extra="allow")  # templates may carry arbitrary extension fields

    template_id: str
    name: str
    version: str = "1.0"
    category: str = ""
    status: str = "active"               # active | draft | deprecated
    description: Optional[str] = None
    abstract: bool = False               # abstract templates are not shown in dashboard
    extends: Optional[str] = None        # parent template_id for section inheritance

    # Per-template workflow definition (overrides global default_states from uniforms.yaml).
    # Structure: {"states": [{"id": str, "label": str, "color": str}], "initial_state": str}
    workflow: Optional[dict[str, Any]] = None

    # Domain-specific metadata – arbitrary key/value pairs accessible via auto_value: meta.<key>
    # Examples for SOC: mitre_tactic, mitre_technique, data_sources
    meta: dict[str, Any] = {}

    sections: list[Any] = []

    # Filesystem metadata – not part of the YAML
    filename: Optional[str] = None
