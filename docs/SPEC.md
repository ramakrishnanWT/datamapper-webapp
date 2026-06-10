# Functional Specification — Data eXchange Mapper (DXM)

> **Project shorthand:** DXM = Data eXchange Mapper  
> **Repo:** `datamapper-webapp`  
> **Status:** Living document — update alongside feature work.

---

## 1. Purpose

DXM is a browser-based visual data mapping and XSLT generation tool. It exposes the full Kaoto DataMapper experience (normally disabled in public Kaoto builds) via a Flask host that provides the `IMetadataApi` implementation the DataMapper requires.

---

## 2. Actors

| Actor | Description |
|---|---|
| Integration Engineer | Primary user — designs JSON↔XML mappings visually |
| Developer | Runs DXM locally; consumes generated XSLT in Camel routes |
| CI Pipeline | Builds the container image; runs automated tests |

---

## 3. Functional Requirements

### 3.1 Frontend — Kaoto DataMapper UI

| ID | Requirement |
|---|---|
| F-01 | The app shall serve the full Kaoto UI (built from source) at `/`. |
| F-02 | The DataMapper view shall be enabled and accessible from the Kaoto sidebar. |
| F-03 | Users shall be able to attach a JSON Schema (`.schema.json`) as the input document. |
| F-04 | Users shall be able to attach an XSD (`.xsd`) as the output document. |
| F-05 | Users shall be able to drag-and-drop fields to create mapping relationships. |
| F-06 | Users shall be able to generate and download XSLT 3.0 output from the mapped design. |
| F-07 | Mapping state shall persist across browser refreshes via `localStorage`. |

### 3.2 Backend — File API

| ID | Requirement |
|---|
---|
| B-01 | `GET /api/files` — list all files in the sandboxed workspace. |
| B-02 | `GET /api/files/<path>` — read a file from the workspace (raw bytes). |
| B-03 | `PUT /api/files/<path>` — create or overwrite a file in the workspace. |
| B-04 | `DELETE /api/files/<path>` — delete a file or empty directory. |
| B-05 | `HEAD /api/files/<path>` — check whether a file exists (200/404). |
| B-06 | All file paths shall be resolved under `WORKSPACE_DIR`; path-traversal attempts shall return HTTP 400. |
| B-07 | `GET /api/samples` — list bundled sample files from the `sample/` directory. |
| B-08 | `POST /api/samples/<name>/copy` — copy a named sample into the workspace. |
| B-09 | `GET /api/health` — liveness check, returns `{"status": "ok"}`. |

### 3.3 Backend — Saved Maps API (DuckDB)

| ID | Requirement |
|---|---|
| M-01 | `GET /api/maps` — return a list of all saved maps (id, name, created_at, updated_at). |
| M-02 | `POST /api/maps` — save a new map; body: `{ name, input_schema, output_schema, map_content }`. Name is required; returns 201 with `{ id, name }`. |
| M-03 | `GET /api/maps/<id>` — return all fields for one saved map. |
| M-04 | `DELETE /api/maps/<id>` — delete a saved map; returns 204. |
| M-05 | Maps shall be stored in a DuckDB file (`maps.duckdb`) whose path is controlled by the `MAPS_DB` environment variable. |
| M-06 | The `maps` table shall store: `id` (integer PK), `name` (varchar), `input_schema` (varchar), `output_schema` (varchar), `map_content` (varchar), `created_at` / `updated_at` (timestamp). |
| M-07 | Input and output schemas shall accept both JSON Schema (`.json`) and XML Schema (`.xsd`) content. |
| M-08 | `GET /api/workspace-snapshot` — scan the workspace and return current files bucketed by type (`input_schema`, `output_schema`, `map_content`) to pre-fill the save dialog. |
| M-09 | `GET /maps` — serve a standalone HTML page listing all saved maps with View and Delete actions. |
| M-10 | The Kaoto SPA page (`/`) shall include a floating toolbar with a **Save Map** button and a link to the Saved Maps page. |
| M-11 | The Save Map dialog shall support file upload (client-side `FileReader`) for all three fields in addition to paste. |
| M-12 | The Save Map dialog shall auto-populate fields from the workspace snapshot on open. |

### 3.4 Build & Setup

| ID | Requirement |
|---|---|
| S-01 | `scripts/setup_kaoto.py` shall clone Kaoto from source, apply `scripts/kaoto.patch`, and produce the built frontend at `.kaoto-src/packages/ui/dist/`. |
| S-02 | `scripts/run_app.py` shall start the Flask server on `FLASK_PORT` (default 5000). |
| S-03 | A Docker multi-stage `Dockerfile` shall produce a self-contained image tagged `data-exchange-mapper:latest`. |
| S-04 | `docker-compose.yml` shall expose the app on `DXM_PORT` (default 8080) and persist the DuckDB maps store in a named Docker volume (`maps_data`). |
| S-05 | The Docker deployment shall run a single Gunicorn worker to avoid multi-process DuckDB file conflicts. |

---

## 4. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NF-01 | The workspace sandbox must reject all path-traversal attempts (OWASP A01). |
| NF-02 | The Flask app shall start in under 3 seconds on local hardware. |
| NF-03 | The Docker image build shall complete in under 10 minutes on a standard CI runner. |
| NF-04 | The backend test suite shall complete in under 30 seconds. |
| NF-05 | No secrets or credentials shall be baked into the Docker image. |
| NF-06 | Saved maps shall survive container restarts (persisted in a named Docker volume). |
| NF-07 | The DuckDB store shall not be corrupted by concurrent requests (single-worker + threading lock). |

---

## 5. Constraints & Assumptions

- Kaoto is cloned at build time; the patch must apply cleanly to the pinned ref.
- The frontend state (`localStorage`) is browser-local; no server-side session is maintained.
- The file API is intended for local/trusted deployments only. Shared deployments must add auth (see B-06 / PLAN.md).
- XSLT output is compatible with Apache Camel's Saxon processor.

---

## 6. Out of Scope (v1)

- User authentication / multi-user sessions
- Server-side XSLT execution / testing
- Live collaboration / shared workspaces
- Support for EDI or flat-file schemas
- Map versioning / diff history
