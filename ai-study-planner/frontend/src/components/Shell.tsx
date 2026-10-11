import { useQueryClient } from "@tanstack/react-query";
import { BarChart3, Bell, BookOpen, CalendarDays, CheckSquare, LayoutDashboard, ListChecks, LogOut, Menu, Moon, Settings as Cog, Sparkles, Sun, Timer, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { post, put } from "../lib/api";
import { useAuth, useTheme } from "../lib/auth";
import { useFocus } from "../lib/focus";
import { useNotifications, useSettings } from "../lib/hooks";
import { clsx } from "../lib/util";
import { Assistant } from "./Assistant";
import { Banner } from "./ui";

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/subjects", label: "My Subjects", icon: BookOpen },
  { to: "/planner", label: "Study Planner", icon: ListChecks },
  { to: "/calendar", label: "Calendar", icon: CalendarDays },
  { to: "/tasks", label: "Tasks", icon: CheckSquare },
  { to: "/focus", label: "Focus Mode", icon: Timer },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/recommendations", label: "AI Recommendations", icon: Sparkles },
  { to: "/settings", label: "Settings", icon: Cog },
];
const MOBILE = ["/dashboard", "/planner", "/calendar", "/tasks"];

export const mmss = (ms: number) => { const s = Math.ceil(ms / 1000); return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; };

function Logo() { return <Link to="/dashboard" className="flex items-center gap-2 font-display text-lg font-semibold"><span className="grid h-8 w-8 place-items-center rounded-lg bg-primary text-primary-ink"><ListChecks className="h-4 w-4" /></span>Study Planner</Link>; }

