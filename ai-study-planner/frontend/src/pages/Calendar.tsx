import { useMutation } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { TaskCard, TaskEditor, useTaskActions } from "../components/tasks";
import { ErrorNote, Modal, PageHeader, Segmented, Skeleton, useToast } from "../components/ui";
import { put } from "../lib/api";
import { useRefreshAll, useTasks } from "../lib/hooks";
import type { Task } from "../lib/types";
import { WEEKDAYS, addDays, clsx, hm, iso, parseISO, startOfWeek, time12, todayISO } from "../lib/util";

type View = "day" | "week" | "month";
const START = 6 * 60, END = 23 * 60, PX = 0.8;          // grid shows 06:00-23:00, 0.8px per minute
const movable = (t: Task) => t.status !== "completed" && t.status !== "skipped";

function Block({ t, onOpen }: { t: Task; onOpen: (t: Task) => void }) {
  const done = t.status === "completed", bad = t.status === "overdue" || t.status === "skipped";
  const drag = (e: DragEvent) => { const r = (e.currentTarget as HTMLElement).getBoundingClientRect(); e.dataTransfer.setData("text/plain", JSON.stringify({ id: t.id, off: (e.clientY - r.top) / PX })); e.dataTransfer.effectAllowed = "move"; };
  return (
    <button draggable={movable(t)} onDragStart={drag} onClick={() => onOpen(t)} title={`${t.title} · ${t.subject_name}`}
      className={clsx("absolute inset-x-0.5 overflow-hidden rounded-md border-l-[3px] px-1.5 py-0.5 text-left text-[11px] leading-tight transition hover:z-10 hover:shadow-md", done && "opacity-55", bad && "opacity-60")}
      style={{ top: (t.start_minute - START) * PX, height: Math.max(t.duration_minutes * PX - 1, 22), background: `${t.subject_color}24`, borderColor: t.subject_color }}>
      <b className={clsx("block truncate", done && "line-through")}>{t.start_time} {t.title}</b>
      {t.duration_minutes >= 30 && <span className="block truncate text-muted">{t.subject_name}{t.moved_from ? " · moved" : ""}{t.status === "overdue" ? " · missed" : ""}</span>}
    </button>
  );
}

