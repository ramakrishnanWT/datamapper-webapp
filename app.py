"""
DataMapper Web App — Flask backend
==================================

Hosts the React frontend (which embeds Kaoto's DataMapper component)
and exposes a sandboxed file-system REST API. That API is what the
frontend wires up as Kaoto's ``IMetadataApi`` so the DataMapper can
read JSON Schemas / XSDs, persist `.dmf` mapping files, and write the
generated `.xsl` output to disk.

Sandbox
-------
Every file path coming from the frontend is resolved under WORKSPACE_DIR
(``./workspace`` by default). Path-traversal attempts (``..`` etc.) are
rejected with HTTP 400.

Routes
------
GET    /api/files                 list files in the workspace
GET    /api/files/<path>          read a file (raw bytes)
PUT    /api/files/<path>          create/overwrite a file (raw bytes)
DELETE /api/files/<path>          delete a file or empty directory
HEAD   /api/files/<path>          check existence (200 / 404)
GET    /api/samples               list bundled sample files
POST   /api/samples/<name>/copy   copy a sample into the workspace
GET    /api/health                liveness check
GET    /                          serves the built React app
GET    /<asset>                   static assets from the React build
"""

from __future__ import annotations

import mimetypes
import os
import shutil
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = Path(os.environ.get("WORKSPACE_DIR", BASE_DIR / "workspace")).resolve()
SAMPLE_DIR = (BASE_DIR / "sample").resolve()
FRONTEND_DIST = Path(
    os.environ.get("FRONTEND_DIST", BASE_DIR / "frontend" / "dist")
).resolve()
FLASK_PORT = int(os.environ.get("FLASK_PORT", "5000"))

WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=None)


# ---------------------------------------------------------------------------
# Sandboxing
# ---------------------------------------------------------------------------
def _safe_path(rel: str) -> Path:
    """Resolve `rel` under WORKSPACE_DIR; abort 400 on traversal attempts."""
    if not rel or rel.startswith(("/", "\\")) or ".." in rel.replace("\\", "/").split("/"):
        abort(400, description="Invalid path")
    target = (WORKSPACE_DIR / rel).resolve()
    try:
        target.relative_to(WORKSPACE_DIR)
    except ValueError:
        abort(400, description="Path escapes workspace")
    return target


def _rel(p: Path) -> str:
    return p.relative_to(WORKSPACE_DIR).as_posix()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "workspace": str(WORKSPACE_DIR),
            "frontend_built": FRONTEND_DIST.exists(),
        }
    )


# ---------------------------------------------------------------------------
# File API — the thing the Kaoto DataMapper IMetadataApi will call
# ---------------------------------------------------------------------------
@app.get("/api/files")
def list_files():
    """Return a flat list of every file under the workspace."""
    out = []
    for root, _dirs, files in os.walk(WORKSPACE_DIR):
        for f in files:
            full = Path(root) / f
            out.append(
                {
                    "path": _rel(full),
                    "size": full.stat().st_size,
                    "mtime": full.stat().st_mtime,
                }
            )
    return jsonify({"files": sorted(out, key=lambda x: x["path"])})


@app.get("/api/files/<path:rel>")
def read_file(rel: str):
    p = _safe_path(rel)
    if not p.exists() or not p.is_file():
        abort(404)
    mt, _ = mimetypes.guess_type(p.name)
    return send_file(p, mimetype=mt or "application/octet-stream", as_attachment=False)


@app.route("/api/files/<path:rel>", methods=["HEAD"])
def head_file(rel: str):
    p = _safe_path(rel)
    if not p.exists() or not p.is_file():
        return ("", 404)
    return ("", 200)


@app.put("/api/files/<path:rel>")
def write_file(rel: str):
    p = _safe_path(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Accept raw body. Also accept JSON {content: "..."} for convenience.
    body = request.get_data()
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        if "content" in payload:
            body = payload["content"].encode("utf-8")
    p.write_bytes(body)
    return jsonify({"path": _rel(p), "size": p.stat().st_size})


@app.delete("/api/files/<path:rel>")
def delete_file(rel: str):
    p = _safe_path(rel)
    if not p.exists():
        abort(404)
    if p.is_file():
        p.unlink()
    elif p.is_dir():
        try:
            p.rmdir()
        except OSError:
            abort(409, description="Directory not empty")
    return ("", 204)


# ---------------------------------------------------------------------------
# Sample bootstrap — lets the frontend offer "load demo" buttons
# ---------------------------------------------------------------------------
@app.get("/api/samples")
def list_samples():
    if not SAMPLE_DIR.exists():
        return jsonify({"samples": []})
    items = []
    for f in sorted(SAMPLE_DIR.iterdir()):
        if f.is_file():
            items.append({"name": f.name, "size": f.stat().st_size})
    return jsonify({"samples": items})


@app.post("/api/samples/<name>/copy")
def copy_sample(name: str):
    if "/" in name or "\\" in name or ".." in name:
        abort(400)
    src = SAMPLE_DIR / name
    if not src.exists() or not src.is_file():
        abort(404)
    dest = WORKSPACE_DIR / name
    shutil.copyfile(src, dest)
    return jsonify({"path": _rel(dest), "size": dest.stat().st_size})


# ---------------------------------------------------------------------------
# Frontend hosting
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    if not FRONTEND_DIST.exists():
        return _frontend_not_built_page()
    return send_from_directory(FRONTEND_DIST, "index.html")


@app.get("/<path:asset>")
def static_assets(asset: str):
    """Serve any file from frontend/dist, falling back to index.html for
    client-side routes (SPA behaviour)."""
    if not FRONTEND_DIST.exists():
        return _frontend_not_built_page()
    candidate = (FRONTEND_DIST / asset).resolve()
    try:
        candidate.relative_to(FRONTEND_DIST)
    except ValueError:
        abort(404)
    if candidate.is_file():
        return send_from_directory(FRONTEND_DIST, asset)
    # SPA fallback
    return send_from_directory(FRONTEND_DIST, "index.html")


def _frontend_not_built_page():
    return (
        """<!doctype html><meta charset="utf-8"><title>Frontend not built</title>
<style>body{font:14px/1.5 system-ui,sans-serif;max-width:720px;margin:60px auto;padding:0 20px;color:#222}
pre{background:#1e1f22;color:#eee;padding:14px;border-radius:6px;overflow:auto}</style>
<h1>Frontend not built yet</h1>
<p>Run the setup + build steps:</p>
<pre>cd frontend
npm install
npm run build</pre>
<p>Then refresh this page. Backend API is up at
<a href="/api/health">/api/health</a>.</p>""",
        200,
        {"Content-Type": "text/html"},
    )


if __name__ == "__main__":
    print(f" * Workspace: {WORKSPACE_DIR}")
    print(f" * Frontend dist: {FRONTEND_DIST} (exists: {FRONTEND_DIST.exists()})")
    print(f" * Serving on http://127.0.0.1:{FLASK_PORT}")
    app.run(host="127.0.0.1", port=FLASK_PORT, debug=True, threaded=True)
