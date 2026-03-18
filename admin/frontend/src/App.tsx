import { Routes, Route, Navigate } from "react-router";
import { lazy, Suspense } from "react";
import AppLayout from "./components/layout/AppLayout";

const TimelinesPage = lazy(() => import("./pages/TimelinesPage"));
const TimelineEditPage = lazy(() => import("./pages/TimelineEditPage"));
const DevicesPage = lazy(() => import("./pages/DevicesPage"));
const OrchestrationsPage = lazy(() => import("./pages/OrchestrationsPage"));
const OrchestrationEditPage = lazy(() => import("./pages/OrchestrationEditPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));

function Loading() {
  return (
    <div className="flex-1 flex items-center justify-center text-zinc-500">
      Loading…
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/timelines" replace />} />
        <Route
          path="timelines"
          element={
            <Suspense fallback={<Loading />}>
              <TimelinesPage />
            </Suspense>
          }
        />
        <Route
          path="timelines/:id"
          element={
            <Suspense fallback={<Loading />}>
              <TimelineEditPage />
            </Suspense>
          }
        />
        <Route
          path="devices"
          element={
            <Suspense fallback={<Loading />}>
              <DevicesPage />
            </Suspense>
          }
        />
        <Route
          path="orchestrations"
          element={
            <Suspense fallback={<Loading />}>
              <OrchestrationsPage />
            </Suspense>
          }
        />
        <Route
          path="orchestrations/:id"
          element={
            <Suspense fallback={<Loading />}>
              <OrchestrationEditPage />
            </Suspense>
          }
        />
        <Route
          path="settings"
          element={
            <Suspense fallback={<Loading />}>
              <SettingsPage />
            </Suspense>
          }
        />
      </Route>
    </Routes>
  );
}
