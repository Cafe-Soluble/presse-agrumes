from __future__ import annotations

import os
from pathlib import Path

import pytest

from presse_agrumes import config, media
from tests.conftest import make_video, probe_codec, scan_root, wait_job

SETTINGS = {
    "encoder": "auto",
    "preset": 12,
    "crf": 45,
    "pixel_format": "yuv420p",
    "audio_mode": "copy",
    "audio_bitrate_kbps": 128,
    "container": "mkv",
    "subtitles": "copy",
}

OUTPUT_NEW = {
    "mode": "same_dir_new_name",
    "suffix": "test",
    "output_dir": None,
    "overwrite": False,
}

KEEP = {"mode": "keep", "trash_dir": None}


def find_item(scan: dict, filename: str) -> dict:
    item = next((item for item in scan["items"] if item.get("filename") == filename), None)
    if item is None:
        item = next(
            (
                item
                for item in scan["items"]
                if item["kind"] == "series" and any(e["filename"] == filename for e in item.get("episodes", []))
            ),
            None,
        )
    assert item is not None, f"item {filename} absent du scan"
    return item


def test_health_and_spa(client):
    health = client.get("/api/health").json()
    assert health["status"] == "ok"
    assert health["ffmpeg"]
    index = client.get("/")
    assert index.status_code == 200
    assert "Presse-Agrumes" in index.text
    assert client.get("/history").status_code == 200
    assert client.get("/hardware").status_code == 200
    assert client.get("/api/inconnu").status_code == 404


def test_optional_basic_auth(client, monkeypatch):
    from presse_agrumes import config

    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    monkeypatch.setattr(config, "AUTH_USER", "agrumes")
    monkeypatch.setattr(config, "AUTH_PASSWORD", "secret")
    assert client.get("/api/health").status_code == 401
    authorized = client.get("/api/health", auth=("agrumes", "secret"))
    assert authorized.status_code == 200


def test_config_and_path_guard(client, media_root: Path):
    config = client.get("/api/config").json()
    assert config["defaults"]["settings"]["preset"] == 8
    assert config["quality_presets"]
    browse = client.get(f"/api/browse?path={media_root}").json()
    assert any(entry["name"] == "Series" for entry in browse["directories"])
    denied = client.get("/api/browse?path=/etc")
    assert denied.status_code == 400
    assert "autoris" in denied.json()["detail"].lower() or "refus" in denied.json()["detail"].lower()


def test_scan_preflight_and_errors(client, media_root: Path):
    scan = scan_root(client, media_root, [str(media_root / "Series")])
    assert scan["summary"]["items_count"] >= 2
    assert scan["summary"]["pack_count"] == 1
    pack = next(item for item in scan["items"] if item["kind"] == "series")
    assert pack["episode_count"] == 2
    assert "Breaking.Bad" in pack["name"]
    assert pack["season_label"] == "S01"

    if os.geteuid() != 0:
        assert any("illisible" in entry["path"] for entry in scan["errors"])

    film = find_item(scan, "film.mp4")
    response = client.post(
        "/api/preflight",
        json={
            "scan_id": scan["id"],
            "item_ids": [pack["id"], film["id"]],
            "settings": SETTINGS,
            "output": OUTPUT_NEW,
            "originals": KEEP,
            "resource_percent": 70,
            "concurrency": 1,
        },
    )
    assert response.status_code == 200, response.text
    preflight = response.json()
    assert preflight["file_count"] == 3
    assert preflight["estimate"]["seconds"] > 0
    assert preflight["sample_destinations"]
    assert preflight["total_estimated_output_bytes"] > 0


def test_quality_test(client, media_root: Path):
    film = media_root / "film.mp4"
    response = client.post(
        "/api/tests",
        json={
            "path": str(film),
            "duration": 3,
            "start_mode": "percent",
            "start_percent": 10,
            "start_seconds": 0,
            "settings": SETTINGS,
        },
    )
    assert response.status_code == 200, response.text
    job = wait_job(client, response.json()["id"])
    assert job["status"] == "done", job
    test_id = job["result"]["test_id"]
    meta = client.get(f"/api/tests/{test_id}/meta").json()
    assert meta["status"] == "done"
    assert meta["files"]["original_preview"]["size_bytes"] > 0
    assert meta["files"]["compressed"]["size_bytes"] > 0
    assert "saved_percent" in meta["comparison"]
    compressed_path = config.DATA_DIR / "tests" / test_id / meta["files"]["compressed"]["filename"]
    assert probe_codec(compressed_path) == "av1"

    compressed_url = meta["files"]["compressed"]["url"]
    partial = client.get(compressed_url, headers={"Range": "bytes=0-99"})
    assert partial.status_code == 206
    assert len(partial.content) == 100
    download = client.get(f"{compressed_url}?download=1")
    assert download.status_code == 200
    assert "attachment" in download.headers["content-disposition"]


