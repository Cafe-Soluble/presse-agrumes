export type JobStatus = "queued" | "running" | "paused" | "done" | "error" | "cancelled" | "interrupted";
export type JobKind = "scan" | "compress" | "test";

export interface Warning {
  path?: string;
  warning: string;
  error?: boolean;
  info?: boolean;
  item_id?: string;
}

export interface JobProgress {
  phase: string;
  percent: number;
  done: number;
  total: number;
  message: string;
  current?: string | null;
  eta_seconds?: number | null;
  elapsed_seconds: number;
  speed?: string | null;
  fps?: number | null;
}

export interface JobItem {
  task_id: string;
  filename: string;
  source?: string;
  destination?: string;
  duration_sec: number;
  input_size: number;
  status: string;
  percent: number;
  speed?: string | null;
  eta_seconds?: number | null;
  output_size?: number | null;
  saved_bytes?: number | null;
  warning?: string | null;
  error?: string | null;
}

export interface CompressionResult {
  success: number;
  failed: number;
  total: number;
  input_bytes: number;
  output_bytes: number;
  saved_bytes: number;
  saved_percent: number;
  elapsed_seconds: number;
  encoder: string;
  cancelled?: boolean;
  settings?: CompressionSettings;
  originals?: OriginalOptions;
  output?: OutputOptions;
  items?: JobItem[];
}

export interface TestMeta {
  id: string;
  created_at: string;
  status: string;
  source: string;
  source_duration_sec: number;
  start_sec: number;
  duration_sec: number;
  settings: CompressionSettings;
  encoder: string;
  files: {
    original_preview?: TestFile;
    original_raw?: TestFile;
    compressed?: TestFile;
  };
  comparison?: {
    reference?: "original_raw" | "original_preview";
    original_bitrate_bps?: number;
    compressed_bitrate_bps?: number;
    saved_percent?: number;
    note?: string;
  };
  error?: string;
}

export interface TestFile {
  filename: string;
  label: string;
  url: string;
  size_bytes: number;
  size_human: string;
  duration_sec?: number;
  bitrate_bps?: number;
}

export interface JobSnapshot {
  id: string;
  kind: JobKind;
  label: string;
  status: JobStatus;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  seq?: number;
  progress: JobProgress;
  result?: {
    scan_id?: string;
    summary?: ScanSummary;
    test_id?: string;
    meta?: TestMeta;
    success?: number;
    failed?: number;
    cancelled?: boolean;
    [key: string]: unknown;
  } | null;
  error?: string | null;
  warnings: Warning[];
  items: JobItem[];
  estimate?: EstimateInfo | null;
  logs?: string[];
  context?: {
    scan_id?: string;
    item_count?: number;
    root?: string;
    path?: string;
    [key: string]: unknown;
  };
  schedule?: CompressionSchedule | null;
  pause_reasons?: string[];
  next_resume_at?: string | null;
}

export interface EstimateInfo {
  seconds: number;
  fps_reference: number;
  source: "benchmark" | "estimate" | "mesuré" | "indicatif";
  threads_allotted: number;
  threads_per_job: number;
  encoder?: string | null;
  preset?: number;
}

export interface EpisodeInfo {
  id: string;
  path: string;
  relative_path?: string;
  filename: string;
  episode?: string | null;
  size_bytes: number;
  size_human: string;
  duration_sec: number;
  duration_human: string;
  video_codec?: string;
  resolution?: string;
  estimated_gain_bytes: number;
  estimated_gain_human?: string;
  estimated_gain_percent: number;
  already_av1: boolean;
  error?: string | null;
}

export type Recommendation = "excellent" | "bon" | "faible" | "tres_faible" | "already_av1" | string;

