import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { Recommendation, ScanItem } from "./types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const numberFormatter = new Intl.NumberFormat("fr-FR");

export function formatNumber(value: number | null | undefined) {
  return numberFormatter.format(value ?? 0);
}

export function formatBytes(bytes: number | null | undefined) {
  if (bytes === null || bytes === undefined || Number.isNaN(Number(bytes))) return "-";
  let value = Number(bytes);
  if (value < 1024) return `${Math.round(value)} o`;
  const units = ["Ko", "Mo", "Go", "To", "Po"];
  let index = -1;
  do {
    value /= 1024;
    index += 1;
  } while (value >= 1024 && index < units.length - 1);
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[index]}`;
}

export function formatDuration(seconds: number | null | undefined) {
  if (!seconds || seconds <= 0) return "-";
  const total = Math.round(seconds);
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (days) return `${days} j ${hours} h`;
  if (hours) return `${hours} h ${String(minutes).padStart(2, "0")} min`;
  if (minutes) return `${minutes} min ${String(secs).padStart(2, "0")} s`;
  return `${secs} s`;
}

export function formatEta(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return "";
  if (seconds <= 0) return "quelques secondes";
  if (seconds < 60) return `~${Math.ceil(seconds)} s`;
  if (seconds < 3600) return `~${Math.ceil(seconds / 60)} min`;
  return `~${formatDuration(seconds)}`;
}

export function formatPercent(value: number | null | undefined) {
  const number = Number(value ?? 0);
  return `${number.toFixed(number >= 10 ? 0 : 1)} %`;
}

export function formatBits(bitsPerSecond: number | null | undefined) {
  if (!bitsPerSecond) return "-";
  const mbps = bitsPerSecond / 1_000_000;
  return `${mbps.toFixed(mbps >= 10 ? 1 : 2)} Mbps`;
}

export function timeAgo(iso: string | null | undefined) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const diff = Math.max(0, (Date.now() - date.getTime()) / 1000);
  if (diff < 60) return "à l'instant";
  if (diff < 3600) return `il y a ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `il y a ${Math.floor(diff / 3600)} h`;
  return `il y a ${Math.floor(diff / 86400)} j`;
}

export function isAlreadyAv1(item: ScanItem) {
  return item.already_av1 || (item.kind === "series" && item.already_av1_count === item.episode_count);
}

export function recommendationMeta(recommendation: Recommendation) {
  switch (recommendation) {
    case "excellent":
      return { label: "Gain excellent", className: "border-success/30 bg-success/10 text-success" };
    case "bon":
      return { label: "Bon candidat", className: "border-success/30 bg-success/10 text-success" };
    case "faible":
      return { label: "Gain faible", className: "border-warning/30 bg-warning/10 text-warning" };
    case "tres_faible":
      return { label: "Peu intéressant", className: "border-border bg-muted/40 text-muted-foreground" };
    case "already_av1":
      return { label: "Déjà AV1", className: "border-sky-400/30 bg-sky-400/10 text-sky-300" };
    default:
      return { label: "À évaluer", className: "border-border bg-muted/40 text-muted-foreground" };
  }
}

export function errorCodeLabel(code: string | null | undefined) {
  switch (code) {
    case "empty_file":
      return "Fichier vide";
    case "invalid_data":
      return "Format illisible";
    case "permission_denied":
      return "Permission refusée";
    case "not_found":
      return "Fichier introuvable";
    case "timeout":
      return "Délai dépassé";
    case "no_video":
      return "Pas de flux vidéo";
    case "stat_error":
      return "Erreur d'accès";
    default:
      return "Erreur";
  }
}

export function pauseReasonLabel(reason: string) {
  switch (reason) {
    case "manual":
      return "pause manuelle";
    case "schedule":
      return "hors plage horaire";
    default:
      return reason;
  }
}

export function formatDateTime(iso: string | null | undefined) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function itemFileCount(item: ScanItem) {
  return item.kind === "series" ? item.episode_count ?? 1 : 1;
}

export function truncateMiddle(value: string, max = 52) {
  if (value.length <= max) return value;
  const half = Math.floor((max - 1) / 2);
  return `${value.slice(0, half)}…${value.slice(-half)}`;
}
