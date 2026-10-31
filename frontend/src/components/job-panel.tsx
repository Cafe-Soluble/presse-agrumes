import { useEffect, useRef } from "react";
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  ScrollText,
  Square,
  XCircle,
} from "lucide-react";
import type { CompressionResult, JobSnapshot } from "@/lib/types";
import {
  cn,
  formatBytes,
  formatDateTime,
  formatDuration,
  formatEta,
  formatNumber,
  formatPercent,
  pauseReasonLabel,
} from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { StepBadge } from "@/components/page";

interface JobPanelProps {
  job: JobSnapshot;
  onCancel: () => void;
  onRescan: () => void;
  onDismiss: () => void;
  onPause: () => void;
  onResume: () => void;
  pausing?: boolean;
  resuming?: boolean;
}

const statusLabels: Record<string, string> = {
  queued: "en attente",
  running: "en cours",
  paused: "en pause",
  done: "terminé",
  error: "échec",
  cancelled: "annulé",
  interrupted: "interrompu",
};

export function JobPanel({
  job,
  onCancel,
  onRescan,
  onDismiss,
  onPause,
  onResume,
  pausing,
  resuming,
}: JobPanelProps) {
  const progress = job.progress;
  const paused = job.status === "paused";
  const active = job.status === "running" || job.status === "queued" || paused;
  const result = job.result as CompressionResult | undefined;
  const logsRef = useRef<HTMLPreElement>(null);
  const pauseReasons = job.pause_reasons ?? [];

  useEffect(() => {
    const node = logsRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [job.logs]);

  return (
    <Card className="glass-panel" id="job">
      <CardHeader className="gap-3 pb-4">
        <div className="flex flex-wrap items-start gap-3">
          <StepBadge
            step={
              job.status === "done"
                ? "✓"
                : job.status === "error"
                  ? "!"
                  : paused
                    ? <Pause className="h-4 w-4" />
                    : job.status === "running"
                      ? <Loader2 className="h-4 w-4 animate-spin" />
                      : "…"
            }
          />
          <div className="min-w-0 flex-1">
            <CardTitle className="flex flex-wrap items-center gap-2">
              {job.kind === "test" ? "Test qualité" : "Compression"}
              <Badge
                variant={
                  job.status === "done"
                    ? "success"
                    : job.status === "error"
                      ? "destructive"
                      : paused
                        ? "warning"
                        : "secondary"
                }
              >
                {statusLabels[job.status] ?? job.status}
              </Badge>
            </CardTitle>
            <CardDescription className="break-all">{job.label}</CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            {job.kind === "compress" && job.status === "running" && (
              <Button type="button" variant="outline" size="sm" onClick={onPause} disabled={pausing}>
                {pausing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Pause className="h-3.5 w-3.5" />}
                Pause
              </Button>
            )}
            {job.kind === "compress" && paused && pauseReasons.includes("manual") && (
              <Button type="button" variant="outline" size="sm" onClick={onResume} disabled={resuming}>
                {resuming ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                Reprendre
              </Button>
            )}
            {active && (
              <Button type="button" variant="outline" size="sm" onClick={onCancel}>
                <Square className="h-3.5 w-3.5" /> Annuler
              </Button>
            )}
            {!active && (
              <Button type="button" variant="ghost" size="sm" onClick={onDismiss}>
                Fermer
              </Button>
            )}
            {job.status === "done" && (
              <Button type="button" variant="secondary" size="sm" onClick={onRescan}>
                <RefreshCw className="h-3.5 w-3.5" /> Réanalyser
              </Button>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="space-y-2 rounded-lg border border-border/60 bg-background/40 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span className="flex min-w-0 items-center gap-2">
              {job.status === "running" && <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />}
              {paused && <Pause className="h-4 w-4 shrink-0 text-warning" />}
              <span className="truncate">{progress.message || "En cours…"}</span>
            </span>
            <span className="flex shrink-0 items-center gap-2 font-mono text-xs text-muted-foreground">
              {progress.eta_seconds ? <><Clock3 className="h-3 w-3" /> ETA {formatEta(progress.eta_seconds)}</> : null}
              {progress.speed && <span>{progress.speed}</span>}
              {progress.fps ? <span>{progress.fps} fps</span> : null}
            </span>
          </div>
          <Progress value={progress.percent} />
          <div className="flex items-center justify-between gap-3 text-[11px] text-muted-foreground">
            <span className="font-mono">
              {formatNumber(progress.done)}/{formatNumber(progress.total)} · {progress.phase}
            </span>
            <span>{progress.percent ? formatPercent(progress.percent) : ""}</span>
          </div>
        </div>

        {paused && (
          <Alert variant="warning" className="py-2">
            <CalendarClock className="h-4 w-4" />
            <AlertDescription>
              {pauseReasons.length > 0
                ? pauseReasons.map(pauseReasonLabel).join(" + ")
                : "Compression en pause"}
              {job.next_resume_at
                ? ` - reprise automatique prévue le ${formatDateTime(job.next_resume_at)}`
                : ""}
              . Les processus ffmpeg sont suspendus, aucun travail n'est perdu.
            </AlertDescription>
          </Alert>
        )}

        {job.error && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{job.error}</AlertDescription>
          </Alert>
        )}

        {job.items.length > 0 && (
          <div className="max-h-[420px] space-y-1.5 overflow-y-auto pr-1">
            {job.items.map((item) => {
              const done = item.status === "done";
              const error = item.status === "error";
              const cancelled = item.status === "cancelled";
              return (
                <div
                  key={item.task_id}
                  className="flex items-start gap-3 rounded-lg border border-border/50 bg-secondary/20 px-3 py-2"
                >
                  <div className="mt-0.5 shrink-0">
                    {done ? (
                      <CheckCircle2 className="h-4 w-4 text-success" />
                    ) : error || cancelled ? (
                      <XCircle className="h-4 w-4 text-destructive" />
                    ) : item.status === "running" ? (
                      <Loader2 className="h-4 w-4 animate-spin text-primary" />
                    ) : (
                      <Clock3 className="h-4 w-4 text-muted-foreground/60" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="break-all text-xs font-medium">{item.filename}</span>
                      <span
                        className={cn(
                          "shrink-0 font-mono text-[10px]",
                          done && "text-success",
                          error && "text-destructive",
                          item.status === "running" && "text-primary",
                          item.status === "queued" && "text-muted-foreground",
                        )}
                      >
                        {done
                          ? item.saved_bytes !== null && item.saved_bytes !== undefined
                            ? `✓ ${formatBytes(item.saved_bytes)} gagnés`
                            : "✓ terminé"
                          : error
                            ? item.error || "échec"
                            : cancelled
                              ? "annulé"
                              : item.status === "running"
                                ? `${(item.percent || 0).toFixed(0)} %`
                                : "en attente"}
                      </span>
                    </div>
                    {!done && !error && !cancelled && (
                      <Progress value={item.percent} className="mt-1.5 h-1" />
                    )}
                    {item.warning && (
                      <p className="mt-1 text-[10px] text-warning">⚠ {item.warning}</p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {active && job.estimate && (
          <p className="text-[11px] text-muted-foreground">
            Estimation initiale : {formatEta(job.estimate.seconds)} · {job.estimate.threads_per_job} thread(s)
            par encodage.
          </p>
        )}

        {job.logs && job.logs.length > 0 && (
          <details className="rounded-lg border border-border/60 bg-background/60">
            <summary className="cursor-pointer px-3 py-2 text-[11px] text-muted-foreground">
              <ScrollText className="mr-1.5 inline h-3 w-3" /> Journal technique
              <ChevronDown className="ml-1 inline h-3 w-3" />
            </summary>
            <pre
              ref={logsRef}
              className="max-h-56 overflow-auto border-t border-border/40 p-3 font-mono text-[10px] leading-relaxed text-muted-foreground"
            >
              {job.logs.join("\n")}
            </pre>
          </details>
        )}

        {job.status === "done" && result && (
          <div className="rounded-lg border border-success/30 bg-success/[0.07] p-4 text-sm">
            <p className="flex items-center gap-2 font-semibold text-success">
              <CheckCircle2 className="h-4 w-4" /> Compression terminée
            </p>
            <p className="mt-1 text-xs text-emerald-100/90">
              {formatNumber(result.success)} fichier(s) réussi(s)
              {result.failed ? `, ${result.failed} échec(s)` : ""} - {formatBytes(result.saved_bytes)} gagnés
              ({formatPercent(result.saved_percent)}) en {formatDuration(result.elapsed_seconds)}.
            </p>
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
              <div>
                <p className="text-[9px] uppercase tracking-wider text-muted-foreground">Entrée</p>
                <p className="font-mono">{formatBytes(result.input_bytes)}</p>
              </div>
              <div>
                <p className="text-[9px] uppercase tracking-wider text-muted-foreground">Sortie</p>
                <p className="font-mono">{formatBytes(result.output_bytes)}</p>
              </div>
              <div>
                <p className="text-[9px] uppercase tracking-wider text-muted-foreground">Gain</p>
                <p className="font-mono text-success">{formatBytes(result.saved_bytes)}</p>
              </div>
              <div>
                <p className="text-[9px] uppercase tracking-wider text-muted-foreground">Durée</p>
                <p className="font-mono">{formatDuration(result.elapsed_seconds)}</p>
              </div>
            </div>
            <p className="mt-2 text-[10px] text-muted-foreground">
              Relancez une analyse pour actualiser les tailles et les gains estimés.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