function TimeGrid({ days, tasks, onOpen, onMove, onCreate }: { days: string[]; tasks: Task[]; onOpen: (t: Task) => void; onMove: (id: number, date: string, minute: number) => void; onCreate: (date: string, minute: number) => void }) {
  const hours = Array.from({ length: (END - START) / 60 + 1 }, (_, i) => START / 60 + i);
  const today = todayISO(); const now = new Date(); const nowMin = now.getHours() * 60 + now.getMinutes();
  const scroller = useRef<HTMLDivElement>(null);
  const firstStart = tasks.length ? Math.min(...tasks.map((t) => t.start_minute)) : 9 * 60;
  useEffect(() => {   // open the grid at the part of the day that matters: now (if visible this range) or the first session
    const anchor = days.includes(today) ? Math.max(nowMin - 30, START) : firstStart;
    if (scroller.current) scroller.current.scrollTop = Math.max(0, (anchor - START - 60) * PX);
  }, [days.join(","), tasks.length]);   // eslint-disable-line react-hooks/exhaustive-deps
  const drop = (e: DragEvent, date: string) => {
    e.preventDefault();
    try {
      const { id, off } = JSON.parse(e.dataTransfer.getData("text/plain")); const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
      const minute = Math.max(START, Math.min(END - 15, START + Math.round((e.clientY - r.top) / PX - off) / 5 * 5));
      onMove(id, date, Math.round(minute / 5) * 5);
    } catch { /* not one of ours */ }
  };
  return (
    <div className="card overflow-hidden">
      <div className="scroll-thin overflow-x-auto">
        <div style={{ minWidth: days.length > 1 ? 720 : 0 }}>
          <div className="grid border-b border-line bg-surface text-center" style={{ gridTemplateColumns: `3rem repeat(${days.length}, 1fr)` }}>
            <span />{days.map((d) => { const dt = parseISO(d); return <div key={d} className={clsx("py-2 text-xs", d === today && "text-primary")}><span className="font-semibold uppercase tracking-wide">{dt.toLocaleDateString("en-IN", { weekday: "short" })}</span> <span className={clsx("ml-1 inline-grid h-6 min-w-6 place-items-center rounded-full font-display text-sm font-semibold", d === today && "bg-primary text-primary-ink")}>{dt.getDate()}</span></div>; })}
          </div>
          <div ref={scroller} className="scroll-thin relative grid max-h-[68vh] overflow-y-auto" style={{ gridTemplateColumns: `3rem repeat(${days.length}, 1fr)` }}>
            <div>{hours.map((h) => <div key={h} className="pr-1.5 text-right text-[10px] text-muted" style={{ height: 60 * PX }}>{h < 24 ? hm(h * 60) : ""}</div>)}</div>
            {days.map((d) => (
              <div key={d} className="relative border-l border-line" style={{ height: hours.length * 60 * PX }} onDragOver={(e) => e.preventDefault()} onDrop={(e) => drop(e, d)}
                onDoubleClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); onCreate(d, START + Math.round((e.clientY - r.top) / PX / 15) * 15); }}>
                {hours.map((h) => <i key={h} className="absolute inset-x-0 border-t border-line/70" style={{ top: (h * 60 - START) * PX }} />)}
                {d === today && nowMin >= START && nowMin <= END && <i className="absolute inset-x-0 z-10 border-t-2 border-crit" style={{ top: (nowMin - START) * PX }}><b className="absolute -left-1 -top-[5px] h-2 w-2 rounded-full bg-crit" /></i>}
                {tasks.filter((t) => t.date === d).map((t) => <Block key={t.id} t={t} onOpen={onOpen} />)}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function MonthGrid({ anchor, tasks, onOpen, onDay, onMoveDay }: { anchor: Date; tasks: Task[]; onOpen: (t: Task) => void; onDay: (d: string) => void; onMoveDay: (id: number, date: string) => void }) {
  const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1); const gridStart = startOfWeek(first);
  const cells = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i)); const today = todayISO();
  return (
    <div className="card overflow-hidden">
      <div className="grid grid-cols-7 border-b border-line text-center text-[11px] font-semibold uppercase tracking-wide text-muted">{WEEKDAYS.map((w) => <div key={w} className="py-2">{w.slice(0, 3)}</div>)}</div>
      <div className="grid grid-cols-7">
        {cells.map((c) => {
          const d = iso(c), items = tasks.filter((t) => t.date === d), inMonth = c.getMonth() === anchor.getMonth();
          return (
            <div key={d} className={clsx("min-h-[5.2rem] border-b border-r border-line p-1 sm:min-h-[6.5rem]", !inMonth && "bg-sunken/60")} onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { e.preventDefault(); try { onMoveDay(JSON.parse(e.dataTransfer.getData("text/plain")).id, d); } catch { /* ignore */ } }}>
              <button onClick={() => onDay(d)} className={clsx("mb-1 grid h-6 min-w-6 place-items-center rounded-full px-1 text-xs font-semibold", d === today ? "bg-primary text-primary-ink" : inMonth ? "" : "text-muted")}>{c.getDate()}</button>
              <div className="space-y-0.5">
                {items.slice(0, 3).map((t) => (
                  <button key={t.id} draggable={movable(t)} onDragStart={(e) => e.dataTransfer.setData("text/plain", JSON.stringify({ id: t.id, off: 0 }))} onClick={() => onOpen(t)}
                    className={clsx("block w-full truncate rounded px-1 py-0.5 text-left text-[10px] sm:text-[11px]", t.status === "completed" && "line-through opacity-55")} style={{ background: `${t.subject_color}26`, borderLeft: `3px solid ${t.subject_color}` }}>{t.title}</button>
                ))}
                {items.length > 3 && <button className="px-1 text-[10px] font-semibold text-primary" onClick={() => onDay(d)}>+{items.length - 3} more</button>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function CalendarPage() {
  const [view, setView] = useState<View>(() => (window.innerWidth < 640 ? "day" : "week"));
  const [anchor, setAnchor] = useState(() => new Date());
  const [open, setOpen] = useState<Task | null>(null); const [create, setCreate] = useState<{ date: string; start: string } | null>(null);
  const toast = useToast(); const refresh = useRefreshAll(); const a = useTaskActions();

  const { days, rangeStart, rangeEnd, title } = useMemo(() => {
    if (view === "day") return { days: [iso(anchor)], rangeStart: iso(anchor), rangeEnd: iso(anchor), title: anchor.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" }) };
    if (view === "week") { const s = startOfWeek(anchor); const ds = Array.from({ length: 7 }, (_, i) => iso(addDays(s, i))); return { days: ds, rangeStart: ds[0], rangeEnd: ds[6], title: `${s.toLocaleDateString("en-IN", { day: "numeric", month: "short" })} – ${addDays(s, 6).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}` }; }
    const gs = startOfWeek(new Date(anchor.getFullYear(), anchor.getMonth(), 1)); return { days: [], rangeStart: iso(gs), rangeEnd: iso(addDays(gs, 41)), title: anchor.toLocaleDateString("en-IN", { month: "long", year: "numeric" }) };
  }, [view, anchor]);
  const { data: tasks, error, isLoading, refetch } = useTasks(rangeStart, rangeEnd);

  const move = useMutation({ mutationFn: (v: { id: number; date: string; start_time?: string }) => put(`/api/tasks/${v.id}`, { date: v.date, ...(v.start_time ? { start_time: v.start_time } : {}) }), onSuccess: () => { toast("Session moved and pinned."); refresh(); }, onError: (e) => toast((e as Error).message, "err") });
  const step = (n: number) => setAnchor((d) => view === "month" ? new Date(d.getFullYear(), d.getMonth() + n, 1) : addDays(d, n * (view === "week" ? 7 : 1)));
  const list = tasks ?? [];

  return (
    <div>
      <PageHeader title="Calendar" sub={title} actions={<>
        <Segmented<View> value={view} onChange={setView} options={[{ value: "day", label: "Day" }, { value: "week", label: "Week" }, { value: "month", label: "Month" }]} />
        <div className="flex items-center rounded-lg border border-line bg-surface"><button className="btn-quiet !rounded-r-none !p-2" aria-label="Previous" onClick={() => step(-1)}><ChevronLeft className="h-4 w-4" /></button><button className="px-2 text-sm font-semibold" onClick={() => setAnchor(new Date())}>Today</button><button className="btn-quiet !rounded-l-none !p-2" aria-label="Next" onClick={() => step(1)}><ChevronRight className="h-4 w-4" /></button></div>
        <button className="btn-primary" onClick={() => setCreate({ date: iso(anchor), start: "18:00" })}><Plus className="h-4 w-4" />Add</button></>} />
      {error ? <ErrorNote error={error} retry={() => refetch()} /> : isLoading ? <Skeleton className="h-[28rem]" /> : view === "month" ?
        <MonthGrid anchor={anchor} tasks={list} onOpen={setOpen} onDay={(d) => { setAnchor(parseISO(d)); setView("day"); }} onMoveDay={(id, date) => move.mutate({ id, date })} /> :
        <TimeGrid days={days} tasks={list} onOpen={setOpen} onMove={(id, date, m) => move.mutate({ id, date, start_time: hm(m) })} onCreate={(date, m) => setCreate({ date, start: hm(m) })} />}
      <p className="mt-3 text-xs text-muted">Drag a session to reschedule it (it becomes pinned, so automatic replans leave it alone). Double-click an empty slot to add one. On touch screens tap a session to edit its date and time.</p>
      <Modal open={!!open} onClose={() => setOpen(null)} title="Session"><div onClick={(e) => { if ((e.target as HTMLElement).closest("button")) setTimeout(() => setOpen(null), 150); }}>{open && <TaskCard t={open} a={a} />}</div></Modal>
      {create && <TaskEditor task={null} defaults={create} onClose={() => setCreate(null)} onChanged={refresh} />}
      {a.modals}
    </div>
  );
}
