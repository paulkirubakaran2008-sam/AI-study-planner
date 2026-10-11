import { ListChecks, Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { TaskCard, useTaskActions } from "../components/tasks";
import { Empty, ErrorNote, PageHeader, Segmented, Skeleton } from "../components/ui";
import { useSubjects, useTasks } from "../lib/hooks";
import { addDays, fmtLong, iso, todayISO } from "../lib/util";

type Tab = "today" | "upcoming" | "overdue" | "completed" | "skipped" | "all";
export default function Tasks() {
  const today = todayISO();
  const { data, error, isLoading, refetch } = useTasks(iso(addDays(new Date(), -30)), iso(addDays(new Date(), 90)));
  const { data: subjects } = useSubjects();
  const a = useTaskActions();
  const [tab, setTab] = useState<Tab>("today"); const [subject, setSubject] = useState(0); const [q, setQ] = useState("");

  const counts = useMemo(() => { const t = data ?? []; return { today: t.filter((x) => x.date === today).length, upcoming: t.filter((x) => x.date > today && ["pending", "in_progress"].includes(x.status)).length, overdue: t.filter((x) => x.status === "overdue").length, completed: t.filter((x) => x.status === "completed").length, skipped: t.filter((x) => x.status === "skipped").length, all: t.length }; }, [data, today]);
  const rows = useMemo(() => (data ?? []).filter((t) => {
    if (subject && t.subject_id !== subject) return false;
    if (q && !`${t.title} ${t.subject_name} ${t.notes}`.toLowerCase().includes(q.toLowerCase())) return false;
    switch (tab) { case "today": return t.date === today; case "upcoming": return t.date > today && ["pending", "in_progress"].includes(t.status); case "overdue": return t.status === "overdue"; case "completed": return t.status === "completed"; case "skipped": return t.status === "skipped"; default: return true; }
  }).sort((x, y) => (tab === "completed" ? y.date.localeCompare(x.date) : x.date.localeCompare(y.date)) || x.start_minute - y.start_minute), [data, tab, subject, q, today]);
  const groups = useMemo(() => { const m = new Map<string, typeof rows>(); rows.forEach((r) => m.set(r.date, [...(m.get(r.date) ?? []), r])); return [...m.entries()]; }, [rows]);

  return (
    <div>
      <PageHeader title="Tasks" sub="Every study session with its status, priority and notes." actions={<button className="btn-primary" onClick={() => a.edit("new")}><Plus className="h-4 w-4" />Add task</button>} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="scroll-thin max-w-full overflow-x-auto"><Segmented<Tab> value={tab} onChange={setTab} options={(["today", "upcoming", "overdue", "completed", "skipped", "all"] as Tab[]).map((v) => ({ value: v, label: `${v[0].toUpperCase()}${v.slice(1)} ${counts[v] || ""}`.trim() }))} /></div>
        <select className="input !w-auto" aria-label="Filter by subject" value={subject} onChange={(e) => setSubject(Number(e.target.value))}><option value={0}>All subjects</option>{subjects?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
        <div className="relative min-w-[10rem] flex-1 sm:max-w-xs"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted" /><input className="input !pl-9" placeholder="Search tasks" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search tasks" /></div>
      </div>
      {error ? <ErrorNote error={error} retry={() => refetch()} /> : isLoading ? <div className="space-y-3"><Skeleton className="h-32" /><Skeleton className="h-32" /></div> :
        !groups.length ? <Empty icon={<ListChecks className="h-8 w-8" />} title={tab === "overdue" ? "Nothing overdue 🎉" : "No tasks here"} text="Tasks appear when you generate a plan or add your own." action={<button className="btn-ghost" onClick={() => a.edit("new")}>Add a task</button>} /> :
          <div className="space-y-6">{groups.map(([d, items]) => <section key={d}><h2 className="mb-2 text-sm font-bold text-muted">{d === today ? "Today · " : ""}{fmtLong(d)}</h2><div className="space-y-3">{items.map((t) => <TaskCard key={t.id} t={t} a={a} compact />)}</div></section>)}</div>}
      {a.modals}
    </div>
  );
}
