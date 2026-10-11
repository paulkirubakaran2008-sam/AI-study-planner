import { useQueryClient } from "@tanstack/react-query";
import { Check, Send, Sparkles } from "lucide-react";
import { useRef, useState } from "react";
import { post } from "../lib/api";
import type { Interpretation } from "../lib/types";
import { clsx } from "../lib/util";
import { Spinner } from "./ui";

interface Msg { role: "me" | "bot"; text: string; pending?: Interpretation; applied?: { ok: boolean; message: string }[]; done?: boolean }
const SUGGEST = ["Study Trees tomorrow for 1 hour", "Move Python to Saturday", "Give me 30 minutes of revision tonight", "I cannot study tomorrow", "Make my plan easier"];

export function Assistant({ compact }: { compact?: boolean }) {
  const [msgs, setMsgs] = useState<Msg[]>([{ role: "bot", text: "Tell me what to change. I'll show exactly what I'll do before anything is saved." }]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const qc = useQueryClient();
  const end = useRef<HTMLDivElement>(null);
  const scroll = () => setTimeout(() => end.current?.scrollIntoView({ behavior: "smooth", block: "end" }), 50);

  const send = async (t: string) => {
    if (!t.trim() || busy) return;
    setText(""); setBusy(true);
    setMsgs((m) => [...m, { role: "me", text: t }]); scroll();
    try {
      const r = await post<Interpretation>("/api/assistant/interpret", { text: t });
      setMsgs((m) => [...m, { role: "bot", text: r.reply || (r.understood ? "Here's what I'll do:" : "I couldn't do that."), pending: r.understood ? r : undefined }]);
      if (r.errors?.length) setMsgs((m) => [...m, { role: "bot", text: r.errors.join(" ") }]);
    } catch (e) { setMsgs((m) => [...m, { role: "bot", text: (e as Error).message }]); }
    setBusy(false); scroll();
  };
  const apply = async (i: number) => {
    const p = msgs[i].pending!;
    setBusy(true);
    try {
      const r = await post<{ results: { ok: boolean; message: string }[] }>("/api/assistant/apply", { actions: p.actions });
      setMsgs((m) => m.map((x, j) => (j === i ? { ...x, done: true, applied: r.results } : x)));
      qc.invalidateQueries();
    } catch (e) { setMsgs((m) => [...m, { role: "bot", text: (e as Error).message }]); }
    setBusy(false); scroll();
  };

  return (
    <div className={clsx("flex flex-col", compact ? "h-full" : "h-[34rem]")}>
      <div className="scroll-thin flex-1 space-y-3 overflow-y-auto pr-1" aria-live="polite">
        {msgs.map((m, i) => (
          <div key={i} className={clsx("flex", m.role === "me" && "justify-end")}>
            <div className={clsx("max-w-[88%] rounded-2xl px-3.5 py-2.5 text-sm", m.role === "me" ? "bg-primary text-primary-ink" : "bg-sunken")}>
              <p>{m.text}</p>
              {m.pending && !m.done && (
                <div className="mt-2 rounded-lg border border-line bg-surface p-2.5 text-ink">
                  <ul className="space-y-1">{m.pending.descriptions.map((d, k) => <li key={k} className="flex gap-2"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />{d}</li>)}</ul>
                  <div className="mt-2.5 flex items-center gap-2"><button className="btn-primary !py-1.5" disabled={busy} onClick={() => apply(i)}>Apply changes</button><button className="btn-quiet !py-1.5" onClick={() => setMsgs((x) => x.map((y, j) => (j === i ? { ...y, done: true, applied: [] } : y)))}>Dismiss</button>
                    <span className="ml-auto text-[10px] uppercase tracking-wide text-muted">{m.pending.source === "ai" ? "AI-parsed · validated" : "Rule-parsed"}</span></div>
                </div>
              )}
              {m.applied && m.applied.length > 0 && <ul className="mt-2 space-y-1">{m.applied.map((a, k) => <li key={k} className={clsx("text-xs", a.ok ? "text-low" : "text-crit")}>{a.ok ? "✓" : "✕"} {a.message}</li>)}</ul>}
            </div>
          </div>
        ))}
        {busy && <div className="flex items-center gap-2 text-xs text-muted"><Spinner />Working…</div>}
        <div ref={end} />
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">{SUGGEST.slice(0, compact ? 3 : 5).map((s) => <button key={s} className="chip hover:bg-sunken" onClick={() => send(s)}>{s}</button>)}</div>
      <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); send(text); }}>
        <input className="input" value={text} maxLength={400} onChange={(e) => setText(e.target.value)} placeholder="e.g. I can't study tomorrow" aria-label="Ask the planning assistant" />
        <button className="btn-primary" disabled={busy || !text.trim()} aria-label="Send"><Send className="h-4 w-4" /></button>
      </form>
      <p className="mt-2 flex items-center gap-1 text-[11px] text-muted"><Sparkles className="h-3 w-3" />Common requests are parsed locally for free. Anything else may use a small AI call, and its output is validated before it can touch your plan.</p>
    </div>
  );
}
