import { useMemo, useState, type MouseEvent } from "react";
import {
  AlertTriangle,
  ChevronDown,
  Clock3,
  Film,
  FlaskConical,
  FolderOpen,
  RefreshCw,
  Search,
  Trash2,
  Tv,
} from "lucide-react";
import type { CompressionSettings, Hardware, Scan, ScanError, ScanItem } from "@/lib/types";
import { adjustedGain, estimateSeconds, selectionStats } from "@/lib/estimate";
import {
  cn,
  errorCodeLabel,
  formatBytes,
  formatDuration,
  formatEta,
  formatNumber,
  formatPercent,
  isAlreadyAv1,
  itemFileCount,
  recommendationMeta,
  timeAgo,
} from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { StepBadge } from "@/components/page";

type Filter = "all" | "series" | "files" | "excellent" | "already_av1";
type Sort = "gain" | "gain_pct" | "size" | "duration" | "name";

interface ResultsPanelProps {
  scan: Scan;
  selection: Set<string>;
  onToggle: (id: string) => void;
  onSelectAll: (ids: string[]) => void;
  onClearSelection: () => void;
  onTest: (item: ScanItem) => void;
  onDeleteItem: (item: ScanItem) => void;
  onDeleteError: (path: string) => void;
  onCalibrate: (samplePath?: string) => void;
  calibrating?: boolean;
  onRescan: () => void;
  hardware?: Hardware;
  settings: CompressionSettings;
  resourcePercent: number;
  concurrency: number;
}

