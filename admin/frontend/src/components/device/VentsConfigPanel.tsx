import type { VentsStatus } from "../../types/vents";

interface Props {
  status: VentsStatus | null;
  /** Per-channel RPM threshold currently used by the admin's alarm detector. */
  rpmAlarmThreshold?: number;
}

function Stat({
  label, value, unit, dim = false,
}: {
  label: string;
  value: string;
  unit?: string;
  dim?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-[0.18em] text-zinc-500">{label}</span>
      <span className={`text-sm tabular-nums ${dim ? "text-zinc-500" : "text-zinc-200"}`}>
        {value}
        {unit && <span className="text-xs text-zinc-500 ml-1">{unit}</span>}
      </span>
    </div>
  );
}

// Echoes the configuration values the Pi reports in /vents/status, so the
// operator can verify a Settings push actually landed on the device.
export default function VentsConfigPanel({ status, rpmAlarmThreshold }: Props) {
  const max = status?.max_temp_c;
  const minFan = status?.min_fan_pct;
  const maxFan = status?.max_fan_pct;
  const overTempFan = status?.over_temp_fan_pct;
  const target = status?.target_c;

  const fmt = (n: number | null | undefined, digits = 0) =>
    typeof n === "number" ? n.toFixed(digits) : "—";

  return (
    <div className="rounded-2xl border border-white/5 bg-zinc-900/40 px-5 py-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] uppercase tracking-[0.2em] font-semibold text-zinc-400">
          On-device configuration
        </span>
        <span className="text-[10px] text-zinc-600">live from /vents/status</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <Stat label="Target" value={fmt(target, 1)} unit="°C" dim={target == null} />
        <Stat label="Max temp" value={fmt(max, 1)} unit="°C" dim={max == null} />
        <Stat label="Min fan PWM" value={fmt(minFan)} unit="%" dim={minFan == null} />
        <Stat label="Max fan PWM" value={fmt(maxFan)} unit="%" dim={maxFan == null} />
        <Stat label="Over-temp fan" value={fmt(overTempFan)} unit="%" dim={overTempFan == null} />
        {rpmAlarmThreshold != null && (
          <Stat
            label="RPM alarm"
            value={rpmAlarmThreshold > 0 ? String(rpmAlarmThreshold) : "off"}
            unit={rpmAlarmThreshold > 0 ? "RPM" : undefined}
            dim={rpmAlarmThreshold === 0}
          />
        )}
      </div>
      {(minFan == null || maxFan == null || overTempFan == null) && (
        <p className="mt-3 text-[11px] text-zinc-500 leading-snug">
          Some fields are blank — the Pi may be running older firmware that doesn't echo these settings yet.
          Update the device, or push from <span className="font-mono">Settings</span> to re-sync.
        </p>
      )}
    </div>
  );
}
