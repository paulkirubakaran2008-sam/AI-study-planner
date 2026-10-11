import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Flame, Hourglass, Sparkles, Target, Timer } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PriorityBadge, useTaskActions } from "../components/tasks";
import { Banner, Bar, Empty, ErrorNote, PageHeader, Ring, Skeleton, useToast } from "../components/ui";
import { post } from "../lib/api";
import { useDashboard } from "../lib/hooks";
import type { Dashboard as D } from "../lib/types";
import { clsx, fmtDay, fmtLong, masteryTone, mins, time12 } from "../lib/util";

function Countdown({ seconds }: { seconds: number }) {
  const [t0] = useState(Date.now()); const [, f] = useState(0);
  useEffect(() => { const i = setInterval(() => f((n) => n + 1), 1000); return () => clearInterval(i); }, []);
  const left = Math.max(0, seconds - Math.floor((Date.now() - t0) / 1000));
  const d = Math.floor(left / 86400), h = Math.floor((left % 86400) / 3600), m = Math.floor((left % 3600) / 60);
  return <div className="flex gap-4">{[[d, "Days"], [h, "Hours"], [m, "Minutes"]].map(([v, l]) => <div key={l as string}><p className="font-display text-4xl font-semibold tnum leading-none">{v}</p><p className="mt-1 text-xs text-muted">{l}</p></div>)}</div>;
}

function Stat({ icon, label, value, sub, tone }: { icon: React.ReactNode; label: string; value: React.ReactNode; sub?: string; tone?: string }) {
  return <div className="card min-w-0 p-3 sm:p-4"><div className={clsx("mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold text-muted sm:mb-2 sm:gap-2 sm:text-xs", tone)}><span className="hidden sm:inline">{icon}</span><span className="truncate">{label}</span></div><p className="font-display text-xl font-semibold tnum sm:text-3xl">{value}</p>{sub && <p className="mt-0.5 truncate text-[11px] text-muted sm:text-xs">{sub}</p>}</div>;
}

