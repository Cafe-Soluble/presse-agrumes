import {
  AlertTriangle,
  ArrowRight,
  Clock3,
  Cpu,
  FileOutput,
  Gauge,
  Info,
  Loader2,
  Rocket,
  ShieldAlert,
  Sparkles,
  Trash2,
  Wand2,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import type {
  AppConfig,
  CompressionSchedule,
  CompressionSettings,
  Hardware,
  OriginalOptions,
  OutputOptions,
  PreflightResult,
  Scan,
  Warning,
} from "@/lib/types";
import { effectiveEncoder, selectionStats } from "@/lib/estimate";
import { useDiskSpace } from "@/hooks/use-api";
import {
  cn,
  formatBytes,
  formatDuration,
  formatEta,
  formatNumber,
} from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { StepBadge } from "@/components/page";
import { ScheduleEditor } from "@/components/schedule-editor";

interface CompressionPanelProps {
  config?: AppConfig;
  hardware?: Hardware;
  scan: Scan;
  selection: Set<string>;
  settings: CompressionSettings;
  onSettingsChange: (settings: CompressionSettings) => void;
  output: OutputOptions;
  onOutputChange: (output: OutputOptions) => void;
  originals: OriginalOptions;
  onOriginalsChange: (originals: OriginalOptions) => void;
  resourcePercent: number;
  onResourcePercentChange: (value: number) => void;
  concurrency: number;
  onConcurrencyChange: (value: number) => void;
  schedule: CompressionSchedule;
  onScheduleChange: (schedule: CompressionSchedule) => void;
  timezone?: string;
  preflight?: PreflightResult;
  preflightLoading: boolean;
  preflightError?: string;
  onStart: () => void;
  startPending: boolean;
  onBrowse: (mode: "output" | "trash", initialPath: string) => void;
}

export function CompressionPanel({
  config,
  hardware,
  scan,
  selection,
  settings,
  onSettingsChange,
  output,
  onOutputChange,
  originals,
  onOriginalsChange,
  resourcePercent,
  onResourcePercentChange,
  concurrency,
  onConcurrencyChange,
  schedule,
  onScheduleChange,
  timezone,
  preflight,
  preflightLoading,
  preflightError,
  onStart,
  startPending,
  onBrowse,
}: CompressionPanelProps) {
  const navigate = useNavigate();
  const stats = selectionStats(scan, selection, hardware, settings, resourcePercent, concurrency);
  const diskPath =
    output.mode === "custom_dir" && output.output_dir ? output.output_dir : scan.root;
  const diskQuery = useDiskSpace(diskPath);
  const encoders = hardware?.ffmpeg.encoders ?? {};
  const vaapi = hardware?.gpu.vaapi_available;
  const logical = hardware?.cpu.logical_cores ?? 4;
  const threads = Math.max(1, Math.round((logical * resourcePercent) / 100));
  const perJob = Math.max(1, Math.floor(threads / Math.max(1, concurrency)));
  const warnings: Warning[] = [...(preflight?.warnings ?? []), ...(preflight?.skipped ?? [])];
  const spaceInsufficient = Boolean(preflight && preflight.space_ok === false);
  const nothingToDo = Boolean(preflight && preflight.file_count === 0 && selection.size > 0);
  const partial = Boolean(
    preflight &&
      preflight.file_count > 0 &&
      preflight.file_count < preflight.selected_source_count,
  );
  const cannotStart =
    selection.size === 0 ||
    startPending ||
    preflightLoading ||
    Boolean(preflightError) ||
    spaceInsufficient ||
    nothingToDo;
  const patch = (partial: Partial<CompressionSettings>) => onSettingsChange({ ...settings, ...partial });

  return (
    <Card className="glass-panel" id="compression">
      <CardHeader className="gap-3 pb-4">
        <div className="flex items-start gap-3">
          <StepBadge step={2} />
          <div>
            <CardTitle>Réglages de compression</CardTitle>
            <CardDescription>
              Les réglages s'appliquent à la compression et aux tests qualité.
            </CardDescription>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        <div className="grid gap-8 lg:grid-cols-2">
          <div className="space-y-6">
            <section>
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <Wand2 className="h-4 w-4 text-primary" /> Qualité & encodeur
              </h3>
              <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {config?.quality_presets.map((preset) => {
                  const active = settings.preset === preset.preset && settings.crf === preset.crf;
                  return (
                    <button
                      key={preset.id}
                      type="button"
                      onClick={() => patch({ preset: preset.preset, crf: preset.crf })}
                      title={preset.description}
                      className={cn(
                        "rounded-lg border p-2.5 text-center transition-colors",
                        active
                          ? "border-primary/70 bg-primary/10"
                          : "border-border/60 bg-secondary/20 hover:border-border",
                      )}
                    >
                      <span className={cn("block text-xs font-semibold", active && "text-primary")}>{preset.label}</span>
                      <span className="mt-0.5 block font-mono text-[10px] text-muted-foreground">
                        p{preset.preset} · CRF {preset.crf}
                      </span>
                    </button>
                  );
                })}
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Encodeur</Label>
                  <Select
                    value={settings.encoder}
                    onValueChange={(value) => patch({ encoder: value as CompressionSettings["encoder"] })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="auto">
                        Auto - {effectiveEncoder(hardware, { ...settings, encoder: "auto" })}
                      </SelectItem>
                      <SelectItem value="libsvtav1" disabled={!encoders.libsvtav1}>
                        SVT-AV1 (CPU rapide)
                      </SelectItem>
                      <SelectItem value="libaom-av1" disabled={!encoders["libaom-av1"]}>
                        libaom AV1 (CPU lent)
                      </SelectItem>
                      <SelectItem value="av1_vaapi" disabled={!encoders.av1_vaapi || !vaapi}>
                        VAAPI (GPU)
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Conteneur</Label>
                  <Select
                    value={settings.container}
                    onValueChange={(value) => {
                      const container = value as CompressionSettings["container"];
                      patch({ container, subtitles: container === "mkv" ? settings.subtitles : "none" });
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="mkv">MKV (recommandé)</SelectItem>
                      <SelectItem value="mp4">MP4</SelectItem>
                      <SelectItem value="webm">WebM</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2 sm:col-span-2">
                  <div className="flex items-center justify-between text-xs">
                    <Label>Preset SVT-AV1</Label>
                    <span className="font-mono text-primary">{settings.preset}</span>
                  </div>
                  <Slider
                    value={[settings.preset]}
                    onValueChange={([value]) => patch({ preset: value })}
                    min={0}
                    max={13}
                    step={1}
                  />
                  <p className="text-[10px] text-muted-foreground">
                    0 = meilleure qualité/lent · 13 = très rapide.
                  </p>
                </div>

                <div className="space-y-2 sm:col-span-2">
                  <div className="flex items-center justify-between text-xs">
                    <Label>CRF (qualité)</Label>
                    <span className="font-mono text-primary">{settings.crf}</span>
                  </div>
                  <Slider
                    value={[settings.crf]}
                    onValueChange={([value]) => patch({ crf: value })}
                    min={0}
                    max={63}
                    step={1}
                  />
                  <p className="text-[10px] text-muted-foreground">
                    Plus bas = meilleure qualité et fichier plus gros.
                  </p>
                </div>

                <div className="space-y-2">
                  <Label>Profondeur couleur</Label>
                  <Select
                    value={settings.pixel_format}
                    onValueChange={(value) => patch({ pixel_format: value as CompressionSettings["pixel_format"] })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="yuv420p">8 bits</SelectItem>
                      <SelectItem value="yuv420p10le">10 bits (HDR / gradation)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Audio</Label>
                  <Select
                    value={settings.audio_mode}
                    onValueChange={(value) => patch({ audio_mode: value as CompressionSettings["audio_mode"] })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="copy">Copier (sans perte)</SelectItem>
                      <SelectItem value="opus">Réencoder en Opus 128k</SelectItem>
                      <SelectItem value="aac">Réencoder en AAC 128k</SelectItem>
                      <SelectItem value="none">Supprimer l'audio</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Sous-titres</Label>
                  <Select
                    value={settings.subtitles}
                    onValueChange={(value) => patch({ subtitles: value as CompressionSettings["subtitles"] })}
                    disabled={settings.container !== "mkv"}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="copy">Copier (MKV)</SelectItem>
                      <SelectItem value="none">Ignorer</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </section>

            <section>
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <Cpu className="h-4 w-4 text-primary" /> Ressources
              </h3>
              <div className="space-y-4 rounded-lg border border-border/60 bg-secondary/20 p-4">
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <Label>Ressources CPU allouées</Label>
                    <span className="font-mono text-primary">{resourcePercent} %</span>
                  </div>
                  <Slider
                    value={[resourcePercent]}
                    onValueChange={([value]) => onResourcePercentChange(value)}
                    min={5}
                    max={100}
                    step={5}
                  />
                  <p className="text-[10px] text-muted-foreground">
                    {threads} thread(s) sur {logical}
                    {concurrency > 1 ? ` · ${perJob} par encodage simultané` : ""}. Les process sont
                    lancés avec une priorité réduite (nice 10).
                  </p>
                </div>
                <div className="space-y-2">
                  <Label>Fichiers simultanés</Label>
                  <Select
                    value={String(concurrency)}
                    onValueChange={(value) => onConcurrencyChange(Number(value))}
                  >
                    <SelectTrigger className="w-full sm:w-[220px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="1">1 (recommandé)</SelectItem>
                      <SelectItem value="2">2</SelectItem>
                      <SelectItem value="3">3</SelectItem>
                      <SelectItem value="4">4</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </section>

            <ScheduleEditor
              schedule={schedule}
              onChange={onScheduleChange}
              timezone={timezone}
            />
          </div>

          <div className="space-y-6">
            <section>
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <Trash2 className="h-4 w-4 text-primary" /> Fichiers originaux
              </h3>
              <RadioGroup
                value={originals.mode}
                onValueChange={(value) => onOriginalsChange({ ...originals, mode: value as OriginalOptions["mode"] })}
                className="gap-2"
              >
                <RadioCard
                  value="keep"
                  active={originals.mode === "keep"}
                  title="Garder"
                  description="L'original reste en place, le fichier compressé est ajouté à côté."
                />
                <RadioCard
                  value="delete"
                  active={originals.mode === "delete"}
                  title="Supprimer après vérification"
                  description="Irréversible. Chaque sortie est validée par ffprobe avant suppression."
                  tone="destructive"
                />
                <RadioCard
                  value="move"
                  active={originals.mode === "move"}
                  title="Déplacer vers une corbeille"
                  description="Conserve l'arborescence relative pour pouvoir revenir en arrière."
                />
              </RadioGroup>
              {originals.mode === "move" && (
                <div className="mt-2 flex gap-2">
                  <Input
                    value={originals.trash_dir ?? ""}
                    onChange={(event) => onOriginalsChange({ ...originals, trash_dir: event.target.value })}
                    placeholder="/mnt/media/_originaux"
                    className="font-mono text-xs"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => onBrowse("trash", originals.trash_dir ?? scan.root)}
                  >
                    Parcourir
                  </Button>
                </div>
              )}
              {originals.mode === "delete" && (
                <Alert variant="destructive" className="mt-2 py-2">
                  <ShieldAlert className="h-4 w-4" />
                  <AlertDescription>
                    Les originaux seront supprimés après chaque compression réussie. Faites un test
                    qualité avant la première utilisation.
                  </AlertDescription>
                </Alert>
              )}
            </section>

            <section>
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <FileOutput className="h-4 w-4 text-primary" /> Fichier compressé
              </h3>
              <RadioGroup
                value={output.mode}
                onValueChange={(value) => onOutputChange({ ...output, mode: value as OutputOptions["mode"] })}
                className="gap-2"
              >
                <RadioCard
                  value="same_dir_new_name"
                  active={output.mode === "same_dir_new_name"}
                  title="Même dossier, nouveau nom"
                  description="Ajoute un suffixe. L'original et le compressé cohabitent."
                />
                <RadioCard
                  value="same_dir_same_name"
                  active={output.mode === "same_dir_same_name"}
                  title="Même dossier, même nom"
                  description="Remplace le fichier : nécessite de supprimer ou déplacer l'original."
                />
                <RadioCard
                  value="custom_dir"
                  active={output.mode === "custom_dir"}
                  title="Autre dossier"
                  description="Recrée l'arborescence relative du scan dans un dossier dédié."
                />
              </RadioGroup>

              {output.mode === "same_dir_new_name" && (
                <div className="mt-2 space-y-2">
                  <Label htmlFor="suffix">Suffixe</Label>
                  <Input
                    id="suffix"
                    value={output.suffix}
                    onChange={(event) => onOutputChange({ ...output, suffix: event.target.value })}
                    placeholder=".av1"
                    className="font-mono"
                  />
                  <p className="text-[10px] text-muted-foreground">
                    Exemple : <code className="font-mono">film.av1.mkv</code>
                  </p>
                </div>
              )}

              {output.mode === "custom_dir" && (
                <div className="mt-2 flex gap-2">
                  <Input
                    value={output.output_dir ?? ""}
                    onChange={(event) => onOutputChange({ ...output, output_dir: event.target.value })}
                    placeholder="/mnt/media/AV1"
                    className="font-mono text-xs"
                  />
                  <Button type="button" variant="outline" onClick={() => onBrowse("output", output.output_dir ?? scan.root)}>
                    Parcourir
                  </Button>
                </div>
              )}

              {output.mode !== "same_dir_same_name" && (
                <label className="mt-3 flex cursor-pointer items-start gap-2 text-xs text-muted-foreground">
                  <Checkbox
                    className="mt-0.5"
                    checked={output.clean_codec_names ?? false}
                    onCheckedChange={(checked) =>
                      onOutputChange({ ...output, clean_codec_names: checked === true })
                    }
                  />
                  <span>
                    Nettoyer le nom (retirer x264, x265, H264, HEVC, AV1…)
                    <span className="mt-0.5 block text-[10px]">
                      Exemple : <code className="font-mono">Film.2024.1080p.x265-GROUP.mkv</code> →{" "}
                      <code className="font-mono">Film.2024.1080p-GROUP.av1.mkv</code>
                    </span>
                  </span>
                </label>
              )}

              <label className="mt-3 flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
                <Checkbox
                  checked={output.overwrite}
                  onCheckedChange={(checked) => onOutputChange({ ...output, overwrite: checked === true })}
                />
                Écraser une sortie existante
              </label>
            </section>

            <section className="rounded-xl border border-primary/30 bg-gradient-to-br from-primary/[0.09] to-primary/[0.02] p-4">
              <div className="flex items-center justify-between gap-2">
                <h3 className="flex items-center gap-2 text-sm font-semibold text-amber-100">
                  <Clock3 className="h-4 w-4" /> Estimation
                </h3>
                <Badge variant={stats.source === "mesuré" ? "success" : "secondary"}>
                  {stats.source}
                </Badge>
              </div>
              <p className="mt-2 text-3xl font-bold tracking-tight">{formatEta(stats.seconds)}</p>
              <div className="mt-3 space-y-1.5 text-xs">
                <EstimateRow label="Éléments" value={`${formatNumber(stats.fileCount)} fichier(s)`} />
                <EstimateRow label="Durée vidéo" value={formatDuration(stats.duration)} />
                <EstimateRow
                  label="Sortie estimée"
                  value={preflight?.total_estimated_output_human ?? formatBytes(stats.output)}
                />
                <EstimateRow
                  label="Espace libre"
                  value={
                    preflight?.free_space_human ??
                    diskQuery.data?.free_human ??
                    "vérification…"
                  }
                />
                <EstimateRow
                  label="Disque"
                  value={
                    diskQuery.data
                      ? `${diskQuery.data.used_percent} % utilisé sur ${diskQuery.data.total_human}`
                      : "vérification…"
                  }
                />
                <EstimateRow
                  label="Encodeur"
                  value={`${effectiveEncoder(hardware, settings)} · preset ${settings.preset}`}
                />
              </div>
              {stats.source !== "mesuré" && (
                <button
                  type="button"
                  className="mt-3 flex items-center gap-1 text-[11px] text-primary hover:underline"
                  onClick={() => navigate("/hardware")}
                >
                  <Gauge className="h-3 w-3" /> Calibrer l'ETA sur ce matériel <ArrowRight className="h-3 w-3" />
                </button>
              )}
              <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground">
                {stats.source === "mesuré"
                  ? "ETA calculée à partir du benchmark matériel de cette machine."
                  : "ETA indicative : lancez un benchmark dans « Matériel » pour la préciser."}
              </p>
            </section>

            {preflightError && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>Vérification impossible : {preflightError}</AlertDescription>
              </Alert>
            )}

            {preflightLoading && (
              <p className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Vérification des chemins et de l'espace disque…
              </p>
            )}

            {warnings.length > 0 && (
              <div className="space-y-1.5">
                {warnings.slice(0, 8).map((warning, index) => (
                  <Alert
                    key={`${warning.path ?? "w"}-${index}`}
                    variant={warning.error ? "destructive" : "warning"}
                    className="py-2"
                  >
                    <AlertTriangle className="h-4 w-4" />
                    <AlertDescription className="break-words text-[11px]">
                      {warning.warning}
                      {warning.path && (
                        <span className="mt-0.5 block break-all font-mono text-[10px] opacity-70">
                          {warning.path}
                        </span>
                      )}
                    </AlertDescription>
                  </Alert>
                ))}
                {warnings.length > 8 && (
                  <p className="text-[11px] text-muted-foreground">
                    … {warnings.length - 8} autre(s) avertissement(s).
                  </p>
                )}
              </div>
            )}

            {spaceInsufficient && (
              <Alert variant="destructive" className="py-2">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription className="text-[11px]">
                  Espace insuffisant : sortie estimée{" "}
                  <strong>{preflight?.total_estimated_output_human}</strong>, espace libre{" "}
                  <strong>{preflight?.free_space_human}</strong>
                  {preflight?.free_space_path ? ` sur ${preflight.free_space_path}` : ""}. Libère de
                  l'espace ou choisis un autre dossier de sortie.
                </AlertDescription>
              </Alert>
            )}

            {partial && (
              <Alert variant="warning" className="py-2">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription className="text-[11px]">
                  {preflight?.file_count} fichier(s) sur {preflight?.selected_source_count} peuvent
                  être compressés. Les autres sont ignorés (espace, permissions ou conflit de
                  sortie) : voir les avertissements ci-dessus.
                </AlertDescription>
              </Alert>
            )}

            {nothingToDo && (
              <Alert variant="warning" className="py-2">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription className="text-[11px]">
                  Aucun fichier ne peut être compressé avec ces réglages. Consulte la liste des
                  avertissements ci-dessus (espace, permissions, conflits de sortie).
                </AlertDescription>
              </Alert>
            )}

            <Button
              type="button"
              size="lg"
              className="w-full"
              onClick={onStart}
              disabled={cannotStart}
            >
              {startPending ? <Loader2 className="h-5 w-5 animate-spin" /> : <Rocket className="h-5 w-5" />}
              {startPending ? "Démarrage…" : "Lancer la compression"}
            </Button>
            <p className="text-center text-[10px] text-muted-foreground">
              <Sparkles className="mr-1 inline h-3 w-3" />
              L'original n'est supprimé qu'après vérification ffprobe de la sortie.
            </p>
            {selection.size === 0 && (
              <p className="text-center text-[11px] text-muted-foreground">
                <Info className="mr-1 inline h-3 w-3" />
                Sélectionnez des éléments dans les résultats.
              </p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function RadioCard({
  value,
  active,
  title,
  description,
  tone,
}: {
  value: string;
  active: boolean;
  title: string;
  description: string;
  tone?: "destructive";
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors",
        active ? "border-primary/55 bg-primary/[0.055]" : "border-border/60 bg-secondary/15 hover:border-border",
      )}
    >
      <RadioGroupItem value={value} className={cn("mt-0.5", tone === "destructive" && "border-destructive/60")} />
      <span className="min-w-0">
        <span className={cn("block text-sm font-medium", tone === "destructive" && "text-destructive")}>{title}</span>
        <span className="mt-0.5 block text-[11px] leading-relaxed text-muted-foreground">{description}</span>
      </span>
    </label>
  );
}

function EstimateRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="text-muted-foreground">{label}</span>
      <span className="break-all text-right font-medium">{value}</span>
    </div>
  );
}
