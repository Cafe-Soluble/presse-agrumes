import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function PageContainer({ className, children }: { className?: string; children: ReactNode }) {
  return <main className={cn("mx-auto max-w-[1440px] px-4 py-8 sm:px-6", className)}>{children}</main>;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && (
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-primary">{eyebrow}</p>
        )}
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1>
        <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-muted-foreground">{description}</p>
      </div>
      {actions}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card/40 px-6 py-14 text-center">
      <div className="mb-4 grid h-12 w-12 place-items-center rounded-xl border border-border bg-secondary/50 text-primary">
        {icon}
      </div>
      <h3 className="text-base font-semibold">{title}</h3>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function StepBadge({ step }: { step: ReactNode }) {
  return (
    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-primary/30 bg-primary/10 text-sm font-bold text-primary">
      {step}
    </span>
  );
}
