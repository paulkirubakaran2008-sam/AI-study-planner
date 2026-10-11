import { ArrowLeft } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Field, Spinner } from "../components/ui";
import { useAuth } from "../lib/auth";

function Frame({ title, sub, children, foot }: { title: string; sub: string; children: ReactNode; foot: ReactNode }) {
  return (
    <div className="grid min-h-full lg:grid-cols-2">
      <div className="flex flex-col px-5 py-6 sm:px-10">
        <Link to="/" className="flex w-fit items-center gap-1.5 text-sm text-muted hover:text-ink"><ArrowLeft className="h-4 w-4" />Back</Link>
        <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-10">
          <h1 className="text-3xl font-semibold">{title}</h1><p className="mb-6 mt-1.5 text-sm text-muted">{sub}</p>
          {children}<div className="mt-6 text-sm text-muted">{foot}</div>
        </div>
      </div>
      <div className="relative hidden overflow-hidden bg-primary lg:block">
        <div className="absolute inset-0 opacity-20" style={{ backgroundImage: "repeating-linear-gradient(0deg, transparent 0 55px, rgba(255,255,255,.5) 55px 56px)" }} />
        <div className="relative flex h-full flex-col justify-end p-12 text-primary-ink">
          <p className="font-display text-4xl font-semibold leading-tight">A schedule that notices when you miss a session — and rebuilds around it.</p>
          <p className="mt-3 max-w-md text-sm opacity-80">Built from your exams, your free hours, and what you actually finish.</p>
        </div>
      </div>
    </div>
  );
}

function useSubmit(fn: () => Promise<unknown>) {
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false); const nav = useNavigate();
  return { err, busy, setErr, submit: async (e: FormEvent) => { e.preventDefault(); setErr(""); setBusy(true); try { await fn(); nav("/dashboard"); } catch (x) { setErr((x as Error).message); setBusy(false); } } };
}

export function DemoButton({ className = "btn-ghost w-full" }: { className?: string }) {
  const { demo } = useAuth(); const [busy, setBusy] = useState(false); const [err, setErr] = useState(""); const nav = useNavigate();
  return (<>
    <button type="button" className={className} disabled={busy} onClick={async () => { setBusy(true); setErr(""); try { await demo(); nav("/dashboard"); } catch (e) { setErr((e as Error).message); setBusy(false); } }}>{busy && <Spinner />}Try the demo</button>
    {err && <p role="alert" className="mt-2 text-sm text-crit">{err}</p>}
  </>);
}

export function Login() {
  const { login } = useAuth(); const [email, setEmail] = useState(""); const [pw, setPw] = useState("");
  const { err, busy, submit } = useSubmit(() => login(email, pw));
  return (
    <Frame title="Welcome back" sub="Log in to see today's plan." foot={<>New here? <Link className="font-semibold text-primary" to="/register">Create an account</Link></>}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Email"><input className="input" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <Field label="Password"><input className="input" type="password" autoComplete="current-password" required value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
        {err && <p role="alert" className="text-sm text-crit">{err}</p>}
        <button className="btn-primary w-full" disabled={busy}>{busy && <Spinner />}Log in</button>
      </form>
      <div className="my-4 flex items-center gap-3 text-xs text-muted"><i className="h-px flex-1 bg-line" />or<i className="h-px flex-1 bg-line" /></div>
      <DemoButton />
    </Frame>
  );
}

export function Register() {
  const { register } = useAuth(); const [f, setF] = useState({ name: "", email: "", pw: "" });
  const { err, busy, submit } = useSubmit(() => register(f.name, f.email, f.pw));
  return (
    <Frame title="Create your study plan" sub="Takes about two minutes. Free." foot={<>Already have an account? <Link className="font-semibold text-primary" to="/login">Log in</Link></>}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Your name"><input className="input" autoComplete="name" required maxLength={80} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Email"><input className="input" type="email" autoComplete="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="Password" hint="At least 8 characters. Stored hashed (bcrypt), never in plain text."><input className="input" type="password" autoComplete="new-password" required minLength={8} maxLength={72} value={f.pw} onChange={(e) => setF({ ...f, pw: e.target.value })} /></Field>
        {err && <p role="alert" className="text-sm text-crit">{err}</p>}
        <button className="btn-primary w-full" disabled={busy}>{busy && <Spinner />}Create account</button>
      </form>
      <div className="my-4 flex items-center gap-3 text-xs text-muted"><i className="h-px flex-1 bg-line" />or<i className="h-px flex-1 bg-line" /></div>
      <DemoButton />
    </Frame>
  );
}
