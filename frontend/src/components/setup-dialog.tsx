import { useEffect, useMemo, useState } from "react";
import { Container, FolderOpen, HardDrive, Loader2, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import type { SetupState } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Alert, AlertDescription } from "@/components/ui/alert";
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
import { BrowseDialog } from "@/components/browse-dialog";

interface SetupDialogProps {
  open: boolean;
  state?: SetupState;
  initialPath?: string;
  onComplete: (path: string, writable: boolean) => void;
  onSkip: () => void;
}

export function SetupDialog({ open, state, initialPath, onComplete, onSkip }: SetupDialogProps) {
  const [path, setPath] = useState(initialPath ?? "");
  const [browseOpen, setBrowseOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const allRoots = useMemo(() => state?.roots ?? [], [state?.roots]);
  const nonEmptyRoots = useMemo(
    () => allRoots.filter((root) => !root.empty),
    [allRoots],
  );
  // Ne propose que les racines qui contiennent réellement quelque chose.
  // Si tout est vide, on affiche quand même les racines pour expliquer.
  const roots = useMemo(() => {
    const list = [...(nonEmptyRoots.length > 0 ? nonEmptyRoots : allRoots)];
    return list.sort((a, b) => a.path.localeCompare(b.path));
  }, [allRoots, nonEmptyRoots]);

  const noMedia = allRoots.length === 0 || nonEmptyRoots.length === 0;

  useEffect(() => {
    if (!open) return;
    const fallback = roots.find((root) => !root.empty)?.path ?? roots[0]?.path ?? "";
    setPath(state?.media_root || initialPath || fallback);
    setError(null);
  }, [open, state?.media_root, initialPath, roots]);

  const save = async () => {
    const value = path.trim();
    if (!value) return;
    setSaving(true);
    setError(null);
    try {
      const result = await api.saveSetup(value);
      onComplete(result.media_root, result.writable);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (!next) onSkip();
        }}
      >
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-primary" />
              Bienvenue dans Presse-Agrumes
            </DialogTitle>
            <DialogDescription>
              Choisissez le dossier qui contient vos vidéos. Il sera mémorisé sur le serveur et
              prérempli à chaque visite. Vous pourrez le changer plus tard à l'étape 1.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {roots.length > 0 && (
              <div className="grid gap-2 sm:grid-cols-2">
                {roots.map((root) => (
                  <button
                    key={root.path}
                    type="button"
                    disabled={!root.readable}
                    onClick={() => setPath(root.path)}
                    className={cn(
                      "flex min-w-0 items-center gap-3 rounded-lg border border-border/60 bg-secondary/20 px-3 py-2.5 text-left transition-colors",
                      "hover:border-primary/40 hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-40",
                      path === root.path && "border-primary/50 bg-primary/10",
                    )}
                    title={root.path}
                  >
                    <HardDrive className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-mono text-xs">{root.path}</span>
                      <span className="block text-[11px] text-muted-foreground">
                        {root.empty ? "vide ou non monté" : root.writable ? "accessible" : "lecture seule"}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            )}

            <div className="flex flex-col gap-2 sm:flex-row">
              <div className="relative min-w-0 flex-1">
                <FolderOpen className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={path}
                  onChange={(event) => setPath(event.target.value)}
                  placeholder="/media/Films"
                  className="pl-9 font-mono text-sm"
                  spellCheck={false}
                  aria-label="Dossier média"
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !saving) void save();
                  }}
                />
              </div>
              <Button type="button" variant="outline" onClick={() => setBrowseOpen(true)}>
                Parcourir
              </Button>
            </div>

            {noMedia && (
              <Alert>
                <Container className="h-4 w-4" />
                <AlertDescription className="space-y-2">
                  <p>
                    Aucun média n'est visible. En Docker, montez votre dossier dans le conteneur
                    (par exemple <code className="font-mono">-v /mnt/media:/media</code>) puis
                    rechargez cette page.
                  </p>
                  {state?.allowed_roots && state.allowed_roots.length > 0 && (
                    <p className="font-mono text-[11px] text-muted-foreground">
                      Racines autorisées : {state.allowed_roots.join(", ")}
                    </p>
                  )}
                </AlertDescription>
              </Alert>
            )}

            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </div>

          <DialogFooter className="items-center sm:justify-between">
            <Button type="button" variant="ghost" onClick={onSkip} disabled={saving}>
              Plus tard
            </Button>
            <Button type="button" onClick={() => void save()} disabled={saving || !path.trim()}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <FolderOpen className="h-4 w-4" />}
              Utiliser ce dossier
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <BrowseDialog
        open={browseOpen}
        onOpenChange={setBrowseOpen}
        mode="root"
        initialPath={path}
        onSelect={(selected) => {
          setPath(selected);
          setBrowseOpen(false);
        }}
      />
    </>
  );
}
