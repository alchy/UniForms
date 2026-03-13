from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Extension:
    """
    Represents a loaded UniForms extension.

    Extensions provide domain-specific section types, templates, and JS renderers.
    They are discovered from the paths listed in uniforms.yaml under 'extensions'.

    Directory layout expected under extension.path:
        extension.yaml   – manifest (this file describes what to load)
        js/              – JS renderer files (loaded after core uniforms.js)
        workbooks/       – YAML templates made available alongside user templates
    """
    id: str
    name: str
    version: str
    path: Path

    # JS files to inject into pages (paths relative to extension.path)
    js_files: list[str] = field(default_factory=list)

    # Section type identifiers this extension registers
    section_types: list[str] = field(default_factory=list)

    # auto_value key names provided by this extension (e.g. meta.mitre_tactic for SOC)
    auto_values: list[str] = field(default_factory=list)

    # Subdirectory under extension.path containing YAML templates (or None)
    templates_dir: str | None = None
