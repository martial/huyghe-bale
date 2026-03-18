import { useEffect, useState } from "react";
import { getHealth, type HealthStatus } from "../../api/health";

export default function SystemWarnings() {
  const [health, setHealth] = useState<HealthStatus | null>(null);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval>;

    const poll = () => {
      getHealth()
        .then(setHealth)
        .catch(() => setHealth(null));
    };

    poll();
    timer = setInterval(poll, 30_000);
    return () => clearInterval(timer);
  }, []);

  if (!health || health.osc_receiver.running) return null;

  const error = health.osc_receiver.error ?? "OSC receiver is not running";

  return (
    <div className="bg-red-900/80 backdrop-blur border-b border-red-500/40 px-5 py-3 flex items-start gap-3 text-red-100">
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
        <strong>OSC Receiver Error:</strong> {error}
        <span className="mx-2 text-red-400">|</span>
        Device heartbeat monitoring is offline. Fix:{" "}
        <code className="bg-red-950/60 px-1.5 py-0.5 rounded text-red-200 text-xs font-mono">
          kill $(lsof -ti:{health.osc_receiver.port})
        </code>{" "}
        then restart the backend.
      </div>
    </div>
  );
}
