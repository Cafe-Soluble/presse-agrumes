import type { CompressionSettings, Hardware, Scan, ScanItem } from "./types";
import { itemFileCount } from "./utils";

const FALLBACK_FPS: Record<string, Record<number, number>> = {
  libsvtav1: { 0: 2, 2: 6, 4: 13, 6: 24, 8: 42, 10: 70, 12: 115, 13: 140 },
  "libaom-av1": { 0: 1, 2: 2.5, 4: 5, 6: 7, 8: 10, 10: 13, 12: 16, 13: 18 },
  av1_vaapi: { 0: 40, 2: 60, 4: 80, 6: 100, 8: 120, 10: 140, 12: 160, 13: 180 },
};

export function effectiveEncoder(hardware: Hardware | undefined, settings: CompressionSettings) {
  if (settings.encoder !== "auto") return settings.encoder;
  return hardware?.ffmpeg.recommended_encoder ?? "libsvtav1";
}

export function benchmarkFor(hardware: Hardware | undefined, settings: CompressionSettings) {
  const encoder = effectiveEncoder(hardware, settings);
  const preset = Number(settings.preset);
  const benchmarks = hardware?.benchmarks ?? {};
  const prefix = `${encoder}:p${preset}:`;
  for (const [key, value] of Object.entries(benchmarks)) {
    if (key.startsWith(prefix)) {
      return { fps: value.fps, threads: value.threads, source: "mesuré" as const };
    }
  }
  const table = FALLBACK_FPS[encoder] ?? FALLBACK_FPS.libsvtav1;
  const nearest = Object.keys(table)
    .map(Number)
    .reduce((best, key) => (Math.abs(key - preset) < Math.abs(best - preset) ? key : best), 8);
  const logical = hardware?.cpu.logical_cores ?? 4;
  return {
    fps: Math.max(0.5, (table[nearest] ?? 42) * (logical / 12)),
    threads: logical,
    source: "indicatif" as const,
  };
}

export function estimateSeconds(
  durationSec: number,
  fileCount: number,
  hardware: Hardware | undefined,
  settings: CompressionSettings,
  resourcePercent: number,
  concurrency: number,
) {
  const info = benchmarkFor(hardware, settings);
  const logical = hardware?.cpu.logical_cores ?? 4;
  const allotted = Math.max(1, Math.round((logical * resourcePercent) / 100));
  const perJob = Math.max(1, Math.floor(allotted / Math.max(1, concurrency)));
  const scale = Math.min(1, perJob / Math.max(1, info.threads));
  const fps = Math.max(0.2, info.fps * scale);
  return {
    seconds: (durationSec / fps) * 1.12 + fileCount * 1.5,
    source: info.source,
    fps,
    threads: perJob,
  };
}

export function selectionFromState(
  scan: Scan | undefined,
  selection: Set<string>,
): ScanItem[] {
  if (!scan) return [];
  return scan.items.filter((item) => selection.has(item.id));
}

export function selectionStats(
  scan: Scan | undefined,
  selection: Set<string>,
  hardware: Hardware | undefined,
  settings: CompressionSettings,
  resourcePercent: number,
  concurrency: number,
) {
  const items = selectionFromState(scan, selection);
  const fileCount = items.reduce((sum, item) => sum + itemFileCount(item), 0);
  const duration = items.reduce((sum, item) => sum + (item.duration_sec || 0), 0);
  const size = items.reduce((sum, item) => sum + (item.size_bytes || 0), 0);
  const output = items.reduce((sum, item) => sum + (item.estimated_output_bytes || 0), 0);
  const estimate = estimateSeconds(
    duration,
    fileCount,
    hardware,
    settings,
    resourcePercent,
    concurrency,
  );
  return { items, fileCount, duration, size, output, ...estimate };
}
