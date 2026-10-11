import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { post } from "./api";
import { Modal, useToast } from "../components/ui";
import { clsx } from "./util";

export interface FocusTarget { taskId?: number; subjectId?: number; topicId?: number; label: string; subject: string; plannedMin: number }
interface Phase { type: "focus" | "break"; min: number; long?: boolean }
interface FocusState { mode: "focus" | "pomodoro"; target: FocusTarget; phases: Phase[]; idx: number; endAt: number | null; remainingMs: number; studiedMs: number; done: boolean }

const KEY = "asp_focus";
const load = (): FocusState | null => { try { return JSON.parse(localStorage.getItem(KEY) || "null"); } catch { return null; } };

function beep() {
  try {
    const ctx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
    [0, 0.25].forEach((t) => { const o = ctx.createOscillator(), g = ctx.createGain(); o.frequency.value = 660 + t * 400; g.gain.value = 0.06; o.connect(g); g.connect(ctx.destination); o.start(ctx.currentTime + t); o.stop(ctx.currentTime + t + 0.18); });
  } catch { /* audio is optional */ }
}

interface Api {
  state: FocusState | null; remainingMs: number; studiedMin: number; running: boolean; phase: Phase | null;
  start: (t: FocusTarget, o: { mode: "focus" | "pomodoro"; minutes: number; pomodoro?: { focus: number; short_break: number; long_break: number; rounds: number } }) => void;
  pause: () => void; resume: () => void; stop: () => void; discard: () => void;
}
const Ctx = createContext<Api>(null!);
export const useFocus = () => useContext(Ctx);

export function FocusProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<FocusState | null>(load);
  const [, force] = useState(0);
  const toast = useToast();
  const qc = useQueryClient();
  const ref = useRef(state);
  ref.current = state;

  useEffect(() => { state ? localStorage.setItem(KEY, JSON.stringify(state)) : localStorage.removeItem(KEY); }, [state]);

  const advance = useCallback((s: FocusState, now: number): FocusState => {
    let cur = { ...s };
    while (cur.endAt !== null && cur.endAt <= now && !cur.done) {
      const overshoot = now - cur.endAt, p = cur.phases[cur.idx];
      if (p.type === "focus") cur.studiedMs += p.min * 60000;
      cur.idx += 1;
      if (cur.idx >= cur.phases.length) { cur = { ...cur, done: true, endAt: null, remainingMs: 0 }; break; }
      cur.endAt = now - overshoot + cur.phases[cur.idx].min * 60000;
      cur.remainingMs = cur.phases[cur.idx].min * 60000;
      beep();
      if ("Notification" in window && Notification.permission === "granted") new Notification(cur.phases[cur.idx].type === "break" ? "Break time ☕" : "Back to focus 📚");
    }
    if (cur.done) { beep(); }
    return cur;
  }, []);

  useEffect(() => {
    const t = setInterval(() => {
      const s = ref.current;
      if (!s || s.done || s.endAt === null) return;
      const next = advance(s, Date.now());
      if (next !== s && (next.idx !== s.idx || next.done)) setState(next);
      force((n) => n + 1);
    }, 500);
    return () => clearInterval(t);
  }, [advance]);

  const remainingMs = state ? (state.endAt !== null ? Math.max(0, state.endAt - Date.now()) : state.remainingMs) : 0;
  const phase = state && !state.done ? state.phases[state.idx] : null;
  const studiedMs = state ? state.studiedMs + (phase?.type === "focus" ? phase.min * 60000 - remainingMs : 0) : 0;
  const studiedMin = Math.floor(studiedMs / 60000);

  const api = useMemo<Api>(() => ({
    state, remainingMs, studiedMin, phase, running: !!state && state.endAt !== null && !state.done,
    start: (target, o) => {
      const phases: Phase[] = [];
      if (o.mode === "pomodoro" && o.pomodoro) {
        for (let i = 0; i < o.pomodoro.rounds; i++) {
          phases.push({ type: "focus", min: o.pomodoro.focus });
          phases.push(i === o.pomodoro.rounds - 1 ? { type: "break", min: o.pomodoro.long_break, long: true } : { type: "break", min: o.pomodoro.short_break });
        }
        phases.pop();                       // end on the final focus block; the long break is offered after
        phases.push({ type: "break", min: o.pomodoro.long_break, long: true });
      } else phases.push({ type: "focus", min: o.minutes });
      setState({ mode: o.mode, target: { ...target, plannedMin: phases.filter((p) => p.type === "focus").reduce((a, b) => a + b.min, 0) }, phases, idx: 0, endAt: Date.now() + phases[0].min * 60000, remainingMs: phases[0].min * 60000, studiedMs: 0, done: false });
    },
    pause: () => setState((s) => (s && s.endAt !== null ? { ...s, remainingMs: Math.max(0, s.endAt - Date.now()), endAt: null } : s)),
    resume: () => setState((s) => (s && s.endAt === null && !s.done ? { ...s, endAt: Date.now() + s.remainingMs } : s)),
    stop: () => setState((s) => {
      if (!s) return s;
      const p = s.phases[s.idx];
      const cur = s.endAt !== null ? Math.max(0, s.endAt - Date.now()) : s.remainingMs;
      const studied = s.studiedMs + (!s.done && p?.type === "focus" ? p.min * 60000 - cur : 0);
      return { ...s, studiedMs: studied, done: true, endAt: null, remainingMs: 0 };
    }),
    discard: () => setState(null),
  }), [state, remainingMs, studiedMin, phase]);

  const finished = !!state?.done;
  const finalMin = Math.round((state?.studiedMs ?? 0) / 60000);
  return (
    <Ctx.Provider value={api}>
      {children}
      {finished && state && <FinishModal state={state} minutes={finalMin} onDone={(saved) => { setState(null); if (saved) { toast("Session saved. Nice work!"); qc.invalidateQueries(); } }} />}
    </Ctx.Provider>
  );
}