export function ResultsPanel({
  scan,
  selection,
  onToggle,
  onSelectAll,
  onClearSelection,
  onTest,
  onDeleteItem,
  onDeleteError,
  onCalibrate,
  calibrating,
  onRescan,
  hardware,
  settings,
  resourcePercent,
  concurrency,
}: ResultsPanelProps) {
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<Sort>("gain");
  const [search, setSearch] = useState("");
  const [displayLimit, setDisplayLimit] = useState<number | "all">(30);

  const errors = useMemo(() => {
    const map = new Map<string, ScanError>();
    [...scan.walk_errors, ...scan.errors].forEach((entry) => {
      if (entry?.path) map.set(entry.path, entry);
    });
    return [...map.values()];
  }, [scan]);

  const filtered = useMemo(() => {
    let items = [...scan.items];
    if (!scan.options.include_av1 && filter !== "already_av1") {
      items = items.filter((item) => !isAlreadyAv1(item));
    }
    if (filter === "series") items = items.filter((item) => item.kind === "series");
    if (filter === "files") items = items.filter((item) => item.kind === "file");
    if (filter === "excellent") {
      items = items.filter((item) => item.recommendation === "excellent" || item.recommendation === "bon");
    }
    if (filter === "already_av1") items = items.filter(isAlreadyAv1);
    if (search.trim()) {
      const needle = search.trim().toLowerCase();
      items = items.filter((item) =>
        `${item.name} ${item.relative_path} ${item.series_name ?? ""}`.toLowerCase().includes(needle),
      );
    }
    const sorters: Record<Sort, (a: ScanItem, b: ScanItem) => number> = {
      gain: (a, b) => adjustedGain(b, settings.crf).bytes - adjustedGain(a, settings.crf).bytes,
      gain_pct: (a, b) =>
        adjustedGain(b, settings.crf).percent - adjustedGain(a, settings.crf).percent,
      size: (a, b) => (b.size_bytes || 0) - (a.size_bytes || 0),
      duration: (a, b) => (b.duration_sec || 0) - (a.duration_sec || 0),
      name: (a, b) => a.name.localeCompare(b.name, "fr"),
    };
    return items.sort(sorters[sort]);
  }, [scan, filter, sort, search, settings.crf]);

  const visible = displayLimit === "all" ? filtered : filtered.slice(0, displayLimit);
  const calibrationSample = useMemo(() => {
    const pool = scan.items.filter((item) => selection.has(item.id));
    for (const item of [...pool, ...scan.items]) {
      if (item.kind === "series" && item.episodes?.length) return item.episodes[0].path;
      if (item.kind === "file") return item.path;
    }
    return undefined;
  }, [scan.items, selection]);
  const stats = selectionStats(scan, selection, hardware, settings, resourcePercent, concurrency);
  const summary = scan.summary;

  // Le scan calcule un gain de référence (CRF 32) ; on l'ajuste au CRF choisi
  // pour que le résumé et les lignes réagissent au changement de qualité.
  const adjustedSummary = useMemo(() => {
    const gain = scan.items.reduce((sum, item) => {
      if (isAlreadyAv1(item)) return sum;
      return sum + adjustedGain(item, settings.crf).bytes;
    }, 0);
    const size = summary.total_size_bytes || 0;
    return {
      gain,
      percent: size ? (gain / size) * 100 : 0,
      output: Math.max(0, size - gain),
    };
  }, [scan.items, settings.crf, summary.total_size_bytes]);

  return (
    <Card className="glass-panel" id="results">
      <CardHeader className="gap-3 pb-4">
        <div className="flex flex-wrap items-start gap-3">
          <StepBadge step={3} />
          <div className="min-w-0 flex-1">
            <CardTitle>Résultats de l'analyse</CardTitle>
            <p className="mt-1 truncate font-mono text-xs text-muted-foreground" title={scan.root}>
              {scan.root} - {timeAgo(scan.created_at)}
            </p>
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={onRescan}>
            <RefreshCw className="h-3.5 w-3.5" /> Réanalyser
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-5">
          <SummaryCard label="Éléments" value={formatNumber(summary.items_count)} hint={`${summary.pack_count} pack(s) · ${summary.file_count} fichier(s)`} />
          <SummaryCard label="Taille totale" value={summary.total_size_human} hint={`${formatNumber(summary.video_file_count)} vidéo(s)`} />
          <SummaryCard label="Gain potentiel" value={formatBytes(adjustedSummary.gain)} hint={`${formatPercent(adjustedSummary.percent)} de la taille`} accent="success" />
          <SummaryCard label="Après compression" value={formatBytes(adjustedSummary.output)} hint="estimation pessimiste" />
          <SummaryCard label="Durée vidéo" value={summary.total_duration_human} hint={`${summary.already_av1_count} déjà AV1`} />
        </div>

        {scan.summary.partial && (
          <Alert variant="warning">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>Analyse partielle : certains fichiers n'ont pas pu être analysés.</AlertDescription>
          </Alert>
        )}

        {scan.series_roots.length === 0 && (
          <Alert variant="info">
            <FolderOpen className="h-4 w-4" />
            <AlertDescription>
              Aucun dossier de séries marqué : les épisodes sont listés individuellement. Ajoutez un
              dossier dans « Dossiers de séries » puis relancez l'analyse pour les regrouper.
            </AlertDescription>
          </Alert>
        )}

        <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
              }}
              placeholder="Rechercher un film, une série, un épisode…"
              className="pl-9"
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <Select
              value={filter}
              onValueChange={(value) => {
                setFilter(value as Filter);
              }}
            >
              <SelectTrigger className="w-[160px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tout</SelectItem>
                <SelectItem value="series">Séries uniquement</SelectItem>
                <SelectItem value="files">Fichiers seuls</SelectItem>
                <SelectItem value="excellent">Meilleurs gains</SelectItem>
                <SelectItem value="already_av1">Déjà en AV1</SelectItem>
              </SelectContent>
            </Select>
            <Select value={sort} onValueChange={(value) => setSort(value as Sort)}>
              <SelectTrigger className="w-[170px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="gain">Gain potentiel ↓</SelectItem>
                <SelectItem value="gain_pct">Gain % ↓</SelectItem>
                <SelectItem value="size">Taille ↓</SelectItem>
                <SelectItem value="duration">Durée ↓</SelectItem>
                <SelectItem value="name">Nom A→Z</SelectItem>
              </SelectContent>
            </Select>
            <Select
              value={String(displayLimit)}
              onValueChange={(value) => setDisplayLimit(value === "all" ? "all" : Number(value))}
            >
              <SelectTrigger className="w-[130px]" title="Nombre d'éléments affichés">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="10">Afficher 10</SelectItem>
                <SelectItem value="20">Afficher 20</SelectItem>
                <SelectItem value="30">Afficher 30</SelectItem>
                <SelectItem value="50">Afficher 50</SelectItem>
                <SelectItem value="100">Afficher 100</SelectItem>
                <SelectItem value="all">Tout afficher</SelectItem>
              </SelectContent>
            </Select>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => onSelectAll(visible.filter((item) => !isAlreadyAv1(item)).map((item) => item.id))}
              title="Sélectionner uniquement les éléments actuellement affichés"
            >
              Sélectionner affichés ({visible.length})
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onSelectAll(filtered.filter((item) => !isAlreadyAv1(item)).map((item) => item.id))}
            >
              Tout sélectionner
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={onClearSelection}>
              Aucun
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
          <span className="font-medium text-foreground">
            {formatNumber(selection.size)} élément(s) sélectionné(s)
          </span>
          {selection.size > 0 && (
            <>
              <span className="text-muted-foreground/50">•</span>
              <span className="text-muted-foreground">
                {formatBytes(stats.size)} · {formatDuration(stats.duration)}
              </span>
              <span className="text-muted-foreground/50">•</span>
              <span className="text-primary">
                {stats.real ? `ETA initiale ${formatEta(stats.seconds)}` : "ETA à calibrer"}
              </span>
              <Badge variant={stats.source === "mesuré" ? "success" : "secondary"} className="ml-1 text-[10px]">
                {stats.source}
              </Badge>
              <span className="text-[10px] text-muted-foreground">
                affinée au lancement
              </span>
              {stats.source !== "mesuré" && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-[10px] text-primary"
                  onClick={() => onCalibrate(calibrationSample)}
                  disabled={calibrating}
                  title="Mesurer la vitesse réelle de ce preset sur cette machine (mire 1080p, quelques secondes)"
                >
                  {calibrating ? "Calibrage…" : "Calibrer (~5 s)"}
                </Button>
              )}
            </>
          )}
        </div>

        {filtered.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border py-10 text-center text-sm text-muted-foreground">
            Aucun élément ne correspond à ce filtre.
          </div>
        ) : (
          <div className="space-y-2">
            {visible.map((item) => (
              <ItemRow
                key={item.id}
                item={item}
                selected={selection.has(item.id)}
                onToggle={() => onToggle(item.id)}
                onTest={() => onTest(item)}
                onDelete={() => onDeleteItem(item)}
                hardware={hardware}
                settings={settings}
                resourcePercent={resourcePercent}
                concurrency={concurrency}
                crf={settings.crf}
              />
            ))}
            {displayLimit !== "all" && filtered.length > displayLimit && (
              <div className="pt-2 text-center">
                <Button type="button" variant="ghost" onClick={() => setDisplayLimit("all")}>
                  <ChevronDown className="h-4 w-4" /> Afficher tout ({filtered.length} éléments)
                </Button>
              </div>
            )}
          </div>
        )}

        {errors.length > 0 && (
          <details className="rounded-lg border border-destructive/25 bg-destructive/[0.04]">
            <summary className="cursor-pointer px-4 py-3 text-xs font-medium text-red-200">
              <AlertTriangle className="mr-1.5 inline h-3.5 w-3.5" />
              Fichiers / dossiers en erreur ({errors.length}) - ignorés automatiquement
            </summary>
            <div className="max-h-64 space-y-2 overflow-auto px-4 pb-3">
              {errors.map((entry) => (
                <div key={entry.path} className="rounded border-t border-destructive/10 py-2 text-[11px]">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="destructive" className="rounded px-1.5 py-0 text-[9px]">
                      {errorCodeLabel(entry.error_code)}
                    </Badge>
                    <span className="min-w-0 flex-1 break-all font-mono text-red-300">{entry.path}</span>
                    {entry.error_code && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-6 border-destructive/30 px-2 text-[10px] text-destructive hover:bg-destructive/10 hover:text-destructive"
                        onClick={() => onDeleteError(entry.path)}
                        title="Supprimer définitivement ce fichier"
                      >
                        <Trash2 className="h-3 w-3" /> Supprimer
                      </Button>
                    )}
                  </div>
                  <p className="mt-1 text-red-200/90">{entry.error}</p>
                  {entry.error_hint && (
                    <p className="mt-0.5 text-muted-foreground">{entry.error_hint}</p>
                  )}
                </div>
              ))}
            </div>
          </details>
        )}
      </CardContent>
    </Card>
  );
}

