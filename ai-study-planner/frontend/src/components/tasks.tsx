import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clock, Play, RotateCcw, SkipForward, Trash2, Undo2, Pencil } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { del, post, put } from "../lib/api";
import { useFocus } from "../lib/focus";
import { useSubjects } from "../lib/hooks";
import type { Priority, Subject, Task } from "../lib/types";
import { PRIORITY, STATUS_LABEL, clsx, fmtDay, iso, mins, time12 } from "../lib/util";
import { Confirm, Field, Modal, Spinner, useToast } from "./ui";

export function PriorityBadge({ p }: { p: Priority }) {
  const c = PRIORITY[p];
  return <span className={clsx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold", c.bg, c.text)}>{c.icon} {c.label}</span>;
}

export function StatusChip({ s }: { s: Task["status"] }) {
  const tone = { pending: "text-muted", in_progress: "text-primary", completed: "text-low", skipped: "text-muted", overdue: "text-crit" }[s];
  return <span className={clsx("chip", tone)}>{STATUS_LABEL[s]}</span>;
}

const FACES = ["😞", "😐", "🙂", "😃", "🤩"];

export function useTaskActions() {
  const qc = useQueryClient();
  const toast = useToast();
  const nav = useNavigate();
  const focus = useFocus();
  const [completing, setCompleting] = useState<Task | null>(null);
  const [removing, setRemoving] = useState<Task | null>(null);
  const [editing, setEditing] = useState<Task | "new" | null>(null);
  const refresh = () => qc.invalidateQueries();
  const fail = (e: unknown) => toast((e as Error).message, "err");

  const complete = useMutation({
    mutationFn: ({ t, c }: { t: Task; c?: number }) => post<{ next_review: { date: string; start_time: string } | null }>(`/api/tasks/${t.id}/complete`, { confidence: c }),
    onSuccess: (r) => { toast(r.next_review ? `Done! Review scheduled for ${fmtDay(r.next_review.date)} at ${time12(r.next_review.start_time)}.` : "Nice work — task completed."); refresh(); },
    onError: fail,
  });
  const skip = useMutation({
    mutationFn: (t: Task) => post<{ moved: { topic: string; to_date: string; to_time: string }[] }>(`/api/tasks/${t.id}/skip`, { reschedule: true }),
    onSuccess: (r) => { const m = r.moved[0]; toast(m ? `${m.topic} moved to ${fmtDay(m.to_date)} at ${time12(m.to_time)}. Plan recalculated.` : "Skipped. Plan recalculated."); refresh(); },
    onError: fail,
  });
  const remove = useMutation({ mutationFn: (t: Task) => del(`/api/tasks/${t.id}`), onSuccess: () => { toast("Task deleted."); refresh(); }, onError: fail });
  const reopen = useMutation({ mutationFn: (t: Task) => put(`/api/tasks/${t.id}`, { status: "pending" }), onSuccess: refresh, onError: fail });

  const startFocus = (t: Task) => {
    post(`/api/tasks/${t.id}/start`).catch(() => {});
    focus.start({ taskId: t.id, subjectId: t.subject_id, topicId: t.topic_id ?? undefined, label: t.topic_name || t.title, subject: t.subject_name, plannedMin: t.duration_minutes }, { mode: "focus", minutes: t.duration_minutes });
    nav("/focus");
  };

  const modals: ReactNode = (
    <>
      <Modal open={!!completing} onClose={() => setCompleting(null)} title="How did it go?">
        <p className="text-sm text-muted">{completing?.topic_name || completing?.title} · {completing && mins(completing.duration_minutes)}</p>
        <div className="mt-4 grid grid-cols-5 gap-2">
          {FACES.map((f, i) => <button key={i} className="rounded-xl border border-line py-3 text-2xl hover:bg-sunken" onClick={() => { complete.mutate({ t: completing!, c: i + 1 }); setCompleting(null); }}>{f}</button>)}
        </div>
        <div className="mt-4 flex justify-between"><span className="text-xs text-muted">Your rating sets when the next review comes.</span><button className="btn-quiet" onClick={() => { complete.mutate({ t: completing! }); setCompleting(null); }}>Skip rating</button></div>
      </Modal>
      <Confirm open={!!removing} title="Delete this session?" text="It will be removed from your plan. Your other sessions stay as they are." onConfirm={() => remove.mutate(removing!)} onClose={() => setRemoving(null)} />
      {editing && <TaskEditor task={editing === "new" ? null : editing} onClose={() => setEditing(null)} onChanged={refresh} />}
    </>
  );
  return { complete: setCompleting, skip: (t: Task) => skip.mutate(t), remove: setRemoving, reopen: (t: Task) => reopen.mutate(t), startFocus, edit: (t: Task | "new") => setEditing(t), busy: skip.isPending || complete.isPending, modals };
}
export type TaskActions = ReturnType<typeof useTaskActions>;

export function TaskCard({ t, a, compact }: { t: Task; a: TaskActions; compact?: boolean }) {
  const open = t.status === "pending" || t.status === "in_progress" || t.status === "overdue";
  return (
    <div className={clsx("card flex gap-3 p-3.5 sm:p-4", t.status === "completed" && "opacity-70")} style={{ borderLeft: `4px solid ${t.subject_color}` }}>
      <button aria-label={t.status === "completed" ? "Completed" : "Mark complete"} disabled={t.status === "completed" || t.status === "skipped"} onClick={() => a.complete(t)}
        className={clsx("mt-0.5 h-6 w-6 shrink-0 rounded-full border-2 transition", t.status === "completed" ? "border-low bg-low text-white" : "border-line hover:border-primary")}>
        {t.status === "completed" && <CheckCircle2 className="h-5 w-5" />}
      </button>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="tnum text-sm font-semibold">{time12(t.start_time)} – {time12(t.end_time)}</span>
          <PriorityBadge p={t.priority} />
          {t.task_type !== "study" && <span className="chip">{t.task_type === "revision" ? "↻ Revision" : "Practice"}</span>}
          {t.status !== "pending" && <StatusChip s={t.status} />}
        </div>
        <p className={clsx("mt-1 font-display text-lg font-semibold leading-snug", t.status === "completed" && "line-through decoration-1")}>{t.title}</p>
        <p className="text-sm text-muted">{t.subject_name} · <span className="inline-flex items-center gap-1"><Clock className="inline h-3 w-3" />{mins(t.duration_minutes)}</span></p>
        {!compact && t.reason && <p className="mt-1.5 text-xs text-muted">Why now: {t.reason}</p>}
        {t.moved_from && <p className="mt-1.5 inline-flex items-center gap-1 rounded-md bg-amber/15 px-2 py-0.5 text-xs font-medium text-ink"><RotateCcw className="h-3 w-3" />Moved from {fmtDay(t.moved_from)}</p>}
        <div className="mt-3 flex flex-wrap gap-2">
          {open && <button className="btn-primary !py-1.5" onClick={() => a.startFocus(t)}><Play className="h-3.5 w-3.5" />Start</button>}
          {open && <button className="btn-ghost !py-1.5" onClick={() => a.skip(t)}><SkipForward className="h-3.5 w-3.5" />Skip</button>}
          {(t.status === "skipped" || t.status === "overdue") && <button className="btn-ghost !py-1.5" onClick={() => a.reopen(t)}><Undo2 className="h-3.5 w-3.5" />Reopen</button>}
          {t.status !== "completed" && <button className="btn-quiet !py-1.5" onClick={() => a.edit(t)} aria-label="Edit"><Pencil className="h-3.5 w-3.5" /></button>}
          <button className="btn-quiet !py-1.5" onClick={() => a.remove(t)} aria-label="Delete"><Trash2 className="h-3.5 w-3.5" /></button>
        </div>
      </div>
    </div>
  );
}

export function TaskEditor({ task, onClose, onChanged, defaults }: { task: Task | null; onClose: () => void; onChanged: () => void; defaults?: { date?: string; start?: string } }) {
  const { data: subjects } = useSubjects();
  const toast = useToast();
  const [f, setF] = useState({
    subject_id: task?.subject_id ?? 0, topic_id: task?.topic_id ?? (0 as number), title: task?.title ?? "", date: task?.date ?? defaults?.date ?? iso(new Date()),
    start_time: task?.start_time ?? defaults?.start ?? "18:00", duration_minutes: task?.duration_minutes ?? 45, priority: task?.priority ?? ("" as Priority | ""), notes: task?.notes ?? "",
  });
  const subj: Subject | undefined = subjects?.find((s) => s.id === (f.subject_id || subjects[0]?.id));
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((s) => ({ ...s, [k]: v }));
  const save = async () => {
    setBusy(true);
    try {
      if (task) await put(`/api/tasks/${task.id}`, { title: f.title, date: f.date, start_time: f.start_time, duration_minutes: Number(f.duration_minutes), priority: f.priority || undefined, notes: f.notes });
      else await post("/api/tasks", { subject_id: subj!.id, topic_id: f.topic_id || undefined, title: f.title || undefined, date: f.date, start_time: f.start_time, duration_minutes: Number(f.duration_minutes), priority: f.priority || undefined, notes: f.notes });
      toast(task ? "Session updated." : "Session added."); onChanged(); onClose();
    } catch (e) { toast((e as Error).message, "err"); } finally { setBusy(false); }
  };
  return (
    <Modal open onClose={onClose} title={task ? "Edit session" : "Add session"}>
      <div className="space-y-3">
        {!task && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Subject"><select className="input" value={subj?.id ?? ""} onChange={(e) => setF((s) => ({ ...s, subject_id: Number(e.target.value), topic_id: 0 }))}>{subjects?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></Field>
            <Field label="Topic"><select className="input" value={f.topic_id} onChange={(e) => set("topic_id", Number(e.target.value))}><option value={0}>— none —</option>{subj?.topics.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></Field>
          </div>
        )}
        <Field label="Title"><input className="input" value={f.title} maxLength={160} placeholder="e.g. Practice tree traversals" onChange={(e) => set("title", e.target.value)} /></Field>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Date"><input type="date" className="input" value={f.date} onChange={(e) => set("date", e.target.value)} /></Field>
          <Field label="Start"><input type="time" step={300} className="input" value={f.start_time} onChange={(e) => set("start_time", e.target.value)} /></Field>
          <Field label="Minutes"><input type="number" min={5} max={240} step={5} className="input" value={f.duration_minutes} onChange={(e) => set("duration_minutes", Number(e.target.value))} /></Field>
        </div>
        <Field label="Priority"><select className="input" value={f.priority} onChange={(e) => set("priority", e.target.value as Priority)}><option value="">Auto (from your data)</option>{(["critical", "high", "medium", "low"] as Priority[]).map((p) => <option key={p} value={p}>{PRIORITY[p].icon} {PRIORITY[p].label}</option>)}</select></Field>
        <Field label="Notes"><textarea className="input min-h-[70px]" maxLength={500} value={f.notes} onChange={(e) => set("notes", e.target.value)} /></Field>
        {task && <p className="text-xs text-muted">Moving a session pins it: automatic replans will leave it where you put it.</p>}
      </div>
      <div className="mt-5 flex justify-end gap-2"><button className="btn-ghost" onClick={onClose}>Cancel</button><button className="btn-primary" onClick={save} disabled={busy || !subj}>{busy && <Spinner />}Save</button></div>
    </Modal>
  );
}
