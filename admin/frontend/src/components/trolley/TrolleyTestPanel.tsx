import { useEffect, useMemo, useState } from "react";
import type { Device } from "../../types/device";
import type { TrolleyStatus } from "../../types/trolley";
import {
  sendTrolleyCommand,
  fetchTrolleyStatus,
  fetchTrolleyConfig,
  setTrolleyConfig,
} from "../../api/trolley";

// Mirrors MAX_SPEED_PCT in the admin backend and the rpi firmware. Hard cap
// applied at every layer; if you raise this, raise it in all three places.
const MAX_SPEED_PCT = 0.4;

const DEFAULT_RAIL = {
  rail_length_mm: 0,
  wheel_radius_mm: 0,
};

const DEFAULT_MOTOR = {
  steps_per_rev: 200,
  microsteps: 16,
  max_speed_hz: 2000,
  home_speed_hz: 100,
  soft_limit_pct: 0.98,
  accel_time_s: 0,
  decel_time_s: 0,
};

function deriveRailLengthSteps(
  rail_length_mm: number,
  wheel_radius_mm: number,
  steps_per_rev: number,
  microsteps: number,
): number {
  if (!rail_length_mm || !wheel_radius_mm) return 0;
  const travelPerRev = 2 * Math.PI * wheel_radius_mm;
  if (travelPerRev <= 0) return 0;
  const stepsPerMm = (steps_per_rev * microsteps) / travelPerRev;
  return Math.round(rail_length_mm * stepsPerMm);
}

