import { Link, Route, Routes } from "react-router-dom";
import { Compass, FolderSearch } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { WorkspacePage } from "@/pages/workspace-page";
import { HistoryPage } from "@/pages/history-page";
import { HardwarePage } from "@/pages/hardware-page";
import { SystemPage } from "@/pages/system-page";
import { ToastProvider } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { PageContainer } from "@/components/page";

function NotFound() {
  return (
    <PageContainer>
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <div className="mb-4 grid h-14 w-14 place-items-center rounded-2xl border border-border bg-card text-primary">
          <Compass className="h-7 w-7" />
        </div>
        <h1 className="text-2xl font-bold">Page introuvable</h1>
        <p className="mt-2 max-w-md text-sm text-muted-foreground">
          Cette adresse ne correspond à aucune vue de Presse-Agrumes.
        </p>
        <Button asChild className="mt-6">
          <Link to="/">
            <FolderSearch className="h-4 w-4" /> Retour à la compression
          </Link>
        </Button>
      </div>
    </PageContainer>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <TooltipProvider delayDuration={200}>
        <AppShell>
          <Routes>
            <Route path="/" element={<WorkspacePage />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/hardware" element={<HardwarePage />} />
            <Route path="/system" element={<SystemPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </AppShell>
      </TooltipProvider>
    </ToastProvider>
  );
}