function Bells() {
  const { data } = useNotifications();
  const { data: settings } = useSettings();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); }; document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h); }, []);
  useEffect(() => {   // mirror new in-app notifications as browser notifications when permitted
    if (!data || !settings?.browser_notifications || !("Notification" in window) || Notification.permission !== "granted") return;
    const last = Number(localStorage.getItem("asp_last_notified") || 0);
    data.items.filter((n) => !n.read && n.id > last).reverse().forEach((n) => new Notification(n.title, { body: n.body }));
    const max = Math.max(last, ...data.items.map((n) => n.id));
    localStorage.setItem("asp_last_notified", String(max));
  }, [data, settings?.browser_notifications]);
  const readAll = async () => { await post("/api/notifications/read-all"); qc.invalidateQueries({ queryKey: ["notifications"] }); };
  return (
    <div className="relative" ref={ref}>
      <button className="btn-quiet relative !p-2" onClick={() => setOpen((o) => !o)} aria-label={`Notifications${data?.unread ? `, ${data.unread} unread` : ""}`}>
        <Bell className="h-[18px] w-[18px]" />{!!data?.unread && <span className="absolute right-1 top-1 grid h-4 min-w-4 place-items-center rounded-full bg-crit px-1 text-[10px] font-bold text-white">{data.unread}</span>}
      </button>
      {open && (
        <div className="pop absolute right-0 z-40 mt-2 w-[22rem] max-w-[calc(100vw-1.5rem)] rounded-xl border border-line bg-surface shadow-2xl">
          <div className="flex items-center justify-between border-b border-line px-4 py-3"><b className="text-sm">Notifications</b>{!!data?.unread && <button className="text-xs font-semibold text-primary" onClick={readAll}>Mark all read</button>}</div>
          <div className="scroll-thin max-h-80 overflow-y-auto">
            {!data?.items.length ? <p className="p-6 text-center text-sm text-muted">You're all caught up.</p> : data.items.map((n) => (
              <div key={n.id} className={clsx("border-b border-line/60 px-4 py-3 last:border-0", !n.read && "bg-soft/60")}><p className="text-sm font-semibold">{n.title}</p>{n.body && <p className="text-xs text-muted">{n.body}</p>}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function Shell() {
  const { user, logout } = useAuth();
  const theme = useTheme();
  const focus = useFocus();
  const loc = useLocation();
  const [menu, setMenu] = useState(false);
  const [ask, setAsk] = useState(false);
  useEffect(() => { setMenu(false); window.scrollTo(0, 0); }, [loc.pathname]);
  const toggleTheme = () => { theme.toggle(); put("/api/settings", { theme: theme.dark ? "light" : "dark" }).catch(() => {}); };

  return (
    <div className="min-h-full md:pl-60">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-line bg-surface p-4 md:flex">
        <Logo />
        <nav className="mt-6 flex-1 space-y-0.5" aria-label="Main">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => clsx("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors", isActive ? "bg-soft text-primary" : "text-muted hover:bg-sunken hover:text-ink")}>
              <n.icon className="h-[18px] w-[18px]" />{n.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-line pt-3">
          <div className="flex items-center gap-3 px-1"><span className="grid h-9 w-9 place-items-center rounded-full bg-soft font-display font-semibold text-primary">{user?.name[0]?.toUpperCase()}</span>
            <div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{user?.name}</p><p className="truncate text-xs text-muted">{user?.is_demo ? "Demo account" : user?.email}</p></div>
            <button className="btn-quiet !p-2" onClick={logout} aria-label="Log out"><LogOut className="h-4 w-4" /></button></div>
        </div>
      </aside>

      <header className="safe-top sticky top-0 z-20 border-b border-line bg-paper/85 backdrop-blur">
        <div className="flex h-14 items-center gap-2 px-4 md:px-8">
          <div className="md:hidden"><Logo /></div>
          <div className="ml-auto flex items-center gap-1.5">
            {focus.state && !focus.state.done && (
              <Link to="/focus" className="flex items-center gap-2 rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-primary-ink"><Timer className="h-3.5 w-3.5" /><span className="tnum">{mmss(focus.remainingMs)}</span><span className="hidden sm:inline">{focus.phase?.type === "break" ? "Break" : "Focusing"}</span></Link>
            )}
            <button className="btn-ghost !py-1.5" onClick={() => setAsk(true)}><Sparkles className="h-4 w-4 text-primary" /><span className="hidden sm:inline">Ask planner</span></button>
            <Bells />
            <button className="btn-quiet !p-2" onClick={toggleTheme} aria-label={theme.dark ? "Switch to light mode" : "Switch to dark mode"}>{theme.dark ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}</button>
          </div>
        </div>
        {user?.is_demo && (
          <div className="border-t border-line bg-amber/15 px-4 py-1.5 text-center text-xs md:px-8">
            <b>Demo Mode</b> — sample data for a fictional student, kept separate from real accounts and deleted after 24h. <Link className="font-semibold underline" to="/register" onClick={logout}>Create your own plan</Link>
          </div>
        )}
      </header>

      <main className="mx-auto max-w-6xl px-4 pb-28 pt-6 md:px-8 md:pb-12"><Outlet /></main>

      <nav className="safe-bottom fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-line bg-surface/95 backdrop-blur md:hidden" aria-label="Primary">
        {NAV.filter((n) => MOBILE.includes(n.to)).map((n) => (
          <NavLink key={n.to} to={n.to} className={({ isActive }) => clsx("flex flex-col items-center gap-0.5 py-2 text-[10.5px] font-medium", isActive ? "text-primary" : "text-muted")}><n.icon className="h-5 w-5" />{n.label.replace("Study ", "").replace("My ", "")}</NavLink>
        ))}
        <button onClick={() => setMenu(true)} className="flex flex-col items-center gap-0.5 py-2 text-[10.5px] font-medium text-muted"><Menu className="h-5 w-5" />More</button>
      </nav>

      {menu && (
        <div className="fixed inset-0 z-50 bg-ink/40 md:hidden" onClick={() => setMenu(false)}>
          <div className="pop safe-bottom absolute inset-x-0 bottom-0 rounded-t-2xl border border-line bg-surface p-4" onClick={(e) => e.stopPropagation()}>
            <div className="mb-2 flex items-center justify-between"><b>Menu</b><button className="btn-quiet !p-1.5" onClick={() => setMenu(false)} aria-label="Close menu"><X className="h-4 w-4" /></button></div>
            <div className="grid grid-cols-2 gap-2">
              {NAV.filter((n) => !MOBILE.includes(n.to)).map((n) => <NavLink key={n.to} to={n.to} className="flex items-center gap-2 rounded-lg border border-line px-3 py-3 text-sm font-medium"><n.icon className="h-4 w-4 text-primary" />{n.label}</NavLink>)}
              <button onClick={logout} className="flex items-center gap-2 rounded-lg border border-line px-3 py-3 text-sm font-medium"><LogOut className="h-4 w-4" />Log out</button>
            </div>
          </div>
        </div>
      )}

      {ask && (
        <div className="fixed inset-0 z-50 bg-ink/40" onClick={() => setAsk(false)}>
          <aside className="pop absolute inset-y-0 right-0 flex w-full max-w-md flex-col border-l border-line bg-surface p-4" onClick={(e) => e.stopPropagation()} aria-label="Planning assistant">
            <div className="mb-3 flex items-center justify-between"><h2 className="flex items-center gap-2 text-lg font-semibold"><Sparkles className="h-4 w-4 text-primary" />Planning assistant</h2><button className="btn-quiet !p-1.5" onClick={() => setAsk(false)} aria-label="Close"><X className="h-4 w-4" /></button></div>
            <div className="min-h-0 flex-1"><Assistant compact /></div>
          </aside>
        </div>
      )}
    </div>
  );
}
export { Banner };
