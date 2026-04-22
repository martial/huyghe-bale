import type { TrolleyEvent, TrolleyCommand } from "../../types/trolley";

const ALL_COMMANDS: TrolleyCommand[] = [
  "position", "speed", "step", "dir", "enable", "stop", "home",
];

const COMMANDS_WITH_VALUE: TrolleyCommand[] = [
  "position", "speed", "step", "dir", "enable",
];

/**
 * Shape of the value field per command. Used to drive input type + step.
 * - position, speed: float 0..1
 * - dir, enable: int 0..1 (radio-ish)
 * - step: int (pulse count)
 */
const VALUE_HINT: Record<TrolleyCommand, { min?: number; max?: number; step?: number; default: number }> = {
  position: { min: 0, max: 1, step: 0.01, default: 0.5 },
  speed: { min: 0, max: 1, step: 0.01, default: 0.5 },
  step: { min: 1, max: 100000, step: 100, default: 1000 },
  dir: { min: 0, max: 1, step: 1, default: 1 },
  enable: { min: 0, max: 1, step: 1, default: 1 },
  stop: { default: 0 },
  home: { default: 0 },
};

interface Props {
  event: TrolleyEvent;
  duration: number;
  onChange: (next: TrolleyEvent) => void;
  onDelete: () => void;
}

export default function TrolleyEventEditor({ event, duration, onChange, onDelete }: Props) {
  const hint = VALUE_HINT[event.command];
  const hasValue = COMMANDS_WITH_VALUE.includes(event.command);
  const isBinary = event.command === "dir" || event.command === "enable";

  function changeCommand(next: TrolleyCommand) {
    const nextHasValue = COMMANDS_WITH_VALUE.includes(next);
    onChange({
      ...event,
      command: next,
      value: nextHasValue ? (event.value ?? VALUE_HINT[next].default) : undefined,
    });
  }

  return (
    <div className="mx-4 mb-4 p-4 rounded-xl border border-white/10 bg-zinc-900/60 space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-xs uppercase tracking-wider text-zinc-400">Event</h4>
        <button
          onClick={onDelete}
          className="text-xs text-red-400 hover:text-red-300 transition-colors"
        >
          Delete
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">Command</span>
          <select
            value={event.command}
            onChange={(e) => changeCommand(e.target.value as TrolleyCommand)}
            className="bg-zinc-800 border border-zinc-700/50 rounded-lg px-2 py-1 text-sm text-zinc-200 focus:outline-none focus:border-sky-500/50"
          >
            {ALL_COMMANDS.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">Time (s)</span>
          <input
            type="number"
            min={0}
            max={duration}
            step={0.01}
            value={event.time}
            onChange={(e) =>
              onChange({ ...event, time: Math.max(0, Math.min(duration, Number(e.target.value))) })
            }
            className="bg-zinc-800 border border-zinc-700/50 rounded-lg px-2 py-1 text-sm text-zinc-200 font-mono focus:outline-none focus:border-sky-500/50"
          />
        </label>

        {hasValue && (
          <label className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wider text-zinc-500">
              Value
              {event.command === "position" || event.command === "speed"
                ? " (0..1)"
                : event.command === "step"
                ? " (pulses)"
                : " (0 or 1)"}
            </span>
            {isBinary ? (
              <div className="flex gap-2">
                {[0, 1].map((v) => (
                  <button
                    key={v}
                    onClick={() => onChange({ ...event, value: v })}
                    className={`flex-1 px-2 py-1 rounded-lg text-sm font-medium transition-colors ${
                      event.value === v
                        ? "bg-sky-600 text-white"
                        : "bg-zinc-800 hover:bg-zinc-700 text-zinc-300"
                    }`}
                  >
                    {event.command === "dir"
                      ? v === 1
                        ? "forward"
                        : "reverse"
                      : v === 1
                      ? "enabled"
                      : "disabled"}
                  </button>
                ))}
              </div>
            ) : (
              <input
                type="number"
                min={hint.min}
                max={hint.max}
                step={hint.step}
                value={event.value ?? 0}
                onChange={(e) => onChange({ ...event, value: Number(e.target.value) })}
                className="bg-zinc-800 border border-zinc-700/50 rounded-lg px-2 py-1 text-sm text-zinc-200 font-mono focus:outline-none focus:border-sky-500/50"
              />
            )}
          </label>
        )}
      </div>
    </div>
  );
}
