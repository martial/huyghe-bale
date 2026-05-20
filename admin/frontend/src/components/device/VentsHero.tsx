import type { VentsActiveTarget, VentsStatus, VentsState } from "../../types/vents";

const STATE_COLOR: Record<VentsState, { text: string; bg: string; label: string }> = {
  idle:             { text: "text-zinc-300",   bg: "from-zinc-800/40 to-zinc-900/60",     label: "idle" },
  heating:          { text: "text-amber-300",  bg: "from-amber-500/20 to-amber-900/20",   label: "heating" },
  cooling:          { text: "text-sky-300",    bg: "from-sky-500/20 to-sky-900/20",       label: "cooling" },
  holding:          { text: "text-emerald-300", bg: "from-emerald-500/20 to-emerald-900/20", label: "holding" },
  sensor_error:     { text: "text-red-300",    bg: "from-red-500/20 to-red-900/20",       label: "no sensors" },
  probe_unassigned: { text: "text-amber-300",  bg: "from-amber-500/15 to-amber-950/30",   label: "needs probes" },
  over_temp:        { text: "text-orange-300", bg: "from-orange-500/25 to-orange-950/30", label: "over temp" },
  // Unique-peltier-only state: regulator wants to drive on but every cell is
  // still inside its cooldown. Distinct from "cooling"/"holding".
  rest_wait:        { text: "text-violet-300", bg: "from-violet-500/20 to-violet-950/30", label: "rest wait" },
};

// Compact "N min Ns" formatter for the per-cell rest countdown. Operators
// glance at this; precision below 1 s is meaningless given the 5 Hz status
// broadcast.
function fmtRestSeconds(s: number): string {
  const sec = Math.max(0, Math.ceil(s));
  if (sec >= 60) {
    const m = Math.floor(sec / 60);
    const r = sec % 60;
    return r === 0 ? `${m}m` : `${m}m ${r}s`;
  }
  return `${sec}s`;
}

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
  const tHot = status?.temp_hot_c;
  const tCold = status?.temp_cold_c;
  // Dual-setpoint firmware sends temp_hot_c / temp_cold_c. When absent
  // (legacy firmware) we fall back to averaging temp1/temp2 against the
  // single legacy target, preserving the old hero layout.
  const hasDual = tHot !== undefined || tCold !== undefined;
  const hotTarget = status?.hot_target_c ?? status?.target_c;
  const coldTarget = status?.cold_target_c;
  // Pre-active-target firmware doesn't carry this field — fall back to "hot"
  // so old devices keep showing hot as the regulator (matches the back-compat
  // target_c alias).
  const activeTarget: VentsActiveTarget = status?.active_target ?? "hot";
  const avg = [t1, t2].filter((v): v is number => typeof v === "number");
  const avgTemp = avg.length ? avg.reduce((a, b) => a + b, 0) / avg.length : null;
  const maxCeiling = status?.max_temp_c;
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

      {hasDual ? (
        // Dual-setpoint hero: hot + cold side-by-side, each with its setpoint.
        // The active side is rendered at full opacity; the inactive side is
        // dimmed to make the regulation choice glanceable.
        <div className="flex items-stretch gap-4">
          <SidePanel
            label="hot"
            accent="text-orange-300"
            temp={tHot ?? null}
            target={hotTarget ?? null}
            active={activeTarget === "hot"}
          />
          <SidePanel
            label="cold"
            accent="text-sky-300"
            temp={tCold ?? null}
            target={coldTarget ?? null}
            active={activeTarget === "cold"}
          />
          {maxCeiling != null && (
            <div className="ml-auto self-end text-[11px] font-mono text-zinc-400 text-right leading-tight">
              max <span className="text-orange-300/90">{maxCeiling.toFixed(1)}°C</span>
            </div>
          )}
        </div>
      ) : (
        // Legacy hero: single avg temperature against single target.
        <div className="flex items-baseline gap-3">
          <span className={`text-5xl font-light tabular-nums tracking-tight ${avgTemp != null ? "text-white" : "text-zinc-600"}`}>
            {avgTemp != null ? avgTemp.toFixed(1) : "—"}
          </span>
          <span className="text-xl text-zinc-500">°C</span>
          {(hotTarget != null || maxCeiling != null) && (
            <span className="ml-auto text-[11px] font-mono text-zinc-400 text-right leading-tight">
              {hotTarget != null && (
                <>
                  target <span className="text-zinc-200">{hotTarget.toFixed(1)}°C</span>
                </>
              )}
              {hotTarget != null && maxCeiling != null && <span className="text-zinc-600"> · </span>}
              {maxCeiling != null && (
                <>
                  max <span className="text-orange-300/90">{maxCeiling.toFixed(1)}°C</span>
                </>
              )}
            </span>
          )}
        </div>
      )}

      {/* Sub-metrics — raw probe-order view stays for diagnostics. */}
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
        {status?.unique_peltier && status.peltier ? (
          <PeltierCellsUnique status={status} />
        ) : (
          <span>
            peltier <span className="text-zinc-300">
              {status?.peltier
                ? status.peltier.map((on, i) => (on ? i + 1 : "·")).join("")
                : "—"}
            </span>
          </span>
        )}
      </div>
    </div>
  );
}

/** Per-cell badge row for unique-peltier mode. Each cell renders one of:
 *    P1 active          (currently driven; violet)
 *    P1 rest 4m 12s     (off, in cooldown; muted with countdown)
 *    P1 idle            (off, eligible; dim)
 *  Independent timers — the user's blindspot point: while one cell is
 *  "active", the others may be "resting" with their own countdowns. The
 *  top-level state ("heating" / "cooling" / "rest_wait" / …) reflects the
 *  regulator's decision; the per-cell badges reflect the actuators. */
function PeltierCellsUnique({ status }: { status: VentsStatus }) {
  const peltier = status.peltier ?? [false, false, false];
  const remaining = status.peltier_rest_remaining;
  return (
    <span className="flex items-center gap-x-2 flex-wrap">
      <span className="text-zinc-500">peltier</span>
      {[0, 1, 2].map((i) => {
        const on = peltier[i];
        const rest = remaining && remaining[i] > 0 ? remaining[i] : 0;
        if (on) {
          return (
            <span key={i} className="text-violet-300">
              P{i + 1} <span className="font-semibold">active</span>
            </span>
          );
        }
        if (rest > 0) {
          return (
            <span key={i} className="text-zinc-400">
              P{i + 1} <span className="text-zinc-500">rest {fmtRestSeconds(rest)}</span>
            </span>
          );
        }
        return (
          <span key={i} className="text-zinc-500/70">
            P{i + 1} <span>idle</span>
          </span>
        );
      })}
    </span>
  );
}

function SidePanel({
  label, accent, temp, target, active,
}: {
  label: string;
  accent: string;
  temp: number | null;
  target: number | null;
  active: boolean;
}) {
  return (
    <div className={`flex-1 min-w-0 transition-opacity ${active ? "opacity-100" : "opacity-50"}`}>
      <div className={`text-[9px] uppercase tracking-[0.2em] ${accent} font-semibold`}>
        {label}{active ? " ●" : ""}
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className={`text-3xl font-light tabular-nums tracking-tight ${temp != null ? "text-white" : "text-zinc-600"}`}>
          {temp != null ? temp.toFixed(1) : "—"}
        </span>
        <span className="text-base text-zinc-500">°C</span>
      </div>
      <div className="text-[10px] font-mono text-zinc-400">
        target <span className="text-zinc-200">{target != null ? `${target.toFixed(1)}°C` : "—"}</span>
      </div>
    </div>
  );
}
