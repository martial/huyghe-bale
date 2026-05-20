import { useEffect, useState } from "react";
import type { Device } from "../../types/device";
import type { VentsActiveTarget, VentsStatus } from "../../types/vents";
import {
  setVentsPeltier,
  setVentsFan,
  setVentsMode,
  setVentsHotTarget,
  setVentsColdTarget,
  setVentsActiveTarget,
  setVentsUniquePeltier,
  sendVentsCommand,
} from "../../api/vents";

interface Props {
  device: Device;
  status: VentsStatus | null;
}

/**
 * Raw-control surface for a vents device: peltier toggles, fan sliders,
 * target slider, mode flip. The at-a-glance hero block is rendered above
 * this by VentsHero — so this component is pure controls.
 */
export default function VentsTestPanel({ device, status }: Props) {
  const [hotTarget, setHotTarget] = useState(25);
  const [coldTarget, setColdTarget] = useState(20);
  const [busy, setBusy] = useState(false);
  const [fanSlider, setFanSlider] = useState<[number, number]>([0.2, 0.2]);

  // Seed local slider state from the first sensible status push so the
  // controls reflect what the Pi is actually doing. New firmware sends
  // hot_target_c / cold_target_c separately; legacy firmware only carries
  // `target_c` (the back-compat alias for hot — cold falls through to its
  // initial value until the operator moves the slider).
  useEffect(() => {
    if (status) {
      const hot = status.hot_target_c ?? status.target_c;
      if (typeof hot === "number") {
        setHotTarget((t) => (t === 25 && hot !== 25 ? hot : t));
      }
      if (typeof status.cold_target_c === "number") {
        const cold = status.cold_target_c;
        setColdTarget((t) => (t === 20 && cold !== 20 ? cold : t));
      }
    }
    if (status && typeof status.fan1 === "number" && typeof status.fan2 === "number") {
      setFanSlider(([a, b]) => [
        Math.abs(a - status.fan1) > 0.05 ? status.fan1 : a,
        Math.abs(b - status.fan2) > 0.05 ? status.fan2 : b,
      ]);
    }
  }, [status]);

  async function wrap(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      console.error("[vents]", e);
    } finally {
      setBusy(false);
    }
  }

  const online = status?.online ?? false;
  const mode = status?.mode ?? "raw";
  const peltierOn = status?.peltier ?? [false, false, false];
  // Active side gates which slider is the live regulator. Pre-active-target
  // firmware omits this field — fall back to "hot" so old devices keep
  // showing hot as the regulator (matches the back-compat target_c alias).
  const activeTarget: VentsActiveTarget = status?.active_target ?? "hot";

  // Click on a greyed-out slider activates that side without changing its
  // stored value. Subsequent drags then write the value as usual.
  function activateSide(side: VentsActiveTarget) {
    if (activeTarget === side) return;
    wrap(() => setVentsActiveTarget(device.id, side));
  }

  return (
    <div className="space-y-3">
      {/* Mode toggle */}
      <div className="flex items-center gap-2">
        <span className="text-[10px] text-zinc-500 uppercase tracking-wider w-14">Mode</span>
        <button
          disabled={!online || busy || mode === "raw"}
          onClick={() => wrap(() => setVentsMode(device.id, "raw"))}
          className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
            mode === "raw" ? "bg-zinc-700 text-zinc-100" : "bg-zinc-800/60 hover:bg-zinc-700 text-zinc-400"
          } disabled:opacity-30`}
        >
          raw
        </button>
        <button
          disabled={!online || busy || mode === "auto"}
          onClick={() => wrap(() => setVentsMode(device.id, "auto"))}
          className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
            mode === "auto" ? "bg-sky-600 text-white" : "bg-zinc-800/60 hover:bg-zinc-700 text-zinc-400"
          } disabled:opacity-30`}
        >
          auto
        </button>
      </div>

      {/* Unique-peltier sub-mode toggle. Active only in auto; when enabled,
          the Pi drives one cell at a time. The current shared rest threshold
          is shown alongside as a non-editable hint (operator changes it via
          the Settings page, which pushes the new value to every Pi). */}
      <div className="flex items-center gap-2">
        <span className="text-[10px] text-zinc-500 uppercase tracking-wider w-14">Unique</span>
        <button
          disabled={!online || busy}
          onClick={() => wrap(() => setVentsUniquePeltier(device.id, !status?.unique_peltier))}
          className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
            status?.unique_peltier ? "bg-violet-600 text-white" : "bg-zinc-800/60 hover:bg-zinc-700 text-zinc-400"
          } disabled:opacity-30`}
          title="When enabled, only one Peltier cell is driven at a time in auto. Each cell has its own minimum-OFF cooldown."
        >
          {status?.unique_peltier ? "on" : "off"}
        </button>
        {status?.unique_peltier && typeof status.peltier_rest_s === "number" && (
          <span className="text-[10px] text-zinc-500 font-mono">
            rest {status.peltier_rest_s}s
          </span>
        )}
      </div>

      {/* Hot target slider — orange accent. Greyed when not the active side.
          15 °C floor mirrors the Pi-side clamp (which is authoritative). */}
      <div
        className={`flex items-center gap-2 transition-opacity ${
          activeTarget === "hot" ? "opacity-100" : "opacity-40"
        }`}
        onClick={() => activateSide("hot")}
      >
        <span className="text-[10px] text-orange-300 uppercase tracking-wider w-14 font-semibold">
          Hot{activeTarget === "hot" ? " ●" : ""}
        </span>
        <input
          type="range"
          min={15}
          max={35}
          step={0.5}
          value={hotTarget}
          onChange={(e) => setHotTarget(Number(e.target.value))}
          onMouseUp={() => wrap(() => setVentsHotTarget(device.id, hotTarget))}
          onTouchEnd={() => wrap(() => setVentsHotTarget(device.id, hotTarget))}
          disabled={!online || busy}
          className="flex-1 accent-orange-400"
        />
        <span className="text-xs text-zinc-300 font-mono w-12 text-right">
          {hotTarget.toFixed(1)}°C
        </span>
      </div>

      {/* Cold target slider — sky accent. Greyed when not the active side. */}
      <div
        className={`flex items-center gap-2 transition-opacity ${
          activeTarget === "cold" ? "opacity-100" : "opacity-40"
        }`}
        onClick={() => activateSide("cold")}
      >
        <span className="text-[10px] text-sky-300 uppercase tracking-wider w-14 font-semibold">
          Cold{activeTarget === "cold" ? " ●" : ""}
        </span>
        <input
          type="range"
          min={15}
          max={35}
          step={0.5}
          value={coldTarget}
          onChange={(e) => setColdTarget(Number(e.target.value))}
          onMouseUp={() => wrap(() => setVentsColdTarget(device.id, coldTarget))}
          onTouchEnd={() => wrap(() => setVentsColdTarget(device.id, coldTarget))}
          disabled={!online || busy}
          className="flex-1 accent-sky-400"
        />
        <span className="text-xs text-zinc-300 font-mono w-12 text-right">
          {coldTarget.toFixed(1)}°C
        </span>
      </div>

      {/* Peltier toggles */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[10px] text-zinc-500 uppercase tracking-wider w-14">Peltier</span>
        {[1, 2, 3].map((i) => {
          const on = peltierOn[i - 1];
          return (
            <button
              key={i}
              disabled={!online || busy}
              onClick={() => wrap(() => setVentsPeltier(device.id, i as 1 | 2 | 3, !on))}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                on ? "bg-orange-500 text-white" : "bg-zinc-800/60 hover:bg-zinc-700 text-zinc-300"
              } disabled:opacity-30`}
            >
              P{i}
            </button>
          );
        })}
        <button
          disabled={!online || busy}
          onClick={() => wrap(() => sendVentsCommand(device.id, { command: "peltier_mask", value: 0 }))}
          className="px-2 py-1 rounded-lg text-[10px] bg-red-900/40 hover:bg-red-800/60 text-red-200 disabled:opacity-30"
        >
          ALL OFF
        </button>
      </div>

      {/* Fan sliders */}
      {[0, 1].map((idx) => {
        const rpmA = [status?.rpm1A, status?.rpm2A][idx] ?? 0;
        const rpmB = [status?.rpm1B, status?.rpm2B][idx] ?? 0;
        return (
          <div key={idx} className="flex items-center gap-2">
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider w-14">Fan {idx + 1}</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={fanSlider[idx]}
              onChange={(e) => {
                const v = Number(e.target.value);
                setFanSlider(([a, b]) => (idx === 0 ? [v, b] : [a, v]));
              }}
              onMouseUp={() => wrap(() => setVentsFan(device.id, (idx + 1) as 1 | 2, fanSlider[idx]))}
              onTouchEnd={() => wrap(() => setVentsFan(device.id, (idx + 1) as 1 | 2, fanSlider[idx]))}
              disabled={!online || busy}
              className="flex-1 accent-sky-400"
            />
            <span className="text-[10px] text-zinc-400 font-mono w-10 text-right">
              {(fanSlider[idx] * 100).toFixed(0)}%
            </span>
            <span className="text-[9px] text-zinc-500 font-mono w-24 text-right">
              {Math.round(rpmA)} / {Math.round(rpmB)} rpm
            </span>
          </div>
        );
      })}
    </div>
  );
}
