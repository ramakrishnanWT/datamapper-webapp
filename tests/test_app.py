from __future__ import annotations

import importlib
import sys
from pathlib import Path


def load_app(monkeypatch, workspace: Path, frontend_dist: Path | None):
    monkeypatch.setenv("WORKSPACE_DIR", str(workspace))
    if frontend_dist is None:
        monkeypatch.delenv("FRONTEND_DIST", raising=False)
    else:
        monkeypatch.setenv("FRONTEND_DIST", str(frontend_dist))

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