export interface ScanItem {
  id: string;
  kind: "file" | "series";
  name: string;
  path: string;
  relative_path: string;
  filename?: string;
  parent?: string;
  extension?: string;
  size_bytes: number;
  size_human: string;
  duration_sec: number;
  duration_human?: string;
  estimated_gain_bytes: number;
  estimated_gain_human: string;
  estimated_gain_percent: number;
  estimated_output_bytes: number;
  estimated_output_human?: string;
  recommendation: Recommendation;
  already_av1?: boolean;
  episode_count?: number;
  episodes?: EpisodeInfo[];
  already_av1_count?: number;
  codec_summary?: Record<string, number>;
  resolution_summary?: Record<string, number>;
  error_count?: number;
  parent_writable?: boolean;
  video_codec?: string;
  resolution?: string;
  fps?: number | null;
  is_hdr?: boolean;
  is_10bit?: boolean;
  audio_codec?: string;
  series_name?: string;
  error?: string | null;
  error_code?: string | null;
  error_hint?: string | null;
}

export interface ScanSummary {
  id?: string;
  root?: string;
  created_at?: string;
  partial?: boolean;
  series_roots?: string[];
  items_count: number;
  pack_count: number;
  file_count: number;
  error_count: number;
  video_file_count: number;
  total_size_bytes: number;
  total_size_human: string;
  total_gain_bytes: number;
  total_gain_human: string;
  total_gain_percent: number;
  total_output_bytes: number;
  total_output_human: string;
  total_duration_sec: number;
  total_duration_human: string;
  already_av1_count: number;
  walk_errors_count?: number;
  analysis_seconds?: number;
  walk_seconds?: number;
  dirs_scanned?: number;
}

export interface ScanOptions {
  min_size_mb: number;
  workers: number;
  include_av1: boolean;
  follow_symlinks: boolean;
  series_roots: string[];
  exclude_globs: string[];
}

export interface ScanError {
  path: string;
  error: string;
  filename?: string;
  error_code?: string | null;
  error_hint?: string | null;
}

export interface Scan {
  id: string;
  created_at: string;
  root: string;
  options: ScanOptions;
  series_roots: string[];
  walk_errors: ScanError[];
  files: unknown[];
  items: ScanItem[];
  packs: ScanItem[];
  errors: ScanError[];
  summary: ScanSummary;
}

export interface BrowseEntry {
  name: string;
  path: string;
  exists: boolean;
  is_dir: boolean;
  readable: boolean;
  writable: boolean;
  is_symlink?: boolean;
  error?: string;
}

export interface BrowseData {
  path: string;
  parent: string | null;
  name: string;
  directories: BrowseEntry[];
  videos: BrowseEntry[];
  errors: string[];
  permissions: {
    path: string;
    exists: boolean;
    is_dir: boolean;
    readable: boolean;
    writable: boolean;
    error?: string;
  };
  breadcrumbs: { name: string; path: string }[];
}

export interface MountRoot {
  path: string;
  name: string;
  readable: boolean;
  writable: boolean;
  empty?: boolean;
}

export interface SetupState {
  needed: boolean;
  media_root: string;
  media_root_exists: boolean;
  roots: MountRoot[];
  allowed_roots: string[];
}

export interface Hardware {
  hostname: string;
  platform: string;
  cpu: {
    model: string;
    logical_cores: number;
    physical_cores?: number | null;
    mhz?: number | null;
  };
  memory: { total_bytes?: number | null; available_bytes?: number | null };
  gpu: {
    devices: string[];
    vaapi_available: boolean;
    vaapi?: {
      device: string;
      accessible: boolean;
      driver: string | null;
      vainfo_error: string | null;
      reason: string | null;
      tested: boolean;
      decode_ok: boolean | null;
      decode_error: string | null;
      codecs: {
        codec: string;
        label: string;
        decode: boolean;
        encode: boolean;
        compiled: boolean;
        tested_encode: boolean | null;
        tested_decode: boolean | null;
        usable_encode: boolean;
        error: string | null;
      }[];
    };
  };
  ffmpeg: {
    path: string | null;
    ffprobe_path: string | null;
    version: string | null;
    encoders: Record<string, boolean>;
    recommended_encoder: string | null;
  };
  fingerprint: string;
  benchmarks: Record<string, Benchmark>;
  detected_at: string;
}

