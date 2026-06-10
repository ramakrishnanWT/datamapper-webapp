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
GET    /api/maps                  list all saved maps
POST   /api/maps                  save a new map (name, input_schema, output_schema, map_content)
GET    /api/maps/<id>             get a specific saved map
DELETE /api/maps/<id>             delete a saved map
GET    /maps                      HTML page listing saved maps
GET    /                          serves the built React app
GET    /<asset>                   static assets from the React build
"""

from __future__ import annotations

import mimetypes
import os
import shutil
import threading
from pathlib import Path

import duckdb
from flask import Flask, abort, jsonify, request, send_file, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = Path(os.environ.get("WORKSPACE_DIR", BASE_DIR / "workspace")).resolve()
SAMPLE_DIR = (BASE_DIR / "sample").resolve()
FRONTEND_DIST = Path(
    os.environ.get(
        "FRONTEND_DIST",
        BASE_DIR / ".kaoto-src" / "packages" / "ui" / "dist",
    )
).resolve()
FLASK_PORT = int(os.environ.get("FLASK_PORT", "5000"))

WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# DuckDB setup
# ---------------------------------------------------------------------------
DB_PATH = Path(os.environ.get("MAPS_DB", BASE_DIR / "maps.duckdb"))
_db_lock = threading.Lock()


def _get_db() -> duckdb.DuckDBPyConnection:
    """Return a per-call connection to the DuckDB file (thread-safe via lock)."""
    con = duckdb.connect(str(DB_PATH))
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS maps (
            id          INTEGER PRIMARY KEY,
            name        VARCHAR NOT NULL,
            input_schema  VARCHAR,
            output_schema VARCHAR,
            map_content   VARCHAR,
            created_at  TIMESTAMP DEFAULT current_timestamp,
            updated_at  TIMESTAMP DEFAULT current_timestamp
        )
        """
    )
    return con


def _next_id(con: duckdb.DuckDBPyConnection) -> int:
    row = con.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM maps").fetchone()
    return row[0]


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
# Maps API — persist input schema, output schema, and map in DuckDB
# ---------------------------------------------------------------------------
@app.get("/api/maps")
def list_maps():
    with _db_lock:
        con = _get_db()
        try:
            rows = con.execute(
                "SELECT id, name, created_at, updated_at FROM maps ORDER BY updated_at DESC"
            ).fetchall()
        finally:
            con.close()
    return jsonify(
        {
            "maps": [
                {"id": r[0], "name": r[1], "created_at": str(r[2]), "updated_at": str(r[3])}
                for r in rows
            ]
        }
    )


@app.post("/api/maps")
def save_map():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        abort(400, description="'name' is required")
    input_schema = body.get("input_schema") or ""
    output_schema = body.get("output_schema") or ""
    map_content = body.get("map_content") or ""
    with _db_lock:
        con = _get_db()
        try:
            new_id = _next_id(con)
            con.execute(
                """
                INSERT INTO maps (id, name, input_schema, output_schema, map_content)
                VALUES (?, ?, ?, ?, ?)
                """,
                [new_id, name, input_schema, output_schema, map_content],
            )
        finally:
            con.close()
    return jsonify({"id": new_id, "name": name}), 201


@app.get("/api/maps/<int:map_id>")
def get_map(map_id: int):
    with _db_lock:
        con = _get_db()
        try:
            row = con.execute(
                "SELECT id, name, input_schema, output_schema, map_content, created_at, updated_at FROM maps WHERE id = ?",
                [map_id],
            ).fetchone()
        finally:
            con.close()
    if row is None:
        abort(404)
    return jsonify(
        {
            "id": row[0],
            "name": row[1],
            "input_schema": row[2],
            "output_schema": row[3],
            "map_content": row[4],
            "created_at": str(row[5]),
            "updated_at": str(row[6]),
        }
    )


