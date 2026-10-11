import { Maximize2, Pause, Play, Square, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { mmss } from "../components/Shell";
import { PageHeader, Ring, Segmented } from "../components/ui";
import { useFocus } from "../lib/focus";
import { useSettings, useSubjects, useTasks } from "../lib/hooks";
import { clsx, mins, time12, todayISO } from "../lib/util";

type Preset = "25" | "50" | "90" | "custom" | "pomodoro";

export default function Focus() {
  const f = useFocus();
  const { data: subjects } = useSubjects(); const { data: settings } = useSettings();
  const today = todayISO(); const { data: tasks } = useTasks(today, today);
  const open = useMemo(() => (tasks ?? []).filter((t) => ["pending", "in_progress", "overdue"].includes(t.status)), [tasks]);
  const [preset, setPreset] = useState<Preset>("25"); const [custom, setCustom] = useState(40);
  const [taskId, setTaskId] = useState<number>(0); const [subjectId, setSubjectId] = useState(0); const [topicId, setTopicId] = useState(0);
  const [pomo, setPomo] = useState({ focus: 25, short_break: 5, long_break: 15, rounds: 3 });
  const [zen, setZen] = useState(false);
  useEffect(() => { if (settings) setPomo(settings.pomodoro); }, [settings]);
  useEffect(() => { if (!taskId && open[0]) setTaskId(open[0].id); }, [open, taskId]);

  const task = open.find((t) => t.id === taskId);
  const subj = subjects?.find((s) => s.id === (subjectId || subjects[0]?.id));
  const active = !!f.state && !f.state.done;

  const begin = () => {
    const minutes = preset === "custom" ? custom : Number(preset) || 25;
    const target = task ? { taskId: task.id, subjectId: task.subject_id, topicId: task.topic_id ?? undefined, label: task.topic_name || task.title, subject: task.subject_name, plannedMin: minutes }
      : { subjectId: subj?.id, topicId: topicId || undefined, label: subj?.topics.find((t) => t.id === topicId)?.name || subj?.name || "Free study", subject: subj?.name || "Free study", plannedMin: minutes };
    f.start(target, { mode: preset === "pomodoro" ? "pomodoro" : "focus", minutes, pomodoro: pomo });
  };

  const phase = f.phase; const total = phase ? phase.min * 60000 : 1; const pct = active ? (1 - f.remainingMs / total) * 100 : 0; const paused = active && !f.running;
  const phaseIdx = f.state ? f.state.phases.slice(0, f.state.idx).filter((p) => p.type === "focus").length : 0; const rounds = f.state?.phases.filter((p) => p.type === "focus").length ?? 0;

  const Timer = (big: boolean) => (
    <div className="flex flex-col items-center">
      <Ring value={active ? pct : 0} size={big ? 300 : 240} stroke={big ? 12 : 10} color={phase?.type === "break" ? "rgb(var(--low))" : "rgb(var(--primary))"}
        label={<span className={clsx("tnum", big ? "text-6xl" : "text-5xl")}>{active ? mmss(f.remainingMs) : mmss((preset === "custom" ? custom : preset === "pomodoro" ? pomo.focus : Number(preset)) * 60000)}</span>}
        sub={active ? (phase?.type === "break" ? (phase.long ? "Long break" : "Break") : paused ? "Paused" : "Focus") : "Ready"} />
      {active && f.state && <p className="mt-4 text-center text-sm text-muted"><b className="text-ink">{f.state.target.label}</b> · {f.state.target.subject}<br />{f.studiedMin} min studied{f.state.mode === "pomodoro" && ` · round ${Math.min(phaseIdx + (phase?.type === "focus" ? 1 : 0), rounds)} of ${rounds}`}</p>}
      <div className="mt-6 flex items-center gap-3">
        {!active ? <button className="btn-primary !px-8 !py-3 text-base" onClick={begin}><Play className="h-5 w-5" />Start</button> : <>
          {paused ? <button className="btn-primary !px-6 !py-3" onClick={f.resume}><Play className="h-5 w-5" />Resume</button> : <button className="btn-ghost !px-6 !py-3" onClick={f.pause}><Pause className="h-5 w-5" />Pause</button>}
          <button className="btn-danger !px-6 !py-3" onClick={f.stop}><Square className="h-4 w-4" />Stop</button></>}
      </div>
    </div>
  );

  if (zen && active) return (
    <div className="fixed inset-0 z-[70] flex flex-col items-center justify-center bg-paper p-6">
      <button className="btn-quiet absolute right-4 top-4" onClick={() => setZen(false)} aria-label="Exit full screen"><X className="h-5 w-5" /></button>{Timer(true)}
    </div>
  );

  return (
    <div>
      <PageHeader title="Focus Mode" sub="One thing, no distractions. Your time is tracked against the plan." actions={active ? <button className="btn-ghost" onClick={() => setZen(true)}><Maximize2 className="h-4 w-4" />Full screen</button> : undefined} />
      <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
        <section className="card p-5 sm:p-6">
          <div className={clsx("space-y-5", active && "pointer-events-none opacity-50")}>
            <div><span className="label">Session length</span><div className="scroll-thin overflow-x-auto"><Segmented<Preset> value={preset} onChange={setPreset} options={[{ value: "25", label: "25 min" }, { value: "50", label: "50 min" }, { value: "90", label: "90 min" }, { value: "custom", label: "Custom" }, { value: "pomodoro", label: "Pomodoro" }]} /></div></div>
            {preset === "custom" && <div><span className="label">Custom minutes</span><input type="number" min={5} max={240} className="input w-32" value={custom} onChange={(e) => setCustom(Math.max(5, Math.min(240, Number(e.target.value) || 5)))} /></div>}
            {preset === "pomodoro" && (
              <div className="rounded-lg bg-sunken p-3"><p className="mb-2 text-xs text-muted">{Array.from({ length: pomo.rounds }, (_, i) => `${pomo.focus} study → ${i === pomo.rounds - 1 ? pomo.long_break + " long break" : pomo.short_break + " break"}`).join(" → ")}</p>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{([["focus", "Study"], ["short_break", "Break"], ["long_break", "Long break"], ["rounds", "Rounds"]] as const).map(([k, l]) => <label key={k} className="text-xs text-muted">{l}<input type="number" className="input mt-0.5" min={k === "rounds" ? 1 : 1} max={k === "rounds" ? 8 : 90} value={pomo[k]} onChange={(e) => setPomo({ ...pomo, [k]: Math.max(1, Number(e.target.value) || 1) })} /></label>)}</div></div>)}
            <div><span className="label">What are you working on?</span>
              <select className="input" value={taskId} onChange={(e) => setTaskId(Number(e.target.value))}>{open.map((t) => <option key={t.id} value={t.id}>{time12(t.start_time)} · {t.title} ({t.subject_name}, {mins(t.duration_minutes)})</option>)}<option value={0}>Something else (free study)…</option></select></div>
            {!task && <div className="grid grid-cols-2 gap-3"><select className="input" aria-label="Subject" value={subj?.id ?? 0} onChange={(e) => { setSubjectId(Number(e.target.value)); setTopicId(0); }}>{subjects?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
              <select className="input" aria-label="Topic" value={topicId} onChange={(e) => setTopicId(Number(e.target.value))}><option value={0}>Any topic</option>{subj?.topics.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></div>}
          </div>
          {!open.length && !active && <p className="mt-4 text-sm text-muted">No open sessions today. You can still log free study time.</p>}
        </section>
        <section className="card grid place-items-center p-6 sm:p-8">{Timer(false)}</section>
      </div>
    </div>
  );
}
