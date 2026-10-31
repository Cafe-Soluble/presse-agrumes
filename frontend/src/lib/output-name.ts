import type { CompressionSettings, OutputOptions } from "./types";

const CODEC_TOKEN_RE =
  /(^|[^a-z0-9])(?:x264|x265|h\.?264|h\.?265|hevc|avc|av1|vp9|xvid|divx|10bit|8bit|hdr10)(?![a-z0-9])/gi;

function collapseSeparators(value: string) {
  return value.replace(/[._\-\s]{2,}/g, (match) => {
    if (match.includes("-")) return "-";
    if (match.includes("_")) return "_";
    if (match.includes(" ")) return " ";
    return ".";
  });
}

export function stripCodecTokens(stem: string) {
  const cleaned = collapseSeparators(stem.replace(CODEC_TOKEN_RE, "$1"))
    .replace(/^[ ._-]+|[ ._-]+$/g, "");
  return cleaned || stem;
}

export function containerExtension(container: CompressionSettings["container"]) {
  if (container === "mp4") return ".mp4";
  if (container === "webm") return ".webm";
  return ".mkv";
}

export function outputFileName(
  sourceName: string,
  settings: CompressionSettings,
  output: OutputOptions,
) {
  const stem = sourceName.replace(/\.[^.]+$/, "");
  const extension = containerExtension(settings.container);
  if (output.mode === "same_dir_same_name") {
    return `${stem}${extension}`;
  }
  const base = output.clean_codec_names ? stripCodecTokens(stem) : stem;
  const suffix = (output.suffix || "av1").replace(/^\.+/, "");
  return `${base}.${suffix}${extension}`;
}
