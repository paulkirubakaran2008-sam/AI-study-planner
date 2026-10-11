import { useMutation } from "@tanstack/react-query";
import { BookOpen, ChevronDown, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Bar, Confirm, Empty, ErrorNote, Field, Modal, PageHeader, Skeleton, Spinner, useToast } from "../components/ui";
import { del, post, put } from "../lib/api";
import { useRefreshAll, useSubjects } from "../lib/hooks";
import type { Subject, Topic } from "../lib/types";
import { clsx, fmtDay, masteryDot, masteryTone } from "../lib/util";

const COLORS = ["#3B5BDB", "#E8590C", "#0CA678", "#AE3EC9", "#F08C00", "#1098AD", "#D6336C", "#5C7CFA"];

function SubjectModal({ subject, onClose }: { subject: Subject | null; onClose: () => void }) {
  const refresh = useRefreshAll(); const toast = useToast();
  const [f, setF] = useState({ name: subject?.name ?? "", color: subject?.color ?? COLORS[Math.floor(Math.random() * COLORS.length)], difficulty: subject?.difficulty ?? 3, importance: subject?.importance ?? 3, target_marks: subject?.target_marks ?? 80, exam_date: subject?.exam_date ?? "" });
  const save = useMutation({
    mutationFn: () => subject ? put(`/api/subjects/${subject.id}`, { ...f, exam_date: f.exam_date || undefined, clear_exam: !f.exam_date && !!subject.exam_date }) : post("/api/subjects", { ...f, exam_date: f.exam_date || undefined, topics: [] }),
    onSuccess: () => { toast(subject ? "Subject updated and plan refreshed." : "Subject added."); refresh(); onClose(); }, onError: (e) => toast((e as Error).message, "err"),
  });
  const set = (k: string, v: unknown) => setF((s) => ({ ...s, [k]: v }));
  return (
    <Modal open onClose={onClose} title={subject ? "Edit subject" : "Add subject"}>
      <div className="space-y-3">
        <Field label="Name"><input className="input" maxLength={80} value={f.name} onChange={(e) => set("name", e.target.value)} autoFocus /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Exam date"><input type="date" className="input" value={f.exam_date} onChange={(e) => set("exam_date", e.target.value)} /></Field>
          <Field label="Target marks (%)"><input type="number" min={40} max={100} className="input" value={f.target_marks} onChange={(e) => set("target_marks", Number(e.target.value))} /></Field>
          <Field label="Difficulty"><select className="input" value={f.difficulty} onChange={(e) => set("difficulty", Number(e.target.value))}>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n} / 5</option>)}</select></Field>
          <Field label="Importance"><select className="input" value={f.importance} onChange={(e) => set("importance", Number(e.target.value))}>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n} / 5</option>)}</select></Field>
        </div>
        <div><span className="label">Colour</span><div className="flex gap-2">{COLORS.map((c) => <button key={c} aria-label={c} onClick={() => set("color", c)} className={clsx("h-7 w-7 rounded-full border-2", f.color === c ? "border-ink" : "border-transparent")} style={{ background: c }} />)}</div></div>
      </div>
      <div className="mt-5 flex justify-end gap-2"><button className="btn-ghost" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={!f.name.trim() || save.isPending} onClick={() => save.mutate()}>{save.isPending && <Spinner />}Save</button></div>
    </Modal>
  );
}

function TopicRow({ t, color }: { t: Topic; color: string }) {
  const refresh = useRefreshAll(); const toast = useToast();
  const [m, setM] = useState(t.mastery);
  const upd = useMutation({ mutationFn: (p: Partial<Topic>) => put(`/api/topics/${t.id}`, p), onSuccess: refresh, onError: (e) => toast((e as Error).message, "err") });
  const rm = useMutation({ mutationFn: () => del(`/api/topics/${t.id}`), onSuccess: () => { toast("Topic removed."); refresh(); } });
  return (
    <li className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 py-2.5 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1.4fr)_auto_auto]">
      <p className="truncate font-medium">{t.name}</p>
      <div className="order-last col-span-2 flex items-center gap-2 sm:order-none sm:col-span-1">
        <input type="range" min={0} max={100} step={5} value={m} className="w-full accent-[rgb(var(--primary))]" aria-label={`${t.name} mastery`} onChange={(e) => setM(Number(e.target.value))} onPointerUp={() => m !== t.mastery && upd.mutate({ mastery: m })} onKeyUp={() => m !== t.mastery && upd.mutate({ mastery: m })} />
        <span className="w-14 shrink-0 text-right text-sm tnum">{m}% {masteryDot(m)}</span>
      </div>
      <select className="input !w-auto !py-1 !text-xs" aria-label="Difficulty" value={t.difficulty} onChange={(e) => upd.mutate({ difficulty: Number(e.target.value) })}>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>Diff {n}</option>)}</select>
      <button className="btn-quiet !p-1.5" onClick={() => rm.mutate()} aria-label={`Delete ${t.name}`}><Trash2 className="h-3.5 w-3.5" /></button>
    </li>
  );
}

