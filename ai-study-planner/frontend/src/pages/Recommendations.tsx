import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Lightbulb, Sparkles, X } from "lucide-react";
import { useState } from "react";
import { Assistant } from "../components/Assistant";
import { Banner, Empty, ErrorNote, PageHeader, Skeleton, Spinner, useToast } from "../components/ui";
import { post } from "../lib/api";
import { useRecs } from "../lib/hooks";
import type { Recommendation } from "../lib/types";
import { clsx } from "../lib/util";

const TONE = { urgent: "border-crit/40", warn: "border-high/40", info: "border-line" } as const;
const UNAVAILABLE = "AI recommendations are temporarily unavailable. Your normal study planner is still working.";

function RecCard({ r, aiOn }: { r: Recommendation; aiOn: boolean }) {
  const qc = useQueryClient(); const toast = useToast(); const [why, setWhy] = useState(false); const [note, setNote] = useState<string | null>(r.ai_explanation); const [unavail, setUnavail] = useState(false);
  const done = () => qc.invalidateQueries();
  const apply = useMutation({ mutationFn: () => post<{ results: { ok: boolean; message: string }[] }>(`/api/recommendations/${r.id}/apply`), onSuccess: (x) => { toast(x.results.map((y) => y.message).join(" ")); done(); }, onError: (e) => toast((e as Error).message, "err") });
  const dismiss = useMutation({ mutationFn: () => post(`/api/recommendations/${r.id}/dismiss`), onSuccess: done });
  const explain = useMutation({ mutationFn: () => post<{ available: boolean; explanation?: string }>(`/api/recommendations/${r.id}/explain`), onSuccess: (x) => (x.available ? setNote(x.explanation ?? null) : setUnavail(true)), onError: () => setUnavail(true) });
  return (
    <article className={clsx("card p-5", TONE[r.severity])}>
      <div className="flex items-start gap-3">
        <span className={clsx("mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg", r.severity === "info" ? "bg-soft text-primary" : "bg-high/15 text-high")}>{r.severity === "info" ? <Lightbulb className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}</span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">🤖 Recommendation</p>
          <h3 className="mt-0.5 font-display text-lg font-semibold">{r.title}</h3><p className="mt-1 text-sm">{r.body}</p>
          <button className="mt-2 text-xs font-semibold text-primary" onClick={() => setWhy(!why)}>{why ? "Hide" : "Why am I seeing this?"}</button>
          {why && <p className="mt-1.5 rounded-lg bg-sunken p-3 text-sm text-muted">{r.reason}</p>}
          {note && <p className="mt-2 rounded-lg border border-primary/25 bg-soft p-3 text-sm"><Sparkles className="mr-1 inline h-3.5 w-3.5 text-primary" />{note}</p>}
          {unavail && <p className="mt-2 text-xs text-muted">{UNAVAILABLE}</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            {r.action && <button className="btn-primary !py-1.5" disabled={apply.isPending} onClick={() => apply.mutate()}>{apply.isPending && <Spinner />}Apply</button>}
            {aiOn && !note && <button className="btn-ghost !py-1.5" disabled={explain.isPending} onClick={() => explain.mutate()}>{explain.isPending ? <Spinner /> : <Sparkles className="h-3.5 w-3.5" />}Explain with AI</button>}
            <button className="btn-quiet !py-1.5" onClick={() => dismiss.mutate()}><X className="h-3.5 w-3.5" />Dismiss</button>
          </div>
        </div>
      </div>
    </article>
  );
}

export default function Recommendations() {
  const { data, error, isLoading, refetch } = useRecs();
  const [tips, setTips] = useState<string[] | null>(null); const [unavail, setUnavail] = useState(false);
  const strat = useMutation({ mutationFn: () => post<{ available: boolean; tips?: string[] }>("/api/recommendations/strategy"), onSuccess: (x) => (x.available ? (setTips(x.tips ?? []), setUnavail(false)) : setUnavail(true)), onError: () => setUnavail(true) });
  const ai = data?.ai;
  return (
    <div>
      <PageHeader title="AI Recommendations" sub="Specific, explained suggestions from your own study data." actions={ai && <span className="chip">{ai.enabled ? `AI on · ${ai.used}/${ai.limit} calls today` : "Rule-based mode · AI off"}</span>} />
      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <div className="space-y-4">
          {unavail && <Banner tone="warn">{UNAVAILABLE}</Banner>}
          {error ? <ErrorNote error={error} retry={() => refetch()} /> : isLoading ? <><Skeleton className="h-36" /><Skeleton className="h-36" /></> :
            !data?.items.length ? <Empty icon={<Sparkles className="h-8 w-8" />} title="You're on track" text="No recommendations right now. They appear when something in your plan or progress needs attention." /> : data.items.map((r) => <RecCard key={r.id} r={r} aiOn={!!ai?.enabled} />)}
          <section className="card p-5">
            <h2 className="flex items-center gap-2 text-lg font-semibold"><Sparkles className="h-4 w-4 text-primary" />Weekly strategy</h2>
            <p className="mt-1 text-sm text-muted">Three tips from your last 7 days. One small AI call, cached for the day.</p>
            {tips && <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-sm">{tips.map((t, i) => <li key={i}>{t}</li>)}</ol>}
            {ai?.enabled ? <button className="btn-ghost mt-3" disabled={strat.isPending} onClick={() => strat.mutate()}>{strat.isPending && <Spinner />}{tips ? "Refresh tips" : "Get weekly strategy"}</button> : <p className="mt-3 rounded-lg bg-sunken p-3 text-sm text-muted">AI is not configured on this server, so this is switched off. Everything above still works because it's rule-based.</p>}
          </section>
        </div>
        <section className="card h-fit p-5"><h2 className="mb-3 text-lg font-semibold">Planning assistant</h2><Assistant /></section>
      </div>
    </div>
  );
}
