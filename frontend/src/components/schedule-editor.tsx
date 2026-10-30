import { CalendarClock, Plus, Trash2 } from "lucide-react";
import type { CompressionSchedule, ScheduleWindow } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const DAYS = [
  { value: 0, label: "Lun" },
  { value: 1, label: "Mar" },
  { value: 2, label: "Mer" },
  { value: 3, label: "Jeu" },
  { value: 4, label: "Ven" },
  { value: 5, label: "Sam" },
  { value: 6, label: "Dim" },
];

export const DEFAULT_SCHEDULE: CompressionSchedule = {
  enabled: false,
  windows: [{ days: [0, 1, 2, 3, 4, 5, 6], start: "22:00", end: "07:00" }],
};

interface ScheduleEditorProps {
  schedule: CompressionSchedule;
  onChange: (schedule: CompressionSchedule) => void;
  timezone?: string;
}

export function ScheduleEditor({ schedule, onChange, timezone }: ScheduleEditorProps) {
  const updateWindow = (index: number, patch: Partial<ScheduleWindow>) => {
    const windows = schedule.windows.map((window, current) =>
      current === index ? { ...window, ...patch } : window,
    );
    onChange({ ...schedule, windows });
  };

  const toggleDay = (index: number, day: number) => {
    const window = schedule.windows[index];
    const days = window.days.includes(day)
      ? window.days.filter((value) => value !== day)
      : [...window.days, day].sort((a, b) => a - b);
    updateWindow(index, { days });
  };

  const addWindow = () => {
    const windows = [
      ...schedule.windows,
      { days: [0, 1, 2, 3, 4], start: "22:00", end: "07:00" },
    ];
    onChange({ ...schedule, windows });
  };

  const removeWindow = (index: number) => {
    const windows = schedule.windows.filter((_, current) => current !== index);
    onChange({ ...schedule, windows: windows.length ? windows : [DEFAULT_SCHEDULE.windows[0]] });
  };

  return (
    <section className="space-y-3">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <CalendarClock className="h-4 w-4 text-primary" /> Planification
      </h3>
      <div className="rounded-lg border border-border/60 bg-secondary/20 p-4">
        <label className="flex cursor-pointer items-start gap-3">
          <Checkbox
            checked={schedule.enabled}
            onCheckedChange={(checked) => {
              const enabled = checked === true;
              onChange({
                ...schedule,
                enabled,
                windows:
                  enabled && schedule.windows.length === 0
                    ? [{ days: [0, 1, 2, 3, 4, 5, 6], start: "22:00", end: "07:00" }]
                    : schedule.windows,
              });
            }}
            className="mt-0.5"
          />
          <span>
            <span className="block text-sm font-medium">Compresser uniquement sur des plages horaires</span>
            <span className="mt-0.5 block text-[11px] leading-relaxed text-muted-foreground">
              Hors plage, le job est mis en pause (les processus ffmpeg sont suspendus) puis
              reprend automatiquement. Les heures sont celles du serveur
              {timezone ? ` (${timezone})` : ""}.
            </span>
          </span>
        </label>

        {schedule.enabled && (
          <div className="mt-4 space-y-3">
            {schedule.windows.map((window, index) => (
              <div
                key={index}
                className="space-y-2 rounded-lg border border-border/60 bg-background/40 p-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap gap-1">
                    {DAYS.map((day) => {
                      const active = window.days.includes(day.value);
                      return (
                        <button
                          key={day.value}
                          type="button"
                          onClick={() => toggleDay(index, day.value)}
                          className={cn(
                            "rounded-md border px-2 py-1 text-[10px] font-medium transition-colors",
                            active
                              ? "border-primary/50 bg-primary/15 text-primary"
                              : "border-border/60 bg-secondary/30 text-muted-foreground hover:text-foreground",
                          )}
                          aria-pressed={active}
                        >
                          {day.label}
                        </button>
                      );
                    })}
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-muted-foreground hover:text-destructive"
                    onClick={() => removeWindow(index)}
                    title="Supprimer cette plage"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
                <div className="flex flex-wrap items-end gap-3">
                  <div className="space-y-1">
                    <Label className="text-[10px] text-muted-foreground">Début</Label>
                    <Input
                      type="time"
                      value={window.start}
                      onChange={(event) => updateWindow(index, { start: event.target.value })}
                      className="h-8 w-[110px] font-mono text-xs"
                    />
                  </div>
                  <span className="pb-2 text-xs text-muted-foreground">→</span>
                  <div className="space-y-1">
                    <Label className="text-[10px] text-muted-foreground">Fin</Label>
                    <Input
                      type="time"
                      value={window.end}
                      onChange={(event) => updateWindow(index, { end: event.target.value })}
                      className="h-8 w-[110px] font-mono text-xs"
                    />
                  </div>
                  {window.start > window.end && (
                    <span className="pb-2 text-[10px] text-muted-foreground">
                      traverse minuit
                    </span>
                  )}
                </div>
              </div>
            ))}
            <Button type="button" variant="outline" size="sm" onClick={addWindow}>
              <Plus className="h-3.5 w-3.5" /> Ajouter une plage
            </Button>
            <p className="text-[10px] leading-relaxed text-muted-foreground">
              Exemple : lundi 22:00 → 07:00 couvre lundi soir et mardi matin. Une plage
              « 00:00 → 00:00 » signifie toute la journée.
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