function SummaryCard({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: string;
  hint: string;
  accent?: "success";
}) {
  return (
    <div className="rounded-lg border border-border/60 bg-secondary/25 p-3">
      <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={cn("mt-1 text-lg font-bold tracking-tight", accent === "success" && "text-success")}>{value}</p>
      <p className="mt-0.5 truncate text-[10px] text-muted-foreground">{hint}</p>
    </div>
  );
}

function ItemRow({
  item,
  selected,
  onToggle,
  onTest,
  onDelete,
  hardware,
  settings,
  resourcePercent,
  concurrency,
  crf,
}: {
  item: ScanItem;
  selected: boolean;
  onToggle: () => void;
  onTest: () => void;
  onDelete: () => void;
  hardware?: Hardware;
  settings: CompressionSettings;
  resourcePercent: number;
  concurrency: number;
  crf: number;
}) {
  const disabled = isAlreadyAv1(item);
  const gain = adjustedGain(item, crf);
  const series = item.kind === "series";
  const recommendation = recommendationMeta(item.recommendation);
  const estimate = estimateSeconds(
    item.duration_sec || 0,
    itemFileCount(item),
    hardware,
    settings,
    resourcePercent,
    concurrency,
  );
  const codecs = series
    ? Object.entries(item.codec_summary ?? {})
        .map(([codec, count]) => `${(codec || "?").toUpperCase()} ×${count}`)
        .join(", ")
    : (item.video_codec ?? "?").toUpperCase();
  const resolutions = series
    ? Object.keys(item.resolution_summary ?? {}).join(", ")
    : item.resolution;
  const metaParts = [
    codecs,
    resolutions,
    series ? `${item.episode_count ?? 0} épisode(s)` : null,
    item.duration_human,
    item.relative_path,
  ].filter(Boolean);

  const handleRowClick = (event: MouseEvent<HTMLDivElement>) => {
    if (disabled) return;
    const target = event.target as HTMLElement;
    if (target.closest("button, input, a, summary, details, label, video")) return;
    onToggle();
  };

  return (
    <div
      className={cn(
        "grid grid-cols-[auto_minmax(0,1fr)] items-start gap-3 rounded-lg border p-3.5 transition-colors sm:grid-cols-[auto_minmax(0,1fr)_auto_auto] sm:items-center",
        selected ? "border-primary/50 bg-primary/[0.055]" : "border-border/60 bg-secondary/20 hover:border-border",
        disabled ? "opacity-60" : "cursor-pointer",
      )}
      onClick={handleRowClick}
      title={disabled ? undefined : "Cliquer pour sélectionner"}
    >
      <div className="flex h-9 items-center">
        <Checkbox checked={selected} disabled={disabled} onCheckedChange={onToggle} aria-label={`Sélectionner ${item.name}`} />
      </div>

      <div className="min-w-0">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md border border-border/60 bg-secondary/60 text-primary">
            {series ? <Tv className="h-3.5 w-3.5" /> : <Film className="h-3.5 w-3.5" />}
          </span>
          <span className="min-w-0 break-words text-sm font-semibold" title={item.relative_path}>
            {item.name}
          </span>
        </div>
        <p className="mt-1 break-words text-[11px] leading-relaxed text-muted-foreground">
          {metaParts.map((part, index) => (
            <span key={index}>
              {index > 0 && <span className="mx-1 text-muted-foreground/40">·</span>}
              {part}
            </span>
          ))}
        </p>
        <div className="mt-1.5 flex flex-wrap gap-1">
          <span className={cn("rounded border px-1.5 py-0.5 text-[10px] font-medium", recommendation.className)}>
            {recommendation.label}
          </span>
          {disabled && (
            <Badge variant="info" className="rounded px-1.5 py-0 text-[10px]">
              déjà AV1
            </Badge>
          )}
          {Boolean(item.error_count) && (
            <Badge variant="warning" className="rounded px-1.5 py-0 text-[10px]">
              {item.error_count} erreur(s)
            </Badge>
          )}
          {item.is_hdr && (
            <Badge variant="warning" className="rounded px-1.5 py-0 text-[10px]">
              HDR
            </Badge>
          )}
          {item.is_10bit && (
            <Badge variant="secondary" className="rounded px-1.5 py-0 text-[10px]">
              10 bits
            </Badge>
          )}
        </div>
        {series && item.episodes && item.episodes.length > 0 && <EpisodesTable item={item} crf={crf} />}
      </div>

      <div className="col-start-2 flex flex-wrap items-center gap-x-5 gap-y-2 sm:col-start-auto sm:justify-end sm:text-right">
        <div>
          <p className="text-[9px] uppercase tracking-wider text-muted-foreground">Taille</p>
          <p className="text-xs font-semibold tabular-nums">{item.size_human}</p>
        </div>
        <div>
          <p className="text-[9px] uppercase tracking-wider text-muted-foreground">Gain</p>
          <p className={cn("text-xs font-semibold tabular-nums", !disabled && "text-success")}>
            {disabled ? "-" : formatBytes(gain.bytes)}
          </p>
          {!disabled && <p className="text-[10px] text-muted-foreground">{formatPercent(gain.percent)}</p>}
        </div>
        <div>
          <p className="text-[9px] uppercase tracking-wider text-muted-foreground">ETA</p>
          <p className="flex items-center gap-1 text-xs font-semibold tabular-nums text-primary sm:justify-end">
            <Clock3 className="h-3 w-3" />{" "}
            {disabled ? "-" : estimate.real ? formatEta(estimate.seconds) : "à calibrer"}
          </p>
        </div>
      </div>

      <div className="col-start-2 flex flex-wrap gap-1.5 sm:col-start-auto">
        <Button type="button" variant="outline" size="sm" onClick={onTest}>
          <FlaskConical className="h-3.5 w-3.5" /> Test
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="border-destructive/30 text-destructive hover:bg-destructive/10 hover:text-destructive"
          onClick={onDelete}
          title="Supprimer définitivement ce fichier ou ce pack"
        >
          <Trash2 className="h-3.5 w-3.5" /> Suppr.
        </Button>
      </div>
    </div>
  );
}

