import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  CalendarClock,
  Loader2,
  Pause,
  Play,
  ScanSearch,
  Timer,
  FlaskConical,
} from "lucide-react";
import { api } from "@/lib/api";
import type { JobSnapshot } from "@/lib/types";
import { useActiveJobs } from "@/hooks/use-api";
import {
  cn,
  formatEta,
  formatNumber,
  pauseReasonLabel,
  formatDateTime,
} from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/components/ui/toaster";

const kindMeta = {
  scan: { label: "Analyse", icon: ScanSearch },
  compress: { label: "Compression", icon: Timer },
  test: { label: "Test qualité", icon: FlaskConical },
};

export function ActiveJobsBanner() {
  const active = useActiveJobs();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { toast } = useToast();

  const pause = useMutation({
    mutationFn: (jobId: string) => api.pauseJob(jobId),
    onSuccess: (_data, jobId) => {
      queryClient.invalidateQueries({ queryKey: ["jobs", "active"] });
      queryClient.invalidateQueries({ queryKey: ["job", jobId] });
      toast({ title: "Compression mise en pause", variant: "warning" });
    },
    onError: (error: Error) =>
      toast({ title: "Pause impossible", description: error.message, variant: "error" }),
  });

  const resume = useMutation({
    mutationFn: (jobId: string) => api.resumeJob(jobId),
    onSuccess: (_data, jobId) => {
      queryClient.invalidateQueries({ queryKey: ["jobs", "active"] });
      queryClient.invalidateQueries({ queryKey: ["job", jobId] });
      toast({ title: "Compression reprise", variant: "success" });
    },
    onError: (error: Error) =>
      toast({ title: "Reprise impossible", description: error.message, variant: "error" }),
  });

  const jobs = active.data ?? [];
  if (jobs.length === 0) return null;

  const goToJob = (job: JobSnapshot) => {
    if (job.kind === "compress" && job.context?.scan_id) {
      navigate(`/?scan=${job.context.scan_id}`);
    } else {
      navigate("/");
    }
  };

  return (
    <div className="sticky top-16 z-30 border-b border-primary/25 bg-[#1a150d]/95 backdrop-blur-xl">
      <div className="mx-auto max-w-[1440px] divide-y divide-border/30 px-4 sm:px-6">
        {jobs.slice(0, 2).map((job) => {
          const meta = kindMeta[job.kind] ?? kindMeta.compress;
          const Icon = meta.icon;
          const paused = job.status === "paused";
          const progress = job.progress;
          const reasons = job.pause_reasons ?? [];
          const canPause = job.kind === "compress" && !paused;
          const canResume = job.kind === "compress" && paused && reasons.includes("manual");
          return (
            <div key={job.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-2.5">
              <Badge
                variant={paused ? "warning" : job.status === "queued" ? "secondary" : "default"}
                className="shrink-0 gap-1.5"
              >
                <Icon className="h-3 w-3" />
                {meta.label}
                {paused ? " · en pause" : ""}
              </Badge>
              <div className="min-w-0 flex-1 basis-64">
                <div className="flex items-center gap-2 text-xs">
                  <span className="truncate font-medium">{progress.message || job.label}</span>
                  <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
                    {formatNumber(progress.done)}/{formatNumber(progress.total)}
                  </span>
                </div>
                <Progress value={progress.percent} className="mt-1 h-1.5" />
              </div>
              <div className="flex shrink-0 items-center gap-3 text-[11px] text-muted-foreground">
                <span className="font-mono">{Math.round(progress.percent)} %</span>
                {progress.eta_seconds ? (
                  <span className="hidden items-center gap-1 sm:flex">
                    <Timer className="h-3 w-3" /> {formatEta(progress.eta_seconds)}
                  </span>
                ) : null}
                {progress.speed && <span className="hidden font-mono md:inline">{progress.speed}</span>}
                {progress.fps ? <span className="hidden font-mono lg:inline">{progress.fps} fps</span> : null}
                {paused && reasons.length > 0 && (
                  <span className="hidden items-center gap-1 text-warning md:flex">
                    <CalendarClock className="h-3 w-3" />
                    {reasons.map(pauseReasonLabel).join(" + ")}
                    {job.next_resume_at ? ` · reprise ${formatDateTime(job.next_resume_at)}` : ""}
                  </span>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                {job.kind === "compress" && canPause && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={pause.isPending || resume.isPending}
                    onClick={() => pause.mutate(job.id)}
                  >
                    {pause.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Pause className="h-3.5 w-3.5" />}
                    Pause
                  </Button>
                )}
                {canResume && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={pause.isPending || resume.isPending}
                    onClick={() => resume.mutate(job.id)}
                  >
                    {resume.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                    Reprendre
                  </Button>
                )}
                <Button
                  type="button"
                  size="sm"
                  variant={paused ? "secondary" : "default"}
                  onClick={() => goToJob(job)}
                >
                  Suivi <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          );
        })}
        {jobs.length > 2 && (
          <p className={cn("py-1.5 text-[10px] text-muted-foreground")}>
            + {jobs.length - 2} autre(s) tâche(s) active(s)
          </p>
        )}
      </div>
    </div>
  );
}
