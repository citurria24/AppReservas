import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "../layouts/AppLayout";
import { ErrorState, LoadingSkeleton } from "../components/ui/primitives";
const AgendaPage = lazy(() =>
  import("../pages/AgendaPage").then((module) => ({
    default: module.AgendaPage,
  })),
);
const StatisticsPage = lazy(() =>
  import("../pages/StatisticsPage").then((module) => ({
    default: module.StatisticsPage,
  })),
);
export function App() {
  return (
    <BrowserRouter basename="/app">
      <Suspense
        fallback={
          <main className="login-state">
            <LoadingSkeleton />
          </main>
        }
      >
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<Navigate to="/agenda" replace />} />
            <Route path="agenda" element={<AgendaPage />} />
            <Route path="estadisticas/:slug" element={<StatisticsPage />} />
            <Route
              path="*"
              element={<ErrorState message="No encontramos esta página." />}
            />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
