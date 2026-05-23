"""Тесты /jobs router."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import build_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.paths.resolve_app_data", lambda: tmp_path)
    app = build_app()
    # Замокаем job_runner.schedule, чтобы тесты не лазили в Playwright/Phygital
    with TestClient(app) as c:
        c.app.state.job_runner.schedule = MagicMock()
        yield c


def test_post_jobs_creates_with_known_node(client):
    r = client.post("/jobs", json={"node_id": 94, "params": {"prompt": "hi"}})
    assert r.status_code == 200
    body = r.json()
    assert "job_id" in body and len(body["job_id"]) == 26
    client.app.state.job_runner.schedule.assert_called_once_with(body["job_id"])


def test_post_jobs_rejects_unknown_node(client):
    r = client.post("/jobs", json={"node_id": 999, "params": {}})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "unknown_node"


def test_get_jobs_returns_empty(client):
    r = client.get("/jobs")
    assert r.status_code == 200
    assert r.json() == {"jobs": [], "next_cursor": None}


def test_get_jobs_after_create(client):
    client.post("/jobs", json={"node_id": 94, "params": {}})
    r = client.get("/jobs")
    assert r.status_code == 200
    jobs = r.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["node_id"] == 94
    assert jobs[0]["status"] == "queued"


def test_get_job_by_id(client):
    r = client.post("/jobs", json={"node_id": 94, "params": {}})
    job_id = r.json()["job_id"]
    r2 = client.get(f"/jobs/{job_id}")
    assert r2.status_code == 200
    assert r2.json()["job_id"] == job_id
    assert r2.json()["status"] == "queued"


def test_get_unknown_job_404(client):
    r = client.get("/jobs/01HXNOTEXIST")
    assert r.status_code == 404


def test_delete_job(client):
    r = client.post("/jobs", json={"node_id": 94, "params": {}})
    job_id = r.json()["job_id"]
    r2 = client.delete(f"/jobs/{job_id}")
    assert r2.status_code == 204
    state = client.app.state.task_registry.get(job_id)
    assert state is None
    # idempotency: повторный delete тоже не должен возвращать что-то кроме 404
    r3 = client.delete(f"/jobs/{job_id}")
    assert r3.status_code == 404


def test_download_404_if_not_completed(client):
    r = client.post("/jobs", json={"node_id": 94, "params": {}})
    job_id = r.json()["job_id"]
    r2 = client.get(f"/jobs/{job_id}/download")
    assert r2.status_code == 409


def test_download_blocks_path_traversal(client, tmp_path):
    """C4: result_paths указывающий за пределы downloads_dir должен дать 403."""
    from app import paths as paths_mod
    r = client.post("/jobs", json={"node_id": 94, "params": {}})
    job_id = r.json()["job_id"]
    state = client.app.state.task_registry.get(job_id)
    # Создаём целевой файл вне downloads (имитируем атаку).
    evil = tmp_path / "secrets.txt"
    evil.write_text("password=hunter2", encoding="utf-8")
    # Прямо подменяем result_paths/status, минуя update_status — имитируем
    # повреждённый jsonl или future-cloud-sync.
    state.result_paths = [str(evil)]
    state.status = "completed"
    r2 = client.get(f"/jobs/{job_id}/download")
    assert r2.status_code == 403
    assert r2.json()["detail"]["error"] == "path_outside_downloads"


def test_download_works_for_legitimate_path(client, tmp_path):
    """Канонический путь под downloads_dir должен качаться."""
    from app import paths as paths_mod
    # downloads_dir уже = tmp_path/downloads из-за monkeypatch resolve_app_data.
    target = paths_mod.downloads_dir() / "abc.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"hello")

    r = client.post("/jobs", json={"node_id": 94, "params": {}})
    job_id = r.json()["job_id"]
    state = client.app.state.task_registry.get(job_id)
    state.result_paths = [str(target)]
    state.status = "completed"
    r2 = client.get(f"/jobs/{job_id}/download")
    assert r2.status_code == 200
    assert r2.content == b"hello"


def test_post_jobs_accepts_init_files_dict(client):
    r = client.post(
        "/jobs",
        json={
            "node_id": 94,
            "params": {"prompt": "hi"},
            "init_files": {"init_img": ["/tmp/a.png"]},
        },
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    state = client.app.state.task_registry.get(job_id)
    assert state.params["_init_files"] == {"init_img": ["/tmp/a.png"]}


def test_post_jobs_back_compat_init_files_list(client):
    """list[str] нормализуется в {"init_img": list}."""
    r = client.post(
        "/jobs",
        json={
            "node_id": 94,
            "params": {"prompt": "hi"},
            "init_files": ["/tmp/a.png"],
        },
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    state = client.app.state.task_registry.get(job_id)
    assert state.params["_init_files"] == {"init_img": ["/tmp/a.png"]}


def test_post_jobs_no_init_files_no_marker(client):
    r = client.post("/jobs", json={"node_id": 94, "params": {"prompt": "hi"}})
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    state = client.app.state.task_registry.get(job_id)
    assert "_init_files" not in state.params
