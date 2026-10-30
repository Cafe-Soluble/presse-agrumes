"""Schémas Pydantic de l'API.

Les valeurs par défaut sont pensées pour un NAS : MKV, SVT-AV1 preset 8,
CRF 32, audio copié (aucune perte supplémentaire), ressources limitées.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .schedule import normalize_hhmm, parse_hhmm


class ScanOptions(BaseModel):
    min_size_mb: float = Field(default=0, ge=0, le=1_000_000)
    workers: int = Field(default=2, ge=1, le=16)
    include_av1: bool = True
    follow_symlinks: bool = False
    series_roots: list[str] = Field(default_factory=list)
    exclude_globs: list[str] = Field(default_factory=list)


class ScanRequest(BaseModel):
    root: str
    options: ScanOptions = Field(default_factory=ScanOptions)


class Sv1Settings(BaseModel):
    """Réglages de compression AV1."""

    encoder: Literal["auto", "libsvtav1", "libaom-av1", "av1_vaapi"] = "auto"
    preset: int = Field(default=8, ge=0, le=13)
    crf: int = Field(default=32, ge=0, le=63)
    pixel_format: Literal["yuv420p", "yuv420p10le"] = "yuv420p"
    audio_mode: Literal["copy", "opus", "aac", "none"] = "copy"
    audio_bitrate_kbps: int = Field(default=128, ge=32, le=512)
    container: Literal["mkv", "mp4", "webm"] = "mkv"
    subtitles: Literal["copy", "none"] = "copy"

    @field_validator("preset")
    @classmethod
    def _preset_for_aom(cls, value: int) -> int:
        # libaom n'accepte que 0-8 ; le moteur borne la valeur au moment de
        # construire la commande. On garde la valeur SVT telle quelle en base.
        return value


class CompressionSettings(Sv1Settings):
    pass


class OutputOptions(BaseModel):
    mode: Literal["same_dir_same_name", "same_dir_new_name", "custom_dir"] = "same_dir_new_name"
    suffix: str = Field(default=".av1", max_length=64)
    output_dir: str | None = None
    overwrite: bool = False

    @field_validator("suffix")
    @classmethod
    def _clean_suffix(cls, value: str) -> str:
        value = value.strip()
        if value.startswith("."):
            value = value[1:]
        return value


class OriginalOptions(BaseModel):
    mode: Literal["keep", "delete", "move"] = "keep"
    trash_dir: str | None = None


class ScheduleWindow(BaseModel):
    days: list[int] = Field(default_factory=lambda: list(range(7)))
    start: str = "22:00"
    end: str = "07:00"

    @field_validator("days")
    @classmethod
    def _valid_days(cls, value: list[int]) -> list[int]:
        days = sorted({int(day) for day in value})
        if not days:
            raise ValueError("Sélectionnez au moins un jour.")
        if any(day < 0 or day > 6 for day in days):
            raise ValueError("Les jours doivent être compris entre 0 (lundi) et 6 (dimanche).")
        return days

    @field_validator("start", "end")
    @classmethod
    def _valid_time(cls, value: str) -> str:
        parse_hhmm(value)
        return normalize_hhmm(value)


class CompressionSchedule(BaseModel):
    enabled: bool = False
    windows: list[ScheduleWindow] = Field(default_factory=list)

    @model_validator(mode="after")
    def _windows_required(self):
        if self.enabled and not self.windows:
            raise ValueError("Ajoutez au moins une plage horaire ou désactivez la planification.")
        return self


class CompressRequest(BaseModel):
    scan_id: str
    item_ids: list[str] = Field(min_length=1)
    settings: CompressionSettings = Field(default_factory=CompressionSettings)
    output: OutputOptions = Field(default_factory=OutputOptions)
    originals: OriginalOptions = Field(default_factory=OriginalOptions)
    resource_percent: int = Field(default=70, ge=5, le=100)
    concurrency: int = Field(default=1, ge=1, le=4)
    verify: bool = True
    schedule: CompressionSchedule = Field(default_factory=CompressionSchedule)


class TestRequest(BaseModel):
    path: str
    duration: int = Field(default=20, ge=3, le=120)
    start_mode: Literal["percent", "seconds"] = "percent"
    start_percent: float = Field(default=25, ge=0, le=95)
    start_seconds: float = Field(default=0, ge=0)
    settings: CompressionSettings = Field(default_factory=CompressionSettings)


class PreflightRequest(BaseModel):
    scan_id: str
    item_ids: list[str] = Field(min_length=1)
    settings: CompressionSettings = Field(default_factory=CompressionSettings)
    output: OutputOptions = Field(default_factory=OutputOptions)
    originals: OriginalOptions = Field(default_factory=OriginalOptions)
    resource_percent: int = Field(default=70, ge=5, le=100)
    concurrency: int = Field(default=1, ge=1, le=4)


class SetupRequest(BaseModel):
    """Dossier média choisi dans l'assistant de premier démarrage."""

    media_root: str = Field(min_length=1, max_length=4096)


class BenchmarkRequest(BaseModel):
    encoder: Literal["libsvtav1", "libaom-av1", "av1_vaapi"] = "libsvtav1"
    preset: int = Field(default=8, ge=0, le=13)
    threads: int | None = Field(default=None, ge=1, le=128)
    force: bool = False


class DeleteScanItems(BaseModel):
    """Suppression directe de fichiers depuis un scan (sans compression)."""

    item_ids: list[str] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _at_least_one(self):
        if not self.item_ids and not self.paths:
            raise ValueError("Indiquez au moins un item ou un chemin à supprimer.")
        return self
