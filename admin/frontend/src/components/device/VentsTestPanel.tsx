import { useEffect, useState } from "react";
import type { Device } from "../../types/device";
import type { VentsStatus } from "../../types/vents";
import {
  fetchVentsStatus,
  setVentsPeltier,
  setVentsFan,
  setVentsMode,
  setVentsTarget,
  sendVentsCommand,
} from "../../api/vents";

const STATE_BADGE: Record<string, string> = {
  idle: "bg-zinc-700/30 text-zinc-300 border-zinc-600/50",
  cooling: "bg-sky-500/20 text-sky-300 border-sky-500/40",
  holding: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  coasting: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  sensor_error: "bg-red-500/20 text-red-300 border-red-500/40",
};

function Pill({ label, value, warn = false }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="flex flex-col bg-black/30 border border-white/5 rounded-lg px-2 py-1">
      <span className="text-[9px] uppercase tracking-wider text-zinc-500">{label}</span>
      <span className={`text-xs font-mono ${warn ? "text-orange-300" : "text-zinc-200"}`}>{value}</span>
    </div>
  );
}

export default function VentsTestPanel({ device }: { device: Device }) {
  const [status, setStatus] = useState<VentsStatus | null>(null);
  const [target, setTarget] = useState(25);
  const [busy, setBusy] = useState(false);
  const [fanSlider, setFanSlider] = useState<[number, number]>([0.2, 0.2]);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const s = await fetchVentsStatus(device.id);
        if (!cancelled) {
          setStatus(s);
          // Seed the target input once from the Pi's reported value, but
          // only if it actually reported a number. A Pi that hasn't
          // broadcast yet returns a partial {online: false} payload where
          // target_c/fan1/fan2 are undefined.
          if (typeof s.target_c === "number") {
            setTarget((t) => (t === 25 && s.target_c !== 25 ? s.target_c : t));
          }
          if (typeof s.fan1 === "number" && typeof s.fan2 === "number") {
            setFanSlider(([a, b]) => [
              Math.abs(a - s.fan1) > 0.05 ? s.fan1 : a,
              Math.abs(b - s.fan2) > 0.05 ? s.fan2 : b,
            ]);
          }
        }
      } catch {
        /* transient */
      }
    }
    poll();
    const t = setInterval(poll, 700);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [device.id]);

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
  const state = status?.state ?? "idle";
  const stateClass = STATE_BADGE[state] ?? STATE_BADGE.idle;
  const t1 = status?.temp1_c;
  const t2 = status?.temp2_c;
  const avg = [t1, t2].filter((v): v is number => typeof v === "number");
  const avgTemp = avg.length ? avg.reduce((a, b) => a + b, 0) / avg.length : null;

  const peltierOn = status?.peltier ?? [false, false, false];

  return (
    <div className="mt-3 p-3 rounded-xl border border-white/5 bg-black/30 space-y-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] uppercase tracking-wider font-semibold text-orange-300/80">Vents</span>
          <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium border ${stateClass}`}>
            {state}
          </span>
          <span className="text-[10px] text-zinc-500">
            mode: <span className="text-zinc-300">{mode}</span>
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            disabled={!online || busy || mode === "raw"}
            onClick={() => wrap(() => setVentsMode(device.id, "raw"))}
            className={`px-2 py-0.5 text-[10px] rounded transition-colors ${
              mode === "raw"
                ? "bg-zinc-700 text-zinc-100"
                : "bg-zinc-800/60 hover:bg-zinc-700 text-zinc-400"
            } disabled:opacity-30`}
          >
            raw
          </button>
          <button
            disabled={!online || busy || mode === "auto"}
            onClick={() => wrap(() => setVentsMode(device.id, "auto"))}
            className={`px-2 py-0.5 text-[10px] rounded transition-colors ${
              mode === "auto"
                ? "bg-sky-600 text-white"
                : "bg-zinc-800/60 hover:bg-zinc-700 text-zinc-400"
            } disabled:opacity-30`}
          >
            auto
          </button>
        </div>
      </div>

      {/* Live readings */}
      <div className="grid grid-cols-4 gap-2">
        <Pill label="T1" value={t1 != null ? `${t1.toFixed(1)}°C` : "—"} warn={t1 == null} />
        <Pill label="T2" value={t2 != null ? `${t2.toFixed(1)}°C` : "—"} warn={t2 == null} />
        <Pill label="AVG" value={avgTemp != null ? `${avgTemp.toFixed(1)}°C` : "—"} />
        <Pill label="TARGET" value={`${(status?.target_c ?? target).toFixed(1)}°C`} />
      </div>

      {/* Target slider (only meaningful in auto mode) */}
      <div className="flex items-center gap-2">
        <span className="text-[10px] text-zinc-500 w-14">Target</span>
        <input
          type="range"
          min={5}
          max={35}
          step={0.5}
          value={target}
          onChange={(e) => setTarget(Number(e.target.value))}
          onMouseUp={() => wrap(() => setVentsTarget(device.id, target))}
          onTouchEnd={() => wrap(() => setVentsTarget(device.id, target))}
          disabled={!online || busy}
          className="flex-1 accent-orange-400"
        />
        <span className="text-xs text-zinc-300 font-mono w-12 text-right">
          {target.toFixed(1)}°C
        </span>
      </div>

      {/* Peltier toggles */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[10px] text-zinc-500 w-14">Peltier</span>
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
          onClick={() =>
            wrap(() =>
              sendVentsCommand(device.id, { command: "peltier_mask", value: 0 }),
            )
          }
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
            <span className="text-[10px] text-zinc-500 w-14">Fan {idx + 1}</span>
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
              onMouseUp={() =>
                wrap(() => setVentsFan(device.id, (idx + 1) as 1 | 2, fanSlider[idx]))
              }
              onTouchEnd={() =>
                wrap(() => setVentsFan(device.id, (idx + 1) as 1 | 2, fanSlider[idx]))
              }
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
