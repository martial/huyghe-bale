import { useEffect, useMemo, useState, useRef } from "react";
import type { BridgeEvent, BridgeState, BridgeRouting } from "../types/bridge";
import {
  getBridgeState,
  clearBridgeEvents,
  subscribeBridgeStream,
} from "../api/bridge";
import { useSettingsStore } from "../stores/settings-store";
import { useDeviceStore } from "../stores/device-store";

const MAX_ROWS = 500;
const ROUTING_OPTIONS: { value: BridgeRouting; label: string; hint: string }[] = [
  { value: "type-match", label: "type-match", hint: "/vents/* → vents, /trolley/* → trolley, /sys/* → all" },
  { value: "passthrough", label: "passthrough", hint: "forward every message to every device" },
  { value: "none", label: "none (tap only)", hint: "log but don't forward" },
];

function formatTime(t: number): string {
  const d = new Date(t * 1000);
  return d.toLocaleTimeString(undefined, { hour12: false }) +
    "." + String(d.getMilliseconds()).padStart(3, "0");
}

function formatArgs(args: unknown[]): string {
  if (!args.length) return "—";
  return args
    .map((a) => {
      if (typeof a === "number") {
        return Number.isInteger(a) ? String(a) : a.toFixed(3);
      }
      return String(a);
    })
    .join(", ");
}

