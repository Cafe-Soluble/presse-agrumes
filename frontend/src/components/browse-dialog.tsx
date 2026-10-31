import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowUp, ChevronRight, Folder, FolderTree, Link2, Lock, Tv } from "lucide-react";
import { api } from "@/lib/api";
import type { BrowseEntry } from "@/lib/types";
import { useMounts } from "@/hooks/use-api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { ScrollArea } from "@/components/ui/scroll-area";

export type BrowseMode = "root" | "series" | "output" | "trash";

const titles: Record<BrowseMode, { title: string; description: string }> = {
  root: { title: "Choisir le dossier à analyser", description: "Tous les sous-dossiers seront parcourus." },
  series: { title: "Choisir un dossier de séries", description: "Chaque dossier de saison deviendra un pack unique." },
  output: { title: "Choisir le dossier de sortie", description: "L'arborescence relative du scan sera recréée ici." },
  trash: { title: "Choisir la corbeille", description: "Les originaux y seront déplacés avec leur arborescence." },
};

interface BrowseDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: BrowseMode;
  initialPath?: string;
  onSelect: (path: string) => void;
  onMarkSeries?: (path: string) => void;
}

export function BrowseDialog({
  open,
  onOpenChange,
  mode,
  initialPath,
  onSelect,
  onMarkSeries,
}: BrowseDialogProps) {
  const mountsQuery = useMounts();
  const roots = mountsQuery.data?.roots ?? [];

  // Sans chemin initial, on ouvre sur une racine réellement autorisée. En
  // Docker, « / » est hors périmètre : on ne le propose jamais par défaut.
  const defaultPath = useMemo(
    () => roots.find((root) => !root.empty)?.path ?? roots[0]?.path ?? "",
    [roots],
  );

  // Un ancien chemin « / » mémorisé (installation native) est ignoré si « / »
  // n'est pas une racine autorisée sur ce serveur.
  const startPath = useMemo(() => {
    if (initialPath && (initialPath !== "/" || roots.some((root) => root.path === "/"))) {
      return initialPath;
    }
    return defaultPath;
  }, [initialPath, defaultPath, roots]);

  const [path, setPath] = useState(startPath);
  const [input, setInput] = useState(startPath);

  useEffect(() => {
    if (!open) return;
    setPath(startPath);
    setInput(startPath);
  }, [open, startPath]);

  const browse = useQuery({
    queryKey: ["browse", path],
    queryFn: () => api.browse(path),
    enabled: open && Boolean(path),
    retry: 0,
  });

  const data = browse.data;

  useEffect(() => {
    if (data?.path) setInput(data.path);
  }, [data?.path]);

  const navigate = (next: string) => {
    setPath(next);
    setInput(next);
  };

  const choose = () => {
    if (!data) return;
    onSelect(data.path);
    onOpenChange(false);
  };

  const markSeries = () => {
    if (!data) return;
    onMarkSeries?.(data.path);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FolderTree className="h-5 w-5 text-primary" />
            {titles[mode].title}
          </DialogTitle>
          <DialogDescription>{titles[mode].description}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap items-center gap-1 rounded-lg border border-border/60 bg-secondary/30 px-2 py-1.5">
          {data?.breadcrumbs.map((crumb, index) => (
            <span key={crumb.path} className="flex min-w-0 items-center">
              {index > 0 && <ChevronRight className="mx-0.5 h-3 w-3 shrink-0 text-muted-foreground/60" />}
              <button
                type="button"
                className={cn(
                  "max-w-[180px] truncate rounded px-1.5 py-0.5 font-mono text-[11px] transition-colors hover:bg-secondary hover:text-foreground",
                  index === (data?.breadcrumbs.length ?? 0) - 1 ? "text-primary" : "text-muted-foreground",
                )}
                onClick={() => navigate(crumb.path)}
                title={crumb.path}
              >
                {crumb.name}
              </button>
            </span>
          ))}
        </div>

        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={() => data?.parent && navigate(data.parent)}
            disabled={!data?.parent}
            title="Dossier parent"
          >
            <ArrowUp className="h-4 w-4" />
          </Button>
          <Input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") navigate(input.trim());
            }}
            className="font-mono text-xs"
            aria-label="Chemin"
          />
          <Button type="button" variant="secondary" onClick={() => navigate(input.trim())}>
            Ouvrir
          </Button>
        </div>

        {browse.isError && (
          <Alert variant="destructive">
            <AlertDescription>{(browse.error as Error).message}</AlertDescription>
          </Alert>
        )}

        <ScrollArea className="h-[44vh] min-h-[240px] rounded-lg border border-border/60 bg-background/40">
          <div className="space-y-0.5 p-2">
            {!path && mountsQuery.isLoading && (
              <p className="p-4 text-center text-sm text-muted-foreground">Chargement des racines…</p>
            )}
            {!path && mountsQuery.isSuccess && (
              <p className="p-4 text-center text-sm text-muted-foreground">
                Aucune racine autorisée accessible. Montez un dossier média puis rechargez.
              </p>
            )}
            {browse.isLoading && (
              <p className="p-4 text-center text-sm text-muted-foreground">Chargement…</p>
            )}
            {!browse.isLoading && data?.directories.length === 0 && (
              <p className="p-4 text-center text-sm text-muted-foreground">Aucun sous-dossier.</p>
            )}
            {data?.directories.map((entry) => (
              <BrowseRow
                key={entry.path}
                entry={entry}
                onOpen={() => navigate(entry.path)}
                onMarkSeries={
                  mode === "series" && onMarkSeries
                    ? () => {
                        onMarkSeries(entry.path);
                      }
                    : undefined
                }
              />
            ))}
            {data?.errors.map((error) => (
              <p key={error} className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-red-200">
                {error}
              </p>
            ))}
          </div>
        </ScrollArea>

        <DialogFooter className="items-center sm:justify-between">
          <p className="min-w-0 flex-1 truncate font-mono text-[11px] text-muted-foreground">
            {data?.path}
          </p>
          <div className="flex gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Annuler
            </Button>
            {mode === "series" && onMarkSeries && (
              <Button type="button" variant="outline" onClick={markSeries} disabled={!data}>
                <Tv className="h-4 w-4" />
                Marquer comme séries
              </Button>
            )}
            <Button type="button" onClick={choose} disabled={!data}>
              Choisir ce dossier
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function BrowseRow({
  entry,
  onOpen,
  onMarkSeries,
}: {
  entry: BrowseEntry;
  onOpen: () => void;
  onMarkSeries?: () => void;
}) {
  const locked = !entry.readable;
  return (
    <div
      className={cn(
        "group flex items-center gap-3 rounded-md border border-transparent px-2 py-2 text-sm transition-colors",
        locked ? "opacity-60" : "cursor-pointer hover:border-border/60 hover:bg-secondary/50",
      )}
      onClick={() => !locked && onOpen()}
    >
      <Folder className={cn("h-4 w-4 shrink-0", locked ? "text-muted-foreground" : "text-primary/80")} />
      <span className="min-w-0 flex-1 truncate">{entry.name}</span>
      {entry.is_symlink && (
        <span title="Lien symbolique">
          <Link2 className="h-3 w-3 text-muted-foreground" />
        </span>
      )}
      {!entry.readable && (
        <span title="Non lisible">
          <Lock className="h-3 w-3 text-destructive" />
        </span>
      )}
      <span className="hidden text-[10px] font-mono text-muted-foreground sm:inline">
        {entry.readable ? "lecture" : "non lisible"}
        {entry.writable ? " · écriture" : ""}
      </span>
      {onMarkSeries && (
        <button
          type="button"
          className="rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-secondary hover:text-primary group-hover:opacity-100"
          onClick={(event) => {
            event.stopPropagation();
            onMarkSeries();
          }}
          title="Marquer comme dossier de séries"
        >
          <Tv className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}