def test_compression_delete_original(client, media_root: Path):
    source = media_root / "a-delete.mp4"
    make_video(source, duration=3, frequency=700)
    scan = scan_root(client, media_root, [str(media_root / "Series")])
    item = find_item(scan, source.name)
    response = client.post(
        "/api/compressions",
        json={
            "scan_id": scan["id"],
            "item_ids": [item["id"]],
            "settings": SETTINGS,
            "output": {**OUTPUT_NEW, "suffix": "delete"},
            "originals": {"mode": "delete", "trash_dir": None},
            "resource_percent": 70,
            "concurrency": 1,
            "verify": True,
        },
    )
    assert response.status_code == 200, response.text
    job = wait_job(client, response.json()["id"])
    assert job["status"] == "done", job
    destination = Path(job["result"]["items"][0]["destination"])
    assert destination.exists()
    assert probe_codec(destination) == "av1"
    assert not source.exists(), "l'original devait être supprimé après vérification"


def test_compression_move_and_replace(client, media_root: Path):
    move_source = media_root / "b-move.mp4"
    replace_source = media_root / "c-replace.mkv"
    make_video(move_source, duration=3, frequency=800)
    make_video(replace_source, duration=3, frequency=900)
    trash = media_root / "_trash"
    scan = scan_root(client, media_root, [str(media_root / "Series")])

    move_item = find_item(scan, move_source.name)
    response = client.post(
        "/api/compressions",
        json={
            "scan_id": scan["id"],
            "item_ids": [move_item["id"]],
            "settings": SETTINGS,
            "output": {**OUTPUT_NEW, "suffix": "moved"},
            "originals": {"mode": "move", "trash_dir": str(trash)},
            "resource_percent": 70,
            "concurrency": 1,
            "verify": True,
        },
    )
    assert response.status_code == 200, response.text
    job = wait_job(client, response.json()["id"])
    assert job["status"] == "done", job
    assert not move_source.exists()
    assert (trash / move_source.name).exists()

    scan = scan_root(client, media_root, [str(media_root / "Series")])
    replace_item = find_item(scan, replace_source.name)
    response = client.post(
        "/api/compressions",
        json={
            "scan_id": scan["id"],
            "item_ids": [replace_item["id"]],
            "settings": SETTINGS,
            "output": {
                "mode": "same_dir_same_name",
                "suffix": "x",
                "output_dir": None,
                "overwrite": False,
            },
            "originals": {"mode": "delete", "trash_dir": None},
            "resource_percent": 70,
            "concurrency": 1,
            "verify": True,
        },
    )
    assert response.status_code == 200, response.text
    job = wait_job(client, response.json()["id"])
    assert job["status"] == "done", job
    assert replace_source.exists()
    assert probe_codec(replace_source) == "av1"


def test_custom_dir_mirrors_relative_path(client, media_root: Path):
    output = media_root / "_out"
    scan = scan_root(client, media_root, [str(media_root / "Series")])
    pack = find_item(scan, "Breaking.Bad.S01E01.mkv")
    preflight = client.post(
        "/api/preflight",
        json={
            "scan_id": scan["id"],
            "item_ids": [pack["id"]],
            "settings": SETTINGS,
            "output": {
                "mode": "custom_dir",
                "suffix": "mirror",
                "output_dir": str(output),
                "overwrite": False,
            },
            "originals": KEEP,
            "resource_percent": 70,
            "concurrency": 1,
        },
    )
    assert preflight.status_code == 200, preflight.text
    destination = Path(preflight.json()["sample_destinations"][0]["destination"])
    assert destination == output / "Series" / "Breaking.Bad.S01" / "Breaking.Bad.S01E01.mirror.mkv"


def test_readonly_output_dir_is_reported(client, media_root: Path):
    if os.geteuid() == 0:
        pytest.skip("root ignore les permissions")
    readonly = media_root / "_readonly"
    readonly.mkdir(exist_ok=True)
    readonly.chmod(0o555)
    try:
        scan = scan_root(client, media_root)
        item = find_item(scan, "film.mp4")
        response = client.post(
            "/api/preflight",
            json={
                "scan_id": scan["id"],
                "item_ids": [item["id"]],
                "settings": SETTINGS,
                "output": {
                    "mode": "custom_dir",
                    "suffix": "x",
                    "output_dir": str(readonly / "out"),
                    "overwrite": False,
                },
                "originals": KEEP,
                "resource_percent": 70,
                "concurrency": 1,
            },
        )
        assert response.status_code == 400
        assert "permission" in response.json()["detail"].lower() or "écriture" in response.json()["detail"].lower()
    finally:
        readonly.chmod(0o755)


