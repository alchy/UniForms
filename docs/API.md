# UniForms – API Reference

REST API for managing records, templates, collections, users, and settings. Intended for developers and integrators consuming the API.

All communication uses JSON. Authentication is handled via an httpOnly cookie `uniforms_token` (JWT HS256) — the login request sets the cookie automatically and the browser sends it with every subsequent request.

**Interactive documentation:** http://localhost:8080/api/docs (Swagger UI) · http://localhost:8080/api/redoc

---

## How it works

Overview of the architecture — from client through JWT middleware to endpoint groups:

```
Browser / client
    │
    │  HTTP request + Cookie: uniforms_token=<jwt>
    ▼
┌─────────────────────────────────────────────────┐
│  FastAPI app (uvicorn, port 8080)               │
│                                                 │
│  JWT middleware                                 │
│    │  verifies token, sets request.state.user   │
│    ▼                                            │
│  Route handler                                  │
│    │                                            │
│    ├── /api/v1/auth/*         authentication    │
│    ├── /api/v1/info/          app info          │
│    ├── /api/v1/collections/*  collections       │
│    ├── /api/v1/records/*      records           │
│    ├── /api/v1/templates/*    templates         │
│    ├── /api/v1/admin/*        role management   │
│    ├── /api/v1/settings/*     settings (admin)  │
│    └── /api/v1/users/*        users (admin)     │
└─────────────────────────────────────────────────┘
```

Endpoints marked **admin** require global role `system_admin`. Endpoints marked **collection admin** require role `collection_admin` in the given collection (or global `system_admin`).

---

## Quick start — authentication

Login and first request using `curl`:

```bash
# 1. Login — saves cookie to file
curl -s -c /tmp/uf.cookies -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'

# 2. List collections with saved cookie
curl -s -b /tmp/uf.cookies http://localhost:8080/api/v1/collections/

# 3. Logout
curl -s -b /tmp/uf.cookies -c /tmp/uf.cookies \
  -X POST http://localhost:8080/api/v1/auth/logout \
  -H "Content-Type: application/json"
```

---

## AUTH – `/api/v1/auth`

Endpoints for login, logout, and getting the current user.

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/v1/auth/login` | Login — sets httpOnly cookie | — |
| POST | `/api/v1/auth/logout` | Logout — deletes cookie | — |
| GET | `/api/v1/auth/me` | Info about the logged-in user | required |

### `POST /api/v1/auth/login`

Authenticates the user and sets the cookie `uniforms_token`. The token is valid for `JWT_EXPIRE_MINUTES` (default: 480 minutes / 8 hours).

```bash
curl -s -c /tmp/uf.cookies -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'
```

```json
// Request
{ "username": "admin", "password": "admin" }

// Response 200 — sets Set-Cookie: uniforms_token=<jwt>; HttpOnly; SameSite=Lax
{ "access_token": "<jwt>", "token_type": "bearer" }

// Response 401 — invalid credentials
{ "detail": "Invalid credentials" }
```

| Key | Required | Description |
|-----|----------|-------------|
| `username` | ✓ | Username |
| `password` | ✓ | Password |

The JWT payload contains: `sub` (username) and `role` (system role: `system_admin` or `system_reader`).

### `POST /api/v1/auth/logout`

Deletes the cookie and invalidates the session.

```bash
curl -s -b /tmp/uf.cookies -c /tmp/uf.cookies \
  -X POST http://localhost:8080/api/v1/auth/logout \
  -H "Content-Type: application/json"
```

```json
// Response 200
{ "detail": "Logged out" }
```

### `GET /api/v1/auth/me`

Returns information about the currently logged-in user.

```bash
curl -s -b /tmp/uf.cookies http://localhost:8080/api/v1/auth/me
```

```json
// Response 200
{
  "username": "admin",
  "role": "system_admin",
  "is_active": true,
  "created_at": "2026-01-01T00:00:00"
}
```

---

## INFO – `/api/v1/info`

Public endpoint — no authentication required. Returns the current application branding (values from `uniforms.yaml`).

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/v1/info/` | App name, version, and subtitle | — |

### `GET /api/v1/info/`

```bash
curl -s http://localhost:8080/api/v1/info/
```

```json
// Response 200
{
  "app_name": "UniForms",
  "app_version": "1.0.0",
  "app_subtitle": "Universal Forms Engine"
}
```