export default function Dashboard() {
  const { data, error, isLoading, refetch } = useDashboard();
  const a = useTaskActions();
  const toast = useToast(); const qc = useQueryClient();
  const apply = useMutation({ mutationFn: (id: number) => post<{ results: { message: string }[] }>(`/api/recommendations/${id}/apply`), onSuccess: (r) => { toast(r.results[0]?.message || "Applied."); qc.invalidateQueries(); }, onError: (e) => toast((e as Error).message, "err") });

  if (error) return <ErrorNote error={error} retry={() => refetch()} />;
  if (isLoading || !data) return <div className="space-y-4"><Skeleton className="h-10 w-72" /><div className="grid gap-4 sm:grid-cols-3"><Skeleton className="h-28" /><Skeleton className="h-28" /><Skeleton className="h-28" /></div><Skeleton className="h-72" /></div>;
  const d: D = data; const s = d.stats;
  const hasPlan = d.today_tasks.length > 0;

  return (
    <div className="space-y-6">
      <PageHeader title={`${d.greeting}, ${d.name} 👋`} sub={hasPlan ? "Your study plan is ready." : "Nothing left on today's plan."} actions={<Link to="/planner" className="btn-ghost">Open planner<ArrowRight className="h-4 w-4" /></Link>} />

      {d.sync.missed > 0 && (
        <Banner tone="warn">
          <b>I rebuilt your plan around {d.sync.missed} missed session{d.sync.missed > 1 ? "s" : ""}.</b>{" "}
          {d.sync.moved.slice(0, 2).map((m) => `${m.topic} → ${fmtDay(m.to_date)} ${time12(m.to_time)}`).join(" · ")}
        </Banner>
      )}
      {d.warnings.length > 0 && <Banner tone="warn" action={<Link to="/recommendations" className="font-semibold underline">Rebalance</Link>}>⚠️ {fmtDay(d.warnings[0].date, { weekday: "long" })}'s plan has {(d.warnings[0].planned_minutes / 60).toFixed(1)}h. Recommended maximum: {(d.warnings[0].recommended_max / 60).toFixed(1)}h.</Banner>}

      <div className="grid grid-cols-3 gap-2 sm:gap-4">
        <Stat icon={<Timer className="h-3.5 w-3.5" />} label="Study today" value={mins(s.study_minutes_today)} sub={s.planned_minutes_today ? `of ${mins(s.planned_minutes_today)} planned` : "nothing planned"} />
        <Stat icon={<Target className="h-3.5 w-3.5" />} label="Completion" value={`${s.completion_rate_week}%`} sub={`${d.score.score}/100 study score`} />
        <Stat icon={<Flame className="h-3.5 w-3.5 text-amber" />} label="Streak" value={<>🔥 {d.streak.current} day{d.streak.current === 1 ? "" : "s"}</>} sub={`Best ${d.streak.longest} · ${d.streak.total_hours}h total`} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <section className="card min-w-0 p-4 sm:p-5">
          <div className="mb-4 flex items-center justify-between"><h2 className="text-xl font-semibold">Today's plan</h2><span className="text-sm text-muted">{fmtLong(d.today)}</span></div>
          {!hasPlan ? <Empty title="No sessions today" text={d.priority_task ? `Next up: ${d.priority_task.title} on ${fmtDay(d.priority_task.date)} at ${time12(d.priority_task.start_time)}.` : "Add subjects and exam dates to get a plan."} /> : (
            <ul className="divide-y divide-line">
              {d.today_tasks.map((t) => (
                <li key={t.id} className="flex items-center gap-3 py-3">
                  <span className="w-[3.2rem] shrink-0 text-xs tnum text-muted sm:w-[4.6rem] sm:text-sm">{t.start_time}<br />{t.end_time}</span>
                  <i className="h-10 w-1 shrink-0 rounded-full" style={{ background: t.subject_color }} />
                  <div className="min-w-0 flex-1"><p className={clsx("truncate font-semibold", t.status === "completed" && "line-through opacity-60")}>{t.subject_name}</p><p className="truncate text-sm text-muted">{t.title}{t.task_type === "revision" ? " · revision" : ""}</p></div>
                  <span className="hidden sm:inline-flex"><PriorityBadge p={t.priority} /></span>
                  {(t.status === "pending" || t.status === "in_progress") ? <button className="btn-primary !py-1.5" onClick={() => a.startFocus(t)}>Start</button> : <span className="chip">{t.status === "completed" ? "Done ✓" : t.status}</span>}
                </li>
              ))}
            </ul>
          )}
          <div className="mt-4 flex items-center gap-4 rounded-lg bg-sunken p-3">
            <Ring value={s.completion_today} size={64} stroke={7} />
            <div className="text-sm"><p className="font-semibold">Progress today</p><p className="text-muted">{s.tasks_done_today} of {s.tasks_today} done · {s.remaining_today} remaining · {s.remaining_total} upcoming overall</p></div>
          </div>
        </section>

        <div className="min-w-0 space-y-6">
          {d.next_exam ? (
            <section className="card p-5">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">Next exam</p>
              <p className="mt-1 flex items-center gap-2 font-display text-xl font-semibold"><i className="h-3 w-3 rounded-full" style={{ background: d.next_exam.color }} />{d.next_exam.subject}</p>
              <div className="my-4"><Countdown seconds={d.next_exam.seconds_remaining} /></div>
              <div className="flex items-center gap-2 text-sm"><span className="w-24 text-muted">Preparation</span><Bar value={d.next_exam.preparation} /><b className="tnum">{d.next_exam.preparation}%</b></div>
              <p className="mt-3 rounded-lg bg-soft px-3 py-2 text-sm"><b>Recommended:</b> {d.next_exam.recommended}</p>
            </section>
          ) : <Empty icon={<Hourglass />} title="No upcoming exams" text="Add an exam date on the Subjects page to see a countdown." />}

          {d.priority_task && (
            <section className="card p-5" style={{ borderTop: `3px solid rgb(var(--${d.priority_task.priority === "critical" ? "crit" : d.priority_task.priority === "high" ? "high" : d.priority_task.priority === "medium" ? "med" : "low"}))` }}>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">Priority task</p>
              <p className="mt-1 font-display text-xl font-semibold">{d.priority_task.title}</p>
              <p className="text-sm text-muted">{d.priority_task.subject_name} · {fmtDay(d.priority_task.date)} {time12(d.priority_task.start_time)} · {mins(d.priority_task.duration_minutes)}</p>
              <p className="mt-2 text-xs text-muted">Why: {d.priority_task.reason}</p>
              <div className="mt-3 flex items-center gap-2"><PriorityBadge p={d.priority_task.priority} />{["pending", "in_progress"].includes(d.priority_task.status) && d.priority_task.date === d.today && <button className="btn-primary !py-1.5" onClick={() => a.startFocus(d.priority_task!)}>Start now</button>}</div>
            </section>
          )}

          {d.recommendation && (
            <section className="card border-primary/30 bg-soft/50 p-5">
              <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-primary"><Sparkles className="h-3.5 w-3.5" />Recommendation</p>
              <p className="mt-1 font-display text-lg font-semibold">{d.recommendation.title}</p>
              <p className="mt-1 text-sm">{d.recommendation.body}</p>
              <p className="mt-2 text-xs text-muted"><b>Why:</b> {d.recommendation.reason}</p>
              <div className="mt-3 flex gap-2">{d.recommendation.action && <button className="btn-primary !py-1.5" disabled={apply.isPending} onClick={() => apply.mutate(d.recommendation!.id)}>Apply</button>}<Link to="/recommendations" className="btn-ghost !py-1.5">All recommendations</Link></div>
            </section>
          )}
        </div>
      </div>

      {d.exams.length > 0 && (
        <section className="card p-5">
          <h2 className="mb-3 text-xl font-semibold">Exam readiness</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {d.exams.map((e) => (<div key={e.subject}><div className="mb-1 flex items-center justify-between text-sm"><span className="flex items-center gap-2 font-semibold"><i className="h-2.5 w-2.5 rounded-full" style={{ background: e.color }} />{e.subject}</span><span className="text-muted">{e.days_left}d</span></div><Bar value={e.preparation} tone={masteryTone(e.preparation)} /><div className="mt-1 text-xs text-muted tnum">{e.preparation}% prepared · {fmtDay(e.date)}</div></div>))}
          </div>
        </section>
      )}
      {a.modals}
    </div>
  );
}