@app.delete("/api/maps/<int:map_id>")
def delete_map(map_id: int):
    with _db_lock:
        con = _get_db()
        try:
            exists = con.execute("SELECT 1 FROM maps WHERE id = ?", [map_id]).fetchone()
            if exists is None:
                abort(404)
            con.execute("DELETE FROM maps WHERE id = ?", [map_id])
        finally:
            con.close()
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
@app.get("/maps")
def maps_page():
    return (
        """<!doctype html>
<meta charset="utf-8">
<title>Saved Maps</title>
<style>
  *, *::before, *::after { box-sizing: border-box; }
  body { font: 14px/1.6 system-ui, sans-serif; margin: 0; background: #f5f6fa; color: #222; }
  header { background: #1e1f22; color: #eee; padding: 14px 24px; display: flex; align-items: center; gap: 16px; }
  header h1 { margin: 0; font-size: 1.1rem; font-weight: 600; }
  header a { color: #7ec8e3; font-size: 0.85rem; text-decoration: none; }
  header a:hover { text-decoration: underline; }
  .container { max-width: 960px; margin: 32px auto; padding: 0 20px; }
  .toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
  .toolbar h2 { margin: 0; font-size: 1rem; }
  button { cursor: pointer; border: none; border-radius: 6px; padding: 7px 14px; font-size: 0.85rem; }
  .btn-primary { background: #0078d4; color: #fff; }
  .btn-primary:hover { background: #006cbe; }
  .btn-danger  { background: #d44; color: #fff; }
  .btn-danger:hover  { background: #b33; }
  .btn-secondary { background: #e0e1e5; color: #222; }
  .btn-secondary:hover { background: #cdd0d8; }
  table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.1); }
  th { background: #f0f1f5; font-weight: 600; text-align: left; padding: 10px 14px; font-size: 0.8rem; text-transform: uppercase; letter-spacing: .04em; color: #555; }
  td { padding: 10px 14px; border-top: 1px solid #eee; vertical-align: top; }
  tr:hover td { background: #fafbff; }
  .empty { text-align: center; padding: 40px; color: #888; }
  /* modal */
  .modal-bg { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 100; align-items: center; justify-content: center; }
  .modal-bg.open { display: flex; }
  .modal { background: #fff; border-radius: 10px; width: 680px; max-width: 95vw; max-height: 90vh; display: flex; flex-direction: column; box-shadow: 0 8px 32px rgba(0,0,0,.25); }
  .modal-header { padding: 16px 20px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }
  .modal-header h3 { margin: 0; font-size: 1rem; }
  .modal-close { background: none; border: none; font-size: 1.3rem; cursor: pointer; color: #888; padding: 0; }
  .modal-body { padding: 20px; overflow-y: auto; flex: 1; }
  .modal-footer { padding: 14px 20px; border-top: 1px solid #eee; display: flex; gap: 10px; justify-content: flex-end; }
  label { display: block; font-size: 0.82rem; font-weight: 600; margin-bottom: 4px; color: #444; }
  input[type=text] { width: 100%; padding: 8px 10px; border: 1px solid #ccc; border-radius: 6px; font-size: 0.9rem; }
  textarea { width: 100%; padding: 8px 10px; border: 1px solid #ccc; border-radius: 6px; font-size: 0.82rem; font-family: 'Cascadia Code', 'Fira Code', monospace; resize: vertical; }
  .field { margin-bottom: 14px; }
  #msg { margin-top: 12px; font-size: 0.85rem; }
  .ok { color: #2a7a2a; } .err { color: #c00; }
  .upload-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
  .upload-row label { margin: 0; flex: 1; }
  .upload-btn { font-size: 0.75rem; padding: 3px 10px; background: #e8f0fe; color: #0078d4; border: 1px solid #c0d4f5; border-radius: 5px; cursor: pointer; white-space: nowrap; }
  .upload-btn:hover { background: #d0e4fc; }
  .upload-fname { font-size: 0.72rem; color: #777; max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>

<header>
  <h1>DataMapper — Saved Maps</h1>
  <a href="#" onclick="window.close(); return false;">&#8592; Close &amp; return to DataMapper</a>
</header>

<div class="container">
  <div class="toolbar">
    <h2 id="count">Loading&hellip;</h2>
    <button class="btn-primary" onclick="openSaveModal()">+ Save New Map</button>
  </div>
  <table id="tbl">
    <thead><tr><th>#</th><th>Name</th><th>Saved</th><th>Actions</th></tr></thead>
    <tbody id="tbody"><tr><td colspan="4" class="empty">Loading&hellip;</td></tr></tbody>
  </table>
</div>

<!-- Save modal -->
<div class="modal-bg" id="saveModal">
  <div class="modal">
    <div class="modal-header">
      <h3>Save Map</h3>
      <button class="modal-close" onclick="closeModal('saveModal')">&times;</button>
    </div>
    <div class="modal-body">
      <div class="field"><label>Map Name *</label><input type="text" id="mapName" placeholder="e.g. order-to-invoice-v1"></div>
      <div class="field">
        <div class="upload-row">
          <label>Input Schema</label>
          <label class="upload-btn" title="Upload JSON Schema (.json) or XML Schema (.xsd)">&#128194; Upload file<input type="file" accept=".json,.schema.json,.xsd,.xml" style="display:none" onchange="readUpload(this,'inputSchema','inFname')"></label>
          <span class="upload-fname" id="inFname"></span>
        </div>
        <textarea id="inputSchema" rows="5" placeholder='Paste JSON Schema / XSD or upload a file above...'></textarea>
      </div>
      <div class="field">
        <div class="upload-row">
          <label>Output Schema</label>
          <label class="upload-btn" title="Upload JSON Schema (.json) or XML Schema (.xsd)">&#128194; Upload file<input type="file" accept=".json,.schema.json,.xsd,.xml" style="display:none" onchange="readUpload(this,'outputSchema','outFname')"></label>
          <span class="upload-fname" id="outFname"></span>
        </div>
        <textarea id="outputSchema" rows="5" placeholder='Paste JSON Schema / XSD or upload a file above...'></textarea>
      </div>
      <div class="field">
        <div class="upload-row">
          <label>Map Content (XSLT / .dmf)</label>
          <label class="upload-btn" title="Upload a .xsl or .dmf file">&#128194; Upload file<input type="file" accept=".xsl,.xslt,.dmf,.camel.yaml,.yaml" style="display:none" onchange="readUpload(this,'mapContent','mapFname')"></label>
          <span class="upload-fname" id="mapFname"></span>
        </div>
        <textarea id="mapContent" rows="7" placeholder='Paste XSLT/DMF or upload a file above...'></textarea>
      </div>
      <div id="msg"></div>
    </div>
    <div class="modal-footer">
      <button class="btn-secondary" onclick="closeModal('saveModal')">Cancel</button>
      <button class="btn-primary" onclick="doSave()">Save</button>
    </div>
  </div>
</div>

<!-- View modal -->
<div class="modal-bg" id="viewModal">
  <div class="modal">
    <div class="modal-header">
      <h3 id="viewTitle">Map Detail</h3>
      <button class="modal-close" onclick="closeModal('viewModal')">&times;</button>
    </div>
    <div class="modal-body">
      <div class="field"><label>Input Schema</label><textarea id="vInputSchema" rows="8" readonly></textarea></div>
      <div class="field"><label>Output Schema</label><textarea id="vOutputSchema" rows="8" readonly></textarea></div>
      <div class="field"><label>Map Content</label><textarea id="vMapContent" rows="10" readonly></textarea></div>
    </div>
    <div class="modal-footer">
      <button class="btn-secondary" onclick="closeModal('viewModal')">Close</button>
    </div>
  </div>
</div>

<script>
async function loadMaps() {
  const res = await fetch('/api/maps');
  const data = await res.json();
  const tbody = document.getElementById('tbody');
  document.getElementById('count').textContent = data.maps.length + ' saved map(s)';
  if (!data.maps.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty">No maps saved yet. Click "+ Save New Map" to get started.</td></tr>';
    return;
  }
  tbody.innerHTML = data.maps.map(m => `
    <tr>
      <td>${m.id}</td>
      <td><strong>${esc(m.name)}</strong></td>
      <td>${new Date(m.updated_at).toLocaleString()}</td>
      <td style="white-space:nowrap">
        <button class="btn-secondary" onclick="viewMap(${m.id}, '${esc(m.name)}')">View</button>
        &nbsp;
        <button class="btn-danger" onclick="deleteMap(${m.id}, '${esc(m.name)}')">Delete</button>
      </td>
    </tr>`).join('');
}

function esc(s) { return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

function readUpload(input, textareaId, fnameId) {
  const file = input.files[0];
  if (!file) return;
  document.getElementById(fnameId).textContent = file.name;
  const reader = new FileReader();
  reader.onload = e => { document.getElementById(textareaId).value = e.target.result; };
  reader.readAsText(file);
}

function openSaveModal() {
  document.getElementById('mapName').value = '';
  document.getElementById('inputSchema').value = '';
  document.getElementById('outputSchema').value = '';
  document.getElementById('mapContent').value = '';
  document.getElementById('msg').textContent = '';
  ['inFname','outFname','mapFname'].forEach(id => document.getElementById(id).textContent = '');
  document.getElementById('saveModal').classList.add('open');
}

function closeModal(id) { document.getElementById(id).classList.remove('open'); }

async function doSave() {
  const name = document.getElementById('mapName').value.trim();
  const msg = document.getElementById('msg');
  if (!name) { msg.className = 'err'; msg.textContent = 'Name is required.'; return; }
  msg.className = ''; msg.textContent = 'Saving…';
  try {
    const res = await fetch('/api/maps', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        name,
        input_schema:  document.getElementById('inputSchema').value,
        output_schema: document.getElementById('outputSchema').value,
        map_content:   document.getElementById('mapContent').value,
      })
    });
    if (!res.ok) throw new Error(await res.text());
    const d = await res.json();
    msg.className = 'ok'; msg.textContent = 'Saved as ID ' + d.id;
    await loadMaps();
    setTimeout(() => closeModal('saveModal'), 800);
  } catch (e) { msg.className = 'err'; msg.textContent = 'Error: ' + e.message; }
}

async function viewMap(id, name) {
  const res = await fetch('/api/maps/' + id);
  if (!res.ok) { alert('Could not load map.'); return; }
  const d = await res.json();
  document.getElementById('viewTitle').textContent = name + ' (#' + id + ')';
  document.getElementById('vInputSchema').value  = d.input_schema  || '(empty)';
  document.getElementById('vOutputSchema').value = d.output_schema || '(empty)';
  document.getElementById('vMapContent').value   = d.map_content   || '(empty)';
  document.getElementById('viewModal').classList.add('open');
}

async function deleteMap(id, name) {
  if (!confirm('Delete map "' + name + '"?')) return;
  const res = await fetch('/api/maps/' + id, { method: 'DELETE' });
  if (!res.ok) { alert('Delete failed.'); return; }
  await loadMaps();
}

// Close modal on background click
document.querySelectorAll('.modal-bg').forEach(bg => bg.addEventListener('click', e => { if (e.target === bg) bg.classList.remove('open'); }));

loadMaps();
</script>
""",
        200,
        {"Content-Type": "text/html"},
    )


