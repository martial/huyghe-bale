import { useEffect, useState } from "react";
import {
  getHealth,
  type HealthStatus,
  type VentsOverTempItem,
  type VentsProbeUnassignedItem,
} from "../../api/health";

type Warning = {
  title: string;
  detail: string;
  hint?: React.ReactNode;
};

function collectCriticalWarnings(h: HealthStatus): Warning[] {
  const out: Warning[] = [];

  if (!h.osc_receiver.running) {
    out.push({
      title: "OSC Receiver",
      detail: h.osc_receiver.error ?? "not running",
      hint: (
        <>
          Device heartbeat is offline. Fix:{" "}
          <code className="bg-red-950/60 px-1.5 py-0.5 rounded text-red-200 text-xs font-mono">
            kill $(lsof -ti:{h.osc_receiver.port})
          </code>{" "}
          then relaunch.
        </>
      ),
    });
  }

  if (h.bridge.error) {
    out.push({
      title: "OSC Bridge",
      detail: h.bridge.error,
      hint: h.bridge.port ? (
        <>
          Port{" "}
          <code className="bg-red-950/60 px-1.5 py-0.5 rounded text-red-200 text-xs font-mono">{h.bridge.port}</code>{" "}
          may already be in use.
        </>
      ) : null,
    });
  }

  if (h.playback.last_error) {
    out.push({
      title: "Playback",
      detail: h.playback.last_error,
      hint: <>Playback stopped. Restart the timeline once the underlying issue is fixed.</>,
    });
  }

  return out;
}

function formatThermalDetail(v: VentsOverTempItem): string {
  const parts: string[] = [
    `${v.name}: state over_temp (any probe above safety max) — Peltiers off; fans pinned to over_temp_fan_pct.`,
  ];
  // Prefer the dual-setpoint view (hot/cold split) when the firmware sends
  // it; fall back to the legacy avg-vs-single-target line.
  if (typeof v.temp_hot_c === "number" || typeof v.temp_cold_c === "number") {
    const segs: string[] = [];
    if (typeof v.temp_hot_c === "number" && typeof v.hot_target_c === "number") {
      segs.push(`hot ${v.temp_hot_c.toFixed(1)}°C / target ${v.hot_target_c.toFixed(1)}°C`);
    }
    if (typeof v.temp_cold_c === "number" && typeof v.cold_target_c === "number") {
      segs.push(`cold ${v.temp_cold_c.toFixed(1)}°C / target ${v.cold_target_c.toFixed(1)}°C`);
    }
    if (segs.length) parts.push(segs.join(", "));
  } else {
    const nums = [v.temp1_c, v.temp2_c].filter((x): x is number => typeof x === "number");
    if (nums.length && v.target_c != null) {
      const avg = nums.reduce((a, b) => a + b, 0) / nums.length;
      parts.push(`avg ≈ ${avg.toFixed(1)}°C, target ${v.target_c.toFixed(1)}°C`);
    }
  }
  if (typeof v.max_temp_c === "number") {
    parts.push(`max threshold ${v.max_temp_c.toFixed(1)}°C`);
  }
  return parts.join(" ");
}

function formatProbeUnassignedDetail(v: VentsProbeUnassignedItem): string {
  const missing: string[] = [];
  if (v.probe_hot_id == null) missing.push("hot");
  if (v.probe_cold_id == null) missing.push("cold");
  const parts = [`${v.name}: ${missing.length ? missing.join(" + ") + " probe(s) need assignment" : "assigned probes not currently on bus"}`];
  if (v.discovered.length) {
    parts.push(`${v.discovered.length} probe(s) discovered`);
  } else {
    parts.push("no probes detected");
  }
  return parts.join(" — ");
}

export default function SystemWarnings() {
  const [health, setHealth] = useState<HealthStatus | null>(null);

  useEffect(() => {
    const poll = () => {
      getHealth()
        .then(setHealth)
        .catch(() => {
          // Keep the last-known state on a transient fetch failure so the
          // banner doesn't flicker in/out every poll.
        });
    };
    poll();
    const timer = setInterval(poll, 10_000);
    return () => clearInterval(timer);
  }, []);

  if (!health) return null;

  const thermal = health.vents_over_temp ?? [];
  const probeUnassigned = health.vents_probe_unassigned ?? [];
  const critical = collectCriticalWarnings(health);

  if (thermal.length === 0 && probeUnassigned.length === 0 && critical.length === 0) return null;

  return (
    <>
      {probeUnassigned.length > 0 && (
        <div className="bg-amber-950/80 backdrop-blur border-b border-amber-500/35 text-amber-100">
          {probeUnassigned.map((v, i) => (
            <div
              key={`pu-${v.device_id}-${i}`}
              className="px-5 py-3 flex items-start gap-3 border-b border-amber-500/20 last:border-b-0"
            >
              <svg
                className="w-5 h-5 mt-0.5 shrink-0 text-amber-300"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 17l3-3-3-3M3 12h13a4 4 0 014 4v0a4 4 0 01-4 4H3"
                />
              </svg>
              <div className="text-sm leading-relaxed">
                <strong>Vents — probes need assignment:</strong> {formatProbeUnassignedDetail(v)}
                <span className="mx-2 text-amber-400">|</span>
                Open the device card and use the probe assignment panel (touch a probe with your finger to identify it).
              </div>
            </div>
          ))}
        </div>
      )}

      {thermal.length > 0 && (
        <div className="bg-orange-950/85 backdrop-blur border-b border-orange-500/35 text-orange-100">
          {thermal.map((v, i) => (
            <div
              key={`${v.device_id}-${i}`}
              className="px-5 py-3 flex items-start gap-3 border-b border-orange-500/20 last:border-b-0"
            >
              <svg
                className="w-5 h-5 mt-0.5 shrink-0 text-orange-300"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01M10.29 3.86l-8.6 14.86A1 1 0 002.54 20h18.92a1 1 0 00.85-1.28l-8.6-14.86a1 1 0 00-1.42 0z"
                />
              </svg>
              <div className="text-sm leading-relaxed">
                <strong>Vents — over temperature:</strong> {formatThermalDetail(v)}
              </div>
            </div>
          ))}
        </div>
      )}

      {critical.length > 0 && (
        <div className="bg-red-900/80 backdrop-blur border-b border-red-500/40 text-red-100">
          {critical.map((w, i) => (
            <div
              key={i}
              className="px-5 py-3 flex items-start gap-3 border-b border-red-500/20 last:border-b-0"
            >
              <svg
                className="w-5 h-5 mt-0.5 shrink-0 text-red-300"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01M10.29 3.86l-8.6 14.86A1 1 0 002.54 20h18.92a1 1 0 00.85-1.28l-8.6-14.86a1 1 0 00-1.42 0z"
                />
              </svg>
              <div className="text-sm leading-relaxed">
                <strong>{w.title}:</strong> {w.detail}
                {w.hint && (
                  <>
                    <span className="mx-2 text-red-400">|</span>
                    {w.hint}
                  </>
                )}
              </div>
            </div>
          ))}
          {health.log_path && (
            <div className="px-5 py-2 text-[11px] text-red-200/70 border-t border-red-500/20">
              Full log: <code className="font-mono">{health.log_path}</code>
            </div>
          )}
        </div>
      )}
    </>
  );
}