export default function BridgePage() {
  const settings = useSettingsStore((s) => s.settings);
  const fetchSettings = useSettingsStore((s) => s.fetchSettings);
  const updateSettings = useSettingsStore((s) => s.updateSettings);
  const devices = useDeviceStore((s) => s.list);
  const fetchDevices = useDeviceStore((s) => s.fetchList);

  const [state, setState] = useState<BridgeState | null>(null);
  const [events, setEvents] = useState<BridgeEvent[]>([]);
  const [filter, setFilter] = useState("");
  const [portDraft, setPortDraft] = useState<number | null>(null);
  const [rateOps, setRateOps] = useState(0);

  // Rolling-1s rate: remember timestamps of events in the last second.
  const timestamps = useRef<number[]>([]);

  useEffect(() => {
    fetchSettings();
    fetchDevices();
    getBridgeState().then(setState).catch(() => {});
    const unsubscribe = subscribeBridgeStream((ev) => {
      setEvents((prev) => {
        const next = [ev, ...prev];
        return next.length > MAX_ROWS ? next.slice(0, MAX_ROWS) : next;
      });
      timestamps.current.push(Date.now());
    });
    return unsubscribe;
  }, [fetchSettings, fetchDevices]);

  useEffect(() => {
    const t = setInterval(() => {
      const cutoff = Date.now() - 1000;
      timestamps.current = timestamps.current.filter((ts) => ts > cutoff);
      setRateOps(timestamps.current.length);
    }, 500);
    return () => clearInterval(t);
  }, []);

  // Seed the event list once the initial /state call returns — state.events
  // is the ring buffer snapshot.
  useEffect(() => {
    if (state && events.length === 0 && state.events.length > 0) {
      // state.events is oldest-first; UI renders newest-first.
      setEvents([...state.events].reverse().slice(0, MAX_ROWS));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  const deviceName = useMemo(() => {
    const map: Record<string, string> = {};
    devices.forEach((d) => {
      map[d.id] = d.name || d.ip_address || d.id;
    });
    return map;
  }, [devices]);

  const filteredEvents = useMemo(() => {
    if (!filter.trim()) return events;
    const q = filter.toLowerCase();
    return events.filter(
      (ev) =>
        ev.address.toLowerCase().includes(q) ||
        ev.src.toLowerCase().includes(q) ||
        (ev.dropped || "").toLowerCase().includes(q),
    );
  }, [events, filter]);

  async function toggleEnabled() {
    await updateSettings({ bridge_enabled: !settings.bridge_enabled });
    setState(await getBridgeState());
  }

  async function changeRouting(routing: BridgeRouting) {
    await updateSettings({ bridge_routing: routing });
    setState(await getBridgeState());
  }

  async function commitPort() {
    if (portDraft == null || portDraft === settings.bridge_port) {
      setPortDraft(null);
      return;
    }
    try {
      await updateSettings({ bridge_port: portDraft });
      setState(await getBridgeState());
    } catch (e) {
      console.error("[bridge] port update failed:", e);
    } finally {
      setPortDraft(null);
    }
  }

  async function handleClear() {
    await clearBridgeEvents();
    setEvents([]);
    timestamps.current = [];
  }

  const running = state?.running ?? false;
  const error = state?.error;

  return (
    <div className="p-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="mb-8 pb-4 border-b border-white/10">
        <h1 className="text-3xl font-light tracking-tight text-white mb-1">OSC Bridge</h1>
        <p className="text-zinc-400 text-sm">
          Listen on a UDP port and rebroadcast incoming OSC messages to devices.
          An external source (show controller, Max, TouchDesigner…) sends here; the
          admin fans out based on the selected routing. Every event below is live.
        </p>
      </div>

      {/* Control strip */}
      <div className="rounded-2xl border border-white/10 bg-zinc-900/40 p-4 mb-6 flex flex-wrap items-center gap-4">
        <button
          onClick={toggleEnabled}
          className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${
            settings.bridge_enabled
              ? "bg-emerald-600 hover:bg-emerald-500 text-white"
              : "bg-zinc-800 hover:bg-zinc-700 text-zinc-300"
          }`}
        >
          {settings.bridge_enabled ? "Enabled" : "Disabled"}
        </button>

        <div className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">Status</span>
          <span
            className={`inline-flex w-2.5 h-2.5 rounded-full ${
              running
                ? "bg-green-400 shadow-[0_0_8px_rgba(74,222,128,0.5)]"
                : "bg-zinc-600"
            }`}
          />
          <span className="text-xs text-zinc-300">
            {running ? "listening" : settings.bridge_enabled ? "starting…" : "stopped"}
          </span>
        </div>

        <label className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">Port</span>
          <input
            type="number"
            min={1024}
            max={65535}
            value={portDraft ?? settings.bridge_port}
            onChange={(e) => setPortDraft(Number(e.target.value))}
            onBlur={commitPort}
            onKeyDown={(e) => {
              if (e.key === "Enter") (e.target as HTMLInputElement).blur();
            }}
            className="w-24 bg-zinc-800 border border-zinc-700/50 rounded-lg px-2 py-1 text-sm text-zinc-200 font-mono focus:outline-none focus:border-sky-500/50"
          />
        </label>

        <label className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">Routing</span>
          <select
            value={settings.bridge_routing}
            onChange={(e) => changeRouting(e.target.value as BridgeRouting)}
            className="bg-zinc-800 border border-zinc-700/50 rounded-lg px-2 py-1 text-sm text-zinc-200 focus:outline-none focus:border-sky-500/50"
          >
            {ROUTING_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>

        <div className="ml-auto flex items-center gap-3 text-[10px] text-zinc-500 font-mono">
          <span>
            <span className="text-zinc-300">{rateOps}</span> ev/s
          </span>
          <span>·</span>
          <span>
            <span className="text-zinc-300">{events.length}</span> / {MAX_ROWS} buffered
          </span>
          <button
            onClick={handleClear}
            className="ml-2 text-[10px] text-zinc-400 hover:text-white transition-colors"
          >
            clear
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg border border-red-500/30 bg-red-500/10 text-sm text-red-200">
          Bridge error: <span className="font-mono">{error}</span>
        </div>
      )}

      <p className="text-[11px] text-zinc-500 mb-3">
        {ROUTING_OPTIONS.find((o) => o.value === settings.bridge_routing)?.hint}
      </p>

      {/* Filter */}
      <div className="mb-2">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="filter by address, source IP, or drop reason…"
          className="w-full bg-zinc-900/60 border border-white/5 rounded-lg px-3 py-1.5 text-sm text-zinc-200 font-mono focus:outline-none focus:border-sky-500/30"
        />
      </div>

      {/* Event table */}
      <div className="rounded-2xl border border-white/5 bg-zinc-900/40 overflow-hidden">
        <div className="grid grid-cols-[110px_130px_1fr_1fr_1fr] px-4 py-2 text-[10px] uppercase tracking-wider text-zinc-500 font-mono border-b border-white/5 bg-black/20">
          <span>time</span>
          <span>from</span>
          <span>address</span>
          <span>args</span>
          <span>→ targets</span>
        </div>
        <div className="max-h-[60vh] overflow-y-auto">
          {filteredEvents.length === 0 && (
            <div className="px-4 py-8 text-center text-xs text-zinc-500">
              {events.length === 0
                ? settings.bridge_enabled
                  ? "Waiting for the first OSC message on the bridge port…"
                  : "Bridge is disabled. Toggle it on to start listening."
                : "No events match the filter."}
            </div>
          )}
          {filteredEvents.map((ev, i) => {
            const dropped = !!ev.dropped;
            const targets =
              ev.targets.map((id) => deviceName[id] ?? id).join(", ") || "—";
            return (
              <div
                key={`${ev.t}-${i}`}
                className={`grid grid-cols-[110px_130px_1fr_1fr_1fr] px-4 py-1.5 text-[11px] font-mono border-b border-white/5 last:border-b-0 ${
                  dropped ? "opacity-60" : "hover:bg-white/[0.02]"
                }`}
              >
                <span className="text-zinc-500">{formatTime(ev.t)}</span>
                <span className="text-zinc-400 truncate">{ev.src}</span>
                <span className="text-orange-200/90 truncate">{ev.address}</span>
                <span className="text-zinc-300 truncate">{formatArgs(ev.args)}</span>
                <span
                  className={`truncate ${dropped ? "text-yellow-400/80" : "text-zinc-400"}`}
                  title={dropped ? ev.dropped : targets}
                >
                  {dropped ? `⊘ ${ev.dropped}` : targets}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