_TOOLBAR_HTML = """
<!-- ── DXM floating toolbar ─────────────────────────────────────────── -->
<style>
  #dxm-bar{position:fixed;top:12px;right:16px;z-index:99999;display:flex;gap:8px;align-items:center;
    background:rgba(30,31,34,.92);backdrop-filter:blur(6px);border:1px solid rgba(255,255,255,.12);
    border-radius:10px;padding:7px 14px;box-shadow:0 4px 18px rgba(0,0,0,.4);font-family:system-ui,sans-serif;font-size:13px;}
  #dxm-bar a{color:#7ec8e3;text-decoration:none;font-weight:500;}
  #dxm-bar a:hover{text-decoration:underline;}
  #dxm-bar button{cursor:pointer;border:none;border-radius:6px;padding:5px 12px;
    font-size:12px;font-weight:600;background:#0078d4;color:#fff;}
  #dxm-bar button:hover{background:#006cbe;}
  /* modal */
  #dxm-modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:999999;
    align-items:center;justify-content:center;}
  #dxm-modal-bg.open{display:flex;}
  #dxm-modal{background:#fff;border-radius:10px;width:540px;max-width:96vw;max-height:92vh;
    display:flex;flex-direction:column;box-shadow:0 8px 32px rgba(0,0,0,.3);color:#222;overflow:hidden;font-family:system-ui,sans-serif;}
  #dxm-modal .mh{padding:14px 18px;border-bottom:1px solid #eee;display:flex;justify-content:space-between;align-items:center;}
  #dxm-modal .mh h3{margin:0;font-size:1rem;}
  #dxm-modal .mh button{background:none;border:none;font-size:1.3rem;cursor:pointer;color:#888;}
  #dxm-modal .mb{padding:16px 18px;overflow-y:auto;flex:1;}
  #dxm-modal .mf{padding:12px 18px;border-top:1px solid #eee;display:flex;gap:10px;justify-content:flex-end;align-items:center;}
  .dxm-field{margin-bottom:14px;}
  .dxm-field-hdr{display:flex;align-items:center;gap:8px;margin-bottom:4px;}
  .dxm-field-hdr label{font-size:0.78rem;font-weight:600;color:#444;flex:1;margin:0;}
  .dxm-field-hdr .badge{font-size:0.65rem;padding:1px 6px;border-radius:10px;font-weight:600;}
  .badge-required{background:#fde8e8;color:#b00;}
  .badge-auto{background:#e6f4ea;color:#1a7a2a;}
  .badge-optional{background:#f0f0f0;color:#666;}
  #dxm-modal input[type=text]{width:100%;padding:8px 10px;border:1px solid #ccc;border-radius:5px;font-size:0.92rem;box-sizing:border-box;}
  .dxm-upload-row{display:flex;align-items:center;gap:8px;}
  .dxm-upload-btn{font-size:0.72rem;padding:3px 10px;background:#e8f0fe;color:#0078d4;
    border:1px solid #c0d4f5;border-radius:4px;cursor:pointer;white-space:nowrap;flex-shrink:0;}
  .dxm-upload-btn:hover{background:#d0e4fc;}
  .dxm-fname{font-size:0.7rem;color:#555;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;flex:1;}
  .dxm-fname.empty{color:#aaa;font-style:italic;}
  .dxm-map-status{font-size:0.73rem;margin-top:4px;display:flex;align-items:center;gap:5px;}
  .dxm-map-status .dot{width:7px;height:7px;border-radius:50%;background:#ccc;flex-shrink:0;}
  .dxm-map-status .dot.ok{background:#2a7a2a;} .dxm-map-status .dot.empty{background:#e0a000;}
  .dxm-map-status .dot.loading{background:#0078d4;animation:dxmpulse 1s infinite;}
  @keyframes dxmpulse{0%,100%{opacity:1}50%{opacity:.3}}
  #dxm-msg{font-size:0.8rem;margin-top:6px;}
  #dxm-msg.ok{color:#1a7a2a;} #dxm-msg.err{color:#c00;}
  .btn-ok{background:#0078d4;color:#fff;border:none;border-radius:6px;padding:7px 16px;cursor:pointer;font-size:0.85rem;font-weight:600;}
  .btn-ok:hover{background:#006cbe;} .btn-ok:disabled{background:#8ab8e0;cursor:default;}
  .btn-cn{background:#e0e1e5;color:#222;border:none;border-radius:6px;padding:7px 14px;cursor:pointer;font-size:0.85rem;}
  .dxm-hint{font-size:0.72rem;color:#888;margin-top:3px;line-height:1.4;}
</style>

<div id="dxm-bar">
  <span style="color:#aaa;font-size:11px;font-weight:600;letter-spacing:.05em">DXM</span>
  <button id="dxm-save-ws-btn" onclick="dxmSaveToWorkspace()">&#128427; Save XSLT</button>
  <button onclick="dxmOpenSave()">&#128190; Save Map</button>
  <a href="/maps" target="_blank">&#128203; Saved Maps &#8599;</a>
</div>

<div id="dxm-modal-bg">
  <div id="dxm-modal">
    <div class="mh">
      <h3>Save Current Map</h3>
      <button onclick="dxmClose()">&times;</button>
    </div>
    <div class="mb">

      <!-- Name -->
      <div class="dxm-field">
        <div class="dxm-field-hdr"><label>Map Name <span class="badge badge-required">required</span></label></div>
        <input type="text" id="dxm-name" placeholder="e.g. order-to-invoice-v1" autocomplete="off">
      </div>

      <!-- Info banner -->
      <div style="font-size:0.75rem;color:#555;background:#f5f5f5;border-radius:5px;padding:8px 10px;margin-bottom:14px;line-height:1.5;">
        &#9432; Content is auto-captured from the workspace. Upload a file to override any field.
      </div>

      <!-- Input Schema -->
      <div class="dxm-field">
        <div class="dxm-field-hdr">
          <label>Input Schema <span class="badge" id="dxm-in-badge">checking&hellip;</span></label>
        </div>
        <div class="dxm-upload-row">
          <label class="dxm-upload-btn">&#128194; Override
            <input type="file" accept=".json,.schema.json,.xsd,.xml" style="display:none" onchange="dxmReadFile(this,'in','dxm-in-fn')">
          </label>
          <span class="dxm-fname empty" id="dxm-in-fn">Checking workspace&hellip;</span>
        </div>
        <input type="hidden" id="dxm-in">
      </div>

      <!-- Output Schema -->
      <div class="dxm-field">
        <div class="dxm-field-hdr">
          <label>Output Schema <span class="badge" id="dxm-out-badge">checking&hellip;</span></label>
        </div>
        <div class="dxm-upload-row">
          <label class="dxm-upload-btn">&#128194; Override
            <input type="file" accept=".json,.schema.json,.xsd,.xml" style="display:none" onchange="dxmReadFile(this,'out','dxm-out-fn')">
          </label>
          <span class="dxm-fname empty" id="dxm-out-fn">Checking workspace&hellip;</span>
        </div>
        <input type="hidden" id="dxm-out">
      </div>

      <!-- Map Content / XSLT -->
      <div class="dxm-field">
        <div class="dxm-field-hdr">
          <label>Map Content (XSLT) <span class="badge" id="dxm-map-badge">checking&hellip;</span></label>
        </div>
        <div class="dxm-upload-row">
          <label class="dxm-upload-btn">&#128194; Override
            <input type="file" accept=".xsl,.xslt,.dmf,.yaml" style="display:none" onchange="dxmReadFile(this,'map','dxm-map-fn')">
          </label>
          <span class="dxm-fname empty" id="dxm-map-fn">Checking workspace&hellip;</span>
        </div>
        <input type="hidden" id="dxm-map">
      </div>

      <div id="dxm-msg"></div>
    </div>
    <div class="mf">
      <button class="btn-cn" onclick="dxmClose()">Cancel</button>
      <button class="btn-ok" id="dxm-save-btn" onclick="dxmSave()">Save to DuckDB</button>
    </div>
  </div>
</div>

<script>
(function(){
  // Store content in JS variables — avoids any DOM reference issues
  const _data = { in: '', out: '', map: '' };

  function setBadge(key, hasContent){
    const badge = document.getElementById('dxm-' + key + '-badge');
    if(!badge) return;
    if(hasContent){
      badge.textContent = 'captured \u2713';
      badge.className = 'badge badge-auto';
    } else {
      badge.textContent = 'not found \u2014 upload to add';
      badge.className = 'badge badge-optional';
    }
  }

  function setFname(key, text, isEmpty){
    const el = document.getElementById('dxm-' + key + '-fn');
    if(!el) return;
    el.textContent = text;
    el.className = 'dxm-fname' + (isEmpty ? ' empty' : '');
  }

  window.dxmReadFile = function(input, key, fnameId){
    const file = input.files[0];
    if(!file) return;
    setFname(key, file.name, false);
    setBadge(key, true);
    const r = new FileReader();
    r.onload = e => { _data[key] = e.target.result; };
    r.readAsText(file);
  };

  async function dxmLoadSnapshot(){
    // Reset badges to loading
    ['in','out','map'].forEach(k => {
      const b = document.getElementById('dxm-' + k + '-badge');
      if(b){ b.textContent = 'checking\u2026'; b.className = 'badge badge-auto'; }
      setFname(k, 'Checking workspace\u2026', true);
    });
    try{
      const r = await fetch('/api/workspace-snapshot');
      if(!r.ok) throw new Error('HTTP ' + r.status);
      const d = await r.json();
      _data.in  = d.input_schema  || '';
      _data.out = d.output_schema || '';
      _data.map = d.map_content   || '';
      setBadge('in',  !!_data.in);
      setBadge('out', !!_data.out);
      setBadge('map', !!_data.map);
      setFname('in',  _data.in  ? 'Captured from workspace' : 'Not found \u2014 upload above', !_data.in);
      setFname('out', _data.out ? 'Captured from workspace' : 'Not found \u2014 upload above', !_data.out);
      setFname('map', _data.map ? 'Captured from workspace' : 'Not found \u2014 save in Kaoto (Ctrl+S) first or upload', !_data.map);
    }catch(e){
      ['in','out','map'].forEach(k => {
        setBadge(k, false);
        setFname(k, 'Could not read workspace \u2014 upload above', true);
      });
    }
  }

  window.dxmOpenSave = function(){
    _data.in = ''; _data.out = ''; _data.map = '';
    document.getElementById('dxm-name').value = '';
    document.getElementById('dxm-msg').textContent = '';
    document.getElementById('dxm-modal-bg').classList.add('open');
    setTimeout(() => document.getElementById('dxm-name').focus(), 60);
    dxmLoadSnapshot();
  };

  window.dxmClose = function(){
    document.getElementById('dxm-modal-bg').classList.remove('open');
  };

  window.dxmSave = async function(){
    const name = document.getElementById('dxm-name').value.trim();
    const msg  = document.getElementById('dxm-msg');
    if(!name){ msg.className='err'; msg.textContent='Name is required.'; return; }
    msg.className=''; msg.textContent='Saving\u2026';
    const btn = document.getElementById('dxm-save-btn');
    btn.disabled = true;
    try{
      const res = await fetch('/api/maps',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          name,
          input_schema:  _data.in,
          output_schema: _data.out,
          map_content:   _data.map,
        })
      });
      if(!res.ok) throw new Error(await res.text());
      const d = await res.json();
      msg.className='ok'; msg.textContent='\u2713 Saved as \u201c'+name+'\u201d (ID '+d.id+')';
      setTimeout(()=>dxmClose(), 1200);
    }catch(e){
      msg.className='err'; msg.textContent='Error: '+e.message;
    }finally{
      btn.disabled = false;
    }
  };

  // ── Save XSLT to workspace (triggers Kaoto's own Ctrl+S handler) ──
  window.dxmSaveToWorkspace = function(){
    const btn = document.getElementById('dxm-save-ws-btn');
    const orig = btn.textContent;
    // Dispatch Ctrl+S into the Kaoto app iframe/document so it writes the XSLT
    const ev = new KeyboardEvent('keydown', {
      key: 's', code: 'KeyS', ctrlKey: true, metaKey: false,
      bubbles: true, cancelable: true
    });
    document.dispatchEvent(ev);
    btn.textContent = '\u2713 Saved!';
    btn.disabled = true;
    setTimeout(() => { btn.textContent = orig; btn.disabled = false; }, 1500);
  };

  document.getElementById('dxm-modal-bg').addEventListener('click', function(e){
    if(e.target===this) dxmClose();
  });
  document.getElementById('dxm-name').addEventListener('keydown', function(e){
    if(e.key==='Enter') dxmSave();
  });
})();
</script>

<!-- ── end DXM toolbar ───────────────────────────────────────────────── -->
"""


