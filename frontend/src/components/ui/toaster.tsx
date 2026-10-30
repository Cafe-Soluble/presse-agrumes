import * as React from "react";
import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type ToastVariant = "default" | "success" | "error" | "warning";

interface ToastItem {
  id: string;
  title: string;
  description?: string;
  variant: ToastVariant;
}

interface ToastContextValue {
  toast: (input: { title: string; description?: string; variant?: ToastVariant }) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const icons = {
  default: Info,
  success: CheckCircle2,
  error: XCircle,
  warning: AlertTriangle,
};

const styles: Record<ToastVariant, string> = {
  default: "border-border bg-card text-card-foreground",
  success: "border-success/35 bg-card text-card-foreground",
  error: "border-destructive/40 bg-card text-card-foreground",
  warning: "border-warning/35 bg-card text-card-foreground",
};

const iconStyles: Record<ToastVariant, string> = {
  default: "text-sky-300",
  success: "text-success",
  error: "text-destructive",
  warning: "text-warning",
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const remove = useCallback((id: string) => {
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const toast = useCallback<ToastContextValue["toast"]>(
    ({ title, description, variant = "default" }) => {
      const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      setItems((current) => [...current.slice(-4), { id, title, description, variant }]);
      window.setTimeout(() => remove(id), 6200);
    },
    [remove],
  );

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[min(92vw,420px)] flex-col gap-2">
        {items.map((item) => {
          const Icon = icons[item.variant];
          return (
            <div
              key={item.id}
              className={cn(
                "animate-in-up pointer-events-auto flex items-start gap-3 rounded-xl border p-4 shadow-2xl backdrop-blur",
                styles[item.variant],
              )}
              role="status"
            >
              <Icon className={cn("mt-0.5 h-5 w-5 shrink-0", iconStyles[item.variant])} />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold">{item.title}</p>
                {item.description && (
                  <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{item.description}</p>
                )}
              </div>
              <button
                type="button"
                className="rounded p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                onClick={() => remove(item.id)}
                aria-label="Fermer la notification"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast doit être utilisé dans ToastProvider");
  return context;
}
