"""Plages horaires autorisées pour les compressions planifiées.

Sémantique :
- `days` : jours de début, 0 = lundi, 6 = dimanche.
- `start` / `end` : heures locales du serveur, format HH:MM.
- Une plage `22:00 → 06:00` du lundi couvre lundi 22:00 → mardi 06:00.
- `start == end` signifie « toute la journée » du/des jour(s) indiqué(s).
- Hors plage, le job est mis en pause (SIGSTOP) et reprend automatiquement.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Iterable

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def parse_hhmm(value: str) -> tuple[int, int]:
    match = TIME_RE.match((value or "").strip())
    if not match:
        raise ValueError(f"Heure invalide : {value!r} (format attendu HH:MM).")
    return int(match.group(1)), int(match.group(2))


def normalize_hhmm(value: str) -> str:
    hour, minute = parse_hhmm(value)
    return f"{hour:02d}:{minute:02d}"


def _get(window: Any, key: str, default: Any = None) -> Any:
    if isinstance(window, dict):
        return window.get(key, default)
    return getattr(window, key, default)


def _minutes(value: str) -> int:
    hour, minute = parse_hhmm(value)
    return hour * 60 + minute


def _days(window: Any) -> set[int]:
    days = _get(window, "days", None)
    if days is None:
        return set(range(7))
    result = set()
    for day in days:
        try:
            number = int(day)
        except (TypeError, ValueError):
            continue
        if 0 <= number <= 6:
            result.add(number)
    return result


def is_within_windows(now: datetime, windows: Iterable[Any]) -> bool:
    """Indique si `now` tombe dans au moins une plage autorisée."""
    for window in windows:
        start = _minutes(_get(window, "start", "00:00"))
        end = _minutes(_get(window, "end", "23:59"))
        days = _days(window)
        current = now.hour * 60 + now.minute
        weekday = now.weekday()
        if start == end:
            if weekday in days:
                return True
            continue
        if start < end:
            if weekday in days and start <= current < end:
                return True
        else:
            # Plage qui traverse minuit : le jour de début est `days`, la
            # partie après minuit appartient au lendemain.
            if weekday in days and current >= start:
                return True
            if (weekday - 1) % 7 in days and current < end:
                return True
    return False


def next_window_start(now: datetime, windows: Iterable[Any]) -> datetime | None:
    """Prochaine date/heure de début de plage strictement après `now`."""
    candidates: list[datetime] = []
    for window in windows:
        days = _days(window)
        if not days:
            continue
        start_hour, start_minute = parse_hhmm(_get(window, "start", "00:00"))
        for offset in range(0, 9):
            day = (now + timedelta(days=offset)).date()
            if day.weekday() not in days:
                continue
            candidate = datetime(
                day.year, day.month, day.day,
                start_hour, start_minute,
                tzinfo=now.tzinfo,
            )
            if candidate > now:
                candidates.append(candidate)
    return min(candidates) if candidates else None


def describe_windows(windows: Iterable[Any]) -> str:
    labels = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    parts = []
    for window in windows:
        days = sorted(_days(window))
        if not days:
            continue
        day_label = (
            "Tous les jours"
            if len(days) == 7
            else " ".join(labels[day] for day in days)
        )
        parts.append(
            f"{day_label} {normalize_hhmm(str(_get(window, 'start', '00:00')))}–"
            f"{normalize_hhmm(str(_get(window, 'end', '23:59')))}"
        )
    return " · ".join(parts) if parts else "aucune plage"
