from __future__ import annotations

import importlib
import sys
from pathlib import Path


def load_app(monkeypatch, workspace: Path, frontend_dist: Path | None, maps_db: Path | None = None):
    monkeypatch.setenv("WORKSPACE_DIR", str(workspace))
    if frontend_dist is None:
        monkeypatch.delenv("FRONTEND_DIST", raising=False)
    else:
        monkeypatch.setenv("FRONTEND_DIST", str(frontend_dist))
    if maps_db is not None:
        monkeypatch.setenv("MAPS_DB", str(maps_db))

    sys.modules.pop("app", None)
    return importlib.import_module("app")


def test_default_frontend_dist_points_to_kaoto_build(monkeypatch, tmp_path):
    app_module = load_app(monkeypatch, tmp_path / "workspace", None)

    assert app_module.FRONTEND_DIST == (
        app_module.BASE_DIR / ".kaoto-src" / "packages" / "ui" / "dist"
    ).resolve()


def test_missing_frontend_page_shows_current_setup_commands(monkeypatch, tmp_path):
    app_module = load_app(
        monkeypatch,
        tmp_path / "workspace",
        tmp_path / "missing-dist",
    )
    client = app_module.app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "python scripts/setup_kaoto.py" in body
    assert "python scripts/run_app.py" in body
    assert "cd frontend" not in body


def test_file_api_crud_and_traversal_rejection(monkeypatch, tmp_path):
    app_module = load_app(
        monkeypatch,
        tmp_path / "workspace",
        tmp_path / "missing-dist",
    )
    client = app_module.app.test_client()

    write_response = client.put("/api/files/nested/hello.txt", data=b"hello")
    assert write_response.status_code == 200
    assert write_response.json == {"path": "nested/hello.txt", "size": 5}

    read_response = client.get("/api/files/nested/hello.txt")
    assert read_response.status_code == 200
    assert read_response.data == b"hello"

    list_response = client.get("/api/files")
    assert list_response.status_code == 200
    assert list_response.json["files"][0]["path"] == "nested/hello.txt"

    traversal_response = client.get("/api/files/../outside.txt")
    assert traversal_response.status_code == 400


