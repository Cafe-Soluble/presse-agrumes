"""Application web FastAPI de Presse-Agrumes.

Lancement :
    python -m presse_agrumes
    # ou
    ./run.sh

L'interface est servie sur http://<ip-du-serveur>:8080 (0.0.0.0 par défaut).
"""

from __future__ import annotations

import asyncio
import base64
import hmac
import json
import mimetypes
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config, hardware, media, paths, storage
from . import __version__
from .jobs import TERMINAL_STATUSES, manager
from .models import (
    BenchmarkRequest,
    CompressRequest,
    DeleteScanItems,
    PreflightRequest,
    ScanRequest,
    TestRequest,
)
from .series import resolve_item_files

FRONTEND_DIST = config.BASE_DIR / "frontend" / "dist"
QUALITY_PRESETS = [
    {"id": "rapide", "label": "Rapide", "preset": 10, "crf": 34,
     "description": "Encode vite, gain maximal, qualité correcte."},
    {"id": "equilibre", "label": "Équilibré", "preset": 8, "crf": 32,
     "description": "Bon compromis temps/qualité, recommandé pour un NAS."},
    {"id": "qualite", "label": "Qualité", "preset": 6, "crf": 28,
     "description": "Plus lent, meilleure qualité perçue."},
    {"id": "archivage", "label": "Archivage", "preset": 4, "crf": 24,
     "description": "Très lent, qualité quasi transparente."},
]


