import { useMutation } from "@tanstack/react-query";
import { Bell, LogOut, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Confirm, ErrorNote, Field, PageHeader, Skeleton, Spinner, useToast } from "../components/ui";
import { del, put } from "../lib/api";
import { useAuth, useTheme } from "../lib/auth";
import { useRefreshAll, useSettings } from "../lib/hooks";
import type { Settings as S } from "../lib/types";
import { WEEKDAYS, clsx, fmtDay } from "../lib/util";

const TIMES = [["morning", "Morning"], ["afternoon", "Afternoon"], ["evening", "Evening"], ["night", "Night"]];
const Section = ({ title, children, desc }: { title: string; desc?: string; children: React.ReactNode }) => <section className="card p-5"><h2 className="text-lg font-semibold">{title}</h2>{desc && <p className="mb-4 mt-0.5 text-sm text-muted">{desc}</p>}<div className={desc ? "" : "mt-4"}>{children}</div></section>;

export default function Settings() {
  const { data, error, isLoading, refetch } = useSettings();
  const { user, logout, refresh } = useAuth(); const theme = useTheme(); const toast = useToast(); const refreshAll = useRefreshAll(); const nav = useNavigate();
  const [f, setF] = useState<S | null>(null); const [block, setBlock] = useState(""); const [confirm, setConfirm] = useState(false);
  useEffect(() => { if (data) setF(data); }, [data]);
  const save = useMutation({ mutationFn: (p: Partial<S>) => put<S>("/api/settings", p), onSuccess: (s) => { setF(s); toast("Settings saved. Plan recalculated."); refreshAll(); refresh(); }, onError: (e) => toast((e as Error).message, "err") });
  const remove = useMutation({ mutationFn: () => del("/api/account"), onSuccess: () => { logout(); nav("/"); } });
  if (error) return <ErrorNote error={error} retry={() => refetch()} />;
  if (isLoading || !f) return <div className="space-y-4"><Skeleton className="h-40" /><Skeleton className="h-60" /></div>;
  const set = <K extends keyof S>(k: K, v: S[K]) => setF({ ...f, [k]: v });
  const dirty = JSON.stringify(f) !== JSON.stringify(data);
  const askNotif = async () => {
    if (!("Notification" in window)) return toast("This browser doesn't support notifications. You'll still get in-app ones.", "err");
    const p = await Notification.requestPermission();
    if (p === "granted") { set("browser_notifications", true); toast("Browser notifications enabled. Save to keep it."); } else toast("Permission not granted. In-app notifications still work.", "err");
  };

  return (
    <div className="max-w-3xl space-y-5 pb-16">
      <PageHeader title="Settings" actions={<button className="btn-primary" disabled={!dirty || save.isPending} onClick={() => save.mutate({ ...f, blocked_dates: f.blocked_dates } as unknown as Partial<S>)}>{save.isPending && <Spinner />}Save changes</button>} />
      <Section title="Profile">
        <div className="grid gap-4 sm:grid-cols-2"><Field label="Name"><input className="input" value={f.name} maxLength={80} onChange={(e) => set("name", e.target.value)} /></Field><Field label="Year"><select className="input" value={f.year} onChange={(e) => set("year", Number(e.target.value))}>{[1, 2, 3, 4, 5].map((y) => <option key={y} value={y}>Year {y}</option>)}</select></Field>
          <Field label="College"><input className="input" value={f.college} maxLength={120} onChange={(e) => set("college", e.target.value)} /></Field><Field label="Department"><input className="input" value={f.department} maxLength={120} onChange={(e) => set("department", e.target.value)} /></Field></div>
      </Section>
      <Section title="Study time" desc="Your daily ceiling per weekday. The planner never schedules past it.">
        <div className="space-y-3">{WEEKDAYS.map((w, i) => <div key={w} className="grid grid-cols-[5.5rem_1fr_3rem] items-center gap-3 text-sm"><span>{w}</span><input type="range" min={0} max={480} step={30} className="accent-[rgb(var(--primary))]" aria-label={`${w} study minutes`} value={f.daily_minutes[i]} onChange={(e) => set("daily_minutes", f.daily_minutes.map((v, j) => (j === i ? Number(e.target.value) : v)))} /><b className="text-right tnum">{f.daily_minutes[i] / 60}h</b></div>)}</div>
        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          <Field label="Max hours in one day" hint="Hard cap used by overload detection"><input type="number" className="input" min={1} max={10} step={0.5} value={f.max_daily_minutes / 60} onChange={(e) => set("max_daily_minutes", Math.round(Number(e.target.value) * 60))} /></Field>
          <Field label="Longest block (min)"><input type="number" className="input" min={20} max={90} step={5} value={f.max_block_minutes} onChange={(e) => set("max_block_minutes", Number(e.target.value))} /></Field>
          <Field label="Break between blocks (min)"><input type="number" className="input" min={5} max={30} step={5} value={f.break_minutes} onChange={(e) => set("break_minutes", Number(e.target.value))} /></Field></div>
        <div className="mt-5"><span className="label">Preferred study times</span><div className="flex flex-wrap gap-2">{TIMES.map(([k, l]) => { const on = f.preferred_times.includes(k); return <button key={k} aria-pressed={on} onClick={() => set("preferred_times", on ? f.preferred_times.filter((x) => x !== k) : [...f.preferred_times, k])} className={clsx("rounded-full border px-3.5 py-1.5 text-sm font-medium", on ? "border-primary bg-soft text-primary" : "border-line text-muted")}>{l}</button>; })}</div></div>
        <div className="mt-5"><span className="label">Days you can't study</span><div className="flex flex-wrap items-center gap-2">{f.blocked_dates.map((d) => <span key={d} className="chip !py-1">{fmtDay(d)}<button aria-label={`Unblock ${d}`} onClick={() => set("blocked_dates", f.blocked_dates.filter((x) => x !== d))}>×</button></span>)}
          <input type="date" className="input !w-auto" value={block} onChange={(e) => setBlock(e.target.value)} aria-label="Add blocked date" /><button className="btn-ghost" disabled={!block} onClick={() => { set("blocked_dates", Array.from(new Set([...f.blocked_dates, block])).sort()); setBlock(""); }}>Block day</button></div></div>
        <Field label="Target marks (%)"><input type="number" className="mt-4 input !w-28" min={40} max={100} value={f.target_marks} onChange={(e) => set("target_marks", Number(e.target.value))} /></Field>
      </Section>
      <Section title="Pomodoro" desc="Defaults for Pomodoro sessions in Focus Mode.">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">{([["focus", "Study (min)"], ["short_break", "Break (min)"], ["long_break", "Long break (min)"], ["rounds", "Rounds"]] as const).map(([k, l]) => <Field key={k} label={l}><input type="number" className="input" min={1} max={90} value={f.pomodoro[k]} onChange={(e) => set("pomodoro", { ...f.pomodoro, [k]: Number(e.target.value) })} /></Field>)}</div>
      </Section>
      <Section title="Appearance & notifications">
        <div className="space-y-4">
          <div className="flex items-center justify-between"><div><p className="font-semibold">Dark mode</p><p className="text-sm text-muted">Saved on this device and to your account.</p></div><button role="switch" aria-checked={theme.dark} className={clsx("relative h-6 w-11 rounded-full transition", theme.dark ? "bg-primary" : "bg-line")} onClick={() => { theme.toggle(); save.mutate({ theme: theme.dark ? "light" : "dark" }); }}><i className={clsx("absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all", theme.dark ? "left-[22px]" : "left-0.5")} /></button></div>
          <div className="flex items-center justify-between"><div><p className="font-semibold">In-app notifications</p><p className="text-sm text-muted">Upcoming session, missed task, exam approaching, daily plan, streak reminder.</p></div><input type="checkbox" className="h-5 w-5 accent-[rgb(var(--primary))]" checked={f.notifications_enabled} onChange={(e) => set("notifications_enabled", e.target.checked)} aria-label="In-app notifications" /></div>
          <div className="flex items-center justify-between gap-3"><div><p className="font-semibold">Browser notifications</p><p className="text-sm text-muted">Also pop up while the app is open in a tab.</p></div>{f.browser_notifications ? <button className="btn-ghost" onClick={() => set("browser_notifications", false)}><Bell className="h-4 w-4" />On</button> : <button className="btn-ghost" onClick={askNotif}>Enable</button>}</div>
        </div>
      </Section>
      <Section title="Account">
        <p className="text-sm text-muted">{user?.is_demo ? "This is a demo account with sample data. It's deleted automatically." : user?.email}</p>
        <div className="mt-4 flex flex-wrap gap-2"><button className="btn-ghost" onClick={logout}><LogOut className="h-4 w-4" />Log out</button><button className="btn-danger" onClick={() => setConfirm(true)}><Trash2 className="h-4 w-4" />Delete account</button></div>
      </Section>
      <Confirm open={confirm} title="Delete your account?" text="All subjects, plans, sessions and analytics are permanently deleted. This can't be undone." confirmLabel="Delete everything" onConfirm={() => remove.mutate()} onClose={() => setConfirm(false)} />
    </div>
  );
}
