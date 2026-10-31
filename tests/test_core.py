from __future__ import annotations

import os
import socket
from datetime import datetime, timezone
from pathlib import Path

import pytest

from presse_agrumes import config, media, network, paths, schedule, series
from presse_agrumes.jobs import Job


def test_human_size_and_duration():
    assert media.human_size(0) == "0 o"
    assert media.human_size(1024) == "1.0 Ko"
    assert media.human_size(1024**3) == "1.0 Go"
    assert media.human_duration(3661) == "1 h 01 min"
    assert media.human_duration(90) == "1 min 30 s"


@pytest.mark.parametrize(
    "raw,expected",
    [("25/1", 25.0), ("30000/1001", pytest.approx(29.97, rel=1e-3)), ("0/0", None), (None, None)],
)
def test_parse_frame_rate(raw, expected):
    assert media.parse_frame_rate(raw) == expected


def test_estimate_gain_av1_is_zero():
    factor, gain, bpp, output = media.estimate_gain("av1", 1_000_000, 5_000_000, 1920, 1080, 25)
    assert factor == 0
    assert gain == 0
    assert output == 1_000_000
    assert bpp is None


def test_estimate_gain_h264_is_positive_and_capped():
    factor, gain, _bpp, output = media.estimate_gain("h264", 1_000_000, 8_000_000, 1920, 1080, 25)
    assert 0 < factor <= media.MAX_GAIN_FACTOR
    assert gain > 0
    assert output == 1_000_000 - gain


def test_analyze_real_file(media_root: Path):
    path = media_root / "film.mp4"
    entry = media.analyze_file(path, media_root)
    assert entry["error"] is None
    assert entry["video_codec"] == "h264"
    assert entry["width"] == 640
    assert entry["height"] == 360
    assert entry["duration_sec"] > 3
    assert entry["estimated_gain_bytes"] > 0
    assert entry["relative_path"] == "film.mp4"


def test_analyze_unreadable_file(media_root: Path):
    path = media_root / "illisible.mp4"
    if not path.exists() or os.geteuid() == 0:
        pytest.skip("test exécuté en root : permissions non applicables")
    entry = media.analyze_file(path, media_root)
    assert entry["error"] is not None
    assert entry["error_code"] == "permission_denied"


def test_empty_and_corrupt_files_are_friendly(media_root: Path):
    empty = media_root / "vide-mais-lisible.mp4"
    empty.write_bytes(b"")
    empty.chmod(0o644)
    entry = media.analyze_file(empty, media_root)
    assert entry["error_code"] == "empty_file"
    assert "0 octet" in entry["error"]

    corrupt = media_root / "corrompu.mp4"
    corrupt.write_bytes(b"ceci n'est pas une video" * 100)
    corrupt.chmod(0o644)
    entry = media.analyze_file(corrupt, media_root)
    assert entry["error_code"] in {"invalid_data", "probe_error"}
    assert "corrompu" in entry["error"].lower() or "illisible" in entry["error"].lower()
    assert entry["error_hint"]


def test_schedule_windows_and_next_start():
    # Lundi 2 novembre 2026, 23:00 UTC
    monday = datetime(2026, 11, 2, 23, 0, tzinfo=timezone.utc)
    window = {"days": [0], "start": "22:00", "end": "06:00"}
    assert schedule.is_within_windows(monday, [window])
    tuesday_early = datetime(2026, 11, 3, 5, 30, tzinfo=timezone.utc)
    assert schedule.is_within_windows(tuesday_early, [window])
    tuesday_noon = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
    assert not schedule.is_within_windows(tuesday_noon, [window])
    assert schedule.next_window_start(tuesday_noon, [window]) == datetime(
        2026, 11, 9, 22, 0, tzinfo=timezone.utc
    )

    all_day = {"days": [0], "start": "00:00", "end": "00:00"}
    assert schedule.is_within_windows(monday, [all_day])
    assert "Tous" not in schedule.describe_windows([all_day])  # jour unique


