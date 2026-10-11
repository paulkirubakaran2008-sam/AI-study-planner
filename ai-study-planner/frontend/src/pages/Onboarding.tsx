import { ArrowLeft, ArrowRight, Plus, Sparkles, X } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Field, Spinner } from "../components/ui";
import { post } from "../lib/api";
import { useAuth } from "../lib/auth";
import { clsx, iso, masteryDot, tz } from "../lib/util";

interface Subj { name: string; difficulty: number; exam_date: string; level: number; topics: string }
const STEPS = ["About you", "Subjects", "Topics", "Exam dates", "Study hours", "Preparation", "Target marks", "Study times"];
const TIMES = [{ k: "morning", label: "Morning", sub: "8 – 12" }, { k: "afternoon", label: "Afternoon", sub: "1:30 – 5" }, { k: "evening", label: "Evening", sub: "6 – 9:30" }, { k: "night", label: "Night", sub: "9:30 – 11:30" }];
const hours = (m: number) => `${m / 60}h`;

export default function Onboarding() {
  const { user, refresh } = useAuth(); const nav = useNavigate();
  const [step, setStep] = useState(0);
  const [p, setP] = useState({ name: user?.name ?? "", college: "", department: "", year: 2 });
  const [subjects, setSubjects] = useState<Subj[]>([]);
  const [newName, setNewName] = useState("");
  const [weekday, setWeekday] = useState(180); const [weekend, setWeekend] = useState(240);
  const [target, setTarget] = useState(80);
  const [times, setTimes] = useState<string[]>(["morning", "evening"]);
  const [busy, setBusy] = useState(false); const [err, setErr] = useState("");
  const today = iso(new Date());

  const upd = (i: number, patch: Partial<Subj>) => setSubjects((s) => s.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const addSubject = () => { const n = newName.trim(); if (!n || subjects.some((s) => s.name.toLowerCase() === n.toLowerCase()) || subjects.length >= 15) return; setSubjects((s) => [...s, { name: n, difficulty: 3, exam_date: "", level: 40, topics: "" }]); setNewName(""); };
  const parseTopics = (t: string) => Array.from(new Set(t.split(/[\n,]/).map((x) => x.trim()).filter(Boolean))).slice(0, 60);

  const problem = (): string => {
    if (step === 0) return p.name.trim() ? "" : "Enter your name to continue.";
    if (step === 1) return subjects.length ? "" : "Add at least one subject.";
    if (step === 2) return subjects.every((s) => parseTopics(s.topics).length) ? "" : "Add at least one topic to every subject.";
    if (step === 3) return subjects.every((s) => s.exam_date && s.exam_date >= today) ? "" : "Give every subject an exam date that isn't in the past.";
    if (step === 7) return times.length ? "" : "Pick at least one time of day.";
    return "";
  };
  const next = () => { const m = problem(); if (m) return setErr(m); setErr(""); setStep((s) => s + 1); };

  const finish = async () => {
    const m = problem(); if (m) return setErr(m);
    setBusy(true); setErr("");
    try {
      await post("/api/onboarding", {
        profile: p, weekday_minutes: weekday, weekend_minutes: weekend, preferred_times: times, target_marks: target, default_level: 40, timezone: tz(),
        subjects: subjects.map((s) => ({ name: s.name, difficulty: s.difficulty, importance: 3, target_marks: target, exam_date: s.exam_date, topics: parseTopics(s.topics).map((t) => ({ name: t, difficulty: s.difficulty, mastery: s.level })) })),
      });
      await refresh(); nav("/dashboard");
    } catch (e) { setErr((e as Error).message); setBusy(false); }
  };

  const example = () => {
    const d = (n: number) => iso(new Date(Date.now() + n * 86400000));
    setSubjects([{ name: "Data Structures", difficulty: 4, exam_date: d(14), level: 35, topics: "Arrays, Linked Lists, Stacks, Queues, Trees, Graphs" }, { name: "Operating Systems", difficulty: 4, exam_date: d(19), level: 45, topics: "Scheduling, Deadlocks, Virtual Memory, File Systems" }, { name: "Python", difficulty: 2, exam_date: d(24), level: 60, topics: "Functions, OOP, File Handling, Practice Problems" }]);
    setStep(1);
  };
  const last = step === STEPS.length - 1;

  return (
    <div className="mx-auto flex min-h-full max-w-2xl flex-col px-5 py-8">
      <div className="mb-8 flex items-center justify-between"><span className="flex items-center gap-2 font-display text-lg font-semibold"><Sparkles className="h-5 w-5 text-primary" />Set up your plan</span><span className="text-sm text-muted tnum">Step {step + 1} of {STEPS.length}</span></div>
      <div className="mb-8 flex gap-1.5" role="progressbar" aria-valuenow={step + 1} aria-valuemax={STEPS.length}>{STEPS.map((s, i) => <i key={s} className={clsx("h-1.5 flex-1 rounded-full transition-colors", i <= step ? "bg-primary" : "bg-line")} />)}</div>

      <div className="flex-1">
        <h1 className="text-3xl font-semibold">{["Let's start with you", "What are you studying?", "What's in each subject?", "When are the exams?", "How much time can you give?", "Where are you right now?", "What are you aiming for?", "When do you like to study?"][step]}</h1>
        <div className="mt-6 space-y-5">
          {step === 0 && <div className="grid gap-4 sm:grid-cols-2"><div className="sm:col-span-2"><Field label="Name"><input className="input" value={p.name} maxLength={80} onChange={(e) => setP({ ...p, name: e.target.value })} /></Field></div>
            <Field label="College"><input className="input" value={p.college} maxLength={120} onChange={(e) => setP({ ...p, college: e.target.value })} /></Field>
            <Field label="Department"><input className="input" value={p.department} maxLength={120} onChange={(e) => setP({ ...p, department: e.target.value })} /></Field>
            <Field label="Year"><select className="input" value={p.year} onChange={(e) => setP({ ...p, year: Number(e.target.value) })}>{[1, 2, 3, 4, 5].map((y) => <option key={y} value={y}>Year {y}</option>)}</select></Field></div>}

          {step === 1 && <>
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); addSubject(); }}><input className="input" placeholder="e.g. Data Structures" maxLength={80} value={newName} onChange={(e) => setNewName(e.target.value)} aria-label="Subject name" /><button className="btn-primary" type="submit"><Plus className="h-4 w-4" />Add</button></form>
            <div className="flex flex-wrap gap-2">{subjects.map((s, i) => <span key={s.name} className="chip !border-primary/30 !bg-soft !py-1.5 !text-ink">{s.name}<button aria-label={`Remove ${s.name}`} onClick={() => setSubjects(subjects.filter((_, j) => j !== i))}><X className="h-3 w-3" /></button></span>)}</div>
            {!subjects.length && <button className="text-sm font-semibold text-primary" onClick={example}>Fill with an example →</button>}</>}

          {step === 2 && subjects.map((s, i) => (<div key={s.name} className="card p-4"><div className="mb-3 flex items-center justify-between"><b className="font-display text-lg">{s.name}</b>
            <label className="flex items-center gap-2 text-xs text-muted">Difficulty<select className="input !w-auto !py-1" value={s.difficulty} onChange={(e) => upd(i, { difficulty: Number(e.target.value) })}>{[1, 2, 3, 4, 5].map((d) => <option key={d} value={d}>{d} / 5</option>)}</select></label></div>
            <textarea className="input min-h-[96px]" placeholder={"One topic per line, or comma separated\nArrays\nLinked Lists\nTrees"} value={s.topics} onChange={(e) => upd(i, { topics: e.target.value })} aria-label={`Topics for ${s.name}`} />
            <p className="mt-1 text-xs text-muted">{parseTopics(s.topics).length} topic(s)</p></div>))}

          {step === 3 && subjects.map((s, i) => <Field key={s.name} label={s.name}><input type="date" min={today} className="input" value={s.exam_date} onChange={(e) => upd(i, { exam_date: e.target.value })} /></Field>)}

          {step === 4 && <>
            <Slider label="Weekdays" value={weekday} min={0} max={480} step={30} fmt={hours} onChange={setWeekday} />
            <Slider label="Weekends" value={weekend} min={0} max={480} step={30} fmt={hours} onChange={setWeekend} />
            <p className="text-sm text-muted">This is your <b>ceiling</b>. The planner spreads work to finish on time without filling every hour, and never schedules more than you set here (plus a small cap on single-day load).</p></>}

          {step === 5 && <>{subjects.map((s, i) => <Slider key={s.name} label={`${masteryDot(s.level)} ${s.name}`} value={s.level} min={0} max={100} step={5} fmt={(v) => `${v}%`} onChange={(v) => upd(i, { level: v })} />)}
            <p className="text-sm text-muted">A rough guess is fine. How much of each subject do you already know? You can fine-tune every topic later.</p></>}

          {step === 6 && <><Slider label="Target marks" value={target} min={50} max={100} step={5} fmt={(v) => `${v}%`} onChange={setTarget} /><p className="text-sm text-muted">Higher targets mean more time on weak topics and more revision before each exam.</p></>}

          {step === 7 && <div className="grid grid-cols-2 gap-3">{TIMES.map((t) => { const on = times.includes(t.k); return (
            <button key={t.k} onClick={() => setTimes(on ? times.filter((x) => x !== t.k) : [...times, t.k])} aria-pressed={on} className={clsx("rounded-xl border p-4 text-left transition", on ? "border-primary bg-soft" : "border-line hover:bg-sunken")}><p className="font-display text-lg font-semibold">{t.label}</p><p className="text-sm text-muted">{t.sub}</p></button>); })}</div>}
        </div>
        {err && <p role="alert" className="mt-4 text-sm text-crit">{err}</p>}
      </div>

      <div className="mt-8 flex items-center justify-between border-t border-line pt-5">
        <button className="btn-quiet" onClick={() => { setErr(""); setStep(step - 1); }} disabled={step === 0 || busy}><ArrowLeft className="h-4 w-4" />Back</button>
        {last ? <button className="btn-primary !px-5 !py-3" onClick={finish} disabled={busy}>{busy ? <Spinner /> : <Sparkles className="h-4 w-4" />}Generate My Study Plan</button> : <button className="btn-primary" onClick={next}>Next<ArrowRight className="h-4 w-4" /></button>}
      </div>
    </div>
  );
}

function Slider({ label, value, min, max, step, fmt, onChange }: { label: string; value: number; min: number; max: number; step: number; fmt: (v: number) => string; onChange: (v: number) => void }) {
  return (<div><div className="mb-2 flex justify-between text-sm"><span className="font-semibold">{label}</span><span className="tnum font-display text-lg font-semibold">{fmt(value)}</span></div>
    <input type="range" className="w-full accent-[rgb(var(--primary))]" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} aria-label={label} /></div>);
}