export interface Benchmark {
  encoder: string;
  codec?: string;
  preset: number;
  crf?: number;
  threads: number;
  fps: number;
  speed: number;
  elapsed_sec?: number;
  sample_duration_sec?: number;
  tested_at: string;
  cached?: boolean;
  source?: string;
  speed_min?: number;
  speed_max?: number;
  fps_min?: number;
  fps_max?: number;
  samples?: number;
  bytes_per_second?: number;
  estimated_size_bytes?: number;
  real_file?: boolean;
}

export interface QualityPreset {
  id: string;
  label: string;
  preset: number;
  crf: number;
  description: string;
}

export interface CompressionSettings {
  codec: "av1" | "hevc";
  encoder:
    | "auto"
    | "libsvtav1"
    | "libaom-av1"
    | "av1_vaapi"
    | "libx265"
    | "hevc_vaapi"
    | "hevc_qsv";
  preset: number;
  crf: number;
  pixel_format: "yuv420p" | "yuv420p10le";
  audio_mode: "copy" | "opus" | "aac" | "none";
  audio_bitrate_kbps: number;
  container: "mkv" | "mp4" | "webm";
  subtitles: "copy" | "none";
}

export interface OutputOptions {
  mode: "same_dir_same_name" | "same_dir_new_name" | "custom_dir";
  suffix: string;
  output_dir: string | null;
  overwrite: boolean;
  clean_codec_names?: boolean;
}

export interface OriginalOptions {
  mode: "keep" | "delete" | "move";
  trash_dir: string | null;
}

export interface ScheduleWindow {
  days: number[];
  start: string;
  end: string;
}

export interface CompressionSchedule {
  enabled: boolean;
  windows: ScheduleWindow[];
}

export interface AppConfig {
  version: string;
  allowed_roots: string[];
  auth_enabled: boolean;
  auth_user?: string | null;
  server_timezone?: string;
  quality_presets: QualityPreset[];
  defaults: {
    settings: CompressionSettings;
    output: OutputOptions;
    originals: OriginalOptions;
    resource_percent: number;
    concurrency: number;
  };
  notes: string[];
}

export interface Health {
  status: string;
  name: string;
  version: string;
  ffmpeg: string | null;
  ffprobe: string | null;
  auth_enabled: boolean;
  server_timezone?: string;
  server_time?: string;
}

export interface PreflightResult {
  file_count: number;
  selected_source_count: number;
  skipped: Warning[];
  warnings: Warning[];
  estimate: EstimateInfo;
  encoder: string;
  threads: number;
  total_duration_sec: number;
  total_input_bytes: number;
  total_input_human: string;
  total_estimated_output_bytes: number;
  total_estimated_output_human: string;
  free_space_bytes: number;
  free_space_human: string;
  free_space_path?: string;
  space_ok?: boolean;
  sample_destinations: { source: string; destination: string }[];
}

export interface DeleteScanResult {
  deleted: string[];
  deleted_count: number;
  errors: { path: string; error: string }[];
  warnings: Warning[];
  summary: ScanSummary;
}

export interface CompressionPayload {
  scan_id: string;
  item_ids: string[];
  settings: CompressionSettings;
  output: OutputOptions;
  originals: OriginalOptions;
  resource_percent: number;
  concurrency: number;
  verify: boolean;
  schedule: CompressionSchedule;
}

export interface TestPayload {
  path: string;
  duration: number;
  start_mode: "percent" | "seconds";
  start_percent: number;
  start_seconds: number;
  settings: CompressionSettings;
}

export interface SystemStats {
  timestamp: string;
  cpu: {
    percent: number | null;
    cores: number;
    load_1: number | null;
    load_5: number | null;
    load_15: number | null;
  };
  memory: {
    total_bytes: number | null;
    used_bytes: number | null;
    available_bytes: number | null;
    percent: number | null;
  };
  temperature: { celsius: number | null; sensor: string | null };
  gpu: {
    name: string;
    utilization_percent: number | null;
    memory_used_bytes: number | null;
    memory_total_bytes: number | null;
    temperature_c: number | null;
    frequency_mhz: number | null;
    source: string;
  } | null;
}