export default function TrolleyTestPanel({ device }: { device: Device }) {
  const [enabled, setEnabled] = useState(false);
  const [direction, setDirection] = useState<0 | 1>(1);
  const [speed, setSpeed] = useState(0.2);
  const [steps, setSteps] = useState(1000);
  const [position, setPosition] = useState(0.5);
  const [showSettings, setShowSettings] = useState(false);
  const [rail, setRail] = useState(DEFAULT_RAIL);
  const [motor, setMotor] = useState(DEFAULT_MOTOR);
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

  // Prefill rail/motor form from the Pi's persisted settings on mount, so a
  // page reload shows what's actually saved instead of the hardcoded defaults.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetchTrolleyConfig(device.id);
        if (cancelled || !r.ok || !r.config) return;
        const c = r.config;
        setRail({
          rail_length_mm: c.rail_length_mm ?? 0,
          wheel_radius_mm: c.wheel_radius_mm ?? 0,
        });
        setMotor({
          steps_per_rev: c.steps_per_rev,
          microsteps: c.microsteps,
          max_speed_hz: c.max_speed_hz,
          home_speed_hz: c.home_speed_hz,
          soft_limit_pct: c.soft_limit_pct,
          accel_time_s: c.accel_time_s,
          decel_time_s: c.decel_time_s,
        });
      } catch {
        /* unreachable Pi → keep defaults; status badge will show offline */
      }
    })();
    return () => {
      cancelled = true;
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
    const clamped = Math.max(0, Math.min(MAX_SPEED_PCT, next));
    setSpeed(clamped);
    await send("speed", clamped);
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

  async function handleSaveRail() {
    setBusy(true);
    try {
      await setTrolleyConfig(device.id, "rail_length_mm", rail.rail_length_mm);
      await setTrolleyConfig(device.id, "wheel_radius_mm", rail.wheel_radius_mm);
      await sendTrolleyCommand(device.id, "config_save");
    } catch (e) {
      console.error("[trolley] saving rail config failed:", e);
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveSettings() {
    setBusy(true);
    try {
      for (const [key, value] of Object.entries(motor)) {
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
  const alarm = status?.alarm ?? 0;
  const alarmLocked = (status?.alarm_locked ?? 0) === 1;
  const isHoming = state === "homing";
  const positionAvailable = homed === 1 && calibrated === 1 && !alarmLocked;
  // When the firmware has latched the alarm, every motion control is locked
  // out. Operator must clear the underlying CL86Y fault first, then click
  // Reset alarm. Reset itself only succeeds when alarm pin reads LOW.
  const motionLocked = alarmLocked;

  const derivedSteps = useMemo(
    () =>
      deriveRailLengthSteps(
        rail.rail_length_mm,
        rail.wheel_radius_mm,
        motor.steps_per_rev,
        motor.microsteps,
      ),
    [rail.rail_length_mm, rail.wheel_radius_mm, motor.steps_per_rev, motor.microsteps],
  );

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
        <Badge ok={calibrated === 1} label={calibrated ? "Configured" : "Not configured"} />
        <span className="px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 uppercase tracking-wide">
          {state}
        </span>
        {limit === 1 && (
          <span className="px-2 py-0.5 rounded bg-yellow-900/40 text-yellow-300">⚠ limit</span>
        )}
        {alarmLocked && (
          <span className="px-2 py-0.5 rounded bg-red-950 text-red-200 font-semibold tracking-wide">
            ALARM LOCKED
          </span>
        )}
        {!alarmLocked && alarm === 1 && (
          <span className="px-2 py-0.5 rounded bg-red-900/50 text-red-300">⚠ alarm pin</span>
        )}
      </div>

      {/* Alarm-locked banner — visible whenever the firmware refuses motion. */}
      {alarmLocked && (
        <div className="mb-3 p-3 rounded-xl bg-red-950/60 border border-red-700/50">
          <p className="text-xs font-semibold text-red-200 mb-1">
            Driver alarm latched — all motion is locked.
          </p>
          <p className="text-[11px] text-red-300/80 mb-2">
            Clear the CL86Y fault (red LED on the driver), then press Reset alarm.
            Reset only succeeds while the alarm GPIO is LOW.
          </p>
          <button
            onClick={() => send("alarm_reset")}
            disabled={busy || !online || alarm === 1}
            className="w-full px-3 py-1.5 bg-red-700/70 hover:bg-red-600/80 disabled:opacity-30 rounded text-xs font-medium text-red-50 transition-all"
            title={alarm === 1 ? "Alarm pin is still HIGH — clear the driver fault first" : undefined}
          >
            Reset alarm
          </button>
        </div>
      )}

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

      {/* Rail config */}
      <div className="mb-4 p-3 rounded-xl bg-zinc-950/50 border border-zinc-800/60">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-zinc-300">Rail config</span>
          <span className="text-[10px] text-zinc-500 font-mono">
            {calibrated ? "✓ saved" : "not set"}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-2 mb-2">
          <NumField
            label="Rail length (mm)"
            value={rail.rail_length_mm}
            onChange={(v) => setRail({ ...rail, rail_length_mm: v })}
            step={1}
          />
          <NumField
            label="Wheel radius (mm)"
            value={rail.wheel_radius_mm}
            onChange={(v) => setRail({ ...rail, wheel_radius_mm: v })}
            step={0.01}
          />
        </div>
        <p className="text-[10px] text-zinc-500 font-mono mb-2">
          Derived: {derivedSteps.toLocaleString()} steps
        </p>
        <button
          onClick={handleSaveRail}
          disabled={busy || !online || !rail.rail_length_mm || !rail.wheel_radius_mm}
          className="w-full px-3 py-1.5 bg-emerald-700/70 hover:bg-emerald-600/80 disabled:opacity-30 rounded text-xs font-medium text-emerald-100 transition-all"
        >
          Save rail config
        </button>
      </div>

      {/* Home */}
      <div className="mb-4 p-3 rounded-xl bg-zinc-950/50 border border-zinc-800/60">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-zinc-300">Home</span>
          <span className="text-[10px] text-zinc-500 font-mono">
            {isHoming ? "running…" : homed ? "homed" : "—"}
          </span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => send("home", "reverse")}
            disabled={busy || !online || isHoming || motionLocked}
            title={motionLocked ? "Alarm latched — reset first" : "Drive toward home limit switch"}
            className="flex-1 px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-30 rounded text-[11px] font-medium text-zinc-300 transition-all"
          >
            ◄ Home reverse
          </button>
          <button
            onClick={() => send("home", "forward")}
            disabled={busy || !online || isHoming || motionLocked}
            title={motionLocked ? "Alarm latched — reset first" : "Drive toward far limit switch"}
            className="flex-1 px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-30 rounded text-[11px] font-medium text-zinc-300 transition-all"
          >
            Home forward ►
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
            disabled={busy || !online || motionLocked}
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

      {/* Position slider — disabled until configured */}
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
          title={
            motionLocked
              ? "Alarm latched — reset first"
              : !positionAvailable
              ? "Configure rail + home first"
              : undefined
          }
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
            disabled={busy || !online || motionLocked}
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
            disabled={busy || !online || motionLocked}
            className="accent-sky-500"
          />
          Reverse
        </label>
      </div>

      {/* Speed — capped at MAX_SPEED_PCT for safety. */}
      <div className="flex items-center gap-3 mb-4">
        <span className="text-xs text-zinc-500 w-20">
          Speed <span className="text-zinc-600">(max {MAX_SPEED_PCT.toFixed(2)})</span>
        </span>
        <input
          type="range"
          min={0}
          max={MAX_SPEED_PCT}
          step={0.01}
          value={speed}
          onChange={(e) => handleSpeed(Number(e.target.value))}
          disabled={busy || !online || motionLocked}
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
          disabled={busy || !online || motionLocked}
          className="w-32 bg-zinc-800 border border-zinc-700/50 rounded-lg px-2 py-1 text-sm text-zinc-200 font-mono focus:outline-none focus:border-sky-500/50"
        />
        <button
          onClick={handleStep}
          disabled={busy || !online || motionLocked}
          className="ml-2 px-4 py-1.5 bg-sky-600 hover:bg-sky-500 disabled:opacity-30 rounded-lg text-sm font-medium transition-all"
        >
          GO
        </button>
      </div>

      {/* Motor settings (collapsible) */}
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
              label="Steps/rev"
              value={motor.steps_per_rev}
              onChange={(v) => setMotor({ ...motor, steps_per_rev: v })}
              step={1}
            />
            <NumField
              label="Microsteps"
              value={motor.microsteps}
              onChange={(v) => setMotor({ ...motor, microsteps: v })}
              step={1}
            />
            <NumField
              label="Max speed (Hz)"
              value={motor.max_speed_hz}
              onChange={(v) => setMotor({ ...motor, max_speed_hz: v })}
              step={50}
            />
            <NumField
              label="Home speed (Hz)"
              value={motor.home_speed_hz}
              onChange={(v) => setMotor({ ...motor, home_speed_hz: v })}
              step={50}
            />
            <NumField
              label="Accel (s)"
              value={motor.accel_time_s}
              onChange={(v) => setMotor({ ...motor, accel_time_s: v })}
              onCommit={(v) => send("accel", v)}
              step={0.1}
            />
            <NumField
              label="Decel (s)"
              value={motor.decel_time_s}
              onChange={(v) => setMotor({ ...motor, decel_time_s: v })}
              onCommit={(v) => send("decel", v)}
              step={0.1}
            />
            <NumField
              label="Soft limit (0–1)"
              value={motor.soft_limit_pct}
              onChange={(v) => setMotor({ ...motor, soft_limit_pct: v })}
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
              Saved per Pi in <code className="text-zinc-400">device.json</code>. Steps × microsteps
              divided by 2π × wheel radius gives steps/mm; multiplied by rail length gives the total step count.
            </p>
            <p className="text-[10px] text-zinc-500 leading-snug">
              <span className="text-zinc-400">Accel / Decel:</span> linear ramp time (s) applied to{" "}
              <code className="text-zinc-400">/trolley/step</code> and{" "}
              <code className="text-zinc-400">/trolley/position</code>. <span className="text-zinc-400">0</span> = no ramp
              (constant speed). On blur the value is sent live; click Save settings to persist.
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
  onCommit,
  step,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  /** Fires on blur — for fields that have a live OSC effect (e.g. accel/decel). */
  onCommit?: (v: number) => void;
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
        onBlur={onCommit ? (e) => onCommit(Number(e.target.value)) : undefined}
        className="w-24 bg-zinc-800 border border-zinc-700/50 rounded px-2 py-0.5 text-xs text-zinc-200 font-mono focus:outline-none focus:border-sky-500/50"
      />
    </label>
  );
}