---

## COLLECTIONS – `/api/v1/collections`

A collection is a group of templates and records of the same nature (e.g. `soc`, `helpdesk`). Collection definitions are YAML files in `data/collections/{id}.yaml`. Each collection has its own terminology, workflow states, and role assignments.

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/v1/collections/` | List accessible collections | required |
| GET | `/api/v1/collections/{id}` | Get a single collection | required |

### `GET /api/v1/collections/`

Returns all collections accessible to the authenticated user. Users with role `system_admin` see all collections; other users see only collections assigned to them in `collection_roles`.

```bash
curl -s -b /tmp/uf.cookies http://localhost:8080/api/v1/collections/
```

```json
// Response 200
[
  {
    "id": "soc",
    "name": "SOC",
    "description": "Security Operations Center",
    "terminology": {
      "record": "incident",
      "records": "incidents"
    },
    "workflow": {
      "initial_state": "new",
      "states": [
        { "id": "new", "label": "New", "color": "secondary" },
        { "id": "in_progress", "label": "In Progress", "color": "primary" },
        { "id": "closed", "label": "Closed", "color": "success" }
      ]
    },
    "list_columns": [
      { "key": "title", "label": "Title" },
      { "key": "coordinator", "label": "Coordinator" }
    ],
    "roles": [
      { "id": "collection_admin", "label": "Collection Admin" },
      { "id": "collection_user", "label": "Collection User" }
    ]
  }
]
```

### `GET /api/v1/collections/{id}`

```bash
curl -s -b /tmp/uf.cookies http://localhost:8080/api/v1/collections/soc
```

Returns the same structure as a single element from the list above.

---

## RECORDS – `/api/v1/records/{collection_id}`

Records are JSON documents stored in `data/records/{collection_id}/`. Each record is created by cloning a collection template.

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/v1/records/{collection_id}/` | List records in collection (newest first) | required |
| POST | `/api/v1/records/{collection_id}/` | Create record from template | required |
| GET | `/api/v1/records/{collection_id}/{record_id}` | Get record | required |
| PATCH | `/api/v1/records/{collection_id}/{record_id}` | Update status and/or data | required |
| DELETE | `/api/v1/records/{collection_id}/{record_id}` | Delete record | collection admin |
| POST | `/api/v1/records/{collection_id}/{record_id}/lock` | Acquire edit lock | required |
| DELETE | `/api/v1/records/{collection_id}/{record_id}/lock` | Release edit lock | required |

"Required" means the user must have any role in `collection_roles` for the given collection, or be a `system_admin`.

### Record ID format

Each collection defines its own prefix and ID format in `data/collections/{id}.yaml`:

```yaml
id_format:
  prefix: "SOC"
  format: "{prefix}-{YYYYMM}-{rand:04d}"
```

Example generated ID: `SOC-202603-0042`

### `POST /api/v1/records/{collection_id}/` — create record

```bash
curl -s -b /tmp/uf.cookies \
  -X POST http://localhost:8080/api/v1/records/soc/ \
  -H "Content-Type: application/json" \
  -d '{"template_id": "phishing-v1"}'
```

```json
// Request
{ "template_id": "phishing-v1" }

// Response 201
{
  "record_id": "SOC-202603-0042",
  "collection_id": "soc",
  "template_id": "phishing-v1",
  "status": "new",
  "created_by": "user1",
  "created_at": "2026-03-05T14:30:22+00:00",
  "updated_at": "2026-03-05T14:30:22+00:00",
  "locked_by": null,
  "data": { "sections": [] }
}
```

| Key | Required | Description |
|-----|----------|-------------|
| `template_id` | ✓ | ID of the collection template to create the record from |

### `GET /api/v1/records/{collection_id}/{record_id}` — get record

```bash
curl -s -b /tmp/uf.cookies \
  http://localhost:8080/api/v1/records/soc/SOC-202603-0042
```

```json
// Response 200
{
  "record_id": "SOC-202603-0042",
  "collection_id": "soc",
  "template_id": "phishing-v1",
  "status": "in_progress",
  "created_by": "user1",
  "created_at": "2026-03-05T14:30:22+00:00",
  "updated_at": "2026-03-05T15:00:10+00:00",
  "locked_by": "user1",
  "data": { "sections": [] }
}
```

