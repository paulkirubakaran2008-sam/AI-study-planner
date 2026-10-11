import { Award, CheckCircle2, Clock, Flame } from "lucide-react";
import { useState } from "react";
import { Bar, Donut, Empty, ErrorNote, GroupedBars, PageHeader, Ring, Segmented, Skeleton } from "../components/ui";
import { useAnalytics } from "../lib/hooks";
import { clsx, fmtDay, masteryDot, masteryTone, mins, parseISO } from "../lib/util";

const FORMULA = [["Consistency", "30%", "days studied (target 5 of 7) and current streak"], ["Completion", "30%", "completed ÷ sessions that were due"], ["Focus", "20%", "timer coverage and how much of each timed session you finished"], ["Planning", "20%", "realistic days (no overload) and a plan for every available day"]];

export default function Analytics() {
  const [days, setDays] = useState(7);
  const { data: d, error, isLoading, refetch } = useAnalytics(days);
  if (error) return <ErrorNote error={error} retry={() => refetch()} />;
  if (isLoading || !d) return <div className="space-y-4"><Skeleton className="h-10 w-60" /><Skeleton className="h-64" /><Skeleton className="h-64" /></div>;
  const p = d.productivity, sc = d.score;
  const bars = d.series.map((s) => ({ label: days > 14 ? (parseISO(s.date).getDate() % 5 === 0 ? String(parseISO(s.date).getDate()) : "") : parseISO(s.date).toLocaleDateString("en-IN", { weekday: "short" }), planned: s.planned_minutes, actual: s.actual_minutes }));
  const byS = d.topics.reduce<Record<string, typeof d.topics>>((m, t) => ((m[t.subject] ??= []).push(t), m), {});
  const empty = p.actual_minutes === 0 && p.planned_minutes === 0;

  return (
    <div className="space-y-6">
      <PageHeader title="Analytics" sub="Everything here is computed from your sessions and tasks." actions={<Segmented value={days} onChange={setDays} options={[{ value: 7, label: "7 days" }, { value: 14, label: "14 days" }, { value: 30, label: "30 days" }]} />} />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[[<Flame className="h-4 w-4 text-amber" />, "Current streak", `🔥 ${d.streak.current}d`], [<Award className="h-4 w-4 text-primary" />, "Longest streak", `🏆 ${d.streak.longest}d`], [<Clock className="h-4 w-4 text-primary" />, "Total study hours", `📚 ${d.streak.total_hours}h`], [<CheckCircle2 className="h-4 w-4 text-low" />, "Tasks completed", `✅ ${d.streak.tasks_completed}`]].map(([i, l, v], k) => (
          <div key={k} className="card p-4"><p className="flex items-center gap-2 text-xs font-semibold text-muted">{i as React.ReactNode}{l as string}</p><p className="mt-1 font-display text-3xl font-semibold tnum">{v as string}</p></div>))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
        <section className="card p-5">
          <h2 className="text-xl font-semibold">Study score</h2>
          {!sc.has_data ? <p className="mt-3 text-sm text-muted">Complete a session to get your first score.</p> : <>
            <div className="mt-4 flex items-center gap-5"><Ring value={sc.score} size={110} stroke={10} label={<>{sc.score}<span className="text-sm text-muted"> /100</span></>} />
              <div className="flex-1 space-y-2.5">{([["Consistency", sc.consistency], ["Completion", sc.completion], ["Focus", sc.focus], ["Planning", sc.planning]] as const).map(([l, v]) => <div key={l}><div className="flex justify-between text-xs"><span>{l}</span><b className="tnum">{v}</b></div><Bar value={v} h="h-1.5" /></div>)}</div></div></>}
          <details className="mt-4 text-sm"><summary className="cursor-pointer font-semibold text-primary">How is this calculated?</summary>
            <ul className="mt-2 space-y-1 text-muted">{FORMULA.map(([n, w, t]) => <li key={n}><b className="text-ink">{n} ({w})</b>: {t}</li>)}</ul><p className="mt-2 text-xs text-muted">Trailing 7 days. Documented in the backend (analytics_service.py). No randomness.</p></details>
        </section>
        <section className="card p-5">
          <div className="mb-4 flex items-center justify-between"><h2 className="text-xl font-semibold">Study hours</h2><span className="text-sm text-muted">{mins(p.actual_minutes)} studied of {mins(p.planned_minutes)} planned</span></div>
          {empty ? <Empty title="No data yet" text="Your planned and actual study time will chart here." /> : <GroupedBars data={bars} />}
        </section>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card p-5">
          <h2 className="mb-4 text-xl font-semibold">Subject distribution</h2>
          {!d.subject_distribution.length ? <Empty title="Nothing tracked yet" text="Finish a focus session or tick off a task." /> :
            <div className="flex flex-wrap items-center gap-6"><Donut parts={d.subject_distribution.map((s) => ({ value: s.minutes, color: s.color, name: s.name }))} />
              <ul className="min-w-[10rem] flex-1 space-y-2">{d.subject_distribution.map((s) => <li key={s.subject_id} className="flex items-center gap-2 text-sm"><i className="h-3 w-3 rounded-sm" style={{ background: s.color }} /><span className="flex-1 truncate">{s.name}</span><b className="tnum">{s.share}%</b><span className="w-14 text-right text-xs text-muted tnum">{mins(s.minutes)}</span></li>)}</ul></div>}
        </section>
        <section className="card p-5">
          <h2 className="mb-4 text-xl font-semibold">Productivity</h2>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-sm">
            {[["Planned time", mins(p.planned_minutes)], ["Actual time", mins(p.actual_minutes)], ["Completion rate", `${p.completion_rate}%`], ["Focus sessions", String(p.focus_sessions)], ["Missed tasks", String(p.missed_tasks)], ["Avg. confidence", p.avg_confidence ? `${p.avg_confidence} / 5` : "—"]].map(([l, v]) => <div key={l}><dt className="text-xs text-muted">{l}</dt><dd className="font-display text-2xl font-semibold tnum">{v}</dd></div>)}
          </dl>
          <div className="mt-5"><div className="mb-1 flex justify-between text-sm"><span className="font-semibold">Completion rate</span><span className="tnum">{d.completion_rate}%</span></div><Bar value={d.completion_rate} tone="bg-low" h="h-2.5" /></div>
          <p className="mt-3 text-xs text-muted">Time ticked off without the timer is credited at its planned length; timed sessions use real minutes.</p>
        </section>
      </div>

      <section className="card p-5">
        <h2 className="mb-4 text-xl font-semibold">Topic mastery</h2>
        <div className="grid gap-6 sm:grid-cols-2">{Object.entries(byS).map(([subj, ts]) => (
          <div key={subj}><p className="mb-2 flex items-center gap-2 font-display font-semibold"><i className="h-2.5 w-2.5 rounded-full" style={{ background: ts[0].color }} />{subj}</p>
            <ul className="space-y-1.5">{[...ts].sort((a, b) => a.mastery - b.mastery).map((t) => <li key={t.name} className="flex items-center gap-2 text-sm"><span className="w-32 truncate sm:w-40">{t.name}</span><Bar value={t.mastery} tone={masteryTone(t.mastery)} h="h-1.5" /><span className="w-16 text-right text-xs tnum">{t.mastery}% {masteryDot(t.mastery)}</span></li>)}</ul></div>))}</div>
      </section>
    </div>
  );
}
