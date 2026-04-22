import { useEffect, useState } from "react";
import { Link } from "react-router";
import type { Device } from "../../types/device";
import type { TrolleyStatus } from "../../types/trolley";
import { fetchTrolleyStatus } from "../../api/trolley";

export default function TrolleyStatusPanel({ device }: { device: Device }) {
  const [status, setStatus] = useState<TrolleyStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const s = await fetchTrolleyStatus(device.id);
        if (!cancelled) setStatus(s);
      } catch {
        /* transient */
      }
    }
    poll();
    const t = setInterval(poll, 700);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [device.id]);

  const online = status?.online ?? false;
  const position = status?.position ?? 0;
  const limit = status?.limit ?? 0;
  const homed = status?.homed ?? 0;

  return (
    <div className="mt-3 p-3 rounded-xl border border-white/5 bg-black/30 space-y-2">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] uppercase tracking-wider font-semibold text-sky-300/80">
            Trolley
          </span>
          {homed ? (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium border bg-emerald-500/10 text-emerald-300 border-emerald-500/30">
              homed
            </span>
          ) : (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium border bg-zinc-700/30 text-zinc-400 border-zinc-600/40">
              not homed
            </span>
          )}
          {limit === 1 && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium border bg-yellow-500/10 text-yellow-300 border-yellow-500/30">
              ⚠ limit
            </span>
          )}
        </div>
        <Link
          to="/trolleys"
          className="text-[10px] text-zinc-500 hover:text-zinc-200 transition-colors"
        >
          Open panel →
        </Link>
      </div>

      <div>
        <div className="flex items-center justify-between text-[10px] font-mono text-zinc-500 mb-1">
          <span>Position</span>
          <span>{online ? `${(position * 100).toFixed(1)}%` : "—"}</span>
        </div>
        <div className="h-2 rounded bg-zinc-800 overflow-hidden">
          <div
            className="h-full bg-sky-500 transition-[width] duration-150"
            style={{ width: `${Math.max(0, Math.min(100, position * 100))}%` }}
          />
        </div>
      </div>
    </div>
  );
}
