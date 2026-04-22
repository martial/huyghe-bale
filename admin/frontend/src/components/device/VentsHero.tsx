import type { VentsStatus, VentsState } from "../../types/vents";

const STATE_COLOR: Record<VentsState, { text: string; bg: string; label: string }> = {
  idle:          { text: "text-zinc-300",     bg: "from-zinc-800/40 to-zinc-900/60",     label: "idle" },
  cooling:       { text: "text-sky-300",      bg: "from-sky-500/20 to-sky-900/20",       label: "cooling" },
  holding:       { text: "text-emerald-300",  bg: "from-emerald-500/20 to-emerald-900/20", label: "holding" },
  coasting:      { text: "text-amber-300",    bg: "from-amber-500/20 to-amber-900/20",   label: "coasting" },
  sensor_error:  { text: "text-red-300",      bg: "from-red-500/20 to-red-900/20",       label: "no sensors" },
};

interface Props {
  status: VentsStatus | null;
  stale: boolean;
  lastPushAgeS: number | null;
}

export default function VentsHero({ status, stale, lastPushAgeS }: Props) {
  const state: VentsState = status?.state ?? "idle";
  const palette = STATE_COLOR[state] ?? STATE_COLOR.idle;
  const t1 = status?.temp1_c;
  const t2 = status?.temp2_c;
  const avg = [t1, t2].filter((v): v is number => typeof v === "number");
  const avgTemp = avg.length ? avg.reduce((a, b) => a + b, 0) / avg.length : null;
  const target = status?.target_c;
  const mode = status?.mode ?? "raw";

  return (
    <div className={`rounded-2xl bg-gradient-to-br ${palette.bg} border border-white/5 px-5 py-4 ${stale ? "opacity-60" : ""} transition-opacity`}>
      <div className="flex items-start justify-between mb-2">
        <span className={`text-[10px] uppercase tracking-[0.2em] font-semibold ${palette.text}`}>
          {palette.label}
        </span>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-zinc-500 uppercase tracking-wider">{mode}</span>
          {stale && (
            <span
              className="text-[10px] px-1.5 py-0.5 rounded border bg-yellow-500/10 text-yellow-300 border-yellow-500/30"
              title={
                lastPushAgeS != null
                  ? `Last /vents/status ${lastPushAgeS.toFixed(1)}s ago`
                  : "No status yet"
              }
            >
              stale{lastPushAgeS != null && ` ${lastPushAgeS.toFixed(0)}s`}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-baseline gap-3">
        <span className={`text-5xl font-light tabular-nums tracking-tight ${avgTemp != null ? "text-white" : "text-zinc-600"}`}>
          {avgTemp != null ? avgTemp.toFixed(1) : "—"}
        </span>
        <span className="text-xl text-zinc-500">°C</span>
        {target != null && (
          <span className="ml-auto text-[11px] font-mono text-zinc-400">
            target <span className="text-zinc-200">{target.toFixed(1)}°C</span>
          </span>
        )}
      </div>

      {/* Sub-metrics */}
      <div className="mt-3 flex items-center gap-x-4 gap-y-1 flex-wrap text-[10px] font-mono text-zinc-500">
        <span>
          T1 <span className={t1 != null ? "text-zinc-300" : "text-zinc-600"}>
            {t1 != null ? `${t1.toFixed(1)}°` : "—"}
          </span>
        </span>
        <span>
          T2 <span className={t2 != null ? "text-zinc-300" : "text-zinc-600"}>
            {t2 != null ? `${t2.toFixed(1)}°` : "—"}
          </span>
        </span>
        <span>
          fans <span className="text-zinc-300">
            {status ? `${Math.round(status.fan1 * 100)}/${Math.round(status.fan2 * 100)}%` : "—"}
          </span>
        </span>
        <span>
          peltier <span className="text-zinc-300">
            {status ? status.peltier.map((on, i) => (on ? i + 1 : "·")).join("") : "—"}
          </span>
        </span>
      </div>
    </div>
  );
}
