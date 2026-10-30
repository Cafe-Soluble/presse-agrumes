import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { JobSnapshot } from "@/lib/types";

const TERMINAL = new Set(["done", "error", "cancelled", "interrupted"]);

export function useConfig() {
  return useQuery({
    queryKey: ["config"],
    queryFn: api.config,
    staleTime: Infinity,
  });
}

export function useHardware() {
  return useQuery({
    queryKey: ["hardware"],
    queryFn: () => api.hardware(),
    staleTime: 60_000,
  });
}

export function useMounts() {
  return useQuery({
    queryKey: ["mounts"],
    queryFn: api.mounts,
    staleTime: 60_000,
  });
}

export function useScans() {
  return useQuery({
    queryKey: ["scans"],
    queryFn: api.listScans,
    select: (data) => data.scans,
  });
}

export function useScan(scanId: string | null) {
  return useQuery({
    queryKey: ["scan", scanId],
    queryFn: () => api.getScan(scanId!),
    enabled: Boolean(scanId),
    staleTime: 30_000,
  });
}

/**
 * Suit une tâche via SSE, avec polling TanStack Query en repli.
 * Les données SSE mettent à jour le cache de la requête correspondante.
 */
export function useJob(jobId: string | null) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.getJob(jobId!),
    enabled: Boolean(jobId),
    staleTime: 0,
    retry: 0,
    refetchInterval: (current) => {
      const data = current.state.data as JobSnapshot | undefined;
      if (!data || TERMINAL.has(data.status)) return false;
      return 1200;
    },
  });

  useEffect(() => {
    if (!jobId) return;
    const source = new EventSource(`/api/jobs/${jobId}/events`);
    source.onmessage = (event) => {
      try {
        const snapshot = JSON.parse(event.data) as JobSnapshot;
        queryClient.setQueryData(["job", jobId], snapshot);
        if (TERMINAL.has(snapshot.status)) source.close();
      } catch {
        // message SSE incomplet : le polling prendra le relais
      }
    };
    source.onerror = () => source.close();
    return () => source.close();
  }, [jobId, queryClient]);

  return query;
}

export function isTerminal(status: string | undefined) {
  return Boolean(status && TERMINAL.has(status));
}
