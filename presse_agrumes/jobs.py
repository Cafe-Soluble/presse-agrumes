"""Gestionnaire de tâches : scan, compression et tests qualité.

Chaque tâche tourne dans un thread d'arrière-plan et expose un instantané
(`snapshot`) envoyé en SSE à l'interface. Les états sont persistés dans
`data/jobs/` pour l'historique et la reprise après redémarrage du service.

Sécurité des fichiers :
- la sortie est écrite dans un fichier temporaire puis renommée atomiquement ;
- l'original n'est supprimé qu'après vérification ffprobe de la sortie ;
- un fichier déjà AV1 n'est jamais recompressé.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import os
import shutil
import subprocess
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from . import config, hardware, media, paths, series, storage
from .models import BenchmarkRequest, CompressRequest, ScanRequest, TestRequest

TERMINAL_STATUSES = {"done", "error", "cancelled", "interrupted"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _task_id(path: str) -> str:
    return hashlib.sha1(path.encode("utf-8", "replace")).hexdigest()[:16]


def _unique_destination(destination: Path) -> Path:
    """Renvoie un chemin libre en ajoutant .1, .2... si nécessaire."""
    if not destination.exists():
        return destination
    stem = destination.stem
    suffix = destination.suffix
    for index in range(1, 1000):
        candidate = destination.with_name(f"{stem}.{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Impossible de trouver un nom libre pour {destination}")


class Job:
    def __init__(self, job_id: str, kind: str, label: str):
        self.id = job_id
        self.kind = kind
        self.label = label
        self.status = "queued"
        self.created_at = _now()
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.result: dict | None = None
        self.error: str | None = None
        self.warnings: list[dict] = []
        self.items: list[dict] = []
        self.progress = {
            "phase": "queued",
            "percent": 0.0,
            "done": 0,
            "total": 0,
            "message": "En attente…",
            "current": None,
            "eta_seconds": None,
            "elapsed_seconds": 0.0,
            "speed": None,
            "fps": None,
        }
        self.estimate: dict | None = None
        self.logs: deque[str] = deque(maxlen=400)
        self.seq = 0
        self.cancel_event = threading.Event()
        self.processes: set[subprocess.Popen] = set()
        self.lock = threading.RLock()
        self._start_monotonic: float | None = None

    # -- état -------------------------------------------------------------
    def set_status(self, status: str, *, error: str | None = None) -> None:
        with self.lock:
            self.status = status
            if error is not None:
                self.error = error
            if status in {"running"} and not self.started_at:
                self.started_at = _now()
                self._start_monotonic = time.monotonic()
            if status in TERMINAL_STATUSES:
                self.finished_at = _now()
                if self._start_monotonic:
                    self.progress["elapsed_seconds"] = round(
                        time.monotonic() - self._start_monotonic, 1
                    )
            self.seq += 1

    def update_progress(self, **values) -> None:
        with self.lock:
            self.progress.update(values)
            if self._start_monotonic:
                self.progress["elapsed_seconds"] = round(
                    time.monotonic() - self._start_monotonic, 1
                )
            self.seq += 1

    def add_log(self, line: str) -> None:
        line = line.rstrip()
        if not line:
            return
        with self.lock:
            self.logs.append(line)
            self.seq += 1

    def register_process(self, process: subprocess.Popen) -> None:
        with self.lock:
            self.processes.add(process)

    def unregister_process(self, process: subprocess.Popen) -> None:
        with self.lock:
            self.processes.discard(process)

    def request_cancel(self) -> None:
        self.cancel_event.set()
        self.add_log("Annulation demandée par l'utilisateur…")
        with self.lock:
            processes = list(self.processes)
        for process in processes:
            try:
                process.terminate()
            except OSError:
                pass

    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def snapshot(self, *, include_logs: bool = True) -> dict:
        with self.lock:
            data = {
                "id": self.id,
                "kind": self.kind,
                "label": self.label,
                "status": self.status,
                "created_at": self.created_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "seq": self.seq,
                "progress": dict(self.progress),
                "result": self.result,
                "error": self.error,
                "warnings": list(self.warnings),
                "items": [dict(item) for item in self.items],
                "estimate": self.estimate,
                "logs": list(self.logs)[-150:] if include_logs else [],
            }
        return data

    def persisted(self) -> dict:
        data = self.snapshot(include_logs=False)
        data.pop("seq", None)
        return data


class JobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.lock = threading.RLock()

    # -- accès ------------------------------------------------------------
    def get(self, job_id: str) -> Job | None:
        with self.lock:
            return self.jobs.get(job_id)

    def list(self, limit: int = 50) -> list[dict]:
        with self.lock:
            jobs = sorted(
                self.jobs.values(), key=lambda j: j.created_at, reverse=True
            )
        snapshots = {job.id: job.snapshot(include_logs=False) for job in jobs}
        # On complète avec l'historique persisté (après un redémarrage du
        # service, les jobs ne sont plus en mémoire).
        for persisted in storage.list_jobs(limit=limit * 2):
            job_id = persisted.get("id")
            if job_id and job_id not in snapshots:
                snapshots[job_id] = persisted
        result = sorted(
            snapshots.values(), key=lambda item: item.get("created_at") or "",
            reverse=True,
        )
        return result[:limit]

    def _new_job(self, kind: str, label: str) -> Job:
        job = Job(uuid.uuid4().hex, kind, label)
        with self.lock:
            self.jobs[job.id] = job
        return job

    def recover(self) -> None:
        """Marque comme interrompus les jobs laissés en cours au redémarrage."""
        for data in storage.list_jobs(limit=500):
            if data.get("status") in {"queued", "running"}:
                data["status"] = "interrupted"
                data["finished_at"] = _now()
                data["error"] = "Service redémarré pendant la tâche."
                storage.save_job(data)

    # -- scan -------------------------------------------------------------
    def start_scan(self, request: ScanRequest) -> Job:
        job = self._new_job("scan", f"Analyse de {request.root}")
        self._persist(job)
        thread = threading.Thread(
            target=self._run_scan, args=(job, request), daemon=True,
            name=f"scan-{job.id[:8]}",
        )
        thread.start()
        return job

    def _run_scan(self, job: Job, request: ScanRequest) -> None:
        job.set_status("running")
        try:
            root = paths.guard_path(request.root, must_exist=True)
            if not root.is_dir():
                raise ValueError(f"{root} n'est pas un dossier.")
            if not paths.is_readable(root):
                raise PermissionError(f"Dossier non lisible : {root}")
            if not config.ffprobe_bin():
                raise RuntimeError(
                    "ffprobe est introuvable. Installez ffmpeg ou définissez FFPROBE_BIN."
                )

            options = request.options
            series_roots = []
            for raw in options.series_roots:
                try:
                    marker = paths.guard_path(raw, must_exist=True)
                    if marker.is_dir():
                        series_roots.append(str(marker))
                except (paths.PathError, OSError) as exc:
                    job.warnings.append(
                        {"path": raw, "warning": f"marqueur série ignoré : {exc}"}
                    )

            job.update_progress(
                phase="walking", percent=0, message="Parcours des dossiers…"
            )
            last_walk = {"time": 0.0}

            def walk_progress(info: dict) -> None:
                now = time.monotonic()
                if now - last_walk["time"] < 0.6:
                    return
                last_walk["time"] = now
                job.update_progress(
                    phase="walking",
                    message=(
                        f"{info['dirs_scanned']} dossiers parcourus — "
                        f"{info['files_found']} vidéos trouvées"
                    ),
                    current=info.get("current_dir"),
                    done=info["files_found"],
                )

            files, walk_errors, walk_stats = media.find_video_files(
                root,
                exclude_globs=options.exclude_globs,
                follow_symlinks=options.follow_symlinks,
                min_size_bytes=int(options.min_size_mb * 1024 * 1024),
                progress=walk_progress,
                cancel=job.is_cancelled,
            )
            if job.is_cancelled():
                job.set_status("cancelled")
                job.update_progress(message="Analyse annulée.")
                self._persist(job)
                return

            total = len(files)
            job.update_progress(
                phase="probing",
                total=total,
                done=0,
                percent=0,
                message=f"{total} fichier(s) à analyser avec ffprobe…",
            )
            job.add_log(
                f"{total} vidéo(s) trouvée(s) dans {root} "
                f"({walk_stats['dirs_scanned']} dossiers en {walk_stats['elapsed']} s)."
            )

            analyzed: list[dict] = []
            started = time.monotonic()
            done = 0
            workers = max(1, min(options.workers, 16))
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                future_to_path = {
                    pool.submit(media.analyze_file, path, root): path for path in files
                }
                for future in concurrent.futures.as_completed(future_to_path):
                    if job.is_cancelled():
                        for pending in future_to_path:
                            pending.cancel()
                        break
                    try:
                        entry = future.result()
                    except Exception as exc:  # ne jamais tuer le scan
                        path = future_to_path[future]
                        entry = {
                            "path": str(path),
                            "relative_path": str(path),
                            "filename": path.name,
                            "error": f"analyse impossible : {exc}",
                        }
                    analyzed.append(entry)
                    done += 1
                    elapsed = time.monotonic() - started
                    rate = done / elapsed if elapsed else 0
                    remaining = total - done
                    eta = remaining / rate if rate > 0 else None
                    job.update_progress(
                        phase="probing",
                        done=done,
                        total=total,
                        percent=round(done / total * 100, 1) if total else 100,
                        current=entry.get("path"),
                        message=(
                            f"{done}/{total} — {entry.get('filename') or '?'}"
                            + (" (erreur)" if entry.get("error") else "")
                        ),
                        eta_seconds=round(eta, 1) if eta else None,
                    )
                    if entry.get("error"):
                        job.add_log(f"⚠ {entry.get('path')} : {entry['error']}")

            if job.is_cancelled():
                job.set_status("cancelled")
                job.update_progress(message="Analyse annulée.")
                job.result = {
                    "partial": True,
                    "analyzed_files": len(analyzed),
                    "total_files": total,
                }
                self._persist(job)
                return

            job.update_progress(
                phase="grouping", percent=99, message="Regroupement des séries…"
            )
            grouped = series.build_items(analyzed, root, series_roots)
            file_errors = [e for e in analyzed if e.get("error")]
            errors = list(walk_errors) + file_errors
            scan_id = uuid.uuid4().hex
            summary = {
                "id": scan_id,
                "root": str(root),
                "created_at": _now(),
                "partial": False,
                "series_roots": series_roots,
                **grouped["summary"],
                "walk_errors_count": len(walk_errors),
                "analysis_seconds": round(time.monotonic() - started, 1),
                "walk_seconds": walk_stats["elapsed"],
                "dirs_scanned": walk_stats["dirs_scanned"],
            }
            scan = {
                "id": scan_id,
                "created_at": summary["created_at"],
                "root": str(root),
                "options": options.model_dump(),
                "series_roots": series_roots,
                "walk_errors": walk_errors,
                "files": analyzed,
                "items": grouped["items"],
                "packs": grouped["packs"],
                "errors": errors,
                "summary": summary,
            }
            storage.save_scan(scan)
            job.result = {"scan_id": scan_id, "summary": summary}
            job.update_progress(
                phase="done", percent=100, message="Analyse terminée.",
                eta_seconds=0,
            )
            job.set_status("done")
        except (paths.PathError, PermissionError, RuntimeError, ValueError) as exc:
            job.set_status("error", error=str(exc))
            job.add_log(f"Erreur : {exc}")
        except Exception as exc:  # pragma: no cover - filet de sécurité
            job.set_status("error", error=f"Erreur inattendue : {exc}")
            job.add_log(f"Erreur inattendue : {exc}")
        finally:
            self._persist(job)

    # -- planification de compression ------------------------------------
    def plan_compression(self, scan: dict, request: CompressRequest) -> dict:
        files, warnings = series.resolve_item_files(scan, request.item_ids)
        settings = request.settings
        output = request.output
        originals = request.originals
        root = Path(scan["root"])

        hardware_info = hardware.detect_hardware()
        encoder = media.choose_encoder(
            settings.encoder, hardware_info["ffmpeg"]["encoders"]
        )
        if encoder is None:
            raise RuntimeError(
                "Aucun encodeur AV1 disponible dans ffmpeg. "
                "Installez un ffmpeg avec libsvtav1."
            )
        if encoder == "av1_vaapi" and not hardware_info["gpu"]["vaapi_available"]:
            raise RuntimeError("VAAPI indisponible sur cette machine.")

        output_dir = None
        if output.mode == "custom_dir":
            if not output.output_dir:
                raise ValueError("Un dossier de sortie est requis pour le mode personnalisé.")
            output_dir = paths.guard_path(output.output_dir)
            paths.ensure_writable_dir(output_dir)

        trash_dir = None
        if originals.mode == "move":
            if not originals.trash_dir:
                raise ValueError("Un dossier de corbeille est requis pour déplacer les originaux.")
            trash_dir = paths.guard_path(originals.trash_dir)
            paths.ensure_writable_dir(trash_dir)

        tasks: list[dict] = []
        skipped: list[dict] = []
        seen_outputs: set[str] = set()
        total_duration = 0.0
        total_estimated_output = 0
        ext = media.container_extension(settings.container)

        for entry in files:
            try:
                source = Path(entry["path"]).resolve()
            except OSError:
                source = Path(entry["path"])
            if not source.exists():
                skipped.append({"path": str(source), "warning": "fichier introuvable"})
                continue
            if not paths.is_readable(source):
                skipped.append({"path": str(source), "warning": "fichier non lisible (permissions)"})
                continue

            if output.mode == "same_dir_same_name":
                destination = source.with_suffix(ext)
            elif output.mode == "same_dir_new_name":
                destination = source.with_name(
                    media.output_filename(source, settings, output.mode, output.suffix)
                )
            else:
                relative_parent = Path(entry.get("relative_path") or source.name).parent
                destination = output_dir / relative_parent / media.output_filename(
                    source, settings, output.mode, output.suffix
                )

            destination = destination.resolve()
            if str(destination) in seen_outputs:
                skipped.append({
                    "path": str(source),
                    "warning": f"collision de sortie avec un autre fichier : {destination}",
                })
                continue
            seen_outputs.add(str(destination))

            if destination == source:
                if originals.mode == "keep":
                    skipped.append({
                        "path": str(source),
                        "warning": (
                            "la sortie écraserait l'original. Choisissez un autre nom "
                            "ou l'option « remplacer l'original »."
                        ),
                    })
                    continue
                if originals.mode == "move":
                    skipped.append({
                        "path": str(source),
                        "warning": (
                            "impossible de déplacer l'original quand la sortie porte "
                            "le même chemin ; choisissez un autre nom."
                        ),
                    })
                    continue
            try:
                paths.ensure_writable_dir(destination.parent)
            except paths.PathError as exc:
                skipped.append({"path": str(source), "warning": str(exc)})
                continue
            if destination.exists() and not output.overwrite and destination != source:
                skipped.append({
                    "path": str(source),
                    "warning": f"le fichier de sortie existe déjà : {destination}",
                })
                continue

            estimated_output = entry.get("estimated_output_bytes") or int(
                entry.get("size_bytes", 0) * 0.6
            )
            free = shutil.disk_usage(destination.parent).free
            if free < estimated_output * 1.05:
                skipped.append({
                    "path": str(source),
                    "warning": (
                        f"espace disque insuffisant dans {destination.parent} "
                        f"(libre {media.human_size(free)}, estimé {media.human_size(estimated_output)})"
                    ),
                })
                continue

            total_duration += float(entry.get("duration_sec") or 0)
            total_estimated_output += estimated_output
            tasks.append({
                "task_id": _task_id(entry["path"]),
                "source": str(source),
                "relative_path": entry.get("relative_path") or source.name,
                "filename": source.name,
                "destination": str(destination),
                "duration_sec": float(entry.get("duration_sec") or 0),
                "input_size": int(entry.get("size_bytes") or 0),
                "estimated_output_bytes": estimated_output,
                "codec": entry.get("video_codec"),
                "resolution": entry.get("resolution"),
            })

        # Vérification cumulée par dossier de destination : fichier par fichier
        # le contrôle précédent peut passer, mais l'ensemble peut remplir le
        # disque. On retire alors les tâches concernées avec un message clair.
        by_parent: dict[str, list[dict]] = {}
        for task in tasks:
            by_parent.setdefault(str(Path(task["destination"]).parent), []).append(task)
        removed_ids: set[str] = set()
        for parent, group in by_parent.items():
            total_needed = sum(task["estimated_output_bytes"] for task in group)
            try:
                free = shutil.disk_usage(parent).free
            except OSError:
                continue
            if total_needed > free * 0.98:
                for task in group:
                    removed_ids.add(task["task_id"])
                    skipped.append({
                        "path": task["source"],
                        "warning": (
                            f"espace disque cumulé insuffisant dans {parent} "
                            f"(libre {media.human_size(free)}, "
                            f"besoin {media.human_size(total_needed)})"
                        ),
                    })
        if removed_ids:
            tasks = [task for task in tasks if task["task_id"] not in removed_ids]
            total_duration = sum(task["duration_sec"] for task in tasks)
            total_estimated_output = sum(task["estimated_output_bytes"] for task in tasks)

        logical = hardware_info["cpu"]["logical_cores"]
        estimate = hardware.eta_summary(
            total_duration,
            len(tasks),
            hardware_info,
            encoder=encoder,
            preset=settings.preset,
            resource_percent=request.resource_percent,
            concurrency=request.concurrency,
        )
        return {
            "tasks": tasks,
            "skipped": skipped,
            "warnings": warnings,
            "encoder": encoder,
            "hardware": hardware_info,
            "estimate": estimate,
            "total_duration_sec": round(total_duration, 2),
            "total_input_bytes": sum(t["input_size"] for t in tasks),
            "total_estimated_output_bytes": total_estimated_output,
            "free_space": shutil.disk_usage(
                (output_dir or root).resolve()
            ).free,
            "threads": max(1, round(logical * request.resource_percent / 100)),
        }

    # -- compression ------------------------------------------------------
    def start_compression(self, request: CompressRequest) -> Job:
        scan = storage.load_scan(request.scan_id)
        if scan is None:
            raise ValueError("Scan introuvable.")
        job = self._new_job("compress", f"Compression de {len(request.item_ids)} élément(s)")
        self._persist(job)
        thread = threading.Thread(
            target=self._run_compression, args=(job, request, scan), daemon=True,
            name=f"compress-{job.id[:8]}",
        )
        thread.start()
        return job

    def _run_compression(self, job: Job, request: CompressRequest, scan: dict) -> None:
        job.set_status("running")
        try:
            if not config.ffmpeg_bin():
                raise RuntimeError("ffmpeg est introuvable.")
            plan = self.plan_compression(scan, request)
            tasks = plan["tasks"]
            job.warnings = plan["warnings"] + plan["skipped"]
            job.estimate = plan["estimate"]
            if not tasks:
                reasons = "; ".join(w["warning"] for w in plan["skipped"][:3])
                raise RuntimeError(
                    "Aucun fichier compressible après vérifications."
                    + (f" ({reasons})" if reasons else "")
                )

            job.items = [
                {
                    "task_id": task["task_id"],
                    "filename": task["filename"],
                    "source": task["source"],
                    "destination": task["destination"],
                    "duration_sec": task["duration_sec"],
                    "input_size": task["input_size"],
                    "status": "queued",
                    "percent": 0.0,
                    "speed": None,
                    "eta_seconds": None,
                    "output_size": None,
                    "saved_bytes": None,
                    "warning": None,
                    "error": None,
                }
                for task in tasks
            ]
            job.update_progress(
                phase="compressing",
                total=len(tasks),
                done=0,
                percent=0,
                message=f"Compression de {len(tasks)} fichier(s)…",
                eta_seconds=plan["estimate"]["seconds"],
            )
            job.add_log(
                f"Encodeur {media.encoder_display_name(plan['encoder'])}, "
                f"preset {request.settings.preset}, CRF {request.settings.crf}, "
                f"{plan['threads']} thread(s)."
            )
            self._persist(job)

            total_duration = max(0.01, plan["total_duration_sec"])
            completed_duration = 0.0
            per_job_threads = max(
                1,
                plan["threads"] // max(1, min(request.concurrency, len(tasks))),
            )
            started = time.monotonic()
            done = 0
            successes = 0
            failures = 0
            total_input = 0
            total_output = 0
            total_saved = 0

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=max(1, min(request.concurrency, len(tasks)))
            ) as pool:
                futures = {
                    pool.submit(
                        self._compress_one, job, task, request, plan,
                        per_job_threads,
                    ): task
                    for task in tasks
                }
                for future in concurrent.futures.as_completed(futures):
                    task = futures[future]
                    if job.is_cancelled():
                        for pending in futures:
                            pending.cancel()
                        break
                    item = next(
                        (i for i in job.items if i["task_id"] == task["task_id"]), None
                    )
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {
                            "status": "error",
                            "error": f"Erreur inattendue : {exc}",
                        }
                    done += 1
                    completed_duration += task["duration_sec"]
                    if result.get("status") == "done":
                        successes += 1
                        total_input += result.get("input_size", 0)
                        total_output += result.get("output_size", 0)
                        total_saved += max(0, result.get("saved_bytes", 0))
                        if item:
                            item.update(
                                status="done",
                                percent=100,
                                output_size=result.get("output_size"),
                                saved_bytes=result.get("saved_bytes"),
                                warning=result.get("warning"),
                                eta_seconds=0,
                            )
                        job.add_log(
                            f"✓ {task['filename']} → {media.human_size(result.get('output_size'))} "
                            f"({result.get('saved_percent', 0)}% de gain)"
                        )
                    elif result.get("status") == "cancelled":
                        if item:
                            item.update(status="cancelled", error="annulé")
                        job.add_log(f"Annulé : {task['filename']}")
                    else:
                        failures += 1
                        if item:
                            item.update(
                                status="error", error=result.get("error") or "échec"
                            )
                        job.add_log(
                            f"✗ {task['filename']} : {result.get('error') or 'échec'}"
                        )

                    elapsed = time.monotonic() - started
                    overall = min(99.0, completed_duration / total_duration * 100)
                    remaining = max(0.0, total_duration - completed_duration)
                    speed_ratio = (completed_duration / elapsed) if elapsed else 0
                    eta = remaining / speed_ratio if speed_ratio > 0 else None
                    job.update_progress(
                        phase="compressing",
                        done=done,
                        total=len(tasks),
                        percent=round(overall, 1),
                        message=f"{done}/{len(tasks)} fichier(s) traité(s)",
                        current=None,
                        eta_seconds=round(eta, 1) if eta else None,
                    )
                    self._persist(job)

            if job.is_cancelled():
                job.set_status("cancelled", error="Compression annulée par l'utilisateur.")
                job.result = {
                    "success": successes,
                    "failed": failures,
                    "cancelled": True,
                }
                return

            if successes == 0:
                raise RuntimeError(
                    f"Aucune compression réussie ({failures} échec(s)). "
                    "Consultez le journal."
                )

            summary = {
                "success": successes,
                "failed": failures,
                "total": len(tasks),
                "input_bytes": total_input,
                "output_bytes": total_output,
                "saved_bytes": max(0, total_input - total_output),
                "saved_percent": round(
                    (1 - total_output / total_input) * 100, 1
                ) if total_input else 0,
                "elapsed_seconds": round(time.monotonic() - started, 1),
                "encoder": plan["encoder"],
                "settings": request.settings.model_dump(),
                "originals": request.originals.model_dump(),
                "output": request.output.model_dump(),
                "items": job.items,
            }
            job.result = summary
            job.update_progress(
                phase="done", percent=100, done=len(tasks),
                message="Compression terminée.", eta_seconds=0,
            )
            job.set_status("done")
        except (paths.PathError, PermissionError, RuntimeError, ValueError) as exc:
            job.set_status("error", error=str(exc))
            job.add_log(f"Erreur : {exc}")
        except Exception as exc:  # pragma: no cover
            job.set_status("error", error=f"Erreur inattendue : {exc}")
            job.add_log(f"Erreur inattendue : {exc}")
        finally:
            self._persist(job)

    def _compress_one(
        self, job: Job, task: dict, request: CompressRequest, plan: dict, threads: int
    ) -> dict:
        source = Path(task["source"])
        destination = Path(task["destination"])
        settings = request.settings
        originals = request.originals
        started = time.monotonic()

        if job.is_cancelled():
            return {"status": "cancelled"}
        if not source.exists():
            return {"status": "error", "error": "fichier source introuvable"}
        if not paths.is_readable(source):
            return {"status": "error", "error": "fichier source non lisible (permissions)"}

        token = uuid.uuid4().hex[:8]
        temp = destination.with_name(
            f".{destination.stem}.pa-tmp-{token}{destination.suffix}"
        )
        final_existed = destination.exists()
        command = media.build_compress_command(
            source, temp, settings, encoder=plan["encoder"], threads=threads,
            duration_sec=task["duration_sec"],
        )
        item = next((i for i in job.items if i["task_id"] == task["task_id"]), None)
        if item:
            item.update(status="running")

        def on_progress(info: dict) -> None:
            percent = info.get("percent")
            eta = info.get("eta_seconds")
            if item and percent is not None:
                item.update(
                    status="running",
                    percent=round(min(99.0, percent), 1),
                    speed=info.get("speed"),
                    fps=info.get("fps"),
                    eta_seconds=eta,
                )
            # Progression globale : on ajoute la fraction du fichier courant.
            total_count = max(1, job.progress.get("total") or 1)
            done_count = job.progress.get("done") or 0
            current_fraction = (percent or 0) / 100
            overall = min(99.0, (done_count + current_fraction) / total_count * 100)
            job.update_progress(
                phase="compressing",
                percent=round(overall, 1),
                message=f"{task['filename']} — {percent:.0f}%" if percent else task["filename"],
                current=task["filename"],
                speed=info.get("speed"),
                fps=info.get("fps"),
                eta_seconds=eta,
            )

        try:
            returncode, logs = self._run_ffmpeg(
                job, command, task["duration_sec"], on_progress
            )
        except Exception as exc:
            return {"status": "error", "error": f"ffmpeg : {exc}"}

        if job.is_cancelled() or returncode != 0:
            if temp.exists():
                temp.unlink(missing_ok=True)
            if job.is_cancelled():
                return {"status": "cancelled"}
            tail = " | ".join(logs[-4:]) if logs else "code retour non nul"
            return {"status": "error", "error": f"ffmpeg a échoué : {tail}"}

        valid, verify_error = media.file_is_valid_video(temp)
        if request.verify and not valid:
            temp.unlink(missing_ok=True)
            return {"status": "error", "error": f"sortie invalide : {verify_error}"}

        try:
            if destination.exists() and not request.output.overwrite and destination != source:
                temp.unlink(missing_ok=True)
                return {
                    "status": "error",
                    "error": f"le fichier de sortie est apparu entre-temps : {destination}",
                }
            os.replace(temp, destination)
        except OSError as exc:
            temp.unlink(missing_ok=True)
            return {"status": "error", "error": f"renommage final impossible : {exc}"}

        warnings = []
        if destination == source:
            warnings.append("l'original a été remplacé par la version AV1")
        elif request.output.overwrite or final_existed:
            warnings.append("fichier de sortie existant remplacé")

        # Gestion de l'original APRÈS succès et vérification de la sortie.
        try:
            if destination != source:
                if originals.mode == "delete":
                    source.unlink(missing_ok=True)
                elif originals.mode == "move":
                    assert originals.trash_dir
                    trash_root = paths.guard_path(originals.trash_dir)
                    relative_parent = Path(task["relative_path"]).parent
                    target = _unique_destination(trash_root / relative_parent / source.name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source), str(target))
            elif originals.mode == "delete":
                # La sortie a remplacé l'original : rien d'autre à faire.
                pass
        except (OSError, paths.PathError) as exc:
            warnings.append(f"original non traité : {exc}")

        output_size = destination.stat().st_size
        input_size = task["input_size"] or source.stat().st_size
        saved = max(0, input_size - output_size)
        if output_size >= input_size:
            warnings.append("le fichier compressé est plus gros que l'original")
        return {
            "status": "done",
            "output_path": str(destination),
            "input_size": input_size,
            "output_size": output_size,
            "saved_bytes": saved,
            "saved_percent": round(saved / input_size * 100, 1) if input_size else 0,
            "encode_seconds": round(time.monotonic() - started, 1),
            "warning": "; ".join(warnings) if warnings else None,
            "logs": logs[-5:],
        }

    def _run_ffmpeg(self, job: Job, command: list[str], duration: float, on_progress=None) -> tuple[int, list[str]]:
        # Priorité réduite : même à 100 % de threads, le NAS reste réactif.
        nice = shutil.which("nice")
        if nice:
            command = [nice, "-n", "10", *command]
        job.add_log("$ " + " ".join(str(part) for part in command[:10]) + " …")
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            raise RuntimeError(f"impossible de lancer ffmpeg : {exc}") from exc
        job.register_process(process)
        logs: deque[str] = deque(maxlen=30)
        started = time.monotonic()
        last_emit = 0.0
        out_time = 0.0
        speed = None
        fps = None
        try:
            if process.stdout:
                for line in process.stdout:
                    if job.is_cancelled():
                        try:
                            process.terminate()
                        except OSError:
                            pass
                    line = line.strip()
                    if not line:
                        continue
                    key, sep, value = line.partition("=")
                    if sep and key in {
                        "out_time_us", "out_time_ms", "speed", "fps",
                        "progress", "frame", "bitrate", "total_size",
                    }:
                        if key in {"out_time_us", "out_time_ms"}:
                            try:
                                out_time = float(value) / 1_000_000
                            except ValueError:
                                pass
                        elif key == "speed":
                            speed = value
                        elif key == "fps":
                            try:
                                fps = round(float(value), 1)
                            except ValueError:
                                pass
                        continue
                    logs.append(line)
                    if not line.startswith(("frame=", "size=", "time=")) and len(logs) <= 6:
                        job.add_log(line[:300])
                    now = time.monotonic()
                    if now - last_emit >= 0.7 and duration > 0:
                        percent = min(99.9, out_time / duration * 100)
                        eta = None
                        if speed and speed.endswith("x"):
                            try:
                                ratio = float(speed[:-1])
                                if ratio > 0:
                                    eta = max(0.0, (duration - out_time) / ratio)
                            except ValueError:
                                pass
                        if eta is None and percent > 0:
                            elapsed = now - started
                            eta = elapsed / percent * (100 - percent)
                        if on_progress:
                            on_progress({
                                "percent": percent,
                                "speed": speed,
                                "fps": fps,
                                "eta_seconds": round(eta, 1) if eta else None,
                                "out_time": out_time,
                            })
                        last_emit = now
            returncode = process.wait()
            if duration > 0 and on_progress:
                on_progress({
                    "percent": 100.0 if returncode == 0 else min(99.0, out_time / duration * 100),
                    "speed": speed,
                    "fps": fps,
                    "eta_seconds": 0 if returncode == 0 else None,
                    "out_time": out_time,
                })
            return returncode, list(logs)
        finally:
            job.unregister_process(process)

    # -- test qualité -----------------------------------------------------
    def start_test(self, request: TestRequest) -> Job:
        label = f"Test qualité — {Path(request.path).name}"
        job = self._new_job("test", label)
        self._persist(job)
        thread = threading.Thread(
            target=self._run_test, args=(job, request), daemon=True,
            name=f"test-{job.id[:8]}",
        )
        thread.start()
        return job

    def _run_test(self, job: Job, request: TestRequest) -> None:
        job.set_status("running")
        test_id = job.id
        output_dir = storage.test_dir(test_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            if not config.ffmpeg_bin():
                raise RuntimeError("ffmpeg est introuvable.")
            source = paths.guard_path(request.path, must_exist=True)
            if not paths.is_readable(source):
                raise PermissionError(f"Fichier non lisible : {source}")

            source_duration, probe, probe_error = media.probe_duration(source)
            if probe is None:
                raise RuntimeError(probe_error or "Impossible de lire le fichier source.")
            if source_duration <= 0:
                raise RuntimeError("Durée du fichier source inconnue.")

            duration = min(float(request.duration), max(1.0, source_duration))
            if request.start_mode == "seconds":
                start = max(0.0, float(request.start_seconds))
            else:
                start = source_duration * request.start_percent / 100
            start = min(start, max(0.0, source_duration - duration))

            hardware_info = hardware.detect_hardware()
            encoder = media.choose_encoder(
                request.settings.encoder, hardware_info["ffmpeg"]["encoders"]
            )
            if encoder is None:
                raise RuntimeError("Aucun encodeur AV1 disponible.")
            if encoder == "av1_vaapi" and not hardware_info["gpu"]["vaapi_available"]:
                encoder = media.choose_encoder("auto", hardware_info["ffmpeg"]["encoders"])
            if encoder is None:
                raise RuntimeError("Aucun encodeur AV1 disponible.")

            logical = hardware_info["cpu"]["logical_cores"]
            threads = max(1, round(logical * 0.7))
            meta = {
                "id": test_id,
                "created_at": _now(),
                "status": "running",
                "source": str(source),
                "source_duration_sec": round(source_duration, 2),
                "start_sec": round(start, 2),
                "duration_sec": round(duration, 2),
                "settings": request.settings.model_dump(),
                "encoder": encoder,
                "files": {},
            }
            storage.save_test_meta(test_id, meta)

            steps = [
                ("original_preview", 0.0, 35.0, media.build_preview_original_command(
                    source, output_dir / "original.mp4", start, duration)),
                ("original_raw", 35.0, 45.0, media.build_raw_clip_command(
                    source, output_dir / "original-raw.mkv", start, duration)),
                ("compressed", 45.0, 100.0, media.build_compress_test_command(
                    source, output_dir / "compressed.mp4", request.settings,
                    encoder=encoder, threads=threads, start=start, duration=duration)),
            ]

            for name, pct_start, pct_end, command in steps:
                if job.is_cancelled():
                    job.set_status("cancelled", error="Test annulé.")
                    meta["status"] = "cancelled"
                    storage.save_test_meta(test_id, meta)
                    return
                job.update_progress(
                    phase=name,
                    percent=pct_start,
                    message=f"Génération {name.replace('_', ' ')}…",
                    current=str(source),
                )

                def progress(info, p0=pct_start, p1=pct_end):
                    percent = p0 + (p1 - p0) * (info.get("percent", 0) / 100)
                    job.update_progress(percent=round(percent, 1))

                returncode, logs = self._run_ffmpeg(
                    job, command, duration, progress
                )
                target = Path(command[-1])
                if returncode != 0:
                    if name == "original_raw":
                        job.add_log("⚠ l'extrait original brut n'a pas pu être copié (codec exotique).")
                        continue
                    raise RuntimeError(
                        f"Échec de {name} : " + " | ".join(logs[-4:])
                    )
                if not target.exists() or target.stat().st_size == 0:
                    if name == "original_raw":
                        continue
                    raise RuntimeError(f"Sortie vide pour {name}.")

            def file_info(filename: str, label: str) -> dict:
                path = output_dir / filename
                if not path.exists():
                    return {}
                duration, _probe, _error = media.probe_duration(path)
                return {
                    "filename": filename,
                    "label": label,
                    "url": f"/api/tests/{test_id}/files/{filename}",
                    "size_bytes": path.stat().st_size,
                    "size_human": media.human_size(path.stat().st_size),
                    "duration_sec": round(duration, 2),
                    "bitrate_bps": int(path.stat().st_size * 8 / duration) if duration else None,
                }

            original = file_info("original.mp4", "Extrait original (aperçu H.264)")
            raw = file_info("original-raw.mkv", "Extrait original brut (téléchargement)")
            compressed = file_info("compressed.mp4", "Extrait compressé en AV1")
            if not compressed:
                raise RuntimeError("L'extrait compressé n'a pas été généré.")
            reference = raw if raw and raw.get("bitrate_bps") else original
            if reference and compressed.get("bitrate_bps"):
                saved_percent = round(
                    (1 - compressed["bitrate_bps"] / reference["bitrate_bps"]) * 100, 1
                )
                meta["comparison"] = {
                    "reference": "original_raw" if reference is raw else "original_preview",
                    "original_bitrate_bps": reference["bitrate_bps"],
                    "compressed_bitrate_bps": compressed["bitrate_bps"],
                    "saved_percent": saved_percent,
                    "note": (
                        "Comparaison calculée sur le débit (taille/durée) : l'extrait "
                        "brut peut inclure quelques secondes supplémentaires car la "
                        "découpe sans réencodage se cale sur une image-clé. L'aperçu "
                        "original en H.264 CRF 18 sert uniquement à la lecture navigateur."
                    ),
                }
            meta["files"] = {
                "original_preview": original,
                "original_raw": raw,
                "compressed": compressed,
            }
            meta["status"] = "done"
            meta["finished_at"] = _now()
            storage.save_test_meta(test_id, meta)
            job.result = {"test_id": test_id, "meta": meta}
            job.update_progress(phase="done", percent=100, message="Test prêt.", eta_seconds=0)
            job.set_status("done")
        except (paths.PathError, PermissionError, RuntimeError, ValueError) as exc:
            job.set_status("error", error=str(exc))
            job.add_log(f"Erreur : {exc}")
            meta = storage.load_test_meta(test_id) or {"id": test_id}
            meta["status"] = "error"
            meta["error"] = str(exc)
            storage.save_test_meta(test_id, meta)
        except Exception as exc:  # pragma: no cover
            job.set_status("error", error=f"Erreur inattendue : {exc}")
            job.add_log(f"Erreur inattendue : {exc}")
        finally:
            self._persist(job)

    # -- benchmark --------------------------------------------------------
    def run_benchmark(self, request: BenchmarkRequest) -> dict:
        return hardware.benchmark(
            request.encoder, request.preset, request.threads, force=request.force
        )

    # -- persistance ------------------------------------------------------
    def _persist(self, job: Job) -> None:
        try:
            storage.save_job(job.persisted())
        except OSError:
            pass

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None or job.status in TERMINAL_STATUSES:
            return False
        job.request_cancel()
        return True


manager = JobManager()
