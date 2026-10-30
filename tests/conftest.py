"""Fixtures de test : environnement isolé + vrais médias générés par ffmpeg.

Les tests n'utilisent jamais le dossier `data/` du projet : `PA_DATA_DIR` et
`PA_ALLOWED_ROOTS` pointent vers un répertoire temporaire créé avant l'import
de l'application.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

TEST_ROOT = Path(tempfile.mkdtemp(prefix="presse-agrumes-tests-"))
os.environ["PA_DATA_DIR"] = str(TEST_ROOT / "data")
os.environ["PA_ALLOWED_ROOTS"] = str(TEST_ROOT)
os.environ["PA_AUTH_DISABLED"] = "1"
os.environ.pop("PA_AUTH_USER", None)
os.environ.pop("PA_AUTH_PASSWORD", None)

from fastapi.testclient import TestClient  # noqa: E402

from presse_agrumes import config, media  # noqa: E402
from presse_agrumes.app import app  # noqa: E402


def ffmpeg_available() -> bool:
    return bool(config.ffmpeg_bin() and config.ffprobe_bin())


def make_video(path: Path, *, duration: float = 3.0, frequency: int = 440) -> Path:
    """Génère une petite vidéo H.264 + AAC avec ffmpeg."""
    path.parent.mkdir(parents=True, exist_ok=True)
    binary = config.ffmpeg_bin()
    assert binary, "ffmpeg requis pour les tests"
    command = [
        binary, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=25:duration={duration}",
        "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration={duration}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
        str(path),
    ]
    subprocess.run(command, check=True, capture_output=True, timeout=120)
    return path


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def media_root() -> Path:
    if not ffmpeg_available():
        pytest.skip("ffmpeg/ffprobe indisponibles")
    root = TEST_ROOT / "media"
    root.mkdir(parents=True, exist_ok=True)
    make_video(root / "film.mp4", duration=4, frequency=440)
    series_dir = root / "Series" / "Breaking.Bad.S01"
    make_video(series_dir / "Breaking.Bad.S01E01.mkv", duration=3, frequency=330)
    make_video(series_dir / "Breaking.Bad.S01E02.mkv", duration=3, frequency=550)
    (root / "sous-dossier").mkdir(exist_ok=True)
    make_video(root / "sous-dossier" / "autre video.mp4", duration=3, frequency=660)

    # Fichier non lisible : pertinent uniquement si les tests ne tournent pas
    # en root (root ignore les permissions).
    if os.geteuid() != 0:
        broken = root / "illisible.mp4"
        broken.write_bytes(b"")
        broken.chmod(0o000)
    yield root
    # Restaure les permissions avant le nettoyage.
    for path in root.rglob("*"):
        try:
            if path.is_file():
                path.chmod(0o644)
        except OSError:
            pass


@pytest.fixture(scope="session", autouse=True)
def _cleanup():
    yield
    try:
        for path in TEST_ROOT.rglob("*"):
            try:
                if path.is_file():
                    path.chmod(0o644)
            except OSError:
                pass
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
    except OSError:
        pass


def wait_job(client: TestClient, job_id: str, timeout: float = 180.0) -> dict:
    import time

    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = client.get(f"/api/jobs/{job_id}").json()
        if last.get("status") in {"done", "error", "cancelled"}:
            return last
        time.sleep(0.25)
    raise AssertionError(f"Job {job_id} non terminé : {last}")


def scan_root(client: TestClient, root: Path, series_roots: list[str] | None = None) -> dict:
    response = client.post(
        "/api/scans",
        json={
            "root": str(root),
            "options": {
                "workers": 2,
                "series_roots": series_roots or [],
                "include_av1": True,
            },
        },
    )
    assert response.status_code == 200, response.text
    job = response.json()
    final = wait_job(client, job["id"])
    assert final["status"] == "done", final
    scan_id = final["result"]["scan_id"]
    return client.get(f"/api/scans/{scan_id}").json()


def probe_codec(path: Path) -> str | None:
    probe, _error = media.run_ffprobe(path)
    if not probe:
        return None
    video = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), {})
    return video.get("codec_name")
