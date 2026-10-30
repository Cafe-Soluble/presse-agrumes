"""Détection matérielle, benchmark AV1 et estimation des temps.

Le benchmark encode quelques secondes de mire 1080p avec ffmpeg et mesure les
images/seconde réelles. Le résultat est mis en cache et associé à une
empreinte de la machine (modèle CPU + nombre de threads + version ffmpeg)
pour éviter de réutiliser une mesure obsolète après migration du NAS.
"""

from __future__ import annotations

import os
import platform
import re
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config, storage
from .media import available_encoders, ffmpeg_version

# Ordonnées (images/s à 1080p avec 12 threads) utilisées si aucun benchmark
# n'a été lancé. Volontairement approximatives : l'interface indique alors
# « estimation indicative ».
FALLBACK_FPS = {
    "libsvtav1": {0: 2, 2: 6, 4: 13, 6: 24, 8: 42, 10: 70, 12: 115, 13: 140},
    "libaom-av1": {0: 1, 2: 2.5, 4: 5, 6: 7, 8: 10, 10: 13, 12: 16, 13: 18},
    "av1_vaapi": {0: 40, 2: 60, 4: 80, 6: 100, 8: 120, 10: 140, 12: 160, 13: 180},
}


def _read_cpuinfo() -> dict:
    info = {
        "model": platform.processor() or "inconnu",
        "logical_cores": os.cpu_count() or 1,
        "physical_cores": None,
        "mhz": None,
    }
    try:
        text = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return info

    models = re.findall(r"^model name\s*:\s*(.+)$", text, re.MULTILINE)
    if models:
        info["model"] = models[0].strip()
    mhz_values = re.findall(r"^cpu MHz\s*:\s*([\d.]+)$", text, re.MULTILINE)
    if mhz_values:
        info["mhz"] = round(sum(float(v) for v in mhz_values) / len(mhz_values))

    physical_ids = re.findall(r"^physical id\s*:\s*(\d+)$", text, re.MULTILINE)
    core_ids = re.findall(r"^core id\s*:\s*(\d+)$", text, re.MULTILINE)
    if physical_ids and core_ids:
        info["physical_cores"] = len(set(zip(physical_ids, core_ids)))
    else:
        cores = re.findall(r"^cpu cores\s*:\s*(\d+)$", text, re.MULTILINE)
        sockets = re.findall(r"^physical id\s*:\s*(\d+)$", text, re.MULTILINE)
        if cores:
            info["physical_cores"] = int(cores[0]) * max(1, len(set(sockets)))
    return info


def _read_memory() -> dict:
    total = available = None
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                total = int(line.split()[1]) * 1024
            elif line.startswith("MemAvailable:"):
                available = int(line.split()[1]) * 1024
    except OSError:
        pass
    return {"total_bytes": total, "available_bytes": available}


def _machine_fingerprint(cpu_model: str, logical_cores: int, ffmpeg: str | None) -> str:
    return f"{cpu_model}|{logical_cores}|{(ffmpeg or '')[:80]}"


def detect_hardware(force_encoders: bool = False) -> dict:
    cpu = _read_cpuinfo()
    memory = _read_memory()
    encoders = available_encoders(force=force_encoders)
    ffmpeg = ffmpeg_version()
    vaapi_device = Path("/dev/dri/renderD128")
    gpu_devices = []
    try:
        gpu_devices = sorted(p.name for p in Path("/dev/dri").iterdir())
    except OSError:
        pass

    cache = storage.load_hardware_cache()
    fingerprint = _machine_fingerprint(cpu["model"], cpu["logical_cores"], ffmpeg)
    benchmarks = {}
    if cache.get("fingerprint") == fingerprint:
        benchmarks = cache.get("benchmarks", {})

    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "cpu": cpu,
        "memory": memory,
        "gpu": {
            "devices": gpu_devices,
            "vaapi_available": vaapi_device.exists(),
        },
        "ffmpeg": {
            "path": config.ffmpeg_bin(),
            "ffprobe_path": config.ffprobe_bin(),
            "version": ffmpeg,
            "encoders": encoders,
            "recommended_encoder": (
                "libsvtav1" if encoders.get("libsvtav1")
                else "libaom-av1" if encoders.get("libaom-av1")
                else "av1_vaapi" if encoders.get("av1_vaapi")
                else None
            ),
        },
        "fingerprint": fingerprint,
        "benchmarks": benchmarks,
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }


def _encoder_args(encoder: str, preset: int, threads: int) -> list[str]:
    if encoder == "libsvtav1":
        return ["-c:v", "libsvtav1", "-preset", str(preset),
                "-crf", "35", "-pix_fmt", "yuv420p",
                "-svtav1-params", f"lp={threads}"]
    if encoder == "libaom-av1":
        cpu_used = min(8, max(0, round(preset * 8 / 13)))
        return ["-c:v", "libaom-av1", "-cpu-used", str(cpu_used),
                "-crf", "35", "-b:v", "0", "-pix_fmt", "yuv420p",
                "-threads", str(threads)]
    if encoder == "av1_vaapi":
        return ["-vaapi_device", "/dev/dri/renderD128",
                "-vf", "format=nv12,hwupload", "-c:v", "av1_vaapi", "-qp", "120"]
    raise ValueError(f"Encodeur inconnu : {encoder}")


