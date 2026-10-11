import { ArrowRight, BarChart3, BrainCircuit, CalendarClock, Layers, RefreshCcw, Sparkles, Timer, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth, useTheme } from "../lib/auth";
import { clsx } from "../lib/util";
import { DemoButton } from "./Auth";

// ---- hero: a miniature week that shows the product's one big idea (missed session -> automatic reschedule)
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"];
const HOURS = ["09", "11", "13", "15", "17", "19"];
interface B { id: string; label: string; sub: string; col: number; row: number; color: string }
const STATIC: B[] = [
  { id: "os", label: "Virtual Memory", sub: "OS · 40m", col: 0, row: 1, color: "#E8590C" },
  { id: "py", label: "Practice", sub: "Python · 30m", col: 0, row: 5, color: "#0CA678" },
  { id: "ds2", label: "Graphs", sub: "DS · 45m", col: 1, row: 0, color: "#3B5BDB" },
  { id: "jv", label: "Collections", sub: "Java · 40m", col: 2, row: 1, color: "#AE3EC9" },
  { id: "ds3", label: "Queues", sub: "DS · 40m", col: 3, row: 4, color: "#3B5BDB" },
  { id: "os2", label: "Deadlocks", sub: "OS · 45m", col: 4, row: 0, color: "#E8590C" },
];

function Hero() {
  const [phase, setPhase] = useState(0);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setPhase(2); return; }
    const seq = [0, 1, 2, 2, 2];
    let i = 0; const t = setInterval(() => { i = (i + 1) % seq.length; setPhase(seq[i]); }, 1700);
    return () => clearInterval(t);
  }, []);
  const trees = phase < 2 ? { col: 0, row: 0 } : { col: 1, row: 5 };
  return (
    <div className="card relative overflow-hidden p-4 sm:p-5" aria-hidden>
      <div className="mb-3 flex items-center justify-between text-xs"><b className="font-display text-sm">This week</b>
        <span className={clsx("chip transition-colors", phase === 1 && "!border-crit/50 !text-crit", phase === 2 && "!border-low/50 !text-low")}>{phase === 0 ? "On track" : phase === 1 ? "Missed: Trees" : "Replanned ✓"}</span></div>
      <div className="grid grid-cols-[2rem_repeat(5,1fr)] gap-x-1.5 text-[10px] text-muted">
        <span />{DAYS.map((d) => <span key={d} className="pb-1 text-center font-semibold uppercase tracking-wide">{d}</span>)}
      </div>
      <div className="relative grid grid-cols-[2rem_repeat(5,1fr)] gap-x-1.5" style={{ gridTemplateRows: "repeat(6, 3.1rem)" }}>
        {HOURS.map((h, r) => (<div key={h} className="contents"><span className="border-t border-line pt-0.5 text-[10px] text-muted" style={{ gridRow: r + 1, gridColumn: 1 }}>{h}</span>
          {DAYS.map((_, c) => <i key={c} className="border-t border-line" style={{ gridRow: r + 1, gridColumn: c + 2 }} />)}</div>))}
        {STATIC.map((b) => <Block key={b.id} b={b} />)}
        <div className="z-10 transition-all duration-700 ease-out" style={{ gridColumn: trees.col + 2, gridRow: trees.row + 1, padding: 2 }}>
          <div className={clsx("h-full rounded-md border-l-[3px] px-1.5 py-1 text-[10px] leading-tight shadow-sm transition-colors duration-500", phase === 1 ? "bg-crit/15" : phase === 2 ? "bg-amber/25" : "bg-soft")} style={{ borderColor: phase === 1 ? "rgb(var(--crit))" : phase === 2 ? "rgb(var(--amber))" : "#3B5BDB" }}>
            <b className={clsx(phase === 1 && "line-through")}>Trees</b><br /><span className="text-muted">{phase === 2 ? "Moved · 7 PM" : "DS · 50m"}</span>
          </div>
        </div>
      </div>
      <p className="mt-3 text-xs text-muted">Miss a session and the planner re-prioritises the rest of the week around your exam dates, instead of shoving everything one day later.</p>
    </div>
  );
}
function Block({ b }: { b: B }) {
  return <div className="z-10" style={{ gridColumn: b.col + 2, gridRow: b.row + 1, padding: 2 }}><div className="h-full rounded-md border-l-[3px] bg-sunken px-1.5 py-1 text-[10px] leading-tight" style={{ borderColor: b.color }}><b>{b.label}</b><br /><span className="text-muted">{b.sub}</span></div></div>;
}

