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
|---|---|
| B-01 | `GET /api/files` — list all files in the sandboxed workspace. |
| B-02 | `GET /api/files/<path>` — read a file from the workspace (raw bytes). |
| B-03 | `PUT /api/files/<path>` — create or overwrite a file in the workspace. |
| B-04 | `DELETE /api/files/<path>` — delete a file or empty directory. |
| B-05 | `HEAD /api/files/<path>` — check whether a file exists (200/404). |
| B-06 | All file paths shall be resolved under `WORKSPACE_DIR`; path-traversal attempts shall return HTTP 400. |
| B-07 | `GET /api/samples` — list bundled sample files from the `sample/` directory. |
| B-08 | `POST /api/samples/<name>/copy` — copy a named sample into the workspace. |
| B-09 | `GET /api/health` — liveness check, returns `{"status": "ok"}`. |

### 3.3 Build & Setup

| ID | Requirement |
|---|---|
| S-01 | `scripts/setup_kaoto.py` shall clone Kaoto from source, apply `scripts/kaoto.patch`, and produce the built frontend at `.kaoto-src/packages/ui/dist/`. |
| S-02 | `scripts/run_app.py` shall start the Flask server on `FLASK_PORT` (default 5000). |
| S-03 | A Docker multi-stage `Dockerfile` shall produce a self-contained image tagged `data-exchange-mapper:latest`. |
| S-04 | `docker-compose.yml` shall expose the app on `DXM_PORT` (default 5000). |

---

## 4. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NF-01 | The workspace sandbox must reject all path-traversal attempts (OWASP A01). |
| NF-02 | The Flask app shall start in under 3 seconds on local hardware. |
| NF-03 | The Docker image build shall complete in under 10 minutes on a standard CI runner. |
| NF-04 | The backend test suite shall complete in under 30 seconds. |
| NF-05 | No secrets or credentials shall be baked into the Docker image. |

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
