import { useEffect, useState } from "react";
import { getHealth, type HealthStatus } from "../../api/health";

type Warning = {
  title: string;
  detail: string;
  hint?: React.ReactNode;
};

function collectWarnings(h: HealthStatus): Warning[] {
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
          Port <code className="bg-red-950/60 px-1.5 py-0.5 rounded text-red-200 text-xs font-mono">{h.bridge.port}</code> may already be in use.
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
  const warnings = collectWarnings(health);
  if (warnings.length === 0) return null;

  return (
    <div className="bg-red-900/80 backdrop-blur border-b border-red-500/40 text-red-100">
      {warnings.map((w, i) => (
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
  );
}