const FEATURES = [
  { icon: Layers, title: "Smart scheduling", text: "Every topic gets a priority from exam urgency, weakness, difficulty, importance and your history. Time is then allocated inside the hours you actually have, with breaks and subject variety built in." },
  { icon: RefreshCcw, title: "Adaptive planning", text: "Skip or miss a session and the rest of your plan is recalculated against remaining hours and exam dates. The missed topic comes back at the next sensible slot, not just \"tomorrow\"." },
  { icon: Timer, title: "Focus mode", text: "A distraction-free timer with Pomodoro support. Finish a session, rate your confidence, and the time is tracked against the plan." },
  { icon: BarChart3, title: "Honest analytics", text: "Planned versus actual hours, completion rate, streaks and a study score with a published formula. All derived from what you did, nothing invented." },
  { icon: BrainCircuit, title: "Spaced revision", text: "Completed topics come back after 1, 3, 7 and 14 days. Low confidence brings the review forward; high confidence stretches it." },
  { icon: Sparkles, title: "AI that explains", text: "The planner never needs AI. When you want it, AI explains recommendations and turns plain English like \"I can't study tomorrow\" into validated changes." },
];

export default function Landing() {
  const { user } = useAuth(); const theme = useTheme();
  return (
    <div className="min-h-full">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4">
        <span className="flex items-center gap-2 font-display text-lg font-semibold"><span className="grid h-8 w-8 place-items-center rounded-lg bg-primary text-primary-ink"><CalendarClock className="h-4 w-4" /></span>Study Planner</span>
        <nav className="flex items-center gap-1.5">
          <button className="btn-quiet !p-2" onClick={theme.toggle} aria-label="Toggle dark mode">{theme.dark ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}</button>
          {user ? <Link to="/dashboard" className="btn-primary">Open dashboard</Link> : <><Link to="/login" className="btn-quiet">Log in</Link><Link to="/register" className="btn-primary hidden sm:inline-flex">Get started</Link></>}
        </nav>
      </header>

      <section className="mx-auto grid max-w-6xl items-center gap-10 px-5 pb-16 pt-8 lg:grid-cols-[1.05fr_1fr] lg:pt-14">
        <div>
          <p className="chip mb-5 !border-primary/30 !text-primary"><Sparkles className="h-3 w-3" />Adaptive study planning for college exams</p>
          <h1 className="text-5xl font-semibold leading-[1.02] sm:text-6xl">Plan Smarter.<br />Study Better.<br /><span className="text-primary">Achieve More.</span></h1>
          <p className="mt-5 max-w-lg text-lg text-muted">Your AI-powered personal study planner that adapts to your exams, time, and goals.</p>
          <div className="mt-8 flex flex-wrap gap-3"><Link to="/register" className="btn-primary !px-5 !py-3 text-base">Create My Study Plan<ArrowRight className="h-4 w-4" /></Link><div className="min-w-[10rem]"><DemoButton className="btn-ghost !px-5 !py-3 text-base w-full" /></div></div>
          <p className="mt-4 text-xs text-muted">No card, no AI key needed. The demo opens a sample student's plan in one click.</p>
        </div>
        <Hero />
      </section>

      <section className="border-y border-line bg-surface">
        <div className="mx-auto max-w-6xl px-5 py-16">
          <h2 className="text-3xl font-semibold">How it works</h2>
          <ol className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[["Tell it your exams", "Subjects, topics, exam dates, the hours you have and when you like to study."], ["Get a real plan", "Priorities and time blocks are computed by an algorithm you can inspect, in under a second."], ["Follow it day by day", "Start a focus session, tick tasks off, rate your confidence."], ["It adjusts itself", "Misses, skips and new goals trigger a recalculation, so the plan stays believable."]].map(([t, d], i) => (
              <li key={t} className="rounded-xl border border-line p-5"><span className="font-display text-3xl font-semibold text-primary tnum">0{i + 1}</span><p className="mt-3 font-display text-lg font-semibold">{t}</p><p className="mt-1 text-sm text-muted">{d}</p></li>
            ))}
          </ol>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-5 py-16">
        <h2 className="max-w-xl text-3xl font-semibold">Built around how exam prep actually goes wrong</h2>
        <div className="mt-8 grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (<div key={f.title}><f.icon className="h-5 w-5 text-primary" /><h3 className="mt-3 text-lg font-semibold">{f.title}</h3><p className="mt-1.5 text-sm leading-relaxed text-muted">{f.text}</p></div>))}
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-5 pb-20">
        <div className="rounded-2xl bg-primary px-6 py-12 text-center text-primary-ink sm:px-12">
          <h2 className="text-3xl font-semibold sm:text-4xl">Your exams aren't going to move. Your plan can.</h2>
          <p className="mx-auto mt-3 max-w-lg opacity-85">Set up in two minutes and get a plan for every day until your last exam.</p>
          <Link to="/register" className="mt-6 inline-flex items-center gap-2 rounded-lg bg-white px-5 py-3 font-semibold text-[#2F44E8] hover:bg-white/90">Create My Study Plan<ArrowRight className="h-4 w-4" /></Link>
        </div>
      </section>
      <footer className="border-t border-line py-6 text-center text-xs text-muted">AI Study Planner · built with React, FastAPI and a lot of date arithmetic.</footer>
    </div>
  );
}