def _check_auth(request: Request) -> bool:
    if not config.AUTH_ENABLED:
        return True
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    username, _, password = decoded.partition(":")
    return hmac.compare_digest(username, config.AUTH_USER) and hmac.compare_digest(
        password, config.AUTH_PASSWORD
    )


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    config.ensure_dirs()
    manager.recover()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Presse-Agrumes",
        version=__version__,
        description="Analyse et compression AV1 de bibliothèques vidéo.",
        lifespan=lifespan,
    )
    config.ensure_dirs()
    frontend_built = (FRONTEND_DIST / "index.html").is_file()
    if (FRONTEND_DIST / "assets").is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=FRONTEND_DIST / "assets"),
            name="assets",
        )

    @app.middleware("http")
    async def _middleware(request: Request, call_next):
        if not _check_auth(request):
            return Response(
                content="Authentification requise.",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Presse-Agrumes"'},
            )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; media-src 'self' blob:; img-src 'self' data: https://fastapi.tiangolo.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'"
        )
        if request.url.path == "/" or request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(paths.PathError)
    async def _path_error(_request: Request, exc: paths.PathError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _value_error(_request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(RuntimeError)
    async def _runtime_error(_request: Request, exc: RuntimeError):
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    # -- pages ------------------------------------------------------------
    def _frontend_index() -> Response:
        if frontend_built:
            return FileResponse(FRONTEND_DIST / "index.html", media_type="text/html")
        return HTMLResponse(
            """<!doctype html><html lang="fr"><meta charset="utf-8">
            <title>Presse-Agrumes — frontend non compilé</title>
            <body style="font-family:system-ui;background:#0d1015;color:#e9edf3;padding:3rem;line-height:1.6">
            <h1>🍊 Presse-Agrumes</h1>
            <p>L'interface React n'est pas encore compilée.</p>
            <pre style="background:#171c24;padding:1rem;border-radius:8px">cd frontend
npm install
npm run build</pre>
            <p>Puis rechargez cette page. L'API reste disponible sur <a style="color:#ff9f43" href="/docs">/docs</a>.</p>
            </body></html>""",
            status_code=503,
        )

    @app.get("/", include_in_schema=False)
    async def index():
        return _frontend_index()

    @app.get("/favicon.svg", include_in_schema=False)
    async def favicon():
        path = FRONTEND_DIST / "favicon.svg"
        if path.is_file():
            return FileResponse(path, media_type="image/svg+xml")
        raise HTTPException(status_code=404, detail="Favicon absent.")

    # -- état / configuration --------------------------------------------
    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "name": config.APP_NAME,
            "version": __version__,
            "ffmpeg": config.ffmpeg_bin(),
            "ffprobe": config.ffprobe_bin(),
            "auth_enabled": config.AUTH_ENABLED,
            "server_timezone": datetime.now().astimezone().tzname(),
            "server_time": datetime.now().astimezone().isoformat(),
        }

    @app.get("/api/config")
    async def get_config():
        return {
            "version": __version__,
            "allowed_roots": [str(path) for path in config.ALLOWED_ROOTS],
            "auth_enabled": config.AUTH_ENABLED,
            "auth_user": config.AUTH_USER if config.AUTH_ENABLED else None,
            "server_timezone": datetime.now().astimezone().tzname(),
            "quality_presets": QUALITY_PRESETS,
            "defaults": {
                "settings": {
                    "encoder": "auto",
                    "preset": 8,
                    "crf": 32,
                    "pixel_format": "yuv420p",
                    "audio_mode": "copy",
                    "audio_bitrate_kbps": 128,
                    "container": "mkv",
                    "subtitles": "copy",
                },
                "output": {
                    "mode": "same_dir_new_name",
                    "suffix": ".av1",
                    "output_dir": None,
                    "overwrite": False,
                },
                "originals": {"mode": "keep", "trash_dir": None},
                "resource_percent": 70,
                "concurrency": 1,
            },
            "notes": [
                "L'original n'est supprimé qu'après vérification ffprobe de la sortie.",
                "Les fichiers déjà en AV1 sont ignorés.",
                "Le test qualité force un MP4 AAC pour la lecture navigateur.",
            ],
        }

    @app.get("/api/mounts")
    async def mounts():
        return {"roots": paths.common_roots(), "home": str(Path.home())}

    @app.get("/api/browse")
    async def browse(path: str = Query(default=""), show_files: bool = False):
        target = path or str(Path.home())
        return paths.browse(target, show_files=show_files)

    @app.get("/api/hardware")
    async def get_hardware(refresh: bool = False):
        info = await asyncio.to_thread(hardware.detect_hardware, refresh)
        return info

    @app.post("/api/hardware/benchmark")
    async def run_benchmark(request: BenchmarkRequest):
        try:
            result = await asyncio.to_thread(manager.run_benchmark, request)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        info = await asyncio.to_thread(hardware.detect_hardware)
        return {"benchmark": result, "hardware": info}

    # -- scans ------------------------------------------------------------
    @app.post("/api/scans")
    async def start_scan(request: ScanRequest):
        job = manager.start_scan(request)
        return job.snapshot()

    @app.get("/api/scans")
    async def list_scans():
        return {"scans": storage.list_scans()}

    @app.get("/api/scans/{scan_id}")
    async def get_scan(scan_id: str):
        scan = storage.load_scan(scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="Scan introuvable.")
        return scan

    @app.delete("/api/scans/{scan_id}")
    async def delete_scan(scan_id: str):
        if not storage.delete_scan(scan_id):
            raise HTTPException(status_code=404, detail="Scan introuvable.")
        return {"deleted": True}

    @app.post("/api/scans/{scan_id}/delete")
    async def delete_scan_items(scan_id: str, request: DeleteScanItems):
        scan = storage.load_scan(scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="Scan introuvable.")
        result = await asyncio.to_thread(
            manager.delete_scan_items, scan, request.item_ids, request.paths
        )
        return result

    @app.post("/api/preflight")
    async def preflight(request: PreflightRequest):
        scan = storage.load_scan(request.scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="Scan introuvable.")
        files, warnings = resolve_item_files(scan, request.item_ids)
        compress_request = CompressRequest(**request.model_dump())
        plan = await asyncio.to_thread(manager.plan_compression, scan, compress_request)
        return {
            "file_count": len(plan["tasks"]),
            "selected_source_count": len(files),
            "skipped": plan["skipped"],
            "warnings": warnings,
            "estimate": plan["estimate"],
            "encoder": plan["encoder"],
            "threads": plan["threads"],
            "total_duration_sec": plan["total_duration_sec"],
            "total_input_bytes": plan["total_input_bytes"],
            "total_input_human": media.human_size(plan["total_input_bytes"]),
            "total_estimated_output_bytes": plan["total_estimated_output_bytes"],
            "total_estimated_output_human": media.human_size(
                plan["total_estimated_output_bytes"]
            ),
            "free_space_bytes": plan["free_space"],
            "free_space_human": media.human_size(plan["free_space"]),
            "sample_destinations": [
                {
                    "source": task["source"],
                    "destination": task["destination"],
                }
                for task in plan["tasks"][:5]
            ],
        }

    # -- compression ------------------------------------------------------
    @app.post("/api/compressions")
    async def start_compression(request: CompressRequest):
        try:
            job = manager.start_compression(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return job.snapshot()

    # -- tests qualité ----------------------------------------------------
    @app.post("/api/tests")
    async def start_test(request: TestRequest):
        job = manager.start_test(request)
        return job.snapshot()

    @app.get("/api/tests/{test_id}/meta")
    async def test_meta(test_id: str):
        meta = storage.load_test_meta(test_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="Test introuvable.")
        return meta

    @app.get("/api/tests/{test_id}/files/{filename}")
    async def test_file(test_id: str, filename: str, download: bool = False):
        meta = storage.load_test_meta(test_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="Test introuvable.")
        allowed = {
            info.get("filename")
            for info in meta.get("files", {}).values()
            if isinstance(info, dict)
        }
        if filename not in allowed:
            raise HTTPException(status_code=404, detail="Fichier inconnu.")
        path = storage.test_dir(test_id) / filename
        if not path.exists():
            raise HTTPException(status_code=404, detail="Fichier absent.")
        media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        if filename.endswith(".mkv"):
            media_type = "video/x-matroska"
        headers = {"Cache-Control": "private, max-age=3600"}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        else:
            headers["Content-Disposition"] = f'inline; filename="{filename}"'
        return FileResponse(path, media_type=media_type, headers=headers)

    # -- jobs -------------------------------------------------------------
    @app.get("/api/jobs")
    async def list_jobs(limit: int = Query(default=30, ge=1, le=200)):
        return {"jobs": manager.list(limit)}

    @app.get("/api/jobs/active")
    async def active_jobs():
        return {"jobs": manager.active()}

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str):
        job = manager.get(job_id)
        if job is not None:
            return job.snapshot()
        persisted = storage.load_job(job_id)
        if persisted is None:
            raise HTTPException(status_code=404, detail="Tâche introuvable.")
        return persisted

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str):
        if not manager.cancel(job_id):
            raise HTTPException(status_code=409, detail="Tâche déjà terminée ou inconnue.")
        return {"cancelled": True}

    @app.post("/api/jobs/{job_id}/pause")
    async def pause_job(job_id: str):
        if not manager.pause(job_id):
            raise HTTPException(
                status_code=409,
                detail="Tâche non pausable, déjà terminée ou inconnue.",
            )
        return {"paused": True}

    @app.post("/api/jobs/{job_id}/resume")
    async def resume_job(job_id: str):
        if not manager.resume(job_id):
            raise HTTPException(
                status_code=409,
                detail="Tâche non reprenable, déjà terminée ou inconnue.",
            )
        return {"resumed": True}

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str, request: Request):
        job = manager.get(job_id)
        if job is None:
            persisted = storage.load_job(job_id)
            if persisted is None:
                raise HTTPException(status_code=404, detail="Tâche introuvable.")

            async def one_shot():
                yield f"data: {json.dumps(persisted)}\n\n"

            return StreamingResponse(one_shot(), media_type="text/event-stream")

        async def stream():
            last_seq = -1
            idle_ticks = 0
            while True:
                if await request.is_disconnected():
                    break
                snapshot = job.snapshot()
                if snapshot["seq"] != last_seq:
                    last_seq = snapshot["seq"]
                    idle_ticks = 0
                    yield f"data: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
                    if snapshot["status"] in TERMINAL_STATUSES:
                        break
                else:
                    idle_ticks += 1
                    if idle_ticks % 30 == 0:
                        yield ": keepalive\n\n"
                await asyncio.sleep(0.35)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        """Sert l'index React pour les routes clientes (/history, /hardware…)."""
        if full_path.startswith(("api/", "assets/", "static/")) or full_path in {
            "docs", "redoc", "openapi.json",
        }:
            raise HTTPException(status_code=404, detail="Ressource introuvable.")
        return _frontend_index()

    return app


app = create_app()
