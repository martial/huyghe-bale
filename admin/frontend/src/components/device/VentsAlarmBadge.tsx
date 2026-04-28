import type { DeviceAlarms } from "../../api/devices";
import { VENTS_TACH_CHANNEL_LABEL } from "../../types/vents";

interface Props {
  alarms: DeviceAlarms;
}

export default function VentsAlarmBadge({ alarms }: Props) {
  const channels = alarms.active
    .map((c) => VENTS_TACH_CHANNEL_LABEL[c] ?? `ch ${c}`)
    .join(", ");
  return (
    <div
      role="alert"
      className="rounded-2xl border border-red-500/40 bg-gradient-to-br from-red-500/15 to-red-900/20 px-4 py-3 flex items-center gap-3"
    >
      <span
        aria-hidden
        className="inline-block w-2.5 h-2.5 rounded-full bg-red-400 shadow-[0_0_10px_rgba(248,113,113,0.7)] animate-pulse"
      />
      <div className="flex-1 min-w-0">
        <div className="text-[10px] uppercase tracking-[0.2em] font-semibold text-red-200">
          Fan RPM alarm
        </div>
        <div className="text-xs text-red-100/90 mt-0.5 truncate">
          {channels} below {alarms.threshold} RPM
        </div>
      </div>
    </div>
  );
}