### `PATCH /api/v1/records/{collection_id}/{record_id}` — update

All fields are optional — you can update status only, data only, or both at once.

```bash
curl -s -b /tmp/uf.cookies \
  -X PATCH http://localhost:8080/api/v1/records/soc/SOC-202603-0042 \
  -H "Content-Type: application/json" \
  -d '{"status": "in_progress", "data": {"sections": []}}'
```

```json
// Status only
{ "status": "in_progress" }

// Data only
{ "data": { "sections": [] } }

// Status and data together
{ "status": "closed", "data": { "sections": [] } }
```

| Key | Required | Description |
|-----|----------|-------------|
| `status` | | New workflow state (must be a valid state for the collection) |
| `data` | | Object `{ "sections": [...] }` with updated data |

### `DELETE /api/v1/records/{collection_id}/{record_id}` — delete

Requires role `collection_admin` in the collection or global `system_admin`. Returns `204 No Content`.

```bash
curl -s -b /tmp/uf.cookies \
  -X DELETE http://localhost:8080/api/v1/records/soc/SOC-202603-0042
```

### Locking — edit locks

A lock prevents concurrent edits of the same record. Acquire the lock before editing; release it after saving. Users with role `system_admin` can force-release any lock.

```bash
# Acquire lock
curl -s -b /tmp/uf.cookies \
  -X POST http://localhost:8080/api/v1/records/soc/SOC-202603-0042/lock \
  -H "Content-Type: application/json"

# Release lock
curl -s -b /tmp/uf.cookies \
  -X DELETE http://localhost:8080/api/v1/records/soc/SOC-202603-0042/lock
```

```json
// POST /lock — response 200 (lock acquired)
{ "locked_by": "user1" }

// POST /lock — response 423 (locked by another user)
{
  "detail": {
    "message": "Record is locked by another user",
    "locked_by": "user2",
    "locked_at": "2026-03-05T14:30:22+00:00"
  }
}

// DELETE /lock — response 204 No Content
```

---

## TEMPLATES – `/api/v1/templates/{collection_id}`

Templates are YAML files in `data/schemas/{collection_id}/`. Each template defines the structure of one record type within a collection.

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/v1/templates/{collection_id}/` | List templates in collection | required |
| POST | `/api/v1/templates/{collection_id}/` | Create new template | collection admin |
| GET | `/api/v1/templates/{collection_id}/{template_id}` | Get template (normalized JSON) | required |
| GET | `/api/v1/templates/{collection_id}/{template_id}/source` | Source YAML (for editor) | collection admin |
| PUT | `/api/v1/templates/{collection_id}/{template_id}` | Save updated YAML | collection admin |
| DELETE | `/api/v1/templates/{collection_id}/{template_id}` | Delete template | collection admin |

### `GET /api/v1/templates/{collection_id}/` — list templates

```bash
curl -s -b /tmp/uf.cookies http://localhost:8080/api/v1/templates/soc/
```

```json
// Response 200
[
  {
    "template_id": "phishing-v1",
    "name": "Phishing Incident",
    "version": "1.0",
    "category": "Incident Response",
    "status": "active",
    "description": "Template for phishing incidents.",
    "sections": [],
    "filename": "phishing.yaml"
  }
]
```

### `POST /api/v1/templates/{collection_id}/` — create template

Requires role `collection_admin` or `system_admin`.

```bash
curl -s -b /tmp/uf.cookies \
  -X POST http://localhost:8080/api/v1/templates/soc/ \
  -H "Content-Type: application/json" \
  -d '{"filename": "malware.yaml", "content": "template_id: malware-v1\nname: Malware Incident\nversion: \"1.0\"\nsections: []\n"}'
```

```json
// Request
{ "filename": "malware.yaml", "content": "template_id: malware-v1\nname: Malware Incident\n..." }

// Response 200
{ "ok": true, "template_id": "malware-v1", "filename": "malware.yaml" }

// Response 409 — file with this name already exists
// Response 400 — invalid YAML
```

| Key | Required | Description |
|-----|----------|-------------|
| `filename` | ✓ | Template filename including `.yaml` extension |
| `content` | ✓ | Complete YAML template content as string |

### `PUT /api/v1/templates/{collection_id}/{template_id}` — save template

Requires role `collection_admin` or `system_admin`.

```bash
curl -s -b /tmp/uf.cookies \
  -X PUT http://localhost:8080/api/v1/templates/soc/malware-v1 \
  -H "Content-Type: application/json" \
  -d '{"content": "template_id: malware-v1\nname: Malware Incident\nversion: \"1.1\"\nsections: []\n"}'
