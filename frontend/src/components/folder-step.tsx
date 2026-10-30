import { useState } from "react";
import {
  AlertTriangle,
  Clock3,
  FolderOpen,
  Loader2,
  Plus,
  Search,
  Server,
  Tv,
  X,
} from "lucide-react";
import type { JobSnapshot, MountRoot, ScanOptions, ScanSummary } from "@/lib/types";
import { cn, formatEta, formatNumber, timeAgo } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Checkbox } from "@/components/ui/checkbox";
import { StepBadge } from "@/components/page";

interface FolderStepProps {
  root: string;
  onRootChange: (value: string) => void;
  options: ScanOptions;
  onOptionsChange: (value: ScanOptions) => void;
  excludeText: string;
  onExcludeTextChange: (value: string) => void;
  seriesRoots: string[];
  onAddSeries: (path: string) => void;
  onRemoveSeries: (path: string) => void;
  onBrowse: (mode: "root" | "series", initialPath: string) => void;
  mounts?: MountRoot[];
  lastScan?: ScanSummary;
  onOpenLast: (scanId: string) => void;
  scanning: boolean;
  onStart: () => void;
  job?: JobSnapshot;
  onCancel: () => void;
}

export function FolderStep({
  root,
  onRootChange,
  options,
  onOptionsChange,
  excludeText,
  onExcludeTextChange,
  seriesRoots,
  onAddSeries,
  onRemoveSeries,
  onBrowse,
  mounts,
  lastScan,
  onOpenLast,
  scanning,
  onStart,
  job,
  onCancel,
}: FolderStepProps) {
  const [seriesInput, setSeriesInput] = useState("");
  const progress = job?.progress;
  const running = Boolean(job && (job.status === "running" || job.status === "queued"));
  const showProgress = Boolean(job);
  const walkPhase = progress?.phase === "walking" || progress?.phase === "queued";

  const addSeries = () => {
    const value = seriesInput.trim();
    if (!value) return;
    onAddSeries(value);
    setSeriesInput("");
  };

  return (
    <Card className="glass-panel">
      <CardHeader className="gap-3 pb-4">
        <div className="flex items-start gap-3">
          <StepBadge step={1} />
          <div className="min-w-0">
            <CardTitle>Dossier à analyser</CardTitle>
            <CardDescription>
              Choisissez une racine sur le serveur. Tous les sous-dossiers seront parcourus.
            </CardDescription>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative min-w-0 flex-1">
            <FolderOpen className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={root}
              onChange={(event) => onRootChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !scanning) onStart();
              }}
              placeholder="/mnt/media ou /volume1/video"
              className="pl-9 font-mono text-sm"
              spellCheck={false}
              aria-label="Dossier racine"
            />
          </div>
          <div className="flex gap-2">
            <BrowseButton mode="root" initialPath={root} label="Parcourir" onBrowse={onBrowse} />
            <Button type="button" onClick={onStart} disabled={scanning || !root.trim()} className="min-w-[130px]">
              {scanning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              {scanning ? "Analyse…" : "Analyser"}
            </Button>
          </div>
        </div>

        {mounts && mounts.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {mounts.slice(0, 9).map((mount) => (
              <button
                key={mount.path}
                type="button"
                onClick={() => onRootChange(mount.path)}
                className={cn(
                  "rounded-full border border-border/60 bg-secondary/30 px-2.5 py-1 font-mono text-[10px] text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground",
                  root === mount.path && "border-primary/40 bg-primary/10 text-primary",
                )}
                title={mount.path}
              >
                {mount.path}
              </button>
            ))}
          </div>
        )}

        {lastScan?.id && !job && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-sky-400/20 bg-sky-400/5 px-3 py-2 text-xs text-sky-100">
            <span className="flex min-w-0 items-center gap-2">
              <Clock3 className="h-3.5 w-3.5 shrink-0" />
              Dernière analyse : <span className="truncate font-mono">{lastScan.root}</span>
              <span className="hidden text-muted-foreground sm:inline">— {timeAgo(lastScan.created_at)}</span>
            </span>
            <Button type="button" variant="ghost" size="sm" onClick={() => lastScan.id && onOpenLast(lastScan.id)}>
              Reprendre
            </Button>
          </div>
        )}

        <Accordion type="single" collapsible>
          <AccordionItem value="options" className="border-border/40">
            <AccordionTrigger className="text-xs text-muted-foreground hover:text-foreground">
              Options d'analyse
            </AccordionTrigger>
            <AccordionContent>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <div className="space-y-2">
                  <Label htmlFor="opt-min-size">Taille minimale (Mo)</Label>
                  <Input
                    id="opt-min-size"
                    type="number"
                    min={0}
                    value={options.min_size_mb}
                    onChange={(event) =>
                      onOptionsChange({ ...options, min_size_mb: Number(event.target.value) || 0 })
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="opt-workers">Threads ffprobe</Label>
                  <Input
                    id="opt-workers"
                    type="number"
                    min={1}
                    max={16}
                    value={options.workers}
                    onChange={(event) =>
                      onOptionsChange({
                        ...options,
                        workers: Math.max(1, Math.min(16, Number(event.target.value) || 1)),
                      })
                    }
                  />
                  <p className="text-[11px] text-muted-foreground">2 sur disques mécaniques, 4-6 sur SSD.</p>
                </div>
                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="opt-exclude">Exclure (globs, un par ligne)</Label>
                  <Textarea
                    id="opt-exclude"
                    rows={2}
                    value={excludeText}
                    onChange={(event) => onExcludeTextChange(event.target.value)}
                    placeholder={"*.tmp\n@eaDir\n#recycle"}
                  />
                </div>
                <label className="flex cursor-pointer items-center gap-2 text-sm sm:col-span-2 lg:col-span-4">
                  <Checkbox
                    checked={options.include_av1}
                    onCheckedChange={(checked) => onOptionsChange({ ...options, include_av1: checked === true })}
                  />
                  Afficher les fichiers déjà en AV1 (jamais recompressés)
                </label>
              </div>
            </AccordionContent>
          </AccordionItem>
        </Accordion>

        <div className="rounded-lg border border-dashed border-primary/30 bg-primary/[0.04] p-4">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h3 className="flex items-center gap-2 text-sm font-semibold">
                <Tv className="h-4 w-4 text-primary" /> Dossiers de séries
              </h3>
              <p className="mt-1 max-w-2xl text-xs leading-relaxed text-muted-foreground">
                Indiquez les dossiers qui contiennent des séries. Chaque dossier de saison (ou de série)
                deviendra <strong className="text-foreground">une seule ligne</strong> dans les résultats.
              </p>
            </div>
            <Badge variant="secondary">{seriesRoots.length}</Badge>
          </div>

          <div className="mt-3 flex flex-wrap gap-1.5">
            {seriesRoots.length === 0 && (
              <span className="text-xs italic text-muted-foreground">Aucun dossier marqué</span>
            )}
            {seriesRoots.map((path) => (
              <span
                key={path}
                className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 py-1 pl-2.5 pr-1.5 text-[11px] text-amber-100"
                title={path}
              >
                <Tv className="h-3 w-3 shrink-0" />
                <span className="truncate">{path}</span>
                <button
                  type="button"
                  className="grid h-4 w-4 shrink-0 place-items-center rounded-full bg-white/10 hover:bg-white/20"
                  onClick={() => onRemoveSeries(path)}
                  aria-label={`Retirer ${path}`}
                >
                  <X className="h-2.5 w-2.5" />
                </button>
              </span>
            ))}
          </div>

          <div className="mt-3 flex flex-col gap-2 sm:flex-row">
            <Input
              value={seriesInput}
              onChange={(event) => setSeriesInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  addSeries();
                }
              }}
              placeholder="/mnt/media/Series"
              className="min-w-0 flex-1 font-mono text-xs"
              aria-label="Dossier de séries"
            />
            <div className="flex gap-2">
              <BrowseButton mode="series" initialPath={seriesInput || root} label="Parcourir" onBrowse={onBrowse} />
              <Button type="button" variant="secondary" onClick={addSeries} disabled={!seriesInput.trim()}>
                <Plus className="h-4 w-4" /> Ajouter
              </Button>
            </div>
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground">
            Exemple : <code className="rounded bg-secondary px-1 py-0.5 font-mono">Breaking Bad/S01/E01.mkv</code>{" "}
            → un pack « Breaking Bad — S01 ».
          </p>
        </div>

        {showProgress && job && (
          <div
            className={cn(
              "space-y-2 rounded-lg border p-4",
              job.status === "error"
                ? "border-destructive/30 bg-destructive/5"
                : "border-border/60 bg-background/40",
            )}
          >
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <span className="flex min-w-0 items-center gap-2">
                {running && <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />}
                {job.status === "error" && <AlertTriangle className="h-4 w-4 shrink-0 text-destructive" />}
                <span className="truncate">{progress?.message ?? job.label}</span>
              </span>
              <span className="shrink-0 font-mono text-xs text-muted-foreground">
                {progress?.eta_seconds ? `ETA ${formatEta(progress.eta_seconds)}` : ""}
              </span>
            </div>
            <Progress
              value={progress?.percent ?? 0}
              indeterminate={running && walkPhase}
              className={job.status === "error" ? "bg-destructive/20" : undefined}
            />
            <div className="flex items-center justify-between gap-3 text-[11px] text-muted-foreground">
              <span className="min-w-0 flex-1 truncate font-mono">{progress?.current ?? ""}</span>
              <div className="flex shrink-0 items-center gap-2">
                {job.status === "done" && (
                  <span className="text-success">
                    {formatNumber(progress?.done)} fichier(s) analysé(s)
                  </span>
                )}
                {running && (
                  <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
                    Annuler
                  </Button>
                )}
              </div>
            </div>
            {job.status === "error" && (
              <Alert variant="destructive" className="mt-2 py-2">
                <AlertDescription>{job.error}</AlertDescription>
              </Alert>
            )}
          </div>
        )}

        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <Server className="h-3 w-3" />
          Le scan est en lecture seule. Aucun fichier n'est modifié pendant l'analyse.
        </div>
      </CardContent>
    </Card>
  );
}

function BrowseButton({
  mode,
  initialPath,
  label,
  onBrowse,
}: {
  mode: "root" | "series";
  initialPath: string;
  label: string;
  onBrowse: (mode: "root" | "series", initialPath: string) => void;
}) {
  return (
    <Button type="button" variant="outline" onClick={() => onBrowse(mode, initialPath)}>
      <FolderOpen className="h-4 w-4" /> {label}
    </Button>
  );
}
