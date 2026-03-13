# UniForms

A generic, configurable forms engine for structured data capture. Define templates in YAML, submit records through the browser, manage everything through a REST API.

## What is UniForms?

UniForms is a web application that turns YAML template definitions into interactive HTML forms. Users open a record in the browser, fill in the structured form rendered from the template, and save. The application handles storage, locking, workflow states, and user management.

UniForms is domain-agnostic. The same engine can power IT helpdesk tickets, HR onboarding requests, support cases, audit checklists, or any other structured workflow — the domain is defined entirely by your templates and configuration.

## Key Features

- **YAML-driven templates** — define form structure, sections, fields, and checklists in plain YAML; no code required for new record types
- **Extension system** — domain-specific section types and logic packaged as extensions (e.g. the `soc` extension adds `classification` and `raci_table` section types)
- **Configurable terminology** — labels like "record", "template", and workflow state names are read from `uniforms.yaml` so the UI reflects your domain language
- **File-based record storage** — records are JSON files on disk; configurable storage path; no external database required
- **JWT authentication** — httpOnly cookie (`uniforms_token`), role-based access (admin / user), configurable session duration
- **Per-template workflow states** — each template can define its own set of workflow states with display labels
- **Template inheritance** — templates can extend a parent template and override or add sections; abstract base templates are supported
- **Record locking** — prevents concurrent edits; lock acquired on open, released on save-and-exit
- **Auto-save on status change** — status field change triggers an immediate background save
- **Print to PDF** — browser print dialog renders a clean print layout

## Quick Start

```bash
git clone https://github.com/your-org/UniForms.git
cd UniForms
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # set JWT_SECRET_KEY and ADMIN_PASSWORD
python scripts/download_vendors.py
python start.py
```

Application available at **http://localhost:8080**. Default login: `admin` / `admin`.

## Configuration Overview

### `.env` — secrets and infrastructure

```ini
JWT_SECRET_KEY=your-random-secret-min-32-chars
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme
DATABASE_PATH=data/uniforms.db
DEFAULT_RECORDS_DIR=data/records
DEFAULT_TEMPLATES_DIR=data/templates
TIMEZONE=UTC
```

### `uniforms.yaml` — domain configuration

Domain-specific settings live in `uniforms.yaml`, not in `.env`. This includes terminology overrides, default workflow states, and extension loading:

```yaml
app_name: UniForms
app_subtitle: IT Helpdesk Portal

terminology:
  record: ticket
  records: tickets
  template: form type

workflow:
  default_states:
    - value: open
      label: Open
    - value: in_progress
      label: In Progress
    - value: resolved
      label: Resolved
    - value: closed
      label: Closed

extensions: []
```

See `uniforms.yaml.example` for a full reference.

## Tech Stack

- **Backend**: FastAPI + Uvicorn (Python 3.11+)
- **Frontend**: Jinja2 + Bootstrap 5 (server-side rendering)
- **Auth**: JWT (PyJWT), httpOnly cookie `uniforms_token`
- **Database**: SQLite — users and settings (aiosqlite)
- **Storage**: JSON files (records), YAML files (templates)
- **JS libraries**: jQuery, DataTables, Bootstrap Icons, Ace Editor
- **Form renderer**: `uniforms.js` — browser-side JSON → interactive HTML form

## Documentation

- [Installation and deployment](docs/INSTALL.md) — local setup, systemd service, nginx reverse proxy
- [API reference](docs/API.md) — all REST endpoints
- [Web rendering](docs/WEB_RENDERING.md) — Jinja2 templates, layout, globals
- [Template guide](docs/TEMPLATE_GUIDE.md) — technical reference for template authors
- [Template authoring](docs/TEMPLATE_AUTHORING.md) — non-developer guide for writing templates
- [Template pipeline](docs/TEMPLATE_PIPELINE.md) — YAML → normalize → clone → record internals
- [uniforms.js developer guide](docs/UNIFORMS_JS.md) — browser-side form renderer API