def test_schedule_validation():
    from presse_agrumes.models import CompressionSchedule, ScheduleWindow

    ScheduleWindow(days=[0, 1], start="22:00", end="06:00")
    with pytest.raises(ValueError):
        ScheduleWindow(days=[], start="22:00", end="06:00")
    with pytest.raises(ValueError):
        ScheduleWindow(days=[7], start="22:00", end="06:00")
    with pytest.raises(ValueError):
        ScheduleWindow(days=[0], start="25:00", end="06:00")
    with pytest.raises(ValueError):
        CompressionSchedule(enabled=True, windows=[])


def test_job_pause_state():
    job = Job("pause-test", "compress", "test")
    job.set_status("running")
    assert job.status == "running"
    job.pause("manual")
    assert job.status == "paused"
    assert "manual" in job.snapshot()["pause_reasons"]
    assert job.resume("manual")
    assert job.status == "running"
    assert job.snapshot()["pause_reasons"] == []


def test_find_available_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        busy = sock.getsockname()[1]
        assert not network.is_port_available(busy, "127.0.0.1")
        found = network.find_available_port(busy, "127.0.0.1", max_tries=20)
        assert found > busy
        assert network.is_port_available(found, "127.0.0.1")
    assert isinstance(network.local_ip_addresses(), list)


def test_guard_path_rejects_outside_allowed_root(tmp_path: Path):
    with pytest.raises(paths.PathError):
        paths.guard_path("/etc")
    inside = config.DATA_DIR.parent / "media"
    assert paths.guard_path(inside).is_absolute()
    with pytest.raises(paths.PathError):
        paths.guard_path(tmp_path)


def test_series_grouping(media_root: Path):
    marker = media_root / "Series"
    entries = []
    for name in ("Breaking.Bad.S01E01.mkv", "Breaking.Bad.S01E02.mkv"):
        entry = media.analyze_file(marker / "Breaking.Bad.S01" / name, media_root)
        entries.append(entry)
    loose = media.analyze_file(media_root / "film.mp4", media_root)
    entries.append(loose)

    grouped = series.build_items(entries, media_root, [str(marker)])
    packs = [item for item in grouped["items"] if item["kind"] == "series"]
    files = [item for item in grouped["items"] if item["kind"] == "file"]
    assert len(packs) == 1
    assert len(files) == 1
    pack = packs[0]
    assert pack["episode_count"] == 2
    assert pack["season_label"] == "S01"
    assert "Breaking.Bad" in pack["name"]
    assert pack["estimated_gain_bytes"] == sum(e["estimated_gain_bytes"] for e in entries[:2])
    assert grouped["summary"]["already_av1_count"] == 0
    assert grouped["summary"]["pack_count"] == 1


def test_series_marking_the_series_folder_itself(media_root: Path):
    marker = media_root / "Series" / "Breaking.Bad.S01"
    entries = [
        media.analyze_file(marker / name, media_root)
        for name in ("Breaking.Bad.S01E01.mkv", "Breaking.Bad.S01E02.mkv")
    ]
    grouped = series.build_items(entries, media_root, [str(marker)])
    pack = grouped["items"][0]
    assert pack["episode_count"] == 2
    # Le dossier marqué est directement le dossier de saison : le nom de série
    # est déduit du parent.
    assert pack["name"].startswith("Breaking.Bad")
    assert "S01" in pack["name"]


def test_adjusted_gain_follows_crf():
    base = 0.4
    low_crf = media.adjusted_gain_for_crf(base, 1_000_000, 24)
    reference = media.adjusted_gain_for_crf(base, 1_000_000, 32)
    high_crf = media.adjusted_gain_for_crf(base, 1_000_000, 34)
    assert low_crf[0] < reference[0] < high_crf[0]
    assert low_crf[2] > reference[2] > high_crf[2]
