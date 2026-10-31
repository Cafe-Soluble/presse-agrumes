import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  CheckCircle2,
  Cpu,
  Gauge,
  HardDrive,
  Loader2,
  MemoryStick,
  MonitorCog,
  ServerCog,
  XCircle,
  Zap,
} from "lucide-react";
import { api } from "@/lib/api";
import { useHardware } from "@/hooks/use-api";
import { effectiveEncoder } from "@/lib/estimate";
import { formatBytes, formatNumber, timeAgo } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useToast } from "@/components/ui/toaster";
import { useConfig } from "@/hooks/use-api";

export function HardwarePage() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const hardwareQuery = useHardware();
  const config = useConfig();
  const hardware = hardwareQuery.data;
  const [encoder, setEncoder] = useState("libsvtav1");
  const [preset, setPreset] = useState(8);
  const initialized = useRef(false);

  useEffect(() => {
    if (!hardware || initialized.current) return;
    const supported = [
      "libsvtav1", "libaom-av1", "av1_vaapi", "libx265", "hevc_vaapi", "hevc_qsv",
    ].filter(
      (name) =>
        hardware.ffmpeg.encoders[name] &&
        (!name.endsWith("_vaapi") || hardware.gpu.vaapi_available),
    );
    if (!supported.includes(encoder) && supported[0]) setEncoder(supported[0]);
    const defaultSettings = config.data?.defaults.settings;
    if (defaultSettings) setPreset(defaultSettings.preset);
    initialized.current = true;
  }, [hardware, encoder, config.data]);

  const probeHardware = useMutation({
    mutationFn: () => api.hardware(true),
    onSuccess: (data) => queryClient.setQueryData(["hardware"], data),
    onError: (error: Error) =>
      toast({
        title: "Test matériel impossible",
        description: error.message,
        variant: "error",
      }),
  });

  const benchmark = useMutation({
    mutationFn: () => api.benchmark({ encoder, preset, force: true }),
    onSuccess: (result) => {
      queryClient.setQueryData(["hardware"], result.hardware);
      toast({
        title: "Benchmark terminé",
        description: `${result.benchmark.fps} fps avec ${result.benchmark.encoder} (preset ${result.benchmark.preset}).`,
        variant: "success",
      });
    },
    onError: (error: Error) => {
      toast({ title: "Benchmark impossible", description: error.message, variant: "error" });
    },
  });

  if (hardwareQuery.isLoading) {
    return (
      <PageShell title="Matériel & estimation" description="Détection du matériel et calibration des temps d'encodage.">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-36 animate-pulse rounded-xl border border-border bg-card/60" />
          ))}
        </div>
      </PageShell>
    );
  }

  if (!hardware) {
    return (
      <PageShell title="Matériel & estimation" description="Détection du matériel et calibration des temps d'encodage.">
        <Alert variant="destructive">
          <AlertDescription>Impossible de détecter le matériel : {(hardwareQuery.error as Error)?.message}</AlertDescription>
        </Alert>
      </PageShell>
    );
  }

  const supportedEncoders = [
    "libsvtav1", "libaom-av1", "av1_vaapi", "libx265", "hevc_vaapi", "hevc_qsv",
  ].filter(
    (name) =>
      hardware.ffmpeg.encoders[name] &&
      (!name.endsWith("_vaapi") || hardware.gpu.vaapi_available),
  );

  return (
    <PageShell
      title="Matériel & estimation"
      description="Presse-Agrumes mesure votre machine pour estimer les temps d'encodage et limiter la charge du NAS."
      actions={
        <Badge variant="secondary" className="font-mono">
          {hardware.hostname} · {hardware.cpu.logical_cores} threads
        </Badge>
      }
    >
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SpecCard
          icon={<Cpu className="h-4 w-4" />}
          title="Processeur"
          main={hardware.cpu.model}
          rows={[
            ["Cœurs physiques", hardware.cpu.physical_cores ? String(hardware.cpu.physical_cores) : "-"],
            ["Threads logiques", String(hardware.cpu.logical_cores)],
            ["Fréquence moyenne", hardware.cpu.mhz ? `${hardware.cpu.mhz} MHz` : "-"],
          ]}
        />
        <SpecCard
          icon={<MemoryStick className="h-4 w-4" />}
          title="Mémoire"
          main={formatBytes(hardware.memory.total_bytes)}
          rows={[
            ["Disponible", formatBytes(hardware.memory.available_bytes)],
            ["Plateforme", hardware.platform],
          ]}
        />
        <SpecCard
          icon={<MonitorCog className="h-4 w-4" />}
          title="GPU / VAAPI"
          main={hardware.gpu.vaapi_available ? "VAAPI utilisable" : "Pas de VAAPI utilisable"}
          rows={[
            ["Périphériques", hardware.gpu.devices.join(", ") || "aucun"],
            ["Pilote", hardware.gpu.vaapi?.driver ?? "-"],
            ["Cause", hardware.gpu.vaapi?.reason ?? (hardware.gpu.vaapi_available ? "aucune" : "-")],
          ]}
        />
        <SpecCard
          icon={<ServerCog className="h-4 w-4" />}
          title="ffmpeg"
          main={hardware.ffmpeg.version?.split(" ").slice(0, 3).join(" ") ?? "introuvable"}
          rows={[
            ["ffmpeg", hardware.ffmpeg.path ?? "-"],
            ["ffprobe", hardware.ffmpeg.ffprobe_path ?? "-"],
          ]}
          mono
        />
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" /> Accélération matérielle
          </CardTitle>
          <CardDescription>
            Capacités réelles du pilote VAAPI, par codec. « Compilé » signifie seulement que
            ffmpeg contient l'encodeur, pas que le GPU sait l'utiliser.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Badge variant={hardware.gpu.vaapi_available ? "success" : "warning"}>
              {hardware.gpu.vaapi_available ? "VAAPI utilisable" : "VAAPI non utilisable"}
            </Badge>
            {hardware.gpu.vaapi?.driver && (
              <span className="text-xs text-muted-foreground">{hardware.gpu.vaapi.driver}</span>
            )}
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="ml-auto"
              disabled={probeHardware.isPending}
              onClick={() => probeHardware.mutate()}
            >
              {probeHardware.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Zap className="h-3.5 w-3.5" />
              )}
              Tester le matériel
            </Button>
          </div>

          {hardware.gpu.vaapi?.reason && (
            <Alert variant="warning" className="py-2">
              <AlertDescription className="text-xs">{hardware.gpu.vaapi.reason}</AlertDescription>
            </Alert>
          )}

          {hardware.gpu.vaapi ? (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border/60 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                      <th className="px-2 py-2">Codec</th>
                      <th className="px-2 py-2 text-center">Décodage</th>
                      <th className="px-2 py-2 text-center">Encodage</th>
                      <th className="px-2 py-2 text-center">Compilé ffmpeg</th>
                      <th className="px-2 py-2 text-center">Test réel</th>
                    </tr>
                  </thead>
                  <tbody>
                    {hardware.gpu.vaapi.codecs.map((codec) => (
                      <tr key={codec.codec} className="border-b border-border/30">
                        <td className="px-2 py-2">{codec.label}</td>
                        <td className="px-2 py-2 text-center">{codec.decode ? "✅" : "❌"}</td>
                        <td className="px-2 py-2 text-center">{codec.encode ? "✅" : "❌"}</td>
                        <td className="px-2 py-2 text-center">{codec.compiled ? "✅" : "❌"}</td>
                        <td className="px-2 py-2 text-center">
                          {codec.tested_encode === null
                            ? "non testé"
                            : codec.tested_encode
                              ? "✅"
                              : "❌"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-[11px] text-muted-foreground">
                Décodage/encodage proviennent de vainfo. « Test réel » lance un mini-encodage
                ffmpeg sur le GPU quand tu cliques sur le bouton.
              </p>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              Aucun diagnostic VAAPI disponible. Vérifie /dev/dri et le paquet vainfo.
            </p>
          )}
        </CardContent>
      </Card>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-primary" /> Encodeurs détectés
            </CardTitle>
            <CardDescription>La disponibilité dépend du build ffmpeg installé sur le NAS.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {Object.entries(hardware.ffmpeg.encoders).map(([name, available]) => (
              <div
                key={name}
                className="flex items-center justify-between gap-3 rounded-lg border border-border/50 bg-secondary/20 px-3 py-2 text-sm"
              >
                <span className="flex items-center gap-2 font-mono text-xs">
                  {available ? (
                    <CheckCircle2 className="h-4 w-4 text-success" />
                  ) : (
                    <XCircle className="h-4 w-4 text-muted-foreground/50" />
                  )}
                  {name}
                </span>
                <span className="flex items-center gap-2">
                  {hardware.ffmpeg.recommended_encoder === name && (
                    <Badge variant="success">recommandé</Badge>
                  )}
                  <span className={available ? "text-xs text-success" : "text-xs text-muted-foreground"}>
                    {available ? "disponible" : "absent"}
                  </span>
                </span>
              </div>
            ))}
            <p className="pt-2 text-xs text-muted-foreground">
              Encodeur auto retenu :{" "}
              <span className="font-mono text-foreground">{effectiveEncoder(hardware, config.data?.defaults.settings ?? defaultSettings)}</span>
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Gauge className="h-4 w-4 text-primary" /> Calibrer l'estimation
            </CardTitle>
            <CardDescription>
              Mesure rapide sur une mire 1080p. Pour une estimation fiable sur tes films, utilise
              le bouton « Calibrer » des résultats : il encode 3 extraits du fichier réel avec les
              réglages choisis.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-[1fr_110px] gap-3">
              <div className="space-y-2">
                <Label>Encodeur</Label>
                <Select value={encoder} onValueChange={setEncoder}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {supportedEncoders.length === 0 && (
                      <SelectItem value="none" disabled>
                        Aucun encodeur AV1
                      </SelectItem>
                    )}
                    {supportedEncoders.map((name) => (
                      <SelectItem key={name} value={name}>
                        {name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Preset</Label>
                <Input
                  type="number"
                  min={0}
                  max={13}
                  value={preset}
                  onChange={(event) => setPreset(Number(event.target.value))}
                />
              </div>
            </div>
            <Button
              type="button"
              className="w-full"
              onClick={() => benchmark.mutate()}
              disabled={benchmark.isPending || supportedEncoders.length === 0}
            >
              {benchmark.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
              {benchmark.isPending ? "Mesure en cours…" : "Lancer le benchmark"}
            </Button>
            {benchmark.data && (
              <Alert variant="success">
                <AlertDescription>
                  <strong>{benchmark.data.benchmark.fps} fps</strong> - vitesse{" "}
                  {benchmark.data.benchmark.speed}×
                  {benchmark.data.benchmark.speed_min !== undefined &&
                  benchmark.data.benchmark.speed_max !== undefined
                    ? ` (fourchette ${benchmark.data.benchmark.speed_min}× à ${benchmark.data.benchmark.speed_max}×)`
                    : ""}
                  . L'ETA est maintenant basée sur cette mesure.
                </AlertDescription>
              </Alert>
            )}
            {benchmark.isError && (
              <Alert variant="destructive">
                <AlertDescription>{(benchmark.error as Error).message}</AlertDescription>
              </Alert>
            )}
            <p className="text-xs leading-relaxed text-muted-foreground">
              Le benchmark est mis en cache et associé à l'empreinte de la machine (CPU + version
              ffmpeg). Il est réutilisé pour toutes les estimations.
            </p>
          </CardContent>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <HardDrive className="h-4 w-4 text-primary" /> Benchmarks en cache
          </CardTitle>
          <CardDescription>Les mesures sont conservées dans data/cache/hardware.json.</CardDescription>
        </CardHeader>
        <CardContent>
          {Object.keys(hardware.benchmarks).length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucun benchmark mesuré pour le moment.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border/60 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                    <th className="px-2 py-2">Encodeur</th>
                    <th className="px-2 py-2">Preset</th>
                    <th className="px-2 py-2">Threads</th>
                    <th className="px-2 py-2 text-right">FPS</th>
                    <th className="px-2 py-2 text-right">Vitesse</th>
                    <th className="px-2 py-2 text-right">Mesuré</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.values(hardware.benchmarks).map((bench) => (
                    <tr key={`${bench.encoder}-${bench.preset}-${bench.threads}`} className="border-b border-border/30">
                      <td className="px-2 py-2 font-mono text-xs">{bench.encoder}</td>
                      <td className="px-2 py-2">{bench.preset}</td>
                      <td className="px-2 py-2">{bench.threads}</td>
                      <td className="px-2 py-2 text-right font-mono">{formatNumber(bench.fps)}</td>
                      <td className="px-2 py-2 text-right font-mono">{bench.speed}×</td>
                      <td className="px-2 py-2 text-right text-xs text-muted-foreground">{timeAgo(bench.tested_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Alert variant="info" className="mt-6">
        <AlertDescription>
          <strong>Comment l'ETA est calculée :</strong> durée vidéo ÷ fps du benchmark, ajustée par le
          pourcentage de threads alloué et le nombre d'encodages simultanés, avec 12 % de marge pour les
          I/O. Les encodeurs SVT-AV1 sont fortement parallélisés : allouer 50 % des threads n'équivaut
          pas exactement à 50 % de vitesse, d'où le calibrage réel.
        </AlertDescription>
      </Alert>
    </PageShell>
  );
}

const defaultSettings = {
  codec: "av1" as const,
  encoder: "auto" as const,
  preset: 8,
  crf: 32,
  pixel_format: "yuv420p" as const,
  audio_mode: "copy" as const,
  audio_bitrate_kbps: 128,
  container: "mkv" as const,
  subtitles: "copy" as const,
};

function PageShell({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <main className="mx-auto max-w-[1440px] px-4 py-8 sm:px-6">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p>
        </div>
        {actions}
      </div>
      {children}
    </main>
  );
}

function SpecCard({
  icon,
  title,
  main,
  rows,
  mono,
}: {
  icon: React.ReactNode;
  title: string;
  main: string;
  rows: [string, string][];
  mono?: boolean;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
          <span className="text-primary">{icon}</span>
          {title}
        </div>
        <CardTitle className={mono ? "break-all font-mono text-sm" : "break-words text-lg"}>{main}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1.5 text-xs">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-start justify-between gap-3">
            <span className="shrink-0 text-muted-foreground">{label}</span>
            <span className={mono ? "break-all text-right font-mono" : "break-words text-right"}>{value}</span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
