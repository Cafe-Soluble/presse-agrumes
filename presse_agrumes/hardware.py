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
    "libx265": {0: 4, 2: 9, 4: 18, 6: 30, 8: 45, 10: 75, 12: 110, 13: 140},
    "hevc_vaapi": {0: 40, 2: 60, 4: 80, 6: 100, 8: 120, 10: 140, 12: 160, 13: 180},
    "hevc_qsv": {0: 40, 2: 60, 4: 80, 6: 100, 8: 120, 10: 140, 12: 160, 13: 180},
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




VAAPI_CODECS = [
    ("h264", "H.264", ("VAProfileH264Main", "VAProfileH264High", "VAProfileH264ConstrainedBaseline"), "h264_vaapi"),
    ("hevc8", "H.265 8 bits", ("VAProfileHEVCMain",), "hevc_vaapi"),
    ("hevc10", "H.265 10 bits", ("VAProfileHEVCMain10",), "hevc_vaapi"),
    ("av1", "AV1", ("VAProfileAV1Profile0", "VAProfileAV1Profile1"), "av1_vaapi"),
    ("vp9", "VP9", ("VAProfileVP9Profile0", "VAProfileVP9Profile1", "VAProfileVP9Profile2", "VAProfileVP9Profile3"), None),
    ("mpeg2", "MPEG-2", ("VAProfileMPEG2Simple", "VAProfileMPEG2Main"), None),
    ("vc1", "VC-1", ("VAProfileVC1Simple", "VAProfileVC1Main", "VAProfileVC1Advanced"), None),
]


def _read_vainfo() -> tuple[dict[str, set[str]], str | None, str | None]:
    try:
        proc = subprocess.run(
            ["vainfo"], capture_output=True, text=True, timeout=10, errors="replace"
        )
    except FileNotFoundError:
        return {}, None, "vainfo introuvable (paquet vainfo)"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {}, None, f"vainfo impossible : {exc}"
    text = (proc.stdout or "") + (proc.stderr or "")
    profiles: dict[str, set[str]] = {}
    for profile, entrypoint in re.findall(r"(VAProfile\w+)\s*:\s*(VAEntrypoint\w+)", text):
        profiles.setdefault(profile, set()).add(entrypoint)
    driver = None
    match = re.search(r"Driver version:\s*(.+)", text)
    if match:
        driver = match.group(1).strip()
    if not profiles:
        return profiles, driver, "vainfo ne retourne aucun profil"
    return profiles, driver, None


