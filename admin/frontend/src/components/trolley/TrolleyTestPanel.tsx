import { useEffect, useState } from "react";
import type { Device } from "../../types/device";
import type { TrolleyStatus } from "../../types/trolley";
import { sendTrolleyCommand, fetchTrolleyStatus } from "../../api/trolley";

export default function TrolleyTestPanel({ device }: { device: Device }) {
  const [enabled, setEnabled] = useState(false);
  const [direction, setDirection] = useState<0 | 1>(1);
  const [speed, setSpeed] = useState(0.5);
  const [steps, setSteps] = useState(1000);
  const [status, setStatus] = useState<TrolleyStatus | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const s = await fetchTrolleyStatus(device.id);
        if (!cancelled) setStatus(s);
      } catch {
        /* ignore transient errors */
      }
    }
    poll();
    const t = setInterval(poll, 500);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [device.id]);

  async function send(command: Parameters<typeof sendTrolleyCommand>[1], value?: number) {
    setBusy(true);
    try {
      await sendTrolleyCommand(device.id, command, value);
    } catch (e) {
      console.error("[trolley] command failed:", e);
    } finally {
      setBusy(false);
    }
  }

  async function handleEnable(next: boolean) {
    setEnabled(next);
    await send("enable", next ? 1 : 0);
  }

  async function handleDir(next: 0 | 1) {
    setDirection(next);
    await send("dir", next);
  }

  async function handleSpeed(next: number) {
    setSpeed(next);
    await send("speed", next);
  }

  async function handleStep() {
    // Re-apply current dir + speed so the burst matches what the UI shows,
    // regardless of what the Pi's last command left the controller in.
    await send("dir", direction);
    await send("speed", speed);
    await send("step", steps);
  }

  const online = status?.online ?? false;
  const limit = status?.limit ?? 0;
  const homed = status?.homed ?? 0;
  const position = status?.position ?? 0;

  return (
    <div className="p-5 rounded-2xl border border-white/5 bg-zinc-900/60 shadow-lg">
      <div className="flex items-center justify-between mb-4">
        <div>
          <p className="text-lg font-medium text-white">{device.name || "(unnamed trolley)"}</p>
          <p className="text-xs text-zinc-500 font-mono">
            {device.ip_address}:{device.osc_port}
          </p>
        </div>
        <span
          className={`inline-flex w-2.5 h-2.5 rounded-full ${
            online
              ? "bg-green-400 shadow-[0_0_10px_rgba(74,222,128,0.5)]"
              : "bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.5)]"
          }`}
        />
      </div>

      {/* Live position bar */}
      <div className="mb-4">
        <div className="flex items-center justify-between text-[10px] font-mono text-zinc-500 mb-1">
          <span>Position</span>
          <span>
            {(position * 100).toFixed(1)}% {homed ? "(homed)" : "(not homed)"}
          </span>
        </div>
        <div className="h-2 rounded bg-zinc-800 overflow-hidden">
          <div
            className="h-full bg-sky-500 transition-[width] duration-150"
            style={{ width: `${Math.max(0, Math.min(100, position * 100))}%` }}
          />
        </div>
        {limit === 1 && (
          <p className="mt-1 text-[10px] text-yellow-400/80 font-mono">⚠ limit switch engaged</p>
        )}
      </div>

      {/* Enable + Home + Stop */}
      <div className="flex items-center gap-2 mb-4">
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => handleEnable(e.target.checked)}
            disabled={busy || !online}
            className="accent-sky-500"
          />
          Enable
        </label>
        <button
          onClick={() => send("home")}
          disabled={busy || !online}
          className="ml-auto px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-30 rounded-lg text-xs font-medium text-zinc-300 transition-all"
        >
          Home
        </button>
        <button
          onClick={() => send("stop")}
          disabled={busy || !online}
          className="px-3 py-1.5 bg-red-900/50 hover:bg-red-800/70 disabled:opacity-30 rounded-lg text-xs font-medium text-red-200 transition-all"
        >
          Stop
        </button>
      </div>

      {/* Direction */}
      <div className="flex items-center gap-3 mb-4">
        <span className="text-xs text-zinc-500 w-20">Direction</span>
        <label className="flex items-center gap-1.5 text-xs text-zinc-300">
          <input
            type="radio"
            name={`dir-${device.id}`}
            checked={direction === 1}
            onChange={() => handleDir(1)}
            disabled={busy || !online}
            className="accent-sky-500"
          />
          Forward
        </label>
        <label className="flex items-center gap-1.5 text-xs text-zinc-300">
          <input
            type="radio"
            name={`dir-${device.id}`}
            checked={direction === 0}
            onChange={() => handleDir(0)}
            disabled={busy || !online}
            className="accent-sky-500"
          />
          Reverse
        </label>
      </div>

      {/* Speed */}
      <div className="flex items-center gap-3 mb-4">
        <span className="text-xs text-zinc-500 w-20">Speed</span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={speed}
          onChange={(e) => handleSpeed(Number(e.target.value))}
          disabled={busy || !online}
          className="flex-1 accent-sky-500"
        />
        <span className="text-xs text-zinc-400 font-mono w-12 text-right">
          {speed.toFixed(2)}
        </span>
      </div>

      {/* Steps + GO */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-zinc-500 w-20">Steps</span>
        <input
          type="number"
          min={1}
          step={1}
          value={steps}
          onChange={(e) => setSteps(Math.max(1, Number(e.target.value)))}
          disabled={busy || !online}
          className="w-32 bg-zinc-800 border border-zinc-700/50 rounded-lg px-2 py-1 text-sm text-zinc-200 font-mono focus:outline-none focus:border-sky-500/50"
        />
        <button
          onClick={handleStep}
          disabled={busy || !online}
          className="ml-2 px-4 py-1.5 bg-sky-600 hover:bg-sky-500 disabled:opacity-30 rounded-lg text-sm font-medium transition-all"
        >
          GO
        </button>
      </div>
    </div>
  );
}
