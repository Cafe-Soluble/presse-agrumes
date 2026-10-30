"""Persistance JSON atomique (scans, jobs, benchmarks, tests).

Aucune base de données : les volumes traités par l'outil sont des vidéos,
et les métadonnées restent petites. Des fichiers JSON sont faciles à
inspecter/dépanner sur un NAS, et l'écriture atomique évite tout fichier
tronqué si le service est coupé.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from . import config

_lock = threading.RLock()


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


# ---------------------------------------------------------------------------
# Scans
# ---------------------------------------------------------------------------

def _scan_path(scan_id: str) -> Path:
    return config.SCANS_DIR / f"{scan_id}.json"


def _scan_index() -> Path:
    return config.SCANS_DIR / "index.json"


def save_scan(scan: dict) -> None:
    with _lock:
        atomic_write_json(_scan_path(scan["id"]), scan)
        index = read_json(_scan_index(), {"scans": []})
        scans = [s for s in index.get("scans", []) if s.get("id") != scan["id"]]
        scans.insert(0, scan.get("summary", {}))
        atomic_write_json(_scan_index(), {"scans": scans[:200]})


def load_scan(scan_id: str) -> dict | None:
    return read_json(_scan_path(scan_id))


def list_scans() -> list[dict]:
    return read_json(_scan_index(), {"scans": []}).get("scans", [])


def delete_scan(scan_id: str) -> bool:
    with _lock:
        path = _scan_path(scan_id)
        existed = path.exists()
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return False
        index = read_json(_scan_index(), {"scans": []})
        scans = [s for s in index.get("scans", []) if s.get("id") != scan_id]
        atomic_write_json(_scan_index(), {"scans": scans})
        return existed


# ---------------------------------------------------------------------------
# Jobs (historique / reprise après redémarrage)
# ---------------------------------------------------------------------------

def save_job(job: dict) -> None:
    with _lock:
        atomic_write_json(config.JOBS_DIR / f"{job['id']}.json", job)


def load_job(job_id: str) -> dict | None:
    return read_json(config.JOBS_DIR / f"{job_id}.json")


def list_jobs(limit: int = 50) -> list[dict]:
    jobs = []
    try:
        paths = sorted(
            config.JOBS_DIR.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return []
    for path in paths[:limit]:
        data = read_json(path)
        if isinstance(data, dict):
            jobs.append(data)
    return jobs


# ---------------------------------------------------------------------------
# Tests qualité et matériel
# ---------------------------------------------------------------------------

def test_dir(test_id: str) -> Path:
    return config.TESTS_DIR / test_id


def save_test_meta(test_id: str, meta: dict) -> None:
    atomic_write_json(test_dir(test_id) / "meta.json", meta)


def load_test_meta(test_id: str) -> dict | None:
    return read_json(test_dir(test_id) / "meta.json")


def hardware_path() -> Path:
    return config.CACHE_DIR / "hardware.json"


def load_hardware_cache() -> dict:
    return read_json(hardware_path(), {}) or {}


def save_hardware_cache(cache: dict) -> None:
    atomic_write_json(hardware_path(), cache)
