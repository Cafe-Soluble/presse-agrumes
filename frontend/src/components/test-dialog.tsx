import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Clock3,
  Download,
  Film,
  FlaskConical,
  Loader2,
  Play,
  RotateCcw,
  Tv,
} from "lucide-react";
import { api, testFileUrl } from "@/lib/api";
import type { CompressionSettings, Hardware, ScanItem, TestMeta } from "@/lib/types";
import { effectiveEncoder } from "@/lib/estimate";
import { cn, formatBits, formatDuration, formatEta } from "@/lib/utils";
import { useJob, isTerminal } from "@/hooks/use-api";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/components/ui/toaster";

interface TestDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  item: ScanItem | null;
  settings: CompressionSettings;
  hardware?: Hardware;
}

export function TestDialog({ open, onOpenChange, item, settings, hardware }: TestDialogProps) {
  const { toast } = useToast();
  const [jobId, setJobId] = useState<string | null>(null);
  const [testId, setTestId] = useState<string | null>(null);
  const [duration, setDuration] = useState(20);
  const [startMode, setStartMode] = useState<"percent" | "seconds">("percent");
  const [startPercent, setStartPercent] = useState(25);
  const [startSeconds, setStartSeconds] = useState(0);
  const [episodePath, setEpisodePath] = useState("");

  const isSeries = item?.kind === "series";
  const episodes = useMemo(
    () => (item?.episodes ?? []).filter((episode) => !episode.already_av1 && !episode.error),
    [item],
  );
  const path = isSeries ? episodePath : item?.path ?? "";

  useEffect(() => {
    if (!open) return;
    setJobId(null);
    setTestId(null);
    setDuration(20);
    setStartMode("percent");
    setStartPercent(25);
    setStartSeconds(0);
    setEpisodePath(episodes[0]?.path ?? "");
  }, [open, item?.id, episodes]);

  const job = useJob(jobId);
  const jobData = job.data;
  const metaFromJob = jobData?.result?.meta as TestMeta | undefined;

  const metaQuery = useQuery({
    queryKey: ["test", testId],
    queryFn: () => api.testMeta(testId!),
    enabled: Boolean(testId) && !metaFromJob,
  });
  const meta = metaFromJob ?? metaQuery.data;

  useEffect(() => {
    if (!jobData) return;
    if (jobData.status === "done" && jobData.result?.test_id) {
      setTestId(String(jobData.result.test_id));
    }
    if (isTerminal(jobData.status) && jobData.status !== "done") {
      toast({
        title: "Test qualité impossible",
        description: jobData.error ?? "Erreur inconnue",
        variant: "error",
      });
    }
  }, [jobData, toast]);

  const mutation = useMutation({
    mutationFn: () =>
      api.startTest({
        path,
        duration,
        start_mode: startMode,
        start_percent: startPercent,
        start_seconds: startSeconds,
        settings,
      }),
    onSuccess: (snapshot) => {
      setJobId(snapshot.id);
      setTestId(null);
    },
    onError: (error: Error) => {
      toast({ title: "Test impossible", description: error.message, variant: "error" });
    },
  });

  const running = Boolean(jobId && jobData && !isTerminal(jobData.status));
  const progress = jobData?.progress;

  const reset = () => {
    setJobId(null);
    setTestId(null);
    mutation.reset();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FlaskConical className="h-5 w-5 text-primary" />
            Test qualité - {isSeries ? "pack de série" : "fichier"}
          </DialogTitle>
          <DialogDescription className="break-all">{item?.name}</DialogDescription>
        </DialogHeader>

        {!meta && (
          <div className="space-y-5">
            {isSeries && (
              <div className="space-y-2">
                <Label className="flex items-center gap-1.5">
                  <Tv className="h-3.5 w-3.5" /> Épisode à tester
                </Label>
                <Select value={episodePath} onValueChange={setEpisodePath}>
                  <SelectTrigger>
                    <SelectValue placeholder="Choisir un épisode" />
                  </SelectTrigger>
                  <SelectContent>
                    {episodes.map((episode) => (
                      <SelectItem key={episode.path} value={episode.path}>
                        {episode.episode || episode.filename} - {episode.size_human} ({episode.video_codec ?? "?"})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {episodes.length === 0 && (
                  <Alert variant="warning">
                    <AlertDescription>Aucun épisode compressible dans ce pack.</AlertDescription>
                  </Alert>
                )}
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="test-duration" className="flex items-center gap-1.5">
                  <Clock3 className="h-3.5 w-3.5" /> Durée (s)
                </Label>
                <Input
                  id="test-duration"
                  type="number"
                  min={3}
                  max={120}
                  value={duration}
                  onChange={(event) => setDuration(Number(event.target.value))}
                />
              </div>
              <div className="space-y-2">
                <Label>Position</Label>
                <Select value={startMode} onValueChange={(value) => setStartMode(value as "percent" | "seconds")}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="percent">Pourcentage du fichier</SelectItem>
                    <SelectItem value="seconds">Temps exact</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="test-start">
                  {startMode === "percent" ? "Départ (%)" : "Départ (s)"}
                </Label>
                <Input
                  id="test-start"
                  type="number"
                  min={0}
                  max={startMode === "percent" ? 95 : undefined}
                  value={startMode === "percent" ? startPercent : startSeconds}
                  onChange={(event) => {
                    const value = Number(event.target.value);
                    if (startMode === "percent") setStartPercent(value);
                    else setStartSeconds(value);
                  }}
                />
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-x-5 gap-y-1 rounded-lg border border-border/60 bg-secondary/30 px-4 py-3 text-xs text-muted-foreground">
              <span>
                Encodeur <strong className="text-foreground">{effectiveEncoder(hardware, settings)}</strong>
              </span>
              <span>
                Preset <strong className="text-foreground">{settings.preset}</strong>
              </span>
              <span>
                CRF <strong className="text-foreground">{settings.crf}</strong>
              </span>
              <span>
                Qualité <strong className="text-foreground">{settings.pixel_format === "yuv420p10le" ? "10 bits" : "8 bits"}</strong>
              </span>
              <span className="text-muted-foreground/80">
                Aperçu compressé en MP4/AAC pour la lecture navigateur.
              </span>
            </div>

            {running && progress && (
              <div className="space-y-2 rounded-lg border border-primary/25 bg-primary/5 p-4">
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin text-primary" />
                    {progress.message}
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {progress.eta_seconds ? `ETA ${formatEta(progress.eta_seconds)}` : ""}
                  </span>
                </div>
                <Progress value={progress.percent} />
              </div>
            )}

            {jobData?.status === "error" && (
              <Alert variant="destructive">
                <AlertDescription>{jobData.error}</AlertDescription>
              </Alert>
            )}

            <div className="flex justify-end">
              <Button
                type="button"
                onClick={() => mutation.mutate()}
                disabled={!path || mutation.isPending || running || (isSeries && episodes.length === 0)}
              >
                {mutation.isPending || running ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
                {running ? "Génération en cours…" : "Générer le test"}
              </Button>
            </div>
          </div>
        )}

        {meta && (
          <div className="space-y-4">
            <div className="grid gap-4 lg:grid-cols-2">
              <ComparePane
                title="Original"
                subtitle="Aperçu H.264 CRF 18 (lecture navigateur)"
                file={meta.files.original_preview}
                testId={meta.id}
                accent="muted"
              />
              <ComparePane
                title="Compressé AV1"
                subtitle={`${meta.encoder} · preset ${meta.settings.preset} · CRF ${meta.settings.crf}`}
                file={meta.files.compressed}
                testId={meta.id}
                accent="primary"
              />
            </div>

            <div className="rounded-lg border border-border/60 bg-secondary/25 p-4 text-xs leading-relaxed text-muted-foreground">
              <p className="flex items-center gap-2 text-sm font-medium text-foreground">
                <Film className="h-4 w-4 text-primary" />
                Comparaison sur {formatDuration(meta.duration_sec)} à partir de {formatDuration(meta.start_sec)}
              </p>
              {meta.comparison?.saved_percent !== undefined && (
                <p className="mt-2">
                  Débit{" "}
                  <strong className="text-foreground">
                    {formatBits(meta.comparison.original_bitrate_bps)}
                  </strong>{" "}
                  →{" "}
                  <strong className="text-success">
                    {formatBits(meta.comparison.compressed_bitrate_bps)}
                  </strong>{" "}
                  soit{" "}
                  <Badge variant="success" className="align-middle">
                    {meta.comparison.saved_percent.toFixed(1)} % de gain
                  </Badge>{" "}
                  sur cet extrait.
                </p>
              )}
              {meta.comparison?.note && <p className="mt-2">{meta.comparison.note}</p>}
              <p className="mt-2">
                La lecture AV1 nécessite un navigateur récent (Chrome, Firefox, Edge). Les fichiers
                sont téléchargeables ci-dessus pour une inspection hors navigateur.
              </p>
            </div>

            <p className="text-[11px] leading-relaxed text-muted-foreground">
              L'aperçu « Original » est réencodé en H.264/AAC 160k pour la lecture navigateur :
              sa taille et son audio diffèrent de la copie brute MKV, qui conserve le flux
              d'origine. Télécharge l'aperçu (bouton ci-dessus) pour comparer exactement ce que tu
              entends dans le navigateur.
            </p>

            {meta.files.original_raw && meta.files.compressed && (
              <div className="flex flex-wrap gap-2">
                <Button asChild variant="outline" size="sm">
                  <a href={testFileUrl(meta.id, meta.files.original_raw.filename, true)} download>
                    <Download className="h-4 w-4" /> Copie brute MKV ({meta.files.original_raw.size_human})
                  </a>
                </Button>
                <Button asChild variant="outline" size="sm">
                  <a href={testFileUrl(meta.id, meta.files.compressed.filename, true)} download>
                    <Download className="h-4 w-4" /> Extrait AV1 MP4 ({meta.files.compressed.size_human})
                  </a>
                </Button>
              </div>
            )}

            <div className="flex justify-end">
              <Button type="button" variant="secondary" onClick={reset}>
                <RotateCcw className="h-4 w-4" /> Refaire un test
              </Button>
            </div>
          </div>
        )}

        {!meta && jobData?.status === "done" && !jobData.result?.test_id && (
          <Alert variant="destructive">
            <AlertDescription>Le test est terminé mais aucun résultat n'a été renvoyé.</AlertDescription>
          </Alert>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ComparePane({
  title,
  subtitle,
  file,
  testId,
  accent,
}: {
  title: string;
  subtitle: string;
  file?: { filename: string; url: string; size_human: string; duration_sec?: number };
  testId: string;
  accent: "muted" | "primary";
}) {
  return (
    <div className="min-w-0 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold">{title}</p>
          <p className="truncate text-[11px] text-muted-foreground">{subtitle}</p>
        </div>
        {file && (
          <div className="flex shrink-0 items-center gap-1.5">
            <Badge variant={accent === "primary" ? "success" : "secondary"}>
              {file.size_human}
            </Badge>
            <Button asChild variant="ghost" size="icon" title="Télécharger ce fichier">
              <a href={testFileUrl(testId, file.filename, true)} download aria-label="Télécharger ce fichier">
                <Download className="h-4 w-4" />
              </a>
            </Button>
          </div>
        )}
      </div>
      {file ? (
        <video
          key={file.url}
          controls
          playsInline
          preload="metadata"
          className={cn(
            "aspect-video w-full rounded-lg border bg-black",
            accent === "primary" ? "border-primary/40" : "border-border",
          )}
          src={testFileUrl(testId, file.filename)}
        />
      ) : (
        <div className="grid aspect-video place-items-center rounded-lg border border-border bg-black/40 text-sm text-muted-foreground">
          Indisponible
        </div>
      )}
    </div>
  );
}
