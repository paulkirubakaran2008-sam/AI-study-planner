import type { Priority } from "./types";

export const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export const parseISO = (s: string) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
export const addDays = (d: Date, n: number) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
export const startOfWeek = (d: Date) => addDays(d, -((d.getDay() + 6) % 7));
export const todayISO = () => iso(new Date());
export const fmtDay = (s: string, o: Intl.DateTimeFormatOptions = { weekday: "short", day: "numeric", month: "short" }) => parseISO(s).toLocaleDateString("en-IN", o);
export const fmtLong = (s: string) => parseISO(s).toLocaleDateString("en-IN", { weekday: "long", month: "long", day: "numeric" });
export const mins = (m: number) => { const h = Math.floor(m / 60), r = Math.round(m % 60); return h ? (r ? `${h}h ${r}m` : `${h}h`) : `${r}m`; };
export const hm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
export const toMin = (t: string) => { const [h, m] = t.split(":").map(Number); return h * 60 + m; };
export const tz = () => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch { return "Asia/Kolkata"; } };
export const clsx = (...a: (string | false | null | undefined)[]) => a.filter(Boolean).join(" ");
export const time12 = (t: string) => { const [h, m] = t.split(":").map(Number); return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`; };

export const PRIORITY: Record<Priority, { label: string; icon: string; text: string; bg: string; bar: string }> = {
  critical: { label: "Critical", icon: "🔴", text: "text-crit", bg: "bg-crit/10", bar: "bg-crit" },
  high: { label: "High", icon: "🟠", text: "text-high", bg: "bg-high/10", bar: "bg-high" },
  medium: { label: "Medium", icon: "🟡", text: "text-med", bg: "bg-med/10", bar: "bg-med" },
  low: { label: "Low", icon: "🟢", text: "text-low", bg: "bg-low/10", bar: "bg-low" },
};
export const masteryDot = (m: number) => (m >= 70 ? "🟢" : m >= 45 ? "🟡" : "🔴");
export const masteryTone = (m: number) => (m >= 70 ? "bg-low" : m >= 45 ? "bg-med" : "bg-crit");
export const STATUS_LABEL: Record<string, string> = { pending: "Pending", in_progress: "In progress", completed: "Completed", skipped: "Skipped", overdue: "Overdue" };
export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
