import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  ChevronRight,
  Clock3,
  Film,
  FolderOpen,
  History,
  Loader2,
  Trash2,
  TrendingDown,
} from "lucide-react";
import { api } from "@/lib/api";
import type { JobSnapshot, ScanSummary } from "@/lib/types";
import { useJobHistory, useScans } from "@/hooks/use-api";
import { formatBytes, formatNumber, formatPercent, timeAgo } from "@/lib/utils";
import { PageContainer, PageHeader, EmptyState } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
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

export function HistoryPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const scans = useScans();
  const jobHistory = useJobHistory();
  const compressions = (jobHistory.data?.jobs ?? []).filter((job) => job.kind === "compress");
  const [toDelete, setToDelete] = useState<ScanSummary | null>(null);

  const remove = useMutation({
    mutationFn: (scanId: string) => api.deleteScan(scanId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scans"] });
      toast({ title: "Analyse supprimée", variant: "success" });
      setToDelete(null);
    },
    onError: (error: Error) => {
      toast({ title: "Suppression impossible", description: error.message, variant: "error" });
    },
  });

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Bibliothèque"
        title="Historique"
        description="Reprenez une analyse sans rescanner le NAS et consultez les compressions effectuées. Seuls les index et les journaux sont conservés : aucun fichier vidéo n'est touché."
        actions={
          <Button variant="outline" onClick={() => navigate("/")}>
            <FolderOpen className="h-4 w-4" /> Nouvelle analyse
          </Button>
        }
      />

      <div className="mb-3">
        <h2 className="text-lg font-semibold tracking-tight">Analyses</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Index des dossiers scannés, réutilisables sans nouvelle analyse.
        </p>
      </div>

      {scans.isLoading && (
        <div className="grid gap-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="h-24 animate-pulse rounded-xl border border-border bg-card/50" />
          ))}
        </div>
      )}

      {scans.isError && (
        <Card>
          <CardContent className="py-8 text-center text-sm text-destructive">
            Impossible de charger l'historique : {(scans.error as Error).message}
          </CardContent>
        </Card>
      )}

      {!scans.isLoading && scans.data?.length === 0 && (
        <EmptyState
          icon={<History className="h-5 w-5" />}
          title="Aucune analyse pour le moment"
          description="Lancez une première analyse depuis la page Compression : choisissez un dossier, puis laissez Presse-Agrumes détecter les vidéos intéressantes."
          action={
            <Button onClick={() => navigate("/")}>
              <FolderOpen className="h-4 w-4" /> Choisir un dossier
            </Button>
          }
        />
      )}

      <div className="grid gap-3">
        {scans.data?.map((scan) => (
          <Card key={scan.id} className="group transition-colors hover:border-border/90 hover:bg-card/80">
            <CardContent className="flex flex-col gap-4 p-5 lg:flex-row lg:items-center">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={scan.partial ? "warning" : "secondary"} className="font-mono text-[10px]">
                    {scan.partial ? "partielle" : "terminée"}
                  </Badge>
                  <span className="text-xs text-muted-foreground">{timeAgo(scan.created_at)}</span>
                </div>
                <p className="mt-2 break-all font-mono text-sm text-foreground">{scan.root}</p>
                <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <Film className="h-3 w-3" /> {formatNumber(scan.items_count)} élément(s)
                  </span>
                  <span className="flex items-center gap-1">
                    <Archive className="h-3 w-3" /> {formatBytes(scan.total_size_bytes)}
                  </span>
                  <span className="flex items-center gap-1 text-success">
                    <TrendingDown className="h-3 w-3" /> {scan.total_gain_human} ({formatPercent(scan.total_gain_percent)})
                  </span>
                  <span className="flex items-center gap-1">
                    <Clock3 className="h-3 w-3" /> {scan.total_duration_human}
                  </span>
                  {scan.pack_count > 0 && (
                    <Badge variant="info" className="text-[10px]">
                      {scan.pack_count} pack(s) série
                    </Badge>
                  )}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => setToDelete(scan)}>
                  <Trash2 className="h-3.5 w-3.5" /> Supprimer
                </Button>
                <Button size="sm" onClick={() => navigate(`/?scan=${scan.id}`)}>
                  Ouvrir <ChevronRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="mt-10 space-y-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Compressions</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Jobs de compression terminés, annulés ou en erreur, avec le gain réellement obtenu.
          </p>
        </div>

        {jobHistory.isLoading && (
          <div className="h-20 animate-pulse rounded-xl border border-border bg-card/50" />
        )}

        {jobHistory.isError && (
          <Card>
            <CardContent className="py-6 text-center text-sm text-destructive">
              Impossible de charger les compressions : {(jobHistory.error as Error).message}
            </CardContent>
          </Card>
        )}

        {!jobHistory.isLoading && compressions.length === 0 && (
          <Card>
            <CardContent className="py-6 text-center text-sm text-muted-foreground">
              Aucune compression effectuée pour le moment.
            </CardContent>
          </Card>
        )}

        <div className="grid gap-3">
          {compressions.map((job) => (
            <CompressionHistoryRow key={job.id} job={job} />
          ))}
        </div>
      </div>

      <AlertDialog open={Boolean(toDelete)} onOpenChange={(open) => !open && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Supprimer cette analyse ?</AlertDialogTitle>
            <AlertDialogDescription>
              L'index de l'analyse <span className="font-mono text-foreground">{toDelete?.root}</span> sera
              supprimé. Aucun fichier vidéo ne sera touché.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={remove.isPending}>Annuler</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={remove.isPending}
              onClick={(event) => {
                event.preventDefault();
                if (toDelete) remove.mutate(toDelete.id!);
              }}
            >
              {remove.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              Supprimer
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageContainer>
  );
}

function CompressionHistoryRow({ job }: { job: JobSnapshot }) {
  const result = job.result ?? {};
  const encoder = result.encoder ? String(result.encoder) : null;
  const savedBytes = Number(result.saved_bytes ?? 0);
  const savedPercent = Number(result.saved_percent ?? 0);
  const success = Number(result.success ?? 0);
  const failed = Number(result.failed ?? 0);
  const total = Number(result.total ?? success + failed);
  const variant =
    job.status === "done" ? "success" : job.status === "error" ? "destructive" : "warning";
  const label =
    job.status === "done"
      ? "terminée"
      : job.status === "error"
        ? "erreur"
        : job.status === "cancelled"
          ? "annulée"
          : job.status;

  return (
    <Card>
      <CardContent className="flex flex-col gap-3 p-5 lg:flex-row lg:items-center">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={variant} className="text-[10px]">
              {label}
            </Badge>
            <span className="text-xs text-muted-foreground">
              {timeAgo(job.finished_at || job.created_at)}
            </span>
            {encoder && (
              <Badge variant="secondary" className="text-[10px]">
                {encoder}
              </Badge>
            )}
          </div>
          <p className="mt-2 truncate text-sm font-medium">{job.label}</p>
          <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <Film className="h-3 w-3" /> {formatNumber(success)}/{formatNumber(total)} fichier(s)
            </span>
            {savedBytes > 0 ? (
              <span className="flex items-center gap-1 text-success">
                <TrendingDown className="h-3 w-3" /> {formatBytes(savedBytes)} économisés (
                {formatPercent(savedPercent)})
              </span>
            ) : (
              <span>{formatBytes(Number(result.output_bytes ?? 0))} produits</span>
            )}
            {failed > 0 && <span className="text-destructive">{failed} échec(s)</span>}
            {job.error && <span className="truncate text-destructive">{job.error}</span>}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