function EpisodesTable({ item, crf }: { item: ScanItem; crf: number }) {
  const episodes = item.episodes ?? [];
  return (
    <details className="mt-2 rounded-md border border-border/50 bg-background/30">
      <summary className="cursor-pointer px-2.5 py-1.5 text-[10px] text-muted-foreground">
        Détail des {episodes.length} fichier(s) du pack - non comparés individuellement
      </summary>
      <div className="overflow-x-auto px-2.5 pb-2">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-left text-[9px] uppercase tracking-wider text-muted-foreground">
              <th className="py-1 pr-2 font-medium">Épisode</th>
              <th className="py-1 pr-2 font-medium">Codec</th>
              <th className="py-1 pr-2 font-medium">Résolution</th>
              <th className="py-1 pr-2 text-right font-medium">Durée</th>
              <th className="py-1 pr-2 text-right font-medium">Taille</th>
              <th className="py-1 text-right font-medium">Gain</th>
            </tr>
          </thead>
          <tbody>
            {episodes.map((episode) => (
              <tr key={episode.path} className="border-t border-border/30">
                <td className="max-w-[260px] truncate py-1 pr-2" title={episode.filename}>
                  {episode.episode || episode.filename}
                </td>
                <td className="py-1 pr-2">{(episode.video_codec ?? "?").toUpperCase()}</td>
                <td className="py-1 pr-2">{episode.resolution ?? "-"}</td>
                <td className="py-1 pr-2 text-right tabular-nums">{episode.duration_human}</td>
                <td className="py-1 pr-2 text-right tabular-nums">{episode.size_human}</td>
                <td className="py-1 text-right tabular-nums">
                  {episode.already_av1
                    ? "déjà AV1"
                    : formatBytes(adjustedGain(episode, crf).bytes)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
