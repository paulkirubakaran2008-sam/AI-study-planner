import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, ChevronLeft, ChevronRight, Plus, RefreshCcw, Wand2 } from "lucide-react";
import { useState } from "react";
import { TaskCard, useTaskActions } from "../components/tasks";
import { Banner, Bar, Empty, ErrorNote, PageHeader, Skeleton, Spinner, useToast } from "../components/ui";
import { post } from "../lib/api";
import { useOverview, useRefreshAll, useTasks } from "../lib/hooks";
import type { Task } from "../lib/types";
import { PRIORITY, addDays, fmtDay, fmtLong, iso, mins, parseISO, todayISO } from "../lib/util";

const GROUPS: { key: string; title: string; match: (t: Task) => boolean; tone: string }[] = [
  { key: "high", title: "🔥 High priority", match: (t) => t.priority === "critical" || t.priority === "high", tone: "text-crit" },
  { key: "medium", title: "Medium", match: (t) => t.priority === "medium", tone: "text-med" },
  { key: "low", title: "Low", match: (t) => t.priority === "low", tone: "text-low" },
];

export default function Planner() {
  const [day, setDay] = useState(todayISO());
  const { data: tasks, error, isLoading, refetch } = useTasks(day, day);
  const { data: ov } = useOverview();
  const a = useTaskActions(); const toast = useToast(); const refresh = useRefreshAll();
  const rebuild = useMutation({ mutationFn: () => post<{ created: number; planned_minutes: number; warnings: { message: string }[] }>("/api/planner/generate"), onSuccess: (r) => { toast(`Plan rebuilt: ${r.created} sessions, ${mins(r.planned_minutes)} of study.`); refresh(); }, onError: (e) => toast((e as Error).message, "err") });
  const rebalance = useMutation({ mutationFn: (date: string) => post<{ moved: number }>("/api/planner/rebalance", { date }), onSuccess: (r) => { toast(`Moved ${r.moved} session(s) to lighter days.`); refresh(); }, onError: (e) => toast((e as Error).message, "err") });

  const isToday = day === todayISO();
  const total = (tasks ?? []).filter((t) => t.status !== "skipped").reduce((s, t) => s + t.duration_minutes, 0);
  const overload = ov?.overloaded_days.find((o) => o.date === day);

  return (
    <div>
      <PageHeader title={isToday ? "Today" : "Study Planner"} sub={<>{fmtLong(day)} · {tasks ? `${tasks.length} session${tasks.length === 1 ? "" : "s"}, ${mins(total)}` : "…"}</>}
        actions={<><div className="flex items-center rounded-lg border border-line bg-surface"><button className="btn-quiet !rounded-r-none !p-2" aria-label="Previous day" onClick={() => setDay(iso(addDays(parseISO(day), -1)))}><ChevronLeft className="h-4 w-4" /></button>
          <button className="px-2 text-sm font-semibold" onClick={() => setDay(todayISO())} disabled={isToday}>{isToday ? "Today" : "Back to today"}</button>
          <button className="btn-quiet !rounded-l-none !p-2" aria-label="Next day" onClick={() => setDay(iso(addDays(parseISO(day), 1)))}><ChevronRight className="h-4 w-4" /></button></div>
          <button className="btn-primary" onClick={() => a.edit("new")}><Plus className="h-4 w-4" />Add session</button></>} />

      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-6">
          {overload && <Banner tone="warn" action={<button className="btn-ghost !py-1.5" disabled={rebalance.isPending} onClick={() => rebalance.mutate(day)}>Rebalance</button>}>⚠️ This day contains {(overload.planned_minutes / 60).toFixed(1)} hours. Recommended maximum: {(overload.recommended_max / 60).toFixed(1)} hours.</Banner>}
          {error ? <ErrorNote error={error} retry={() => refetch()} /> : isLoading ? <div className="space-y-3"><Skeleton className="h-36" /><Skeleton className="h-36" /></div> :
            !tasks?.length ? <Empty title={isToday ? "Nothing scheduled for today" : "Nothing scheduled this day"} text="Either you're free, or this day is blocked, or all sessions are done. Tell the planner what to do in plain English from “Ask planner”." action={<button className="btn-ghost" onClick={() => a.edit("new")}>Add a session</button>} /> :
              GROUPS.map((g) => { const items = tasks.filter(g.match); if (!items.length) return null; return (
                <section key={g.key}><h2 className={`mb-2 text-sm font-bold uppercase tracking-wide ${g.tone}`}>{g.title}</h2><div className="space-y-3">{items.map((t) => <TaskCard key={t.id} t={t} a={a} />)}</div></section>); })}
        </div>

        <aside className="space-y-4">
          <section className="card p-5">
            <h2 className="text-lg font-semibold">Plan health</h2>
            {!ov ? <Skeleton className="mt-3 h-24" /> : <>
              <p className="mt-1 text-sm text-muted">{mins(ov.pending_minutes)} planned of {mins(ov.capacity_minutes)} available before your last exam.</p>
              <div className="mt-4 space-y-3">{ov.subjects.map((s) => (
                <div key={s.subject_id}><div className="mb-1 flex justify-between text-sm"><span className="flex items-center gap-2 font-medium"><i className="h-2.5 w-2.5 rounded-full" style={{ background: s.color }} />{s.name}</span><span className="text-xs text-muted tnum">{mins(s.planned_minutes)} / {mins(s.needed_minutes)} needed</span></div>
                  <Bar value={s.needed_minutes ? (s.planned_minutes / s.needed_minutes) * 100 : 100} tone={s.planned_minutes >= s.needed_minutes * 0.9 ? "bg-low" : "bg-high"} /></div>))}</div>
              {ov.overloaded_days.length > 0 && <div className="mt-4 rounded-lg bg-high/10 p-3 text-sm"><p className="flex items-center gap-1.5 font-semibold"><AlertTriangle className="h-4 w-4 text-high" />{ov.overloaded_days.length} overloaded day{ov.overloaded_days.length > 1 ? "s" : ""}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">{ov.overloaded_days.slice(0, 4).map((o) => <button key={o.date} className="chip hover:bg-sunken" onClick={() => setDay(o.date)}>{fmtDay(o.date)} · {(o.planned_minutes / 60).toFixed(1)}h</button>)}</div></div>}
              <button className="btn-ghost mt-4 w-full" disabled={rebuild.isPending} onClick={() => rebuild.mutate()}>{rebuild.isPending ? <Spinner /> : <RefreshCcw className="h-4 w-4" />}Rebuild plan from today</button>
              <p className="mt-2 text-xs text-muted">Sessions you've moved or added yourself stay where they are.</p></>}
          </section>
          <section className="card p-5">
            <h2 className="flex items-center gap-2 text-lg font-semibold"><Wand2 className="h-4 w-4 text-primary" />How priority is calculated</h2>
            <p className="mt-2 text-sm text-muted">Every topic is scored 0–1 from five normalised signals, every time the plan is built:</p>
            <ul className="mt-3 space-y-1.5 text-sm">{ov && Object.entries(ov.weights).map(([k, w]) => <li key={k} className="flex items-center gap-2"><span className="w-24 capitalize">{k}</span><Bar value={w * 100 / 0.35 * 100 / 100} h="h-1.5" /><span className="w-9 text-right tnum text-muted">{Math.round(w * 100)}%</span></li>)}</ul>
            <div className="mt-3 flex flex-wrap gap-1.5 text-xs">{(["critical", "high", "medium", "low"] as const).map((p) => <span key={p} className={`rounded-full px-2 py-0.5 font-semibold ${PRIORITY[p].bg} ${PRIORITY[p].text}`}>{PRIORITY[p].icon} {PRIORITY[p].label} {p === "critical" ? "≥ .60" : p === "high" ? "≥ .45" : p === "medium" ? "≥ .30" : "< .30"}</span>)}</div>
          </section>
        </aside>
      </div>
      {a.modals}
    </div>
  );
}