```

```json
// Request
{ "content": "template_id: malware-v1\nname: Malware Incident\nversion: \"1.1\"\nsections: []\n" }

// Response 200
{ "ok": true, "filename": "malware.yaml" }
```

### `GET /api/v1/templates/{collection_id}/{template_id}/source` — source YAML

Requires role `collection_admin` or `system_admin`.

```bash
curl -s -b /tmp/uf.cookies \
  http://localhost:8080/api/v1/templates/soc/malware-v1/source
```

```json
// Response 200
{ "content": "template_id: malware-v1\nname: Malware Incident\n..." }
```

---

## ADMIN — collection-roles – `/api/v1/admin/collection-roles`

Manage user role assignments within collections. Requires global role `system_admin`.

Collection roles: `collection_admin` (can edit/delete templates and records), `collection_user` (can create and edit records).

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/v1/admin/collection-roles/` | All role assignments | system_admin |
| PATCH | `/api/v1/admin/collection-roles/{collection_id}` | Set roles for a collection | system_admin |

### Access matrix

| Action | system_admin | collection_admin | collection_user |
|--------|:-:|:-:|:-:|
| View collection records | ✓ | ✓ | ✓ |
| Create record | ✓ | ✓ | ✓ |
| Edit record fields | ✓ | ✓ | ✓ |
| Change workflow status | ✓ | ✓ | ✓ |
| Delete record | ✓ | ✓ | ✗ |
| View templates | ✓ | ✓ | ✓ |
| Edit/delete templates | ✓ | ✓ | ✗ |
| Manage collection roles | ✓ | ✗ | ✗ |

### `PATCH /api/v1/admin/collection-roles/{collection_id}` — set roles

Replaces the entire set of assignments for the given collection. Users not listed in the request lose their assignment to that collection.

```bash
curl -s -b /tmp/uf.cookies \
  -X PATCH http://localhost:8080/api/v1/admin/collection-roles/soc \
  -H "Content-Type: application/json" \
  -d '{
    "assignments": [
      { "username": "alice", "role": "collection_admin" },
      { "username": "bob",   "role": "collection_user" }
    ]
  }'
```

```json
// Request
{
  "assignments": [
    { "username": "alice", "role": "collection_admin" },
    { "username": "bob",   "role": "collection_user" }
  ]
}

// Response 200 — current assignments for collection soc
{
  "collection_id": "soc",
  "assignments": [
    { "username": "alice", "role": "collection_admin" },
    { "username": "bob",   "role": "collection_user" }
  ]
}
```

| Key | Required | Description |
|-----|----------|-------------|
| `assignments` | ✓ | Array of `{ username, role }` objects |
| `assignments[].username` | ✓ | Username (must exist) |
| `assignments[].role` | ✓ | Collection role: `collection_admin` or `collection_user` |

---

## ADMIN — collections – `/api/v1/admin/collections`

Manage collection YAML definitions. Requires global role `system_admin`. Collections are stored in `data/collections/*.yaml`.

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/v1/admin/collections/` | List all collections | system_admin |
| GET | `/api/v1/admin/collections/{id}/source` | Get raw YAML | system_admin |
| POST | `/api/v1/admin/collections/` | Create collection | system_admin |
| PUT | `/api/v1/admin/collections/{id}` | Update collection YAML | system_admin |
| DELETE | `/api/v1/admin/collections/{id}` | Delete collection | system_admin |

---

## SETTINGS – `/api/v1/settings`

Path settings for data directories. Changes take effect immediately without server restart.

The Settings page in the admin UI shows:
- **Editable settings** (path settings): `records_dir`, `schemas_dir`, `collections_dir` — stored in SQLite, editable via the GUI.
- **Init-time settings** (read-only): branding, auth provider, JWT expiry — loaded from `uniforms.yaml` and `.env` at startup; require a server restart to change.

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/v1/settings/` | Current settings | system_admin |
| PATCH | `/api/v1/settings/` | Update path settings | system_admin |

### Available keys (editable via API)