def benchmark(
    encoder: str,
    preset: int,
    threads: int | None = None,
    *,
    force: bool = False,
    sample_duration: int = 4,
) -> dict:
    hardware = detect_hardware()
    if not hardware["ffmpeg"]["encoders"].get(encoder):
        raise RuntimeError(f"L'encodeur {encoder} n'est pas disponible dans ce ffmpeg.")
    if encoder == "av1_vaapi" and not hardware["gpu"]["vaapi_available"]:
        raise RuntimeError("VAAPI indisponible (/dev/dri/renderD128 absent).")

    reference_threads = threads or hardware["cpu"]["logical_cores"]
    fingerprint = hardware["fingerprint"]
    key = f"{encoder}:p{preset}:t{reference_threads}"
    cache = storage.load_hardware_cache()
    if cache.get("fingerprint") != fingerprint:
        cache = {"fingerprint": fingerprint, "benchmarks": {}}
    if not force and key in cache.get("benchmarks", {}):
        cached = dict(cache["benchmarks"][key])
        cached["cached"] = True
        return cached

    binary = config.ffmpeg_bin()
    if not binary:
        raise RuntimeError("ffmpeg introuvable.")
    command = [
        binary, "-hide_banner", "-nostdin",
        "-f", "lavfi", "-i",
        f"testsrc2=size=1920x1080:rate=30:duration={sample_duration}",
        *_encoder_args(encoder, preset, reference_threads),
        "-progress", "pipe:1", "-nostats", "-f", "null", "-",
    ]
    started = time.time()
    try:
        proc = subprocess.run(
            command, capture_output=True, text=True, timeout=180, errors="replace"
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Le benchmark a dépassé 180 s.") from exc
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-5:]
        raise RuntimeError("Échec du benchmark : " + " | ".join(tail))
    elapsed = time.time() - started

    fps_values = [
        float(match.group(1))
        for match in re.finditer(r"^fps=([\d.]+)$", proc.stdout, re.MULTILINE)
    ]
    speed_values = [
        float(match.group(1))
        for match in re.finditer(r"^speed=([\d.]+)x$", proc.stdout, re.MULTILINE)
    ]
    fps = max(fps_values) if fps_values else 0.0
    if fps <= 0 and speed_values:
        # SVT-AV1 renvoie parfois « fps=0.00 » alors que la vitesse réelle est
        # correcte : on la convertit en images/s sur une source à 30 fps.
        fps = max(speed_values) * 30
    if fps <= 0:
        fps = sample_duration * 30 / max(0.001, elapsed)
    if fps <= 0:
        raise RuntimeError("Benchmark invalide : fps nul.")

    result = {
        "encoder": encoder,
        "preset": preset,
        "threads": reference_threads,
        "fps": round(fps, 2),
        "speed": round(fps / 30, 2),
        "elapsed_sec": round(elapsed, 2),
        "sample_duration_sec": sample_duration,
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "cached": False,
    }
    cache.setdefault("benchmarks", {})[key] = result
    cache["fingerprint"] = fingerprint
    storage.save_hardware_cache(cache)
    return result


def fallback_fps(encoder: str | None, preset: int, logical_cores: int) -> float:
    table = FALLBACK_FPS.get(encoder or "libsvtav1", FALLBACK_FPS["libsvtav1"])
    nearest = min(table, key=lambda key: abs(key - preset))
    base = table[nearest]
    return max(0.5, base * max(1, logical_cores) / 12.0)


def get_benchmark_or_estimate(
    hardware: dict, encoder: str | None, preset: int
) -> dict:
    """Retourne le benchmark adapté, sinon une estimation indicative."""
    benchmarks = hardware.get("benchmarks", {})
    prefix = f"{encoder}:p{preset}:"
    for key, value in benchmarks.items():
        if key.startswith(prefix):
            return {**value, "source": "benchmark", "cached": True}
    logical = hardware.get("cpu", {}).get("logical_cores") or 1
    fps = fallback_fps(encoder, preset, logical)
    return {
        "encoder": encoder,
        "preset": preset,
        "threads": logical,
        "fps": round(fps, 2),
        "speed": round(fps / 30, 2),
        "source": "estimate",
        "cached": False,
    }


def estimate_encode_seconds(
    duration_sec: float,
    *,
    fps_at_reference: float,
    reference_threads: int,
    logical_cores: int,
    resource_percent: int,
    concurrency: int = 1,
) -> float:
    """Estime le temps d'encodage d'un fichier.

    Le benchmark est mesuré sur tous les cœurs ; on applique le pourcentage de
    ressources puis on divise par le nombre d'encodages simultanés. Une marge
    de 12 % couvre le multiplexage, les I/O et l'audio.
    """
    if duration_sec <= 0 or fps_at_reference <= 0:
        return 0.0
    allotted = max(1, round(logical_cores * resource_percent / 100))
    per_job = max(1, allotted // max(1, concurrency))
    scale = min(1.0, per_job / max(1, reference_threads))
    effective_fps = max(0.2, fps_at_reference * scale)
    return round(duration_sec / effective_fps * 1.12, 1)


def eta_summary(
    items_duration_sec: float,
    file_count: int,
    hardware: dict,
    *,
    encoder: str | None,
    preset: int,
    resource_percent: int,
    concurrency: int = 1,
) -> dict:
    benchmark_info = get_benchmark_or_estimate(hardware, encoder, preset)
    logical = hardware.get("cpu", {}).get("logical_cores") or 1
    seconds = estimate_encode_seconds(
        items_duration_sec,
        fps_at_reference=benchmark_info["fps"],
        reference_threads=benchmark_info.get("threads") or logical,
        logical_cores=logical,
        resource_percent=resource_percent,
        concurrency=concurrency,
    ) + max(0, file_count) * 1.5
    return {
        "seconds": round(seconds, 1),
        "fps_reference": benchmark_info["fps"],
        "source": benchmark_info["source"],
        "threads_allotted": max(1, round(logical * resource_percent / 100)),
        "threads_per_job": max(
            1, max(1, round(logical * resource_percent / 100)) // max(1, concurrency)
        ),
        "encoder": encoder,
        "preset": preset,
    }