function SubjectCard({ s, onEdit, onDelete }: { s: Subject; onEdit: () => void; onDelete: () => void }) {
  const [open, setOpen] = useState(true); const [name, setName] = useState(""); const refresh = useRefreshAll(); const toast = useToast();
  const add = useMutation({ mutationFn: () => post(`/api/subjects/${s.id}/topics`, { name: name.trim(), difficulty: s.difficulty, mastery: 40 }), onSuccess: () => { setName(""); refresh(); }, onError: (e) => toast((e as Error).message, "err") });
  return (
    <section className="card overflow-hidden" style={{ borderTop: `3px solid ${s.color}` }}>
      <div className="flex flex-wrap items-center gap-3 p-4 sm:p-5">
        <button className="flex min-w-0 flex-1 items-center gap-3 text-left" onClick={() => setOpen(!open)} aria-expanded={open}>
          <ChevronDown className={clsx("h-4 w-4 shrink-0 text-muted transition-transform", !open && "-rotate-90")} />
          <div className="min-w-0"><h2 className="truncate text-xl font-semibold">{s.name}</h2>
            <p className="text-sm text-muted">{s.exam_date ? <>Exam: {fmtDay(s.exam_date, { day: "numeric", month: "short", year: "numeric" })} · <b className={clsx(s.days_left !== null && s.days_left <= 7 && "text-crit")}>{s.days_left}d left</b></> : "No exam date set"} · Difficulty {s.difficulty}/5 · Target {s.target_marks}%</p></div>
        </button>
        <div className="flex w-full items-center gap-2 sm:w-52"><Bar value={s.preparation} tone={masteryTone(s.preparation)} /><b className="text-sm tnum">{s.preparation}%</b></div>
        <button className="btn-quiet !p-2" onClick={onEdit} aria-label={`Edit ${s.name}`}><Pencil className="h-4 w-4" /></button>
        <button className="btn-quiet !p-2" onClick={onDelete} aria-label={`Delete ${s.name}`}><Trash2 className="h-4 w-4" /></button>
      </div>
      {open && (
        <div className="border-t border-line px-4 pb-4 sm:px-5">
          {s.topics.length === 0 ? <p className="py-4 text-sm text-muted">No topics yet. Add the first one below.</p> : <ul className="divide-y divide-line">{s.topics.map((t) => <TopicRow key={t.id} t={t} color={s.color} />)}</ul>}
          <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (name.trim()) add.mutate(); }}>
            <input className="input" placeholder="Add a topic…" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} aria-label={`New topic for ${s.name}`} />
            <button className="btn-ghost" disabled={!name.trim() || add.isPending}><Plus className="h-4 w-4" />Add</button>
          </form>
        </div>
      )}
    </section>
  );
}

export default function Subjects() {
  const { data, error, isLoading, refetch } = useSubjects();
  const [edit, setEdit] = useState<Subject | "new" | null>(null); const [rm, setRm] = useState<Subject | null>(null);
  const refresh = useRefreshAll(); const toast = useToast();
  const remove = useMutation({ mutationFn: (s: Subject) => del(`/api/subjects/${s.id}`), onSuccess: () => { toast("Subject deleted. Plan recalculated."); refresh(); } });
  return (
    <div>
      <PageHeader title="My Subjects" sub="Mastery, difficulty and exam dates drive your plan. Changes replan instantly." actions={<button className="btn-primary" onClick={() => setEdit("new")}><Plus className="h-4 w-4" />Add subject</button>} />
      {error ? <ErrorNote error={error} retry={() => refetch()} /> : isLoading ? <div className="space-y-4"><Skeleton className="h-48" /><Skeleton className="h-48" /></div> :
        !data?.length ? <Empty icon={<BookOpen className="h-8 w-8" />} title="No subjects yet" text="Add a subject with its topics and exam date to generate a plan." action={<button className="btn-primary" onClick={() => setEdit("new")}>Add subject</button>} /> :
          <div className="space-y-4">{data.map((s) => <SubjectCard key={s.id} s={s} onEdit={() => setEdit(s)} onDelete={() => setRm(s)} />)}</div>}
      {edit && <SubjectModal subject={edit === "new" ? null : edit} onClose={() => setEdit(null)} />}
      <Confirm open={!!rm} title={`Delete ${rm?.name}?`} text="Its topics and all of its sessions are removed and your plan is recalculated. This can't be undone." onConfirm={() => remove.mutate(rm!)} onClose={() => setRm(null)} />
    </div>
  );
}
