import type { OrchestrationStep } from "../../types/orchestration";
import type { TimelineSummary } from "../../types/timeline";
import type { Device } from "../../types/device";

interface Props {
  step: OrchestrationStep;
  timelines: TimelineSummary[];
  devices: Device[];
  isFirst: boolean;
  isLast: boolean;
  onChange: (step: OrchestrationStep) => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onRemove: () => void;
}

export default function OrchestrationStepCard({
  step,
  timelines,
  devices,
  isFirst,
  isLast,
  onChange,
  onMoveUp,
  onMoveDown,
  onRemove,
}: Props) {
  function toggleDevice(id: string) {
    const ids = step.device_ids.includes(id)
      ? step.device_ids.filter((x) => x !== id)
      : [...step.device_ids, id];
    onChange({ ...step, device_ids: ids });
  }

  return (
    <div className="p-5 rounded-xl border border-zinc-800/50 bg-zinc-900/80 shadow-sm">
      <div className="flex items-start gap-4">
        {/* Order controls */}
        <div className="flex flex-col gap-0.5 pt-1">
          <button
            onClick={onMoveUp}
            disabled={isFirst}
            className="text-zinc-500 hover:text-white disabled:opacity-20 text-xs transition-colors"
          >
            &uarr;
          </button>
          <span className="text-xs text-zinc-600 text-center">{step.order + 1}</span>
          <button
            onClick={onMoveDown}
            disabled={isLast}
            className="text-zinc-500 hover:text-white disabled:opacity-20 text-xs transition-colors"
          >
            &darr;
          </button>
        </div>

        <div className="flex-1 grid grid-cols-4 gap-3">
          {/* Label */}
          <div>
            <label className="text-xs text-zinc-500 block mb-1">Label</label>
            <input
              value={step.label}
              onChange={(e) => onChange({ ...step, label: e.target.value })}
              className="w-full bg-zinc-800 border border-zinc-700/50 rounded-lg px-2 py-1 text-sm focus:outline-none focus:border-orange-500/50 transition-colors"
              placeholder="Step name"
            />
          </div>

          {/* Timeline */}
          <div>
            <label className="text-xs text-zinc-500 block mb-1">Timeline</label>
            <select
              value={step.timeline_id}
              onChange={(e) => onChange({ ...step, timeline_id: e.target.value })}
              className="w-full bg-zinc-800 border border-zinc-700/50 rounded-lg px-2 py-1 text-sm focus:outline-none focus:border-orange-500/50 transition-colors"
            >
              <option value="">— Select —</option>
              {timelines.map((tl) => (
                <option key={tl.id} value={tl.id}>
                  {tl.name} ({tl.duration}s)
                </option>
              ))}
            </select>
          </div>

          {/* Delay */}
          <div>
            <label className="text-xs text-zinc-500 block mb-1">Delay before (s)</label>
            <input
              value={step.delay_before}
              onChange={(e) => onChange({ ...step, delay_before: Number(e.target.value) })}
              type="number"
              min={0}
              step={0.5}
              className="w-full bg-zinc-800 border border-zinc-700/50 rounded-lg px-2 py-1 text-sm font-mono focus:outline-none focus:border-orange-500/50 transition-colors"
            />
          </div>

          {/* Devices */}
          <div>
            <label className="text-xs text-zinc-500 block mb-1">Devices</label>
            <div className="flex flex-wrap gap-1">
              {devices.map((dev) => (
                <label key={dev.id} className="flex items-center gap-1 text-xs cursor-pointer">
                  <input
                    type="checkbox"
                    checked={step.device_ids.includes(dev.id)}
                    onChange={() => toggleDevice(dev.id)}
                    className="rounded accent-orange-500"
                  />
                  {dev.name}
                </label>
              ))}
            </div>
          </div>
        </div>

        <button onClick={onRemove} className="text-red-400/60 hover:text-red-400 text-xs pt-1 transition-colors">
          Remove
        </button>
      </div>
    </div>
  );
}
