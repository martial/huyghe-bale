import { useEffect, useState } from "react";
import type { Device } from "../../types/device";
import type {
  TrolleyStatus,
  CalibrationDirection,
} from "../../types/trolley";
import {
  sendTrolleyCommand,
  fetchTrolleyStatus,
  setTrolleyConfig,
} from "../../api/trolley";

const DEFAULT_SETTINGS = {
  lead_mm_per_rev: 8,
  steps_per_rev: 200,
  microsteps: 16,
  max_speed_hz: 2000,
  calibration_speed_hz: 600,
  soft_limit_pct: 0.98,
};

export default function TrolleyTestPanel({ device }: { device: Device }) {
  const [enabled, setEnabled] = useState(false);
  const [direction, setDirection] = useState<0 | 1>(1);
  const [speed, setSpeed] = useState(0.5);
  const [steps, setSteps] = useState(1000);
  const [position, setPosition] = useState(0.5);
  const [calibDir, setCalibDir] = useState<CalibrationDirection>("forward");
  const [showSettings, setShowSettings] = useState(false);
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
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

  async function send(
    command: Parameters<typeof sendTrolleyCommand>[1],
    value?: number | string,
  ) {
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
    await send("dir", direction);
    await send("speed", speed);
    await send("step", steps);
  }

  async function handlePosition(next: number) {
    setPosition(next);
    await send("position", next);
  }

  async function handleStartCalibration() {
    // Pass direction so the Pi persists `calibration_direction` before the span pass.
    await send("calibrate_start", calibDir);
  }

  async function handleStopCalibration() {
    await send("calibrate_stop");
  }

  async function handleSaveCalibration() {
    await send("calibrate_save");
  }

  async function handleCancelCalibration() {
    await send("calibrate_cancel");
  }

  async function handleSaveSettings() {
    setBusy(true);
    try {
      for (const [key, value] of Object.entries(settings)) {
        await setTrolleyConfig(device.id, key, value);
      }
      await sendTrolleyCommand(device.id, "config_save");
    } catch (e) {
      console.error("[trolley] saving settings failed:", e);
    } finally {
      setBusy(false);
    }
  }

  const online = status?.online ?? false;
  const limit = status?.limit ?? 0;
  const homed = status?.homed ?? 0;
  const calibrated = status?.calibrated ?? 0;
  const state = status?.state ?? "idle";
  const livePosition = status?.position ?? 0;
  const isCalibrating = state === "calibrating";
  const positionAvailable = homed === 1 && calibrated === 1;

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

      {/* Status badges */}
      <div className="flex flex-wrap gap-1.5 mb-3 text-[10px] font-mono">
        <Badge ok={homed === 1} label={homed ? "Homed" : "Not homed"} />
        <Badge ok={calibrated === 1} label={calibrated ? "Calibrated" : "Not calibrated"} />
        <span className="px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 uppercase tracking-wide">
          {state}
        </span>
        {limit === 1 && (
          <span className="px-2 py-0.5 rounded bg-yellow-900/40 text-yellow-300">⚠ limit</span>
        )}
      </div>

      {/* Live position bar */}
      <div className="mb-4">
        <div className="flex items-center justify-between text-[10px] font-mono text-zinc-500 mb-1">
          <span>Position</span>
          <span>{(livePosition * 100).toFixed(1)}%</span>
        </div>
        <div className="h-2 rounded bg-zinc-800 overflow-hidden">
          <div
            className="h-full bg-sky-500 transition-[width] duration-150"
            style={{ width: `${Math.max(0, Math.min(100, livePosition * 100))}%` }}
          />
        </div>
      </div>

      {/* Calibration section */}
      <div className="mb-4 p-3 rounded-xl bg-zinc-950/50 border border-zinc-800/60">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-zinc-300">Calibration</span>
          <span className="text-[10px] text-zinc-500 font-mono">
            {isCalibrating ? "running…" : calibrated ? "✓ saved" : "not run"}
          </span>
        </div>

        <div className="flex items-center gap-2 mb-2 text-[11px]">
          <span className="text-zinc-500">Direction</span>
          <label className="flex items-center gap-1 text-zinc-300">
            <input
              type="radio"
              name={`calib-dir-${device.id}`}
              checked={calibDir === "forward"}
              onChange={() => setCalibDir("forward")}
              disabled={busy || isCalibrating}
              className="accent-sky-500"
            />
            Forward
          </label>
          <label className="flex items-center gap-1 text-zinc-300">
            <input
              type="radio"
              name={`calib-dir-${device.id}`}
              checked={calibDir === "reverse"}
              onChange={() => setCalibDir("reverse")}
              disabled={busy || isCalibrating}
              className="accent-sky-500"
            />
            Reverse
          </label>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => send("home")}
            disabled={busy || !online || isCalibrating}
            className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-30 rounded text-[11px] font-medium text-zinc-300 transition-all"
          >
            1. Home
          </button>
          <button
            onClick={handleStartCalibration}
            disabled={busy || !online || homed !== 1 || isCalibrating}
            title={homed !== 1 ? "Home first" : undefined}
            className="px-2.5 py-1 bg-amber-900/50 hover:bg-amber-800/70 disabled:opacity-30 rounded text-[11px] font-medium text-amber-200 transition-all"
          >
            2. Start
          </button>
          <button
            onClick={handleStopCalibration}
            disabled={busy || !online || !isCalibrating}
            className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-30 rounded text-[11px] font-medium text-zinc-300 transition-all"
          >
            3. Stop here
          </button>
          <button
            onClick={handleSaveCalibration}
            disabled={busy || !online}
            className="px-2.5 py-1 bg-emerald-900/50 hover:bg-emerald-800/70 disabled:opacity-30 rounded text-[11px] font-medium text-emerald-200 transition-all"
          >
            4. Save
          </button>
          <button
            onClick={handleCancelCalibration}
            disabled={busy || !online}
            className="px-2.5 py-1 bg-red-900/40 hover:bg-red-800/60 disabled:opacity-30 rounded text-[11px] font-medium text-red-200 transition-all"
          >
            Cancel
          </button>
        </div>
      </div>

      {/* Enable + Stop */}
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
          onClick={() => send("stop")}
          disabled={busy || !online}
          className="ml-auto px-3 py-1.5 bg-red-900/50 hover:bg-red-800/70 disabled:opacity-30 rounded-lg text-xs font-medium text-red-200 transition-all"
        >
          Stop
        </button>
      </div>

      {/* Position slider — disabled until calibrated */}
      <div className="mb-4">
        <div className="flex items-center justify-between text-xs text-zinc-500 mb-1">
          <span>Position</span>
          <span className="font-mono">{position.toFixed(2)}</span>
        </div>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={position}
          onChange={(e) => setPosition(Number(e.target.value))}
          onMouseUp={(e) => handlePosition(Number((e.target as HTMLInputElement).value))}
          onTouchEnd={(e) => handlePosition(Number((e.target as HTMLInputElement).value))}
          disabled={busy || !online || !positionAvailable}
          title={!positionAvailable ? "Home + calibrate first" : undefined}
          className="w-full accent-sky-500 disabled:opacity-30"
        />
      </div>

      {/* Direction (raw) */}
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
      <div className="flex items-center gap-2 mb-4">
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

      {/* Settings (collapsible) */}
      <div className="border-t border-zinc-800/60 pt-3">
        <button
          onClick={() => setShowSettings((v) => !v)}
          className="text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          {showSettings ? "▼" : "▶"} Motor settings
        </button>
        {showSettings && (
          <div className="mt-3 space-y-2">
            <NumField
              label="Lead (mm/rev)"
              value={settings.lead_mm_per_rev}
              onChange={(v) => setSettings({ ...settings, lead_mm_per_rev: v })}
              step={0.1}
            />
            <NumField
              label="Steps/rev"
              value={settings.steps_per_rev}
              onChange={(v) => setSettings({ ...settings, steps_per_rev: v })}
              step={1}
            />
            <NumField
              label="Microsteps"
              value={settings.microsteps}
              onChange={(v) => setSettings({ ...settings, microsteps: v })}
              step={1}
            />
            <NumField
              label="Max speed (Hz)"
              value={settings.max_speed_hz}
              onChange={(v) => setSettings({ ...settings, max_speed_hz: v })}
              step={50}
            />
            <NumField
              label="Calibration speed (Hz)"
              value={settings.calibration_speed_hz}
              onChange={(v) => setSettings({ ...settings, calibration_speed_hz: v })}
              step={50}
            />
            <NumField
              label="Soft limit (0–1)"
              value={settings.soft_limit_pct}
              onChange={(v) => setSettings({ ...settings, soft_limit_pct: v })}
              step={0.01}
            />
            <button
              onClick={handleSaveSettings}
              disabled={busy || !online}
              className="w-full mt-2 px-3 py-1.5 bg-sky-600 hover:bg-sky-500 disabled:opacity-30 rounded text-xs font-medium transition-all"
            >
              Save settings
            </button>
            <p className="text-[10px] text-zinc-500 leading-snug">
              Saved per Pi in <code className="text-zinc-400">device.json</code>. Lead × steps × microsteps
              feeds the mm display; the Pi only relies on rail_length_steps from calibration.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function Badge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`px-2 py-0.5 rounded ${
        ok
          ? "bg-emerald-900/40 text-emerald-300"
          : "bg-zinc-800 text-zinc-500"
      }`}
    >
      {label}
    </span>
  );
}

function NumField({
  label,
  value,
  onChange,
  step,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  step: number;
}) {
  return (
    <label className="flex items-center gap-2 text-[11px] text-zinc-400">
      <span className="flex-1">{label}</span>
      <input
        type="number"
        value={value}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-24 bg-zinc-800 border border-zinc-700/50 rounded px-2 py-0.5 text-xs text-zinc-200 font-mono focus:outline-none focus:border-sky-500/50"
      />
    </label>
  );
}
