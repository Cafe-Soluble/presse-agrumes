import { Activity, Cpu, MemoryStick, MonitorCog, Thermometer } from "lucide-react";
import { useSystemStats } from "@/hooks/use-api";
import { formatBytes, formatNumber } from "@/lib/utils";
import { PageContainer, PageHeader } from "@/components/page";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";

export function SystemPage() {
  const stats = useSystemStats();
  const data = stats.data;

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Supervision"
        title="Système"
        description="Charge CPU, mémoire, température et GPU, rafraîchies toutes les 2 secondes."
        actions={
          <Badge variant={stats.isError ? "destructive" : "success"} className="gap-1.5">
            <Activity className="h-3 w-3" />
            {stats.isError ? "indisponible" : "temps réel"}
          </Badge>
        }
      />

      {stats.isError && (
        <Alert variant="destructive">
          <AlertDescription>
            Impossible de lire les métriques : {(stats.error as Error).message}
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={<Cpu className="h-4 w-4" />}
          title="Processeur"
          value={data?.cpu.percent !== null && data?.cpu.percent !== undefined ? `${data.cpu.percent} %` : "-"}
          percent={data?.cpu.percent ?? null}
          rows={[
            ["Threads", data ? formatNumber(data.cpu.cores) : "-"],
            ["Charge 1 min", data?.cpu.load_1 !== null && data?.cpu.load_1 !== undefined ? String(data.cpu.load_1) : "-"],
            ["Charge 5 min", data?.cpu.load_5 !== null && data?.cpu.load_5 !== undefined ? String(data.cpu.load_5) : "-"],
          ]}
        />

        <MetricCard
          icon={<MemoryStick className="h-4 w-4" />}
          title="Mémoire"
          value={data?.memory.percent !== null && data?.memory.percent !== undefined ? `${data.memory.percent} %` : "-"}
          percent={data?.memory.percent ?? null}
          rows={[
            ["Utilisée", data?.memory.used_bytes ? formatBytes(data.memory.used_bytes) : "-"],
            ["Totale", data?.memory.total_bytes ? formatBytes(data.memory.total_bytes) : "-"],
            ["Disponible", data?.memory.available_bytes ? formatBytes(data.memory.available_bytes) : "-"],
          ]}
        />

        <MetricCard
          icon={<Thermometer className="h-4 w-4" />}
          title="Température CPU"
          value={data?.temperature.celsius !== null && data?.temperature.celsius !== undefined ? `${data.temperature.celsius} °C` : "-"}
          percent={null}
          rows={[
            ["Capteur", data?.temperature.sensor ?? "-"],
            ["État", data?.temperature.celsius ? "mesurée" : "indisponible"],
          ]}
        />

        <MetricCard
          icon={<MonitorCog className="h-4 w-4" />}
          title="GPU"
          value={
            data?.gpu?.utilization_percent !== null && data?.gpu?.utilization_percent !== undefined
              ? `${data.gpu.utilization_percent} %`
              : data?.gpu
                ? data.gpu.name
                : "-"
          }
          percent={data?.gpu?.utilization_percent ?? null}
          rows={
            data?.gpu
              ? [
                  ["Modèle", data.gpu.name],
                  [
                    "VRAM",
                    data.gpu.memory_used_bytes && data.gpu.memory_total_bytes
                      ? `${formatBytes(data.gpu.memory_used_bytes)} / ${formatBytes(data.gpu.memory_total_bytes)}`
                      : "-",
                  ],
                  [
                    "Température",
                    data.gpu.temperature_c !== null ? `${data.gpu.temperature_c} °C` : "-",
                  ],
                  [
                    "Fréquence",
                    data.gpu.frequency_mhz !== null ? `${data.gpu.frequency_mhz} MHz` : "-",
                  ],
                ]
              : [["Périphérique", "aucun détecté"]]
          }
        />
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" /> À propos des mesures
          </CardTitle>
          <CardDescription>
            Les valeurs viennent de /proc et /sys, sans agent externe.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-xs leading-relaxed text-muted-foreground">
          <p>
            La charge CPU est calculée sur l'intervalle entre deux rafraîchissements. La première
            mesure peut être approximative.
          </p>
          <p>
            La température est le capteur le plus chaud exposé par le système (thermal_zone ou
            hwmon). Certains NAS n'en exposent aucun.
          </p>
          <p>
            L'utilisation GPU n'est pas standardisée pour Intel : elle peut rester indisponible
            même quand VAAPI fonctionne. AMD et NVIDIA exposent généralement une valeur.
          </p>
          <p className="font-mono text-[10px]">Dernière mesure : {data?.timestamp ?? "-"}</p>
        </CardContent>
      </Card>
    </PageContainer>
  );
}

function MetricCard({
  icon,
  title,
  value,
  percent,
  rows,
}: {
  icon: React.ReactNode;
  title: string;
  value: string;
  percent: number | null;
  rows: [string, string][];
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          {icon} {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-2xl font-bold tracking-tight">{value}</p>
        {percent !== null && <Progress value={percent} />}
        <div className="space-y-1 text-xs">
          {rows.map(([label, rowValue]) => (
            <div key={label} className="flex items-center justify-between gap-3">
              <span className="text-muted-foreground">{label}</span>
              <span className="truncate font-mono">{rowValue}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
