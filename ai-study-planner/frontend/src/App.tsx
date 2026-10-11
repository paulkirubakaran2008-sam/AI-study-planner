import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Shell from "./components/Shell";
import { Spinner } from "./components/ui";
import { useAuth } from "./lib/auth";
import Landing from "./pages/Landing";
import { Login, Register } from "./pages/Auth";

const Onboarding = lazy(() => import("./pages/Onboarding"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Subjects = lazy(() => import("./pages/Subjects"));
const Planner = lazy(() => import("./pages/Planner"));
const CalendarPage = lazy(() => import("./pages/Calendar"));
const Tasks = lazy(() => import("./pages/Tasks"));
const Focus = lazy(() => import("./pages/Focus"));
const Analytics = lazy(() => import("./pages/Analytics"));
const Recommendations = lazy(() => import("./pages/Recommendations"));
const SettingsPage = lazy(() => import("./pages/Settings"));

const Loading = () => <div className="grid h-full min-h-[50vh] place-items-center text-muted"><Spinner className="h-6 w-6" /></div>;

function Guard({ children, needOnboarded = true }: { children: ReactNode; needOnboarded?: boolean }) {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace />;
  if (needOnboarded && !user.onboarded) return <Navigate to="/onboarding" replace />;
  return <>{children}</>;
}
function Guest({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (user) return <Navigate to={user.onboarded ? "/dashboard" : "/onboarding"} replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Guest><Login /></Guest>} />
        <Route path="/register" element={<Guest><Register /></Guest>} />
        <Route path="/onboarding" element={<Guard needOnboarded={false}><Onboarding /></Guard>} />
        <Route element={<Guard><Shell /></Guard>}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/subjects" element={<Subjects />} />
          <Route path="/planner" element={<Planner />} />
          <Route path="/calendar" element={<CalendarPage />} />
          <Route path="/tasks" element={<Tasks />} />
          <Route path="/focus" element={<Focus />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/recommendations" element={<Recommendations />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
