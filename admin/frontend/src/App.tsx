import { Routes, Route, Navigate } from "react-router";
import { lazy, Suspense } from "react";
import AppLayout from "./components/layout/AppLayout";

const VentsPage = lazy(() => import("./pages/VentsPage"));
const TimelineEditPage = lazy(() => import("./pages/TimelineEditPage"));
const TrolleysPage = lazy(() => import("./pages/TrolleysPage"));
const TrolleyEditPage = lazy(() => import("./pages/TrolleyEditPage"));
const DevicesPage = lazy(() => import("./pages/DevicesPage"));
const OrchestrationsPage = lazy(() => import("./pages/OrchestrationsPage"));
const OrchestrationEditPage = lazy(() => import("./pages/OrchestrationEditPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const AboutPage = lazy(() => import("./pages/AboutPage"));
const FAQPage = lazy(() => import("./pages/FAQPage"));
const DocsPage = lazy(() => import("./pages/DocsPage"));
const BridgePage = lazy(() => import("./pages/BridgePage"));

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
        <Route index element={<Navigate to="/vents" replace />} />
        <Route
          path="vents"
          element={
            <Suspense fallback={<Loading />}>
              <VentsPage />
            </Suspense>
          }
        />
        {/* Bookmark compat: /timelines used to be the vents landing. */}
        <Route path="timelines" element={<Navigate to="/vents" replace />} />
        <Route
          path="timelines/:id"
          element={
            <Suspense fallback={<Loading />}>
              <TimelineEditPage />
            </Suspense>
          }
        />
        <Route
          path="trolleys"
          element={
            <Suspense fallback={<Loading />}>
              <TrolleysPage />
            </Suspense>
          }
        />
        <Route
          path="trolleys/:id"
          element={
            <Suspense fallback={<Loading />}>
              <TrolleyEditPage />
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
        <Route
          path="about"
          element={
            <Suspense fallback={<Loading />}>
              <AboutPage />
            </Suspense>
          }
        />
        <Route
          path="faq"
          element={
            <Suspense fallback={<Loading />}>
              <FAQPage />
            </Suspense>
          }
        />
        <Route
          path="docs"
          element={
            <Suspense fallback={<Loading />}>
              <DocsPage />
            </Suspense>
          }
        />
        <Route
          path="bridge"
          element={
            <Suspense fallback={<Loading />}>
              <BridgePage />
            </Suspense>
          }
        />
      </Route>
    </Routes>
  );
}
