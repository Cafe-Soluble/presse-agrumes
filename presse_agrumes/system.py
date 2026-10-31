"""Métriques système pour l'onglet de supervision.

Lecture directe de /proc et /sys, sans dépendance externe. Les valeurs non
disponibles (GPU sans compteur d'utilisation, température absente) sont
renvoyées à None plutôt que inventées.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path

_lock = threading.Lock()
_previous_cpu: tuple[int, int] | None = None


def _read_cpu_times() -> tuple[int, int] | None:
    try:
        line = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        return None
    parts = line.split()
    if len(parts) < 5 or parts[0] != "cpu":
        return None
    try:
        values = [int(value) for value in parts[1:]]
    except ValueError:
        return None
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values), idle


def cpu_usage() -> dict:
    global _previous_cpu
    cores = os.cpu_count() or 1
    try:
        load1, load5, load15 = os.getloadavg()
    except OSError:
        load1 = load5 = load15 = None
    current = _read_cpu_times()
    percent = None
    with _lock:
        if current and _previous_cpu:
            total_delta = current[0] - _previous_cpu[0]
            idle_delta = current[1] - _previous_cpu[1]
            if total_delta > 0:
                percent = round(
                    100 * (total_delta - idle_delta) / total_delta, 1
                )
        _previous_cpu = current
    if percent is None and load1 is not None:
        percent = round(min(100.0, load1 / cores * 100), 1)
    return {
        "percent": percent,
        "cores": cores,
        "load_1": round(load1, 2) if load1 is not None else None,
        "load_5": round(load5, 2) if load5 is not None else None,
        "load_15": round(load15, 2) if load15 is not None else None,
    }


def memory_usage() -> dict:
    total = available = None
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                total = int(line.split()[1]) * 1024
            elif line.startswith("MemAvailable:"):
                available = int(line.split()[1]) * 1024
    except OSError:
        pass
    used = None
    percent = None
    if total and available is not None:
        used = max(0, total - available)
        percent = round(used / total * 100, 1)
    return {
        "total_bytes": total,
        "used_bytes": used,
        "available_bytes": available,
        "percent": percent,
    }


def _read_sensor(path: Path) -> float | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
        value = float(raw)
    except (OSError, ValueError):
        return None
    if value > 1000:
        value /= 1000
    if value <= 0 or value > 150:
        return None
    return round(value, 1)


def cpu_temperature() -> dict:
    sensors: list[dict] = []
    for base in (Path("/sys/class/thermal"), Path("/sys/class/hwmon")):
        if not base.is_dir():
            continue
        for path in base.glob("thermal_zone*/temp"):
            value = _read_sensor(path)
            if value is not None:
                sensors.append({"name": path.parent.name, "celsius": value})
        for path in base.glob("hwmon*/temp*_input"):
            value = _read_sensor(path)
            if value is None:
                continue
            label_path = path.with_name(path.name.replace("_input", "_label"))
            try:
                label = label_path.read_text(encoding="utf-8").strip()
            except OSError:
                label = path.parent.name
            sensors.append({"name": label or path.parent.name, "celsius": value})
    if not sensors:
        return {"celsius": None, "sensor": None}
    hottest = max(sensors, key=lambda item: item["celsius"])
    return {"celsius": hottest["celsius"], "sensor": hottest["name"]}


def _intel_gpu() -> dict | None:
    cards = sorted(Path("/sys/class/drm").glob("card[0-9]*/device"))
    if not cards:
        return None
    device = cards[0]
    try:
        vendor = (device / "vendor").read_text(encoding="utf-8").strip()
    except OSError:
        vendor = ""
    if vendor != "0x8086":
        return None
    name = "Intel"
    try:
        name = (device / "label").read_text(encoding="utf-8").strip() or name
    except OSError:
        pass
    frequency = None
    for path in device.glob("gt_cur_freq_mhz"):
        try:
            frequency = int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            pass
    return {
        "name": name,
        "utilization_percent": None,
        "memory_used_bytes": None,
        "memory_total_bytes": None,
        "temperature_c": None,
        "frequency_mhz": frequency,
        "source": "sysfs",
    }


def _amd_gpu() -> dict | None:
    for device in sorted(Path("/sys/class/drm").glob("card[0-9]*/device")):
        try:
            vendor = (device / "vendor").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if vendor != "0x1002":
            continue
        busy = used = total = None
        try:
            busy = int((device / "gpu_busy_percent").read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            pass
        try:
            used = int((device / "mem_info_vram_used").read_text(encoding="utf-8").strip())
            total = int((device / "mem_info_vram_total").read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            pass
        temperature = None
        for path in Path("/sys/class/hwmon").glob("hwmon*/temp1_input"):
            temperature = _read_sensor(path)
            if temperature is not None:
                break
        return {
            "name": "AMD GPU",
            "utilization_percent": busy,
            "memory_used_bytes": used,
            "memory_total_bytes": total,
            "temperature_c": temperature,
            "frequency_mhz": None,
            "source": "sysfs",
        }
    return None


def _nvidia_gpu() -> dict | None:
    binary = shutil.which("nvidia-smi")
    if not binary:
        return None
    try:
        proc = subprocess.run(
            [
                binary,
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    first = proc.stdout.strip().splitlines()[0]
    parts = [part.strip() for part in first.split(",")]
    if len(parts) < 5:
        return None
    name, utilization, used, total, temperature = parts[:5]

    def _int(value: str) -> int | None:
        try:
            return int(float(value))
        except ValueError:
            return None

    used_mb, total_mb = _int(used), _int(total)
    return {
        "name": name,
        "utilization_percent": _int(utilization),
        "memory_used_bytes": used_mb * 1024 * 1024 if used_mb is not None else None,
        "memory_total_bytes": total_mb * 1024 * 1024 if total_mb is not None else None,
        "temperature_c": float(temperature) if temperature else None,
        "frequency_mhz": None,
        "source": "nvidia-smi",
    }


def gpu_usage() -> dict | None:
    return _nvidia_gpu() or _amd_gpu() or _intel_gpu()


def snapshot() -> dict:
    return {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "cpu": cpu_usage(),
        "memory": memory_usage(),
        "temperature": cpu_temperature(),
        "gpu": gpu_usage(),
    }