def test_av1_files_are_never_recompressed(client, media_root: Path):
    av1_source = media_root / "d-av1.mp4"
    make_video(av1_source, duration=2, frequency=1000)
    scan = scan_root(client, media_root)
    item = find_item(scan, av1_source.name)
    response = client.post(
        "/api/compressions",
        json={
            "scan_id": scan["id"],
            "item_ids": [item["id"]],
            "settings": SETTINGS,
            "output": {
                "mode": "same_dir_same_name",
                "suffix": "x",
                "output_dir": None,
                "overwrite": False,
            },
            "originals": {"mode": "delete", "trash_dir": None},
            "resource_percent": 70,
            "concurrency": 1,
            "verify": True,
        },
    )
    job = wait_job(client, response.json()["id"])
    assert job["status"] == "done", job
    av1_path = Path(job["result"]["items"][0]["destination"])
    assert av1_path.exists()
    assert probe_codec(av1_path) == "av1"

    scan = scan_root(client, media_root)
    av1_item = find_item(scan, av1_path.name)
    assert av1_item["already_av1"] is True
    preflight = client.post(
        "/api/preflight",
        json={
            "scan_id": scan["id"],
            "item_ids": [av1_item["id"]],
            "settings": SETTINGS,
            "output": OUTPUT_NEW,
            "originals": KEEP,
            "resource_percent": 70,
            "concurrency": 1,
        },
    )
    assert preflight.status_code == 200
    assert preflight.json()["file_count"] == 0
    assert any("AV1" in warning["warning"] for warning in preflight.json()["warnings"])


def test_active_jobs_and_pause_api(client):
    from presse_agrumes.jobs import Job, manager

    job = Job("api-pause-test", "compress", "test de pause", {"scan_id": "fake"})
    job.set_status("running")
    with manager.lock:
        manager.jobs[job.id] = job
    try:
        active = client.get("/api/jobs/active").json()["jobs"]
        assert any(item["id"] == job.id for item in active)
        paused = client.post(f"/api/jobs/{job.id}/pause")
        assert paused.status_code == 200, paused.text
        snapshot = client.get(f"/api/jobs/{job.id}").json()
        assert snapshot["status"] == "paused"
        assert "manual" in snapshot["pause_reasons"]
        resumed = client.post(f"/api/jobs/{job.id}/resume")
        assert resumed.status_code == 200, resumed.text
        snapshot = client.get(f"/api/jobs/{job.id}").json()
        assert snapshot["status"] == "running"
    finally:
        job.request_cancel()
        with manager.lock:
            manager.jobs.pop(job.id, None)


def test_scheduled_compression_waits_outside_window(client, media_root: Path):
    import datetime as dt

    source = media_root / "e-schedule.mp4"
    make_video(source, duration=3, frequency=1100)
    scan = scan_root(client, media_root)
    item = find_item(scan, source.name)
    target_day = (dt.datetime.now().astimezone().weekday() + 3) % 7
    response = client.post(
        "/api/compressions",
        json={
            "scan_id": scan["id"],
            "item_ids": [item["id"]],
            "settings": SETTINGS,
            "output": {**OUTPUT_NEW, "suffix": "scheduled"},
            "originals": KEEP,
            "resource_percent": 70,
            "concurrency": 1,
            "verify": True,
            "schedule": {
                "enabled": True,
                "windows": [
                    {"days": [target_day], "start": "00:00", "end": "23:59"}
                ],
            },
        },
    )
    assert response.status_code == 200, response.text
    job_id = response.json()["id"]
    import time

    deadline = time.time() + 20
    snapshot = {}
    while time.time() < deadline:
        snapshot = client.get(f"/api/jobs/{job_id}").json()
        if snapshot["status"] == "paused":
            break
        if snapshot["status"] in {"done", "error", "cancelled"}:
            break
        time.sleep(0.2)
    assert snapshot["status"] == "paused", snapshot
    assert "schedule" in snapshot["pause_reasons"]
    assert snapshot["next_resume_at"]
    assert not (media_root / "e-schedule.scheduled.mkv").exists()
    cancel = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancel.status_code == 200
    final = wait_job(client, job_id)
    assert final["status"] == "cancelled"


def test_manual_pause_resume_real_compression(client, media_root: Path):
    import time

    source = media_root / "f-pause.mp4"
    make_video(source, duration=4, frequency=1200)
    scan = scan_root(client, media_root)
    item = find_item(scan, source.name)
    response = client.post(
        "/api/compressions",
        json={
            "scan_id": scan["id"],
            "item_ids": [item["id"]],
            "settings": {**SETTINGS, "preset": 4},
            "output": {**OUTPUT_NEW, "suffix": "paused"},
            "originals": KEEP,
            "resource_percent": 50,
            "concurrency": 1,
            "verify": True,
        },
    )
    assert response.status_code == 200, response.text
    job_id = response.json()["id"]
    pause = client.post(f"/api/jobs/{job_id}/pause")
    if pause.status_code == 409:
        pytest.skip("compression terminée avant la demande de pause")
    assert pause.status_code == 200, pause.text
    snapshot = client.get(f"/api/jobs/{job_id}").json()
    assert snapshot["status"] == "paused"
    time.sleep(0.3)
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "paused"
    resume = client.post(f"/api/jobs/{job_id}/resume")
    assert resume.status_code == 200, resume.text
    final = wait_job(client, job_id)
    assert final["status"] == "done", final
    assert (media_root / "f-pause.paused.mkv").exists()
