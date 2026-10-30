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
import type { ScanSummary } from "@/lib/types";
import { useScans } from "@/hooks/use-api";
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
        title="Historique des analyses"
        description="Reprenez une analyse existante sans rescanner le NAS. Seuls les index sont conservés : aucun fichier vidéo n'est touché."
        actions={
          <Button variant="outline" onClick={() => navigate("/")}>
            <FolderOpen className="h-4 w-4" /> Nouvelle analyse
          </Button>
        }
      />

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
