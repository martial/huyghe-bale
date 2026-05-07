import { useState } from "react";
import type { Device } from "../../types/device";
import type { VentsStatus } from "../../types/vents";
import { assignVentsProbe, clearVentsProbe } from "../../api/vents";

interface Props {
  device: Device;
  status: VentsStatus | null;
}

/**
 * Touch-test probe assignment panel. Shows every DS18B20 currently on
 * the bus, lets the operator warm a probe with a finger, watch its row
 * tick up, and click "Assign as hot" / "Assign as cold" on whichever
 * just rose. Per-Pi: each install pins its own pair of ROM ids.
 *
 * Renders nothing when the Pi is on legacy firmware (no `probes` field
 * in the snapshot) — the canonical surface stays hidden until the
 * controller can speak the new protocol.
 */
export default function VentsProbeAssignmentPanel({ device, status }: Props) {
  const probes = status?.probes;
  const [busy, setBusy] = useState(false);

  if (!probes) return null;

  const hotId = status?.probe_hot_id ?? null;
  const coldId = status?.probe_cold_id ?? null;
  const online = status?.online ?? false;
  const hotMissing = hotId != null && !probes.some((p) => p.id === hotId);
  const coldMissing = coldId != null && !probes.some((p) => p.id === coldId);

  async function wrap(fn: () => Promise<unknown>) {
    setBusy(true);
    try { await fn(); } catch (e) { console.error("[probe]", e); }
    finally { setBusy(false); }
  }

  const headerBlurb =
    hotId == null || coldId == null
      ? "Touch a probe with your finger to identify it, then click the matching role."
      : "Reassign or clear if the install changes (probe swap, wiring rerouted).";

  return (
    <div className="rounded-2xl border border-white/5 bg-zinc-900/40 px-5 py-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] uppercase tracking-[0.2em] font-semibold text-zinc-400">
          Probe assignment
        </span>
        <button
          disabled={!online || busy || (hotId == null && coldId == null)}
          onClick={() => wrap(() => clearVentsProbe(device.id, "both"))}
          className="text-[10px] px-2 py-0.5 rounded bg-zinc-800/60 hover:bg-zinc-700 text-zinc-400 disabled:opacity-30"
        >
          clear both
        </button>
      </div>
      <p className="text-[11px] text-zinc-500 leading-snug mb-3">{headerBlurb}</p>

      {/* Currently-assigned roles, surfaced as a header strip — including
          the "missing" state when an assigned id isn't on the bus. */}
      <div className="flex gap-3 mb-3">
        <RoleChip
          label="hot"
          accent="text-orange-300 border-orange-500/30 bg-orange-500/10"
          assigned={hotId}
          missing={hotMissing}
        />
        <RoleChip
          label="cold"
          accent="text-sky-300 border-sky-500/30 bg-sky-500/10"
          assigned={coldId}
          missing={coldMissing}
        />
      </div>

      {probes.length === 0 ? (
        <p className="text-[11px] text-amber-300/90 leading-snug">
          No DS18B20 probes detected on the bus. Check wiring and{" "}
          <span className="font-mono">dtoverlay=w1-gpio</span> in{" "}
          <span className="font-mono">/boot/firmware/config.txt</span>.
        </p>
      ) : (
        <div className="space-y-1.5">
          {probes.map((p) => {
            const isHot = p.id === hotId;
            const isCold = p.id === coldId;
            return (
              <div
                key={p.id}
                className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-zinc-950/40 border border-white/5"
              >
                <span className="font-mono text-[11px] text-zinc-300 flex-1 min-w-0 truncate">
                  {p.id}
                </span>
                <span
                  className={`text-xs tabular-nums w-14 text-right ${
                    p.temp_c != null ? "text-zinc-200" : "text-zinc-600"
                  }`}
                >
                  {p.temp_c != null ? `${p.temp_c.toFixed(1)}°C` : "—"}
                </span>
                <button
                  disabled={!online || busy || isHot}
                  onClick={() => wrap(() => assignVentsProbe(device.id, "hot", p.id))}
                  className={`px-2 py-1 rounded text-[10px] font-medium transition-colors ${
                    isHot
                      ? "bg-orange-500/30 text-orange-200 border border-orange-500/40"
                      : "bg-zinc-800/60 hover:bg-orange-500/20 text-zinc-400 hover:text-orange-200"
                  } disabled:opacity-30`}
                >
                  {isHot ? "✓ hot" : "assign hot"}
                </button>
                <button
                  disabled={!online || busy || isCold}
                  onClick={() => wrap(() => assignVentsProbe(device.id, "cold", p.id))}
                  className={`px-2 py-1 rounded text-[10px] font-medium transition-colors ${
                    isCold
                      ? "bg-sky-500/30 text-sky-200 border border-sky-500/40"
                      : "bg-zinc-800/60 hover:bg-sky-500/20 text-zinc-400 hover:text-sky-200"
                  } disabled:opacity-30`}
                >
                  {isCold ? "✓ cold" : "assign cold"}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function RoleChip({
  label, accent, assigned, missing,
}: {
  label: string;
  accent: string;
  assigned: string | null;
  missing: boolean;
}) {
  if (assigned == null) {
    return (
      <div className="flex-1 text-[11px] px-2.5 py-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 text-amber-200">
        <span className="uppercase text-[9px] tracking-[0.2em] font-semibold mr-1.5">{label}</span>
        not assigned
      </div>
    );
  }
  if (missing) {
    return (
      <div className="flex-1 text-[11px] px-2.5 py-1.5 rounded-lg border border-red-500/30 bg-red-500/10 text-red-200">
        <span className="uppercase text-[9px] tracking-[0.2em] font-semibold mr-1.5">{label}</span>
        <span className="font-mono">{assigned}</span> — missing
      </div>
    );
  }
  return (
    <div className={`flex-1 text-[11px] px-2.5 py-1.5 rounded-lg border ${accent}`}>
      <span className="uppercase text-[9px] tracking-[0.2em] font-semibold mr-1.5">{label}</span>
      <span className="font-mono">{assigned}</span>
    </div>
  );
}
