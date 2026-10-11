import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setUnauthorizedHandler, tokenStore } from "./api";
import type { User } from "./types";
import { tz } from "./util";

interface AuthCtx { user: User | null; loading: boolean; login: (e: string, p: string) => Promise<User>; register: (n: string, e: string, p: string) => Promise<User>; demo: () => Promise<User>; logout: () => void; refresh: () => Promise<void> }
const Ctx = createContext<AuthCtx>(null!);
export const useAuth = () => useContext(Ctx);

interface TokenOut { access_token: string; user: User }

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(!!tokenStore.get());
  const qc = useQueryClient();

  const logout = useCallback(() => { tokenStore.clear(); setUser(null); qc.clear(); }, [qc]);
  const refresh = useCallback(async () => { setUser(await api<User>("/api/auth/me")); }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    if (!tokenStore.get()) return;
    refresh().catch(() => tokenStore.clear()).finally(() => setLoading(false));
  }, [logout, refresh]);

  const accept = (r: TokenOut) => { tokenStore.set(r.access_token); qc.clear(); setUser(r.user); return r.user; };
  const value: AuthCtx = {
    user, loading, logout, refresh,
    login: async (email, password) => accept(await api<TokenOut>("/api/auth/login", { method: "POST", body: { email, password }, auth: false })),
    register: async (name, email, password) => accept(await api<TokenOut>("/api/auth/register", { method: "POST", body: { name, email, password, timezone: tz() }, auth: false })),
    demo: async () => accept(await api<TokenOut>("/api/demo/start", { method: "POST", body: { timezone: tz() }, auth: false })),
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  const set = useCallback((d: boolean) => {
    document.documentElement.classList.toggle("dark", d);
    localStorage.setItem("asp_theme", d ? "dark" : "light");
    setDark(d);
  }, []);
  return { dark, set, toggle: () => set(!dark) };
}