def _vaapi_test_encode(encoder: str) -> tuple[bool, str | None]:
    binary = config.ffmpeg_bin()
    if not binary:
        return False, "ffmpeg introuvable"
    cmd = [
        binary, "-hide_banner", "-loglevel", "error", "-nostdin",
        "-vaapi_device", "/dev/dri/renderD128",
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=1",
        "-vf", "format=nv12,hwupload", "-c:v", encoder, "-qp", "28",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if proc.returncode == 0:
        return True, None
    tail = (proc.stderr or "").strip().splitlines()[-2:]
    return False, " | ".join(tail) or "échec ffmpeg"


def _vaapi_test_decode() -> tuple[bool, str | None]:
    binary = config.ffmpeg_bin()
    if not binary:
        return False, "ffmpeg introuvable"
    sample = config.CACHE_DIR / f"vaapi-decode-{os.getpid()}.mp4"
    config.ensure_dirs()
    try:
        make = subprocess.run(
            [
                binary, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=1",
                "-c:v", "libx264", "-preset", "ultrafast", str(sample),
            ],
            capture_output=True, text=True, timeout=60, errors="replace",
        )
        if make.returncode != 0:
            return False, "impossible de générer l'échantillon"
        proc = subprocess.run(
            [
                binary, "-hide_banner", "-loglevel", "error", "-nostdin",
                "-hwaccel", "vaapi", "-hwaccel_output_format", "vaapi",
                "-i", str(sample), "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=60, errors="replace",
        )
    finally:
        sample.unlink(missing_ok=True)
    if proc.returncode == 0:
        return True, None
    tail = (proc.stderr or "").strip().splitlines()[-2:]
    return False, " | ".join(tail) or "échec décodage"


def _vaapi_diagnostics(run_tests: bool = False) -> dict:
    device = Path("/dev/dri/renderD128")
    devices = []
    try:
        devices = sorted(path.name for path in Path("/dev/dri").iterdir())
    except OSError:
        pass
    accessible = device.exists() and os.access(device, os.R_OK | os.W_OK)
    profiles, driver, vainfo_error = _read_vainfo() if device.exists() else ({}, None, None)
    encoders = available_encoders()

    decode_test: tuple[bool, str | None] = (False, None)
    encode_tests: dict[str, tuple[bool, str | None]] = {}
    if run_tests and accessible:
        decode_test = _vaapi_test_decode()
        for encoder in ("h264_vaapi", "hevc_vaapi", "av1_vaapi"):
            if encoders.get(encoder):
                encode_tests[encoder] = _vaapi_test_encode(encoder)

    codecs = []
    any_usable_encode = False
    for key, label, profile_names, encoder in VAAPI_CODECS:
        entries: set[str] = set()
        for name in profile_names:
            entries |= profiles.get(name, set())
        decode = "VAEntrypointVLD" in entries
        encode = bool(entries & {"VAEntrypointEncSlice", "VAEntrypointEncSliceLP"})
        tested = encode_tests.get(encoder) if encoder else None
        compiled = bool(encoder and encoders.get(encoder))
        usable_encode = (tested[0] if tested else encode and compiled)
        if usable_encode:
            any_usable_encode = True
        codecs.append({
            "codec": key,
            "label": label,
            "decode": decode,
            "encode": encode,
            "compiled": compiled,
            "tested_encode": tested[0] if tested else None,
            "tested_decode": decode_test[0] if run_tests and accessible else None,
            "usable_encode": usable_encode,
            "error": tested[1] if tested and not tested[0] else None,
        })

    if not device.exists():
        reason = "Aucun périphérique /dev/dri/renderD128. En Docker/LXC, ajoutez --device /dev/dri."
    elif not accessible:
        reason = "Périphérique présent mais non accessible. Ajoutez l'utilisateur aux groupes render et video."
    elif vainfo_error:
        reason = (
            f"{vainfo_error}. Installez vainfo et le driver VAAPI "
            "(ex. intel-media-va-driver-non-free)."
        )
    elif not any_usable_encode:
        reason = "Driver VAAPI présent, mais aucun encodage supporté par ce GPU."
    else:
        reason = None

    return {
        "devices": devices,
        "device": str(device),
        "accessible": accessible,
        "driver": driver,
        "vainfo_error": vainfo_error,
        "codecs": codecs,
        "decode_ok": decode_test[0] if run_tests and accessible else None,
        "decode_error": decode_test[1] if run_tests and accessible else None,
        "reason": reason,
        "tested": run_tests and accessible,
    }


def detect_hardware(force_encoders: bool = False) -> dict:
    cpu = _read_cpuinfo()
    memory = _read_memory()
    encoders = available_encoders(force=force_encoders)
    ffmpeg = ffmpeg_version()
    vaapi = _vaapi_diagnostics(run_tests=force_encoders)
    gpu_devices = vaapi["devices"]

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
            "vaapi_available": bool(vaapi["accessible"] and any(
                codec["usable_encode"] for codec in vaapi["codecs"]
            )),
            "vaapi": vaapi,
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
    if encoder == "libx265":
        from .media import x265_preset_name
        return ["-c:v", "libx265", "-preset", x265_preset_name(preset),
                "-crf", "26", "-pix_fmt", "yuv420p"]
    if encoder == "hevc_vaapi":
        return ["-vaapi_device", "/dev/dri/renderD128",
                "-vf", "format=nv12,hwupload", "-c:v", "hevc_vaapi", "-qp", "26"]
    if encoder == "hevc_qsv":
        from .media import qsv_preset_name
        return ["-c:v", "hevc_qsv", "-global_quality", "26",
                "-preset", qsv_preset_name(preset)]
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




def _source_fps(probe: dict | None) -> float:
    if not probe:
        return 30.0
    for stream in probe.get("streams", []) or []:
        if stream.get("codec_type") != "video":
            continue
        for key in ("avg_frame_rate", "r_frame_rate"):
            raw = stream.get(key)
            if not raw or raw in {"0/0", "0"}:
                continue
            try:
                num, den = raw.split("/")
                value = float(num) / float(den)
            except (ValueError, ZeroDivisionError):
                continue
            if value > 0:
                return value
    return 30.0


def _run_benchmark_sample(command: list[str], sample_seconds: float) -> tuple[float, int]:
    """Exécute un échantillon et renvoie (speed stable, taille produite)."""
    from . import media

    started = time.monotonic()
    points: list[tuple[float, float]] = []
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        errors="replace",
    )
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if line.startswith("out_time_us="):
                try:
                    encoded = int(line.split("=", 1)[1].strip()) / 1_000_000
                except ValueError:
                    continue
                points.append((time.monotonic() - started, encoded))
        proc.wait(timeout=1800)
    except Exception:
        proc.kill()
        proc.wait()
        raise
    if proc.returncode != 0:
        raise RuntimeError("Échec de l'échantillon de benchmark.")

    # Ignore le warm-up : on mesure la vitesse entre 20 % et 100 % de la durée.
    threshold = max(0.5, sample_seconds * 0.2)
    stable = [(wall, enc) for wall, enc in points if enc >= threshold]
    if len(stable) >= 2:
        (t0, e0), (t1, e1) = stable[0], stable[-1]
        speed = (e1 - e0) / max(0.001, t1 - t0)
    else:
        elapsed = time.monotonic() - started
        speed = (points[-1][1] if points else sample_seconds) / max(0.001, elapsed)
    size = Path(command[-1]).stat().st_size if Path(command[-1]).exists() else 0
    return max(0.001, speed), size


def benchmark_real(
    path: str | Path,
    settings,
    threads: int | None = None,
    *,
    force: bool = False,
    sample_seconds: float = 8.0,
    samples: int = 3,
) -> dict:
    """Benchmark sur le fichier réel, avec les réglages réels.

    Plusieurs extraits répartis sur la durée évitent de mesurer uniquement un
    générique ou des scènes faciles. La vitesse retenue est la médiane, et
    l'estimation de taille utilise le débit produit par les extraits.
    """
    from . import media

    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise RuntimeError(f"Fichier introuvable : {source}")
    duration, probe, error = media.probe_duration(source)
    if not probe or duration <= 0:
        raise RuntimeError(error or "Durée du fichier inconnue.")

    hardware = detect_hardware()
    available = hardware["ffmpeg"]["encoders"]
    encoder = media.choose_encoder(settings.encoder, available, settings.codec)
    if encoder is None:
        raise RuntimeError(f"Aucun encodeur {settings.codec.upper()} disponible.")
    if encoder.endswith("_vaapi") and not hardware["gpu"]["vaapi_available"]:
        raise RuntimeError("VAAPI indisponible.")

    reference_threads = threads or hardware["cpu"]["logical_cores"]
    fingerprint = hardware["fingerprint"]
    key = f"{encoder}:p{settings.preset}:crf{settings.crf}:t{reference_threads}:real"
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
    config.ensure_dirs()
    fps_source = _source_fps(probe)
    positions = [0.2, 0.5, 0.8][: max(1, min(3, samples))]
    speeds: list[float] = []
    rates: list[float] = []
    for index, position in enumerate(positions):
        start = max(0.0, duration * position - sample_seconds / 2)
        length = min(sample_seconds, max(1.0, duration - start))
        temp = config.CACHE_DIR / f"bench-{os.getpid()}-{index}.mkv"
        command = [
            binary, "-hide_banner", "-nostdin", "-y",
            "-ss", f"{start:.3f}", "-t", f"{length:.3f}",
            "-i", str(source),
            "-map", "0:v:0", "-an", "-sn",
            *media.video_encode_args(settings, encoder, reference_threads),
            "-progress", "pipe:1", "-nostats", str(temp),
        ]
        try:
            speed, size = _run_benchmark_sample(command, length)
        finally:
            temp.unlink(missing_ok=True)
        speeds.append(speed)
        if size > 0 and length > 0:
            rates.append(size / length)

    speeds.sort()
    median = speeds[len(speeds) // 2]
    speed_min = speeds[0]
    speed_max = speeds[-1]
    rate = sorted(rates)[len(rates) // 2] if rates else 0.0
    result = {
        "encoder": encoder,
        "codec": settings.codec,
        "preset": settings.preset,
        "crf": settings.crf,
        "threads": reference_threads,
        "fps": round(median * fps_source, 2),
        "speed": round(median, 3),
        "fps_min": round(speed_min * fps_source, 2),
        "fps_max": round(speed_max * fps_source, 2),
        "speed_min": round(speed_min, 3),
        "speed_max": round(speed_max, 3),
        "sample_seconds": sample_seconds,
        "samples": len(speeds),
        "source_fps": round(fps_source, 3),
        "source_duration_sec": round(duration, 1),
        "bytes_per_second": round(rate),
        "estimated_size_bytes": int(rate * duration),
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "real_file": True,
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
    real = [
        value for key, value in benchmarks.items()
        if key.startswith(prefix) and key.endswith(":real")
    ]
    if real:
        return {**real[0], "source": "benchmark", "cached": True}
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