@app.get("/api/workspace-snapshot")
def workspace_snapshot():
    """Auto-detect current workspace files and return them bucketed by type."""
    input_parts: list[str] = []
    output_parts: list[str] = []
    map_parts: list[str] = []

    for root, _dirs, files in os.walk(WORKSPACE_DIR):
        for fname in sorted(files):
            full = Path(root) / fname
            try:
                text = full.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            low = fname.lower()
            _INPUT_KW  = ("input", "source", "src", "-in.", "_in.", "-in-", "_in_")
            _OUTPUT_KW = ("output", "target", "dest", "-out.", "_out.", "-out-", "_out_")
            if low.endswith(".schema.json") or low.endswith(".xsd"):
                # Both JSON Schema and XSD can be used for input or output.
                # Determine direction from filename keywords; fall back to
                # extension (.schema.json → input, .xsd → output) when ambiguous.
                comment = f"<!-- {fname} -->" if low.endswith(".xsd") else f"// {fname}"
                if any(kw in low for kw in _INPUT_KW):
                    input_parts.append(f"{comment}\n{text}")
                elif any(kw in low for kw in _OUTPUT_KW):
                    output_parts.append(f"{comment}\n{text}")
                elif low.endswith(".schema.json"):
                    input_parts.append(f"{comment}\n{text}")
                else:
                    output_parts.append(f"{comment}\n{text}")
            elif low.endswith(".dmf") or low.endswith(".camel.yaml"):
                map_parts.append(f"# {fname}\n{text}")
            elif low.endswith(".xsl") or low.endswith(".xslt"):
                map_parts.append(f"<!-- {fname} -->\n{text}")

    return jsonify(
        {
            "input_schema": "\n\n".join(input_parts),
            "output_schema": "\n\n".join(output_parts),
            "map_content": "\n\n".join(map_parts),
        }
    )


@app.get("/")
def index():
    if not FRONTEND_DIST.exists():
        return _frontend_not_built_page()
    html = (FRONTEND_DIST / "index.html").read_text(encoding="utf-8")
    # Inject toolbar before closing </body> (or at end if tag absent)
    if "</body>" in html:
        html = html.replace("</body>", _TOOLBAR_HTML + "</body>", 1)
    else:
        html += _TOOLBAR_HTML
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.get("/<path:asset>")
def static_assets(asset: str):
    """Serve any file from the built Kaoto dist, falling back to index.html for
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
<pre>python scripts/setup_kaoto.py
python scripts/run_app.py</pre>
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