def test_sample_copy_uses_sandbox_workspace(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    app_module = load_app(monkeypatch, workspace, tmp_path / "missing-dist")
    client = app_module.app.test_client()

    samples_response = client.get("/api/samples")
    assert samples_response.status_code == 200
    sample_names = {sample["name"] for sample in samples_response.json["samples"]}
    assert "order.json" in sample_names

    copy_response = client.post("/api/samples/order.json/copy")
    assert copy_response.status_code == 200
    assert copy_response.json["path"] == "order.json"
    assert (workspace / "order.json").is_file()


# ---------------------------------------------------------------------------
# Maps API tests
# ---------------------------------------------------------------------------

def _maps_client(monkeypatch, tmp_path):
    """Return a test client wired to an isolated in-memory DuckDB."""
    db_path = tmp_path / "test_maps.duckdb"
    app_module = load_app(
        monkeypatch,
        tmp_path / "workspace",
        tmp_path / "missing-dist",
        maps_db=db_path,
    )
    return app_module.app.test_client()


def test_maps_list_empty_on_fresh_db(monkeypatch, tmp_path):
    client = _maps_client(monkeypatch, tmp_path)
    res = client.get("/api/maps")
    assert res.status_code == 200
    assert res.json == {"maps": []}


def test_maps_save_requires_name(monkeypatch, tmp_path):
    client = _maps_client(monkeypatch, tmp_path)
    res = client.post("/api/maps", json={"input_schema": "{}"})
    assert res.status_code == 400


def test_maps_save_and_list(monkeypatch, tmp_path):
    client = _maps_client(monkeypatch, tmp_path)

    res = client.post(
        "/api/maps",
        json={
            "name": "order-map",
            "input_schema": '{"type":"object"}',
            "output_schema": "<xs:schema/>",
            "map_content": "<xsl:stylesheet/>",
        },
    )
    assert res.status_code == 201
    saved = res.json
    assert saved["name"] == "order-map"
    assert "id" in saved

    list_res = client.get("/api/maps")
    assert list_res.status_code == 200
    maps = list_res.json["maps"]
    assert len(maps) == 1
    assert maps[0]["name"] == "order-map"


def test_maps_get_by_id_returns_all_fields(monkeypatch, tmp_path):
    client = _maps_client(monkeypatch, tmp_path)

    post_res = client.post(
        "/api/maps",
        json={
            "name": "my-map",
            "input_schema": '{"type":"string"}',
            "output_schema": "<xs:schema/>",
            "map_content": "<xsl:stylesheet/>",
        },
    )
    map_id = post_res.json["id"]

    get_res = client.get(f"/api/maps/{map_id}")
    assert get_res.status_code == 200
    data = get_res.json
    assert data["name"] == "my-map"
    assert data["input_schema"] == '{"type":"string"}'
    assert data["output_schema"] == "<xs:schema/>"
    assert data["map_content"] == "<xsl:stylesheet/>"
    assert "created_at" in data
    assert "updated_at" in data


def test_maps_get_unknown_id_returns_404(monkeypatch, tmp_path):
    client = _maps_client(monkeypatch, tmp_path)
    res = client.get("/api/maps/9999")
    assert res.status_code == 404


def test_maps_delete(monkeypatch, tmp_path):
    client = _maps_client(monkeypatch, tmp_path)

    post_res = client.post("/api/maps", json={"name": "to-delete"})
    map_id = post_res.json["id"]

    del_res = client.delete(f"/api/maps/{map_id}")
    assert del_res.status_code == 204

    get_res = client.get(f"/api/maps/{map_id}")
    assert get_res.status_code == 404

    list_res = client.get("/api/maps")
    assert list_res.json["maps"] == []


def test_maps_delete_unknown_id_returns_404(monkeypatch, tmp_path):
    client = _maps_client(monkeypatch, tmp_path)
    res = client.delete("/api/maps/9999")
    assert res.status_code == 404


def test_maps_save_accepts_empty_schemas(monkeypatch, tmp_path):
    """Name is the only required field; all schema fields may be omitted."""
    client = _maps_client(monkeypatch, tmp_path)
    res = client.post("/api/maps", json={"name": "minimal"})
    assert res.status_code == 201
    map_id = res.json["id"]

    detail = client.get(f"/api/maps/{map_id}").json
    assert detail["input_schema"] == ""
    assert detail["output_schema"] == ""
    assert detail["map_content"] == ""


def test_maps_multiple_saves_have_distinct_ids(monkeypatch, tmp_path):
    client = _maps_client(monkeypatch, tmp_path)
    ids = [
        client.post("/api/maps", json={"name": f"map-{i}"}).json["id"]
        for i in range(3)
    ]
    assert len(set(ids)) == 3


def test_workspace_snapshot_returns_bucketed_files(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "input.schema.json").write_text('{"type":"object"}')
    (workspace / "output.xsd").write_text("<xs:schema/>")
    (workspace / "mapping.xsl").write_text("<xsl:stylesheet/>")

    app_module = load_app(monkeypatch, workspace, tmp_path / "missing-dist")
    client = app_module.app.test_client()

    res = client.get("/api/workspace-snapshot")
    assert res.status_code == 200
    data = res.json
    assert '{"type":"object"}' in data["input_schema"]
    assert "<xs:schema/>" in data["output_schema"]
    assert "<xsl:stylesheet/>" in data["map_content"]


def test_maps_page_returns_html(monkeypatch, tmp_path):
    client = _maps_client(monkeypatch, tmp_path)
    res = client.get("/maps")
    assert res.status_code == 200
    assert b"Saved Maps" in res.data
    assert b"/api/maps" in res.data
