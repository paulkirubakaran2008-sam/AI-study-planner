import { X, Loader2, AlertTriangle, CheckCircle2, Info } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { clsx, mins } from "../lib/util";

export function Spinner({ className }: { className?: string }) { return <Loader2 className={clsx("h-4 w-4 animate-spin", className)} aria-label="Loading" />; }
export const Skeleton = ({ className }: { className?: string }) => <div className={clsx("skeleton", className)} aria-hidden />;

export function PageHeader({ title, sub, actions }: { title: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div><h1 className="text-2xl font-semibold sm:text-3xl">{title}</h1>{sub && <p className="mt-1 text-sm text-muted">{sub}</p>}</div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Empty({ icon, title, text, action }: { icon?: ReactNode; title: string; text?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-line px-6 py-10 text-center">
      {icon && <div className="mb-3 text-muted">{icon}</div>}
      <p className="font-display text-lg font-semibold">{title}</p>
      {text && <p className="mt-1 max-w-sm text-sm text-muted">{text}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorNote({ error, retry }: { error: unknown; retry?: () => void }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl border border-crit/30 bg-crit/10 p-4 text-sm">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-crit" />
      <div className="flex-1"><p className="font-semibold text-crit">Couldn't load this</p><p className="text-muted">{(error as Error)?.message || "Please try again."}</p></div>
      {retry && <button className="btn-ghost" onClick={retry}>Retry</button>}
    </div>
  );
}

export function Banner({ tone = "info", children, action }: { tone?: "info" | "warn" | "good" | "bad"; children: ReactNode; action?: ReactNode }) {
  const t = { info: "border-primary/30 bg-soft", warn: "border-high/40 bg-high/10", good: "border-low/40 bg-low/10", bad: "border-crit/40 bg-crit/10" }[tone];
  const Icon = tone === "good" ? CheckCircle2 : tone === "info" ? Info : AlertTriangle;
  return (
    <div className={clsx("flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 text-sm", t)}>
      <Icon className="h-4 w-4 shrink-0" /><div className="min-w-0 flex-1">{children}</div>{action}
    </div>
  );
}

export function Modal({ open, onClose, title, children, wide, locked }: { open: boolean; onClose: () => void; title: string; children: ReactNode; wide?: boolean; locked?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && !locked && onClose();
    window.addEventListener("keydown", k);
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", k); document.body.style.overflow = ""; };
  }, [open, onClose, locked]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 p-0 backdrop-blur-[2px] sm:items-center sm:p-4" onMouseDown={(e) => e.target === e.currentTarget && !locked && onClose()}>
      <div role="dialog" aria-modal="true" aria-label={title} className={clsx("pop max-h-[92dvh] w-full overflow-y-auto rounded-t-2xl border border-line bg-surface p-5 shadow-2xl sm:rounded-2xl", wide ? "sm:max-w-2xl" : "sm:max-w-md")}>
        <div className="mb-4 flex items-center justify-between"><h2 className="text-lg font-semibold">{title}</h2>
          {!locked && <button className="btn-quiet !p-1.5" onClick={onClose} aria-label="Close"><X className="h-4 w-4" /></button>}</div>
        {children}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- toasts
interface Toast { id: number; text: string; tone: "ok" | "err" }
const ToastCtx = createContext<(text: string, tone?: "ok" | "err") => void>(() => {});
export const useToast = () => useContext(ToastCtx);
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: "ok" | "err" = "ok") => {
    const id = Date.now() + Math.random();
    setItems((s) => [...s.slice(-3), { id, text, tone }]);
    setTimeout(() => setItems((s) => s.filter((x) => x.id !== id)), 4500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-20 z-[60] flex flex-col items-center gap-2 px-4 md:bottom-6" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={clsx("pop pointer-events-auto max-w-md rounded-lg border px-4 py-2.5 text-sm shadow-lg", t.tone === "ok" ? "border-line bg-ink text-paper" : "border-crit bg-crit text-white")}>{t.text}</div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

// ---------------------------------------------------------------- charts (hand-rolled SVG/CSS: no chart library)
export function Ring({ value, size = 96, stroke = 9, label, sub, color = "rgb(var(--primary))" }: { value: number; size?: number; stroke?: number; label?: ReactNode; sub?: string; color?: string }) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, value));
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} role="img" aria-label={`${v}%`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgb(var(--sunken))" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - v / 100)} style={{ transition: "stroke-dashoffset .7s ease" }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center"><span className="font-display text-xl font-semibold tnum leading-none">{label ?? `${v}%`}</span>{sub && <span className="mt-0.5 text-[10px] text-muted">{sub}</span>}</div>
    </div>
  );
}

export function Bar({ value, tone = "bg-primary", h = "h-2" }: { value: number; tone?: string; h?: string }) {
  return <div className={clsx("w-full overflow-hidden rounded-full bg-sunken", h)}><div className={clsx("h-full rounded-full transition-all duration-500", tone)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div>;
}

export function GroupedBars({ data, labelKey = "label" }: { data: { label: string; planned: number; actual: number }[]; labelKey?: string }) {
  const max = Math.max(60, ...data.flatMap((d) => [d.planned, d.actual]));
  return (
    <div>
      <div className="flex h-44 items-end gap-1.5 sm:gap-3" role="img" aria-label="Planned versus actual study time per day">
        {data.map((d, i) => (
          <div key={i} className="group relative flex h-full min-w-0 flex-1 items-end justify-center gap-[3px]">
            <div className="w-full max-w-[18px] rounded-t bg-line" style={{ height: `${(d.planned / max) * 100}%`, minHeight: d.planned ? 3 : 0 }} />
            <div className="w-full max-w-[18px] rounded-t bg-primary" style={{ height: `${(d.actual / max) * 100}%`, minHeight: d.actual ? 3 : 0 }} />
            <div className="pointer-events-none absolute -top-9 z-10 hidden whitespace-nowrap rounded-md bg-ink px-2 py-1 text-xs text-paper shadow group-hover:block">{mins(d.actual)} of {mins(d.planned)}</div>
          </div>
        ))}
      </div>
      <div className="mt-2 flex gap-1.5 sm:gap-3">{data.map((d, i) => <div key={i} className="min-w-0 flex-1 truncate text-center text-[11px] text-muted">{d.label}</div>)}</div>
      <div className="mt-3 flex gap-4 text-xs text-muted"><span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-sm bg-line" />Planned</span><span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-sm bg-primary" />Studied</span></div>
    </div>
  );
}

export function Donut({ parts, size = 150 }: { parts: { value: number; color: string; name: string }[]; size?: number }) {
  const total = parts.reduce((a, b) => a + b.value, 0) || 1, r = size / 2 - 12, c = 2 * Math.PI * r;
  let off = 0;
  return (
    <svg width={size} height={size} className="-rotate-90" role="img" aria-label="Subject distribution">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgb(var(--sunken))" strokeWidth={18} />
      {parts.map((p, i) => { const len = (p.value / total) * c; const el = <circle key={i} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={p.color} strokeWidth={18} strokeDasharray={`${Math.max(0, len - 2)} ${c}`} strokeDashoffset={-off} />; off += len; return el; })}
    </svg>
  );
}

export function Segmented<T extends string | number>({ value, options, onChange }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex rounded-lg border border-line bg-sunken p-0.5" role="tablist">
      {options.map((o) => (
        <button key={String(o.value)} role="tab" aria-selected={o.value === value} onClick={() => onChange(o.value)}
          className={clsx("rounded-md px-3 py-1.5 text-sm font-medium transition-colors", o.value === value ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink")}>{o.label}</button>
      ))}
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return <label className="block"><span className="label">{label}</span>{children}{hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}</label>;
}

export function Confirm({ open, title, text, confirmLabel = "Delete", onConfirm, onClose }: { open: boolean; title: string; text: string; confirmLabel?: string; onConfirm: () => void; onClose: () => void }) {
  return (
    <Modal open={open} onClose={onClose} title={title}>
      <p className="text-sm text-muted">{text}</p>
      <div className="mt-5 flex justify-end gap-2"><button className="btn-ghost" onClick={onClose}>Cancel</button><button className="btn-danger" onClick={() => { onConfirm(); onClose(); }}>{confirmLabel}</button></div>
    </Modal>
  );
}