| Key | Description |
|-----|-------------|
| `records_dir` | Directory for record JSON files (default: `data/records`) |
| `collections_dir` | Directory for collection YAML definitions (default: `data/collections`) |
| `schemas_dir` | Directory for collection template YAML files (default: `data/schemas`) |

### `PATCH /api/v1/settings/`

```bash
curl -s -b /tmp/uf.cookies \
  -X PATCH http://localhost:8080/api/v1/settings/ \
  -H "Content-Type: application/json" \
  -d '{"records_dir": "data/records", "collections_dir": "data/collections", "schemas_dir": "data/schemas"}'
```

```json
// Request
{
  "records_dir": "data/records",
  "collections_dir": "data/collections",
  "schemas_dir": "data/schemas"
}

// Response 200 — current state after update
{
  "records_dir": "data/records",
  "collections_dir": "data/collections",
  "schemas_dir": "data/schemas"
}
```

---

## USERS – `/api/v1/users`

Manage user accounts. Requires global role `system_admin`.

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/v1/users/` | List all users | system_admin |
| POST | `/api/v1/users/` | Create user | system_admin |
| GET | `/api/v1/users/{username}` | Get user | system_admin |
| PATCH | `/api/v1/users/{username}` | Update role, status, or password | system_admin |
| DELETE | `/api/v1/users/{username}` | Delete user | system_admin |
| GET | `/api/v1/users/{username}/collection-roles` | Get user's collection roles | system_admin |
| PATCH | `/api/v1/users/{username}/collection-roles` | Update user's collection roles | system_admin |

### System roles

| Role | Permissions |
|------|-------------|
| `system_admin` | Full access — manage users, settings, delete records, template editor, manage collection roles |
| `system_reader` | Access only to collections explicitly assigned in `collection_roles` |

### `POST /api/v1/users/` — create user

```bash
curl -s -b /tmp/uf.cookies \
  -X POST http://localhost:8080/api/v1/users/ \
  -H "Content-Type: application/json" \
  -d '{"username": "jsmith", "password": "password123", "role": "system_reader"}'
```

```json
// Request
{ "username": "jsmith", "password": "password123", "role": "system_reader" }

// Response 201
{
  "id": 2,
  "username": "jsmith",
  "role": "system_reader",
  "is_active": true,
  "created_at": "2026-03-05T14:30:22"
}
```

| Key | Required | Description |
|-----|----------|-------------|
| `username` | ✓ | Username (unique) |
| `password` | ✓ | Plaintext password — server stores bcrypt hash |
| `role` | ✓ | System role: `system_admin` or `system_reader` |

### `PATCH /api/v1/users/{username}` — update user

All fields are optional.

```bash
curl -s -b /tmp/uf.cookies \
  -X PATCH http://localhost:8080/api/v1/users/jsmith \
  -H "Content-Type: application/json" \
  -d '{"role": "system_admin", "is_active": true, "password": "newpassword456"}'
```

| Key | Required | Description |
|-----|----------|-------------|
| `role` | | New system role: `system_admin` or `system_reader` |
| `is_active` | | Activate (`true`) or deactivate (`false`) the account |
| `password` | | New password — server stores bcrypt hash |

---

## HTTP status codes

| Code | When |
|------|------|
| 200 OK | Success (GET, PATCH, PUT) |
| 201 Created | Record or user created |
| 204 No Content | Delete or lock release |
| 400 Bad Request | Invalid request body (e.g. invalid template YAML) |
| 401 Unauthorized | Missing or expired JWT token |
| 403 Forbidden | Insufficient permissions (higher role required) |
| 404 Not Found | Record, collection, or template not found |
| 409 Conflict | Template or collection file with this name already exists |
| 415 Unsupported Media Type | Missing `Content-Type: application/json` on POST/PUT/PATCH |
| 423 Locked | Record is locked by another user |

---

## Reference

- Interactive documentation (Swagger UI): http://localhost:8080/api/docs
- Interactive documentation (ReDoc): http://localhost:8080/api/redoc
- Authentication and security: [AUTH.md](AUTH.md)
- Template authoring: [TEMPLATE_AUTHORING.md](TEMPLATE_AUTHORING.md)
- Frontend rendering: [UNIFORMS_JS.md](UNIFORMS_JS.md)
- Installation and deployment: [INSTALL.md](INSTALL.md)
