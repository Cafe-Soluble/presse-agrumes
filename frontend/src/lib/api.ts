import type {
  AppConfig,
  BrowseData,
  CompressionPayload,
  Health,
  Hardware,
  JobSnapshot,
  MountRoot,
  PreflightResult,
  Scan,
  ScanOptions,
  ScanSummary,
  TestMeta,
  TestPayload,
  Benchmark,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  const text = await response.text();
  let payload: unknown = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = text;
  }
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : typeof payload === "string" && payload
          ? payload
          : `Erreur HTTP ${response.status}`;
    throw new Error(detail);
  }
  return payload as T;
}

export const api = {
  health: () => request<Health>("/api/health"),
  config: () => request<AppConfig>("/api/config"),
  hardware: (refresh = false) =>
    request<Hardware>(`/api/hardware${refresh ? "?refresh=true" : ""}`),
  mounts: () => request<{ roots: MountRoot[]; home: string }>("/api/mounts"),
  disk: (path: string) =>
    request<{
      path: string;
      free_bytes: number;
      free_human: string;
      total_bytes: number;
      total_human: string;
      used_percent: number;
    }>(`/api/disk?path=${encodeURIComponent(path)}`),
  setup: () => request<import("./types").SetupState>("/api/setup"),
  saveSetup: (mediaRoot: string) =>
    request<{ configured: boolean; media_root: string; writable: boolean }>("/api/setup", {
      method: "POST",
      body: JSON.stringify({ media_root: mediaRoot }),
    }),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<{ changed: boolean }>("/api/auth/password", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),
  browse: (path: string) =>
    request<BrowseData>(`/api/browse?path=${encodeURIComponent(path)}`),
  createFolder: (parent: string, name: string) =>
    request<{ path: string }>("/api/browse/mkdir", {
      method: "POST",
      body: JSON.stringify({ parent, name }),
    }),
  startScan: (root: string, options: ScanOptions) =>
    request<JobSnapshot>("/api/scans", {
      method: "POST",
      body: JSON.stringify({ root, options }),
    }),
  listScans: () => request<{ scans: ScanSummary[] }>("/api/scans"),
  getScan: (scanId: string) => request<Scan>(`/api/scans/${scanId}`),
  deleteScan: (scanId: string) =>
    request<{ deleted: boolean }>(`/api/scans/${scanId}`, { method: "DELETE" }),
  deleteScanItems: (scanId: string, itemIds: string[], paths: string[]) =>
    request<import("./types").DeleteScanResult>(`/api/scans/${scanId}/delete`, {
      method: "POST",
      body: JSON.stringify({ item_ids: itemIds, paths }),
    }),
  preflight: (payload: CompressionPayload) =>
    request<PreflightResult>("/api/preflight", {
      method: "POST",
      body: JSON.stringify({
        scan_id: payload.scan_id,
        item_ids: payload.item_ids,
        settings: payload.settings,
        output: payload.output,
        originals: payload.originals,
        resource_percent: payload.resource_percent,
        concurrency: payload.concurrency,
      }),
    }),
  startCompression: (payload: CompressionPayload) =>
    request<JobSnapshot>("/api/compressions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  startTest: (payload: TestPayload) =>
    request<JobSnapshot>("/api/tests", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  testMeta: (testId: string) => request<TestMeta>(`/api/tests/${testId}/meta`),
  getJob: (jobId: string) => request<JobSnapshot>(`/api/jobs/${jobId}`),
  activeJobs: () => request<{ jobs: JobSnapshot[] }>("/api/jobs/active"),
  pauseJob: (jobId: string) =>
    request<{ paused: boolean }>(`/api/jobs/${jobId}/pause`, { method: "POST" }),
  resumeJob: (jobId: string) =>
    request<{ resumed: boolean }>(`/api/jobs/${jobId}/resume`, { method: "POST" }),
  cancelJob: (jobId: string) =>
    request<{ cancelled: boolean }>(`/api/jobs/${jobId}/cancel`, { method: "POST" }),
  jobs: (limit = 50) =>
    request<{ jobs: import("./types").JobSnapshot[] }>(`/api/jobs?limit=${limit}`),
  listJobs: (limit = 30) => request<{ jobs: JobSnapshot[] }>(`/api/jobs?limit=${limit}`),
  benchmark: (payload: {
    encoder: string;
    preset: number;
    force?: boolean;
    path?: string;
    settings?: import("./types").CompressionSettings;
    samples?: number;
    threads?: number;
  }) =>
    request<{ benchmark: Benchmark; hardware: Hardware }>("/api/hardware/benchmark", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

export function testFileUrl(testId: string, filename: string, download = false) {
  return `/api/tests/${testId}/files/${encodeURIComponent(filename)}${download ? "?download=1" : ""}`;
}
