import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Citrus, Cpu, History, MonitorPlay, Server, TriangleAlert } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

const navigation = [
  { to: "/", label: "Compression", icon: MonitorPlay, end: true },
  { to: "/history", label: "Historique", icon: History, end: false },
  { to: "/hardware", label: "Matériel", icon: Cpu, end: false },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const serverOk = health.data?.status === "ok" && Boolean(health.data?.ffmpeg);

  return (
    <div className="relative min-h-screen">
      <div className="app-glow pointer-events-none fixed inset-x-0 top-0 z-0 h-[60vh]" aria-hidden />
      <header className="sticky top-0 z-40 border-b border-border/70 bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1440px] items-center gap-4 px-4 sm:px-6">
          <NavLink to="/" className="group flex min-w-0 items-center gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-amber-300 to-orange-600 text-orange-950 shadow-[0_8px_24px_hsl(30_100%_55%/0.3)]">
              <Citrus className="h-6 w-6" />
            </span>
            <span className="min-w-0">
              <span className="block truncate text-base font-bold leading-tight tracking-tight">
                Presse-Agrumes
              </span>
              <span className="hidden text-[11px] text-muted-foreground sm:block">
                Compression AV1 pour votre vidéothèque
              </span>
            </span>
          </NavLink>

          <nav className="ml-auto flex items-center gap-1 overflow-x-auto rounded-lg border border-border/60 bg-secondary/40 p-1 no-scrollbar">
            {navigation.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2 whitespace-nowrap rounded-md px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground",
                    isActive && "bg-background text-foreground shadow-sm",
                  )
                }
              >
                <item.icon className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">{item.label}</span>
              </NavLink>
            ))}
          </nav>

          <Badge
            variant={health.isError ? "destructive" : serverOk ? "success" : "warning"}
            className="hidden shrink-0 gap-1.5 md:inline-flex"
            title={health.data?.ffmpeg ?? "Serveur injoignable"}
          >
            {health.isError ? (
              <TriangleAlert className="h-3 w-3" />
            ) : (
              <Server className="h-3 w-3" />
            )}
            {health.isError
              ? "Serveur injoignable"
              : serverOk
                ? "Serveur prêt"
                : "ffmpeg manquant"}
          </Badge>
        </div>
      </header>

      <div className="relative z-10">{children}</div>

      <footer className="relative z-10 mx-auto mt-16 flex max-w-[1440px] flex-col gap-2 border-t border-border/60 px-4 py-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <span>
          Presse-Agrumes v{health.data?.version ?? "0.1.0"} — outil prévu pour un réseau local de confiance.
        </span>
        <span className="flex gap-4">
          <a href="/docs" target="_blank" rel="noreferrer" className="transition-colors hover:text-primary">
            API
          </a>
          <span>AV1 · SVT-AV1 · ffmpeg</span>
        </span>
      </footer>
    </div>
  );
}
