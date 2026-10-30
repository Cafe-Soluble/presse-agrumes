import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Cpu,
  Gauge,
  History,
  Loader2,
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";
import { api } from "@/lib/api";
import type {
  CompressionPayload,
  CompressionSchedule,
  CompressionSettings,
  OriginalOptions,
  OutputOptions,
  ScanItem,
  ScanOptions,
} from "@/lib/types";
import {
  useActiveJobs,
  useConfig,
  useHardware,
  useJob,
  useMounts,
  useScan,
  useScans,
  useSetup,
} from "@/hooks/use-api";
import { useDebouncedValue, useLocalStorage } from "@/hooks/use-utils";
import { effectiveEncoder } from "@/lib/estimate";
import { formatBytes, formatNumber } from "@/lib/utils";
import { PageContainer } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent } from "@/components/ui/card";
import { FolderStep } from "@/components/folder-step";
import { ResultsPanel } from "@/components/results-panel";
import { CompressionPanel } from "@/components/compression-panel";
import { JobPanel } from "@/components/job-panel";
import { TestDialog } from "@/components/test-dialog";
import { SetupDialog } from "@/components/setup-dialog";
import { BrowseDialog, type BrowseMode } from "@/components/browse-dialog";
import { DEFAULT_SCHEDULE } from "@/components/schedule-editor";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useToast } from "@/components/ui/toaster";

const DEFAULT_SETTINGS: CompressionSettings = {
  encoder: "auto",
  preset: 8,
  crf: 32,
  pixel_format: "yuv420p",
  audio_mode: "copy",
  audio_bitrate_kbps: 128,
  container: "mkv",
  subtitles: "copy",
};

const DEFAULT_OUTPUT: OutputOptions = {
  mode: "same_dir_new_name",
  suffix: ".av1",
  output_dir: null,
  overwrite: false,
};

const DEFAULT_ORIGINALS: OriginalOptions = { mode: "keep", trash_dir: null };

const DEFAULT_SCAN_OPTIONS: ScanOptions = {
  min_size_mb: 0,
  workers: 2,
  include_av1: true,
  follow_symlinks: false,
  series_roots: [],
  exclude_globs: [],
};

interface BrowseState {
  open: boolean;
  mode: BrowseMode;
  initial: string;
}

type DeleteTarget =
  | { kind: "item"; item: ScanItem }
  | { kind: "error"; path: string };

