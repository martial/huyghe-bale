import { Link } from "react-router";
import type { TrolleyStatus } from "../../types/trolley";

interface Props {
  status: TrolleyStatus | null;
  stale: boolean;
  lastPushAgeS: number | null;
}

export default function TrolleyHero({ status, stale, lastPushAgeS }: Props) {
  const position = status?.position ?? 0;
  const homed = status?.homed ?? 0;
  const limit = status?.limit ?? 0;
  const online = status?.online ?? false;
  const gradient = homed
    ? "from-sky-500/20 to-sky-900/20"
    : "from-zinc-800/40 to-zinc-900/60";

  return (
    <div
      className={`rounded-2xl bg-gradient-to-br ${gradient} border border-white/5 px-5 py-4 ${stale ? "opacity-60" : ""} transition-opacity`}
    >
      <div className="flex items-start justify-between mb-2">
        <span className="text-[10px] uppercase tracking-[0.2em] font-semibold text-sky-300">
          position
        </span>
        <div className="flex items-center gap-1.5 flex-wrap justify-end">
          {homed ? (
            <span className="text-[10px] px-1.5 py-0.5 rounded border bg-emerald-500/10 text-emerald-300 border-emerald-500/30">
              homed
            </span>
          ) : (
            <span className="text-[10px] px-1.5 py-0.5 rounded border bg-zinc-700/30 text-zinc-400 border-zinc-600/40">
              not homed
            </span>
          )}
          {limit === 1 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded border bg-yellow-500/10 text-yellow-300 border-yellow-500/30">
              ⚠ limit
            </span>
          )}
          {stale && (
            <span
              className="text-[10px] px-1.5 py-0.5 rounded border bg-yellow-500/10 text-yellow-300 border-yellow-500/30"
              title={
                lastPushAgeS != null
                  ? `Last /trolley/status ${lastPushAgeS.toFixed(1)}s ago`
                  : "No status yet"
              }
            >
              stale{lastPushAgeS != null && ` ${lastPushAgeS.toFixed(0)}s`}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-baseline gap-3">
        <span className={`text-5xl font-light tabular-nums tracking-tight ${online ? "text-white" : "text-zinc-600"}`}>
          {online ? (position * 100).toFixed(1) : "—"}
        </span>
        <span className="text-xl text-zinc-500">%</span>
        <Link
          to="/trolleys"
          className="ml-auto text-[10px] text-zinc-500 hover:text-sky-300 transition-colors"
        >
          Open panel →
        </Link>
      </div>

      <div className="mt-3 h-2 rounded-full bg-zinc-800 overflow-hidden">
        <div
          className="h-full bg-sky-400 transition-[width] duration-150"
          style={{ width: `${Math.max(0, Math.min(100, position * 100))}%` }}
        />
      </div>
    </div>
  );
}
