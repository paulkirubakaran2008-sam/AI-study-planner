import { useQuery, useQueryClient } from "@tanstack/react-query";
import { get } from "./api";
import type { Analytics, AppNotification, Dashboard, Overview, Recommendation, Settings, Subject, Task } from "./types";

export const useDashboard = () => useQuery({ queryKey: ["dashboard"], queryFn: () => get<Dashboard>("/api/dashboard"), staleTime: 15_000 });
export const useSubjects = () => useQuery({ queryKey: ["subjects"], queryFn: () => get<Subject[]>("/api/subjects") });
export const useTasks = (start: string, end: string) => useQuery({ queryKey: ["tasks", start, end], queryFn: () => get<Task[]>(`/api/tasks?start=${start}&end=${end}`), placeholderData: (p) => p });
export const useAnalytics = (days: number) => useQuery({ queryKey: ["analytics", days], queryFn: () => get<Analytics>(`/api/analytics?days=${days}`) });
export const useRecs = () => useQuery({ queryKey: ["recs"], queryFn: () => get<{ items: Recommendation[]; ai: { enabled: boolean; used: number; limit: number } }>("/api/recommendations") });
export const useSettings = () => useQuery({ queryKey: ["settings"], queryFn: () => get<Settings>("/api/settings") });
export const useOverview = () => useQuery({ queryKey: ["overview"], queryFn: () => get<Overview>("/api/planner/overview") });
export const useNotifications = (enabled = true) => useQuery({ queryKey: ["notifications"], enabled, refetchInterval: 60_000, queryFn: () => get<{ items: AppNotification[]; unread: number }>("/api/notifications") });

/** Any change to tasks/subjects/plan can affect every screen, so refresh all cached data. */
export function useRefreshAll() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries();
}