export function WorkspacePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeScanId = searchParams.get("scan");

  const configQuery = useConfig();
  const hardwareQuery = useHardware();
  const mountsQuery = useMounts();
  const scansQuery = useScans();
  const activeJobsQuery = useActiveJobs();
  const setupQuery = useSetup();
  const scanQuery = useScan(activeScanId);
  const scan = scanQuery.data;

  const [root, setRoot] = useLocalStorage("pa.root", "");
  const [scanOptions, setScanOptions] = useLocalStorage<ScanOptions>("pa.scanOptions", DEFAULT_SCAN_OPTIONS);
  const [excludeText, setExcludeText] = useLocalStorage("pa.excludeText", "");
  const [seriesRoots, setSeriesRoots] = useLocalStorage<string[]>("pa.seriesRoots", []);
  const [settings, setSettings] = useLocalStorage<CompressionSettings>("pa.settings", DEFAULT_SETTINGS);
  const [output, setOutput] = useLocalStorage<OutputOptions>("pa.output", DEFAULT_OUTPUT);
  const [originals, setOriginals] = useLocalStorage<OriginalOptions>("pa.originals", DEFAULT_ORIGINALS);
  const [resourcePercent, setResourcePercent] = useLocalStorage("pa.resource", 70);
  const [concurrency, setConcurrency] = useLocalStorage("pa.concurrency", 1);
  const [schedule, setSchedule] = useLocalStorage<CompressionSchedule>("pa.schedule", DEFAULT_SCHEDULE);

  const [scanJobId, setScanJobId] = useState<string | null>(null);
  const scanJob = useJob(scanJobId);
  const [compressionJobId, setCompressionJobId] = useState<string | null>(null);
  const compressionJob = useJob(compressionJobId);
  const [selection, setSelection] = useState<Set<string>>(new Set());
  const [testItem, setTestItem] = useState<ScanItem | null>(null);
  const [browse, setBrowse] = useState<BrowseState>({ open: false, mode: "root", initial: "" });
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [jobDismissed, setJobDismissed] = useState(false);
  const [setupDismissed, setSetupDismissed] = useLocalStorage("pa.setupDismissed", false);

  const scanTerminalRef = useRef("");
  const compressionTerminalRef = useRef("");
  const scrollToResultsRef = useRef(false);
  const autoOpenedJobRef = useRef<string | null>(null);

  const selectedIds = useMemo(() => [...selection].sort(), [selection]);

  // Assistant de premier démarrage : uniquement sur une installation neuve
  // (pas de réglages enregistrés, aucun scan, aucun dossier déjà saisi).
  const setupNeeded =
    setupQuery.isSuccess &&
    scansQuery.isSuccess &&
    Boolean(setupQuery.data?.needed) &&
    (scansQuery.data?.length ?? 0) === 0 &&
    !root &&
    !setupDismissed;

  useEffect(() => {
    const saved = setupQuery.data?.media_root;
    if (saved && !root) setRoot(saved);
  }, [setupQuery.data?.media_root, root, setRoot]);

  const preflightPayload = useMemo<CompressionPayload | null>(() => {
    if (!scan || selectedIds.length === 0) return null;
    return {
      scan_id: scan.id,
      item_ids: selectedIds,
      settings,
      output: {
        ...output,
        suffix: (output.suffix || "av1").replace(/^\./, ""),
        output_dir: output.mode === "custom_dir" ? output.output_dir : null,
      },
      originals: {
        ...originals,
        trash_dir: originals.mode === "move" ? originals.trash_dir : null,
      },
      resource_percent: resourcePercent,
      concurrency,
      verify: true,
      schedule,
    };
  }, [scan, selectedIds, settings, output, originals, resourcePercent, concurrency, schedule]);

  const debouncedPayload = useDebouncedValue(preflightPayload, 700);
  const payloadReady =
    Boolean(preflightPayload && debouncedPayload) &&
    JSON.stringify(preflightPayload) === JSON.stringify(debouncedPayload);

  const preflightQuery = useQuery({
    queryKey: ["preflight", debouncedPayload],
    queryFn: () => api.preflight(debouncedPayload!),
    enabled: Boolean(debouncedPayload),
    retry: false,
    staleTime: 20_000,
  });

  const preflight = payloadReady ? preflightQuery.data : undefined;
  const preflightLoading =
    Boolean(preflightPayload) && (!payloadReady || preflightQuery.isFetching);

  useEffect(() => {
    setSelection(new Set());
    setJobDismissed(false);
  }, [activeScanId]);

  // Le bouton « Suivi » de la bannière navigue avec #job : on scrolle vers le
  // panneau une fois que le job est chargé.
  useEffect(() => {
    if (location.hash !== "#job" || !compressionJob.data) return;
    const timer = window.setTimeout(() => {
      document.getElementById("job")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 200);
    return () => window.clearTimeout(timer);
  }, [location.hash, compressionJob.data]);

  // Si un job de compression tourne encore (navigateur fermé puis rouvert),
  // on réaffiche automatiquement son suivi et le scan associé.
  useEffect(() => {
    const active = activeJobsQuery.data?.find((job) => job.kind === "compress");
    if (!active || autoOpenedJobRef.current === active.id) return;
    autoOpenedJobRef.current = active.id;
    setCompressionJobId(active.id);
    setJobDismissed(false);
    const scanId = active.context?.scan_id;
    if (scanId && !activeScanId) {
      setSearchParams({ scan: String(scanId) });
    }
  }, [activeJobsQuery.data, activeScanId, setSearchParams]);

  useEffect(() => {
    if (!scan) return;
    setRoot(scan.root);
    setSeriesRoots(scan.series_roots);
    if (scrollToResultsRef.current) {
      scrollToResultsRef.current = false;
      window.setTimeout(() => {
        document.getElementById("results")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 180);
    }
  }, [scan?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const snapshot = scanJob.data;
    if (!snapshot) return;
    if (snapshot.status === "done") {
      const scanId = snapshot.result?.scan_id;
      if (!scanId || scanTerminalRef.current === `${snapshot.id}:done`) return;
      scanTerminalRef.current = `${snapshot.id}:done`;
      queryClient.invalidateQueries({ queryKey: ["scans"] });
      scrollToResultsRef.current = true;
      setSearchParams({ scan: scanId });
      setScanJobId(null);
      const summary = snapshot.result?.summary;
      toast({
        title: "Analyse terminée",
        description: summary
          ? `${formatNumber(summary.items_count)} élément(s), ${summary.total_gain_human} de gain potentiel.`
          : undefined,
        variant: "success",
      });
    } else if (snapshot.status === "error" || snapshot.status === "cancelled") {
      const key = `${snapshot.id}:${snapshot.status}`;
      if (scanTerminalRef.current === key) return;
      scanTerminalRef.current = key;
      toast({
        title: snapshot.status === "cancelled" ? "Analyse annulée" : "Analyse en échec",
        description: snapshot.error ?? undefined,
        variant: snapshot.status === "cancelled" ? "warning" : "error",
      });
    }
  }, [scanJob.data, queryClient, setSearchParams, toast]);

  useEffect(() => {
    const snapshot = compressionJob.data;
    if (!snapshot) return;
    const key = `${snapshot.id}:${snapshot.status}`;
    if (compressionTerminalRef.current === key) return;
    if (snapshot.status === "done") {
      compressionTerminalRef.current = key;
      queryClient.invalidateQueries({ queryKey: ["scans"] });
      queryClient.invalidateQueries({ queryKey: ["hardware"] });
      if (scan?.id) queryClient.invalidateQueries({ queryKey: ["scan", scan.id] });
      const result = snapshot.result as { saved_bytes?: number; success?: number } | undefined;
      toast({
        title: "Compression terminée",
        description: `${formatBytes(result?.saved_bytes)} gagnés sur ${formatNumber(result?.success)} fichier(s).`,
        variant: "success",
      });
    } else if (snapshot.status === "error" || snapshot.status === "cancelled") {
      compressionTerminalRef.current = key;
      toast({
        title: snapshot.status === "cancelled" ? "Compression annulée" : "Compression en échec",
        description: snapshot.error ?? undefined,
        variant: snapshot.status === "cancelled" ? "warning" : "error",
      });
    }
  }, [compressionJob.data, queryClient, scan?.id, toast]);

  const startScan = useMutation({
    mutationFn: ({ targetRoot, options }: { targetRoot: string; options: ScanOptions }) =>
      api.startScan(targetRoot, options),
    onSuccess: (job) => {
      scanTerminalRef.current = "";
      queryClient.setQueryData(["job", job.id], job);
      setScanJobId(job.id);
    },
    onError: (error: Error) => {
      toast({ title: "Analyse impossible", description: error.message, variant: "error" });
    },
  });

  const cancelScan = useMutation({
    mutationFn: (jobId: string) => api.cancelJob(jobId),
    onSuccess: () => toast({ title: "Annulation demandée", variant: "warning" }),
    onError: (error: Error) => toast({ title: "Annulation impossible", description: error.message, variant: "error" }),
  });

  const startCompression = useMutation({
    mutationFn: (payload: CompressionPayload) => api.startCompression(payload),
    onSuccess: (job) => {
      compressionTerminalRef.current = "";
      setJobDismissed(false);
      queryClient.setQueryData(["job", job.id], job);
      setCompressionJobId(job.id);
      window.setTimeout(() => {
        document.getElementById("job")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 150);
    },
    onError: (error: Error) => {
      toast({ title: "Compression impossible", description: error.message, variant: "error", });
    },
  });

  const cancelCompression = useMutation({
    mutationFn: (jobId: string) => api.cancelJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs", "active"] });
      toast({ title: "Annulation demandée", variant: "warning" });
    },
    onError: (error: Error) => toast({ title: "Annulation impossible", description: error.message, variant: "error" }),
  });

  const pauseCompression = useMutation({
    mutationFn: (jobId: string) => api.pauseJob(jobId),
    onSuccess: (_data, jobId) => {
      queryClient.invalidateQueries({ queryKey: ["jobs", "active"] });
      queryClient.invalidateQueries({ queryKey: ["job", jobId] });
      toast({ title: "Compression mise en pause", variant: "warning" });
    },
    onError: (error: Error) => toast({ title: "Pause impossible", description: error.message, variant: "error" }),
  });

  const resumeCompression = useMutation({
    mutationFn: (jobId: string) => api.resumeJob(jobId),
    onSuccess: (_data, jobId) => {
      queryClient.invalidateQueries({ queryKey: ["jobs", "active"] });
      queryClient.invalidateQueries({ queryKey: ["job", jobId] });
      toast({ title: "Compression reprise", variant: "success" });
    },
    onError: (error: Error) => toast({ title: "Reprise impossible", description: error.message, variant: "error" }),
  });

  const deleteMedia = useMutation({
    mutationFn: (target: DeleteTarget) => {
      if (!scan) throw new Error("Aucun scan actif.");
      return api.deleteScanItems(
        scan.id,
        target.kind === "item" ? [target.item.id] : [],
        target.kind === "error" ? [target.path] : [],
      );
    },
    onSuccess: (result, target) => {
      if (scan) queryClient.invalidateQueries({ queryKey: ["scan", scan.id] });
      queryClient.invalidateQueries({ queryKey: ["scans"] });
      if (target.kind === "item") {
        setSelection((current) => {
          const next = new Set(current);
          next.delete(target.item.id);
          return next;
        });
      }
      if (result.deleted_count > 0) {
        toast({
          title: `${formatNumber(result.deleted_count)} fichier(s) supprimé(s)`,
          description: result.errors.length
            ? `${result.errors.length} fichier(s) n'ont pas pu être supprimés.`
            : "Suppression définitive effectuée.",
          variant: result.errors.length ? "warning" : "success",
        });
      } else {
        toast({
          title: "Suppression impossible",
          description: result.errors[0]?.error ?? "Aucun fichier supprimé.",
          variant: "error",
        });
      }
      setDeleteTarget(null);
    },
    onError: (error: Error) => {
      toast({ title: "Suppression impossible", description: error.message, variant: "error" });
      setDeleteTarget(null);
    },
  });

  const calibrate = useMutation({
    mutationFn: () =>
      api.benchmark({
        encoder: effectiveEncoder(hardwareQuery.data, settings),
        preset: Number(settings.preset),
        force: false,
      }),
    onSuccess: (result) => {
      queryClient.setQueryData(["hardware"], result.hardware);
      toast({
        title: "ETA calibrée",
        description: `${result.benchmark.fps} fps mesurés pour ${result.benchmark.encoder} (preset ${result.benchmark.preset}).`,
        variant: "success",
      });
    },
    onError: (error: Error) =>
      toast({ title: "Calibrage impossible", description: error.message, variant: "error" }),
  });

  const scanning = startScan.isPending || (scanJob.data ? ["queued", "running"].includes(scanJob.data.status) : false);

  const handleStartScan = (rootOverride?: string) => {
    const targetRoot = (rootOverride ?? root).trim();
    if (!targetRoot) {
      toast({ title: "Dossier manquant", description: "Indiquez le dossier à analyser.", variant: "warning" });
      return;
    }
    const options: ScanOptions = {
      ...scanOptions,
      series_roots: seriesRoots,
      exclude_globs: excludeText
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean),
    };
    setSelection(new Set());
    setCompressionJobId(null);
    setScanJobId(null);
    setSearchParams({});
    startScan.mutate({ targetRoot, options });
  };

  const addSeriesRoot = (path: string) => {
    const clean = path.trim();
    if (!clean) return;
    if (seriesRoots.includes(clean)) {
      toast({ title: "Dossier déjà marqué", description: clean, variant: "warning" });
      return;
    }
    setSeriesRoots([...seriesRoots, clean]);
    toast({ title: "Dossier de séries ajouté", description: clean, variant: "success" });
  };

  const removeSeriesRoot = (path: string) => {
    setSeriesRoots(seriesRoots.filter((entry) => entry !== path));
  };

  const toggleItem = (id: string) => {
    setSelection((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const openTest = (item: ScanItem) => setTestItem(item);

  const openBrowse = (mode: BrowseMode, initialPath: string) => {
    setBrowse({ open: true, mode, initial: initialPath });
  };

  const handleBrowseSelect = (path: string) => {
    if (browse.mode === "root") {
      setRoot(path);
    } else if (browse.mode === "series") {
      addSeriesRoot(path);
    } else if (browse.mode === "output") {
      setOutput({ ...output, mode: "custom_dir", output_dir: path });
    } else if (browse.mode === "trash") {
      setOriginals({ ...originals, mode: "move", trash_dir: path });
    }
  };

  const requestCompression = () => {
    if (!preflightPayload) {
      toast({ title: "Aucune sélection", description: "Sélectionnez au moins un élément.", variant: "warning" });
      return;
    }
    if (originals.mode === "move" && !originals.trash_dir) {
      toast({ title: "Corbeille manquante", description: "Indiquez le dossier de corbeille.", variant: "warning" });
      return;
    }
    if (schedule.enabled) {
      if (schedule.windows.length === 0) {
        toast({ title: "Planification vide", description: "Ajoutez au moins une plage horaire.", variant: "warning" });
        return;
      }
      if (schedule.windows.some((window) => window.days.length === 0)) {
        toast({ title: "Jours manquants", description: "Chaque plage doit avoir au moins un jour.", variant: "warning" });
        return;
      }
    }
    if (output.mode === "custom_dir" && !output.output_dir) {
      toast({ title: "Dossier de sortie manquant", description: "Indiquez le dossier de sortie.", variant: "warning" });
      return;
    }
    if (preflight && preflight.file_count === 0) {
      toast({
        title: "Aucun fichier compressible",
        description: "Corrigez les avertissements de vérification avant de relancer.",
        variant: "error",
      });
      return;
    }
    if (originals.mode === "delete") {
      setConfirmDeleteOpen(true);
      return;
    }
    startCompression.mutate(preflightPayload);
  };

  const confirmCompression = () => {
    setConfirmDeleteOpen(false);
    if (preflightPayload) startCompression.mutate(preflightPayload);
  };

  const closeJob = () => {
    setJobDismissed(true);
    setCompressionJobId(null);
  };

  const jobVisible = Boolean(compressionJob.data && !jobDismissed);
  const encoder = effectiveEncoder(hardwareQuery.data, settings);
  const lastScan = scansQuery.data?.[0];

  return (
    <PageContainer>
      <section className="mb-8 grid gap-6 lg:grid-cols-[1.35fr_0.65fr] lg:items-end">
        <div>
          <Badge variant="secondary" className="mb-3 gap-1.5 border-primary/20 bg-primary/5 text-primary">
            <Sparkles className="h-3 w-3" /> AV1 · test qualité · estimation matérielle
          </Badge>
          <h1 className="max-w-3xl text-3xl font-bold leading-[1.15] tracking-tight sm:text-4xl lg:text-[2.75rem]">
            Votre vidéothèque, <span className="text-gradient">plus légère.</span>
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground sm:text-base">
            Presse-Agrumes détecte les vidéos qui valent le coup d'être réencodées en AV1, regroupe les
            séries par saison, estime le temps sur votre matériel et vérifie la qualité sur un extrait
            avant de toucher au moindre fichier.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-1">
          <HeroStat
            icon={<Cpu className="h-4 w-4" />}
            label="Matériel"
            value={
              hardwareQuery.data
                ? `${hardwareQuery.data.cpu.logical_cores} threads · ${formatBytes(hardwareQuery.data.memory.total_bytes)}`
                : "Détection…"
            }
          />
          <HeroStat icon={<Zap className="h-4 w-4" />} label="Encodeur" value={encoder} />
          <HeroStat
            icon={<Gauge className="h-4 w-4" />}
            label="Benchmark"
            value={hardwareQuery.data && Object.keys(hardwareQuery.data.benchmarks).length > 0 ? "mesuré" : "indicatif"}
            onClick={() => navigate("/hardware")}
          />
        </div>
      </section>

      <div className="space-y-6">
        <FolderStep
          root={root}
          onRootChange={setRoot}
          options={scanOptions}
          onOptionsChange={setScanOptions}
          excludeText={excludeText}
          onExcludeTextChange={setExcludeText}
          seriesRoots={seriesRoots}
          onAddSeries={addSeriesRoot}
          onRemoveSeries={removeSeriesRoot}
          onBrowse={(mode, initialPath) => openBrowse(mode, initialPath)}
          mounts={mountsQuery.data?.roots}
          lastScan={activeScanId ? undefined : lastScan}
          onOpenLast={(scanId) => navigate(`/?scan=${scanId}`)}
          scanning={scanning}
          onStart={() => handleStartScan()}
          job={scanJob.data}
          onCancel={() => scanJob.data && cancelScan.mutate(scanJob.data.id)}
        />

        {activeScanId && scanQuery.isLoading && (
          <Card className="glass-panel">
            <CardContent className="flex items-center justify-center gap-3 py-16 text-sm text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin text-primary" /> Chargement de l'analyse…
            </CardContent>
          </Card>
        )}

        {activeScanId && scanQuery.isError && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>
              Impossible de charger cette analyse : {(scanQuery.error as Error).message}
            </AlertDescription>
          </Alert>
        )}

        {scan && (
          <ResultsPanel
            key={scan.id}
            scan={scan}
            selection={selection}
            onToggle={toggleItem}
            onSelectAll={(ids) => setSelection(new Set(ids))}
            onClearSelection={() => setSelection(new Set())}
            onTest={openTest}
            onDeleteItem={(item) => setDeleteTarget({ kind: "item", item })}
            onDeleteError={(path) => setDeleteTarget({ kind: "error", path })}
            onCalibrate={() => calibrate.mutate()}
            calibrating={calibrate.isPending}
            onRescan={() => handleStartScan(scan.root)}
            hardware={hardwareQuery.data}
            settings={settings}
            resourcePercent={resourcePercent}
            concurrency={concurrency}
          />
        )}

        {scan && (
          <CompressionPanel
            config={configQuery.data}
            hardware={hardwareQuery.data}
            scan={scan}
            selection={selection}
            settings={settings}
            onSettingsChange={setSettings}
            output={output}
            onOutputChange={setOutput}
            originals={originals}
            onOriginalsChange={setOriginals}
            resourcePercent={resourcePercent}
            onResourcePercentChange={setResourcePercent}
            concurrency={concurrency}
            onConcurrencyChange={setConcurrency}
            schedule={schedule}
            onScheduleChange={setSchedule}
            timezone={configQuery.data?.server_timezone}
            preflight={preflight}
            preflightLoading={preflightLoading}
            preflightError={preflightQuery.error ? (preflightQuery.error as Error).message : undefined}
            onStart={requestCompression}
            startPending={startCompression.isPending}
            onBrowse={(mode, initialPath) => openBrowse(mode, initialPath)}
          />
        )}

        {jobVisible && compressionJob.data && (
          <JobPanel
            job={compressionJob.data}
            onCancel={() => compressionJob.data && cancelCompression.mutate(compressionJob.data.id)}
            onRescan={() => handleStartScan(scan?.root)}
            onDismiss={closeJob}
            onPause={() => compressionJob.data && pauseCompression.mutate(compressionJob.data.id)}
            onResume={() => compressionJob.data && resumeCompression.mutate(compressionJob.data.id)}
            pausing={pauseCompression.isPending}
            resuming={resumeCompression.isPending}
          />
        )}

        {!activeScanId && !scanning && scansQuery.data && scansQuery.data.length > 0 && (
          <Card className="border-dashed border-border/60 bg-card/40">
            <CardContent className="flex flex-wrap items-center justify-between gap-4 p-5">
              <div className="flex items-center gap-3">
                <div className="grid h-9 w-9 place-items-center rounded-lg border border-border bg-secondary/50 text-primary">
                  <History className="h-4 w-4" />
                </div>
                <div>
                  <p className="text-sm font-semibold">
                    {formatNumber(scansQuery.data.length)} analyse(s) dans l'historique
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Dernière : {lastScan?.root} — gain potentiel {lastScan?.total_gain_human}.
                  </p>
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={() => navigate("/history")}>
                Voir l'historique <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </CardContent>
          </Card>
        )}

        {!activeScanId && scanning && (
          <Card className="border-border/60 bg-card/40">
            <CardContent className="flex items-center gap-3 p-5 text-sm text-muted-foreground">
              <CheckCircle2 className="h-4 w-4 text-primary" />
              L'analyse est en cours. Les résultats apparaîtront automatiquement à la fin.
            </CardContent>
          </Card>
        )}
      </div>

      <SetupDialog
        open={setupNeeded}
        state={setupQuery.data}
        initialPath={root}
        onComplete={(path) => {
          setRoot(path);
          setSetupDismissed(true);
          void queryClient.invalidateQueries({ queryKey: ["setup"] });
        }}
        onSkip={() => setSetupDismissed(true)}
      />

      <TestDialog
        open={Boolean(testItem)}
        onOpenChange={(open) => !open && setTestItem(null)}
        item={testItem}
        settings={settings}
        hardware={hardwareQuery.data}
      />

      <BrowseDialog
        open={browse.open}
        onOpenChange={(open) => setBrowse((current) => ({ ...current, open }))}
        mode={browse.mode}
        initialPath={browse.initial}
        onSelect={handleBrowseSelect}
        onMarkSeries={addSeriesRoot}
      />

      <AlertDialog open={confirmDeleteOpen} onOpenChange={setConfirmDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Supprimer les originaux ?</AlertDialogTitle>
            <AlertDialogDescription>
              Les fichiers originaux seront supprimés <strong>après vérification ffprobe</strong> de chaque
              sortie. Cette action est irréversible. Vérifiez d'abord avec un test qualité si nécessaire.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={startCompression.isPending}>Annuler</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={startCompression.isPending}
              onClick={(event) => {
                event.preventDefault();
                confirmCompression();
              }}
            >
              {startCompression.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <AlertTriangle className="h-4 w-4" />
              )}
              Supprimer les originaux
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={Boolean(deleteTarget)} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Trash2 className="h-5 w-5 text-destructive" /> Supprimer définitivement ?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {deleteTarget?.kind === "item" ? (
                <>
                  <strong className="text-foreground">
                    {deleteTarget.item.kind === "series"
                      ? `${deleteTarget.item.episode_count ?? 0} fichier(s) du pack`
                      : "Le fichier"}{" "}
                    « {deleteTarget.item.name} » ({deleteTarget.item.size_human})
                  </strong>{" "}
                  sera supprimé du disque.
                </>
              ) : (
                <>
                  Le fichier <strong className="break-all font-mono text-foreground">{deleteTarget?.path}</strong>{" "}
                  sera supprimé du disque.
                </>
              )}{" "}
              Cette action est <strong>irréversible</strong> : aucune corbeille, aucun test qualité,
              aucun original conservé. Le scan sera actualisé après suppression.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMedia.isPending}>Annuler</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={deleteMedia.isPending}
              onClick={(event) => {
                event.preventDefault();
                if (deleteTarget) deleteMedia.mutate(deleteTarget);
              }}
            >
              {deleteMedia.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              Supprimer définitivement
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageContainer>
  );
}

function HeroStat({
  icon,
  label,
  value,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  onClick?: () => void;
}) {
  const content = (
    <>
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-border/60 bg-secondary/50 text-primary">
        {icon}
      </span>
      <span className="min-w-0">
        <span className="block text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span>
        <span className="block truncate text-xs font-semibold">{value}</span>
      </span>
    </>
  );
  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className="flex items-center gap-2.5 rounded-lg border border-border/60 bg-card/50 p-2.5 text-left transition-colors hover:border-primary/40"
      >
        {content}
      </button>
    );
  }
  return <div className="flex items-center gap-2.5 rounded-lg border border-border/60 bg-card/50 p-2.5">{content}</div>;
}