const FACES = [{ v: 1, e: "😞", t: "Lost" }, { v: 2, e: "😐", t: "Shaky" }, { v: 3, e: "🙂", t: "OK" }, { v: 4, e: "😃", t: "Good" }, { v: 5, e: "🤩", t: "Nailed it" }];

function FinishModal({ state, minutes, onDone }: { state: FocusState; minutes: number; onDone: (saved: boolean) => void }) {
  const [conf, setConf] = useState<number | null>(null);
  const [complete, setComplete] = useState(state.target.taskId ? minutes >= state.target.plannedMin * 0.8 : false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const tooShort = minutes < 1;
  const save = async () => {
    setBusy(true);
    try {
      await post("/api/sessions", { task_id: state.target.taskId, subject_id: state.target.subjectId, topic_id: state.target.topicId, duration_minutes: Math.max(1, minutes), planned_minutes: state.target.plannedMin, mode: state.mode, confidence: conf ?? undefined, complete_task: complete });
      onDone(true);
    } catch (e) { toast((e as Error).message, "err"); setBusy(false); }
  };
  return (
    <Modal open locked onClose={() => {}} title={tooShort ? "Session ended" : "🎉 Session complete"}>
      {tooShort ? (
        <><p className="text-sm text-muted">That was under a minute, so nothing was logged.</p><div className="mt-4 flex justify-end"><button className="btn-primary" onClick={() => onDone(false)}>Close</button></div></>
      ) : (
        <>
          <p className="font-display text-3xl font-semibold tnum">{minutes} minutes studied</p>
          <p className="mt-1 text-sm text-muted">Topic: <b className="text-ink">{state.target.label}</b> · {state.target.subject}</p>
          <p className="mb-2 mt-5 text-sm font-semibold">How confident are you?</p>
          <div className="grid grid-cols-5 gap-2" role="radiogroup" aria-label="Confidence">
            {FACES.map((f) => (
              <button key={f.v} role="radio" aria-checked={conf === f.v} onClick={() => setConf(f.v)} className={clsx("flex flex-col items-center rounded-xl border py-2.5 transition", conf === f.v ? "border-primary bg-soft" : "border-line hover:bg-sunken")}>
                <span className="text-2xl">{f.e}</span><span className="mt-0.5 text-[11px] text-muted">{f.t}</span>
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-muted">Low confidence schedules your next review sooner; high confidence spaces it further out.</p>
          {state.target.taskId && <label className="mt-4 flex items-center gap-2 text-sm"><input type="checkbox" checked={complete} onChange={(e) => setComplete(e.target.checked)} className="h-4 w-4 accent-[rgb(var(--primary))]" />Mark this task as completed</label>}
          <div className="mt-5 flex justify-end gap-2"><button className="btn-quiet" onClick={() => onDone(false)} disabled={busy}>Discard</button><button className="btn-primary" onClick={save} disabled={busy}>Save session</button></div>
        </>
      )}
    </Modal>
  );
}
