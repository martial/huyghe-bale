import { useEffect, useState } from "react";
import { useSettingsStore } from "../stores/settings-store";
import { useNotificationStore } from "../stores/notification-store";
import type { BridgeRouting } from "../api/settings";
import RoutingHelp from "../components/bridge/RoutingHelp";

export default function SettingsPage() {
  const settings = useSettingsStore((s) => s.settings);
  const loading = useSettingsStore((s) => s.loading);
  const fetchSettings = useSettingsStore((s) => s.fetchSettings);
  const updateSettings = useSettingsStore((s) => s.updateSettings);
  const notify = useNotificationStore((s) => s.notify);

  const [frequency, setFrequency] = useState(30);
  const [cap, setCap] = useState(100);
  const [bridgeEnabled, setBridgeEnabled] = useState(false);
  const [bridgePort, setBridgePort] = useState(9002);
  const [bridgeRouting, setBridgeRouting] = useState<BridgeRouting>("type-match");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  useEffect(() => {
    setFrequency(settings.osc_frequency);
  }, [settings.osc_frequency]);

  useEffect(() => {
    setCap(settings.output_cap);
  }, [settings.output_cap]);

  useEffect(() => {
    setBridgeEnabled(settings.bridge_enabled);
    setBridgePort(settings.bridge_port);
    setBridgeRouting(settings.bridge_routing);
  }, [settings.bridge_enabled, settings.bridge_port, settings.bridge_routing]);

  async function handleSave() {
    setSaving(true);
    try {
      await updateSettings({
        osc_frequency: frequency,
        output_cap: cap,
        bridge_enabled: bridgeEnabled,
        bridge_port: bridgePort,
        bridge_routing: bridgeRouting,
      });
      notify("success", "Settings saved successfully");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return null;

  return (
    <div className="p-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="flex items-center justify-between mb-10 pb-4 border-b border-white/10">
        <div>
          <h2 className="text-3xl font-light tracking-tight text-white mb-1">Settings</h2>
          <p className="text-zinc-400 text-sm">Configure playback and output parameters</p>
        </div>
      </div>

      <div className="space-y-6">
        {/* OSC Frequency */}
        <div className="bg-zinc-900/40 backdrop-blur-sm border border-white/5 rounded-2xl p-6 shadow-lg">
          <label className="block text-sm font-medium text-zinc-300 mb-1">
            OSC Send Frequency
          </label>
          <p className="text-xs text-zinc-500 mb-3">
            Rate at which values are sent to devices during playback (1–120 Hz).
          </p>
          <div className="flex items-center gap-3">
            <input
              value={frequency}
              onChange={(e) => setFrequency(Number(e.target.value))}
              type="number"
              min={1}
              max={120}
              step={1}
              className="w-24 bg-zinc-800 border border-white/10 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-orange-500/50 transition-colors"
            />
            <span className="text-sm text-zinc-400">Hz</span>
            <span className="text-xs text-zinc-600 ml-2">
              ({Math.round(1000 / frequency)} ms between messages)
            </span>
          </div>
        </div>

        {/* Output Cap */}
        <div className="bg-zinc-900/40 backdrop-blur-sm border border-white/5 rounded-2xl p-6 shadow-lg">
          <label className="block text-sm font-medium text-zinc-300 mb-1">
            Output Cap
          </label>
          <p className="text-xs text-zinc-500 mb-3">
            Maximum output percentage — 80 means 100% in timeline outputs 80%.
          </p>
          <div className="flex items-center gap-3">
            <input
              value={cap}
              onChange={(e) => setCap(Number(e.target.value))}
              type="number"
              min={1}
              max={100}
              step={1}
              className="w-24 bg-zinc-800 border border-white/10 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-orange-500/50 transition-colors"
            />
            <span className="text-sm text-zinc-400">%</span>
          </div>
        </div>

        {/* OSC Bridge */}
        <div className="bg-zinc-900/40 backdrop-blur-sm border border-white/5 rounded-2xl p-6 shadow-lg space-y-4">
          <div>
            <label className="block text-sm font-medium text-zinc-300 mb-1">
              OSC Bridge
            </label>
            <p className="text-xs text-zinc-500">
              Listen on a UDP port and rebroadcast incoming OSC messages to devices.
              Live feed + toggles also available on the <span className="font-mono">/bridge</span> page.
            </p>
          </div>

          <label className="flex items-center gap-2 text-sm text-zinc-300">
            <input
              type="checkbox"
              checked={bridgeEnabled}
              onChange={(e) => setBridgeEnabled(e.target.checked)}
              className="accent-sky-500"
            />
            Enabled
          </label>

          <div className="flex items-end gap-3 flex-wrap">
            <label className="flex flex-col gap-1">
              <span className="text-[10px] uppercase tracking-wider text-zinc-500">Port</span>
              <input
                value={bridgePort}
                onChange={(e) => setBridgePort(Number(e.target.value))}
                type="number"
                min={1024}
                max={65535}
                step={1}
                className="w-28 bg-zinc-800 border border-white/10 rounded-lg px-3 py-2 text-sm text-zinc-100 font-mono focus:outline-none focus:border-sky-500/50"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[10px] uppercase tracking-wider text-zinc-500 flex items-center gap-1.5">
                Routing
                <RoutingHelp />
              </span>
              <select
                value={bridgeRouting}
                onChange={(e) => setBridgeRouting(e.target.value as BridgeRouting)}
                className="bg-zinc-800 border border-white/10 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-sky-500/50"
              >
                <option value="type-match">type-match — /vents/* → vents, /trolley/* → trolley</option>
                <option value="passthrough">passthrough — forward to all devices</option>
                <option value="none">none — tap only (log, don't forward)</option>
              </select>
            </label>
          </div>
        </div>

        <div className="flex justify-end">
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-5 py-2.5 bg-gradient-to-r from-orange-500 to-orange-400 hover:from-orange-400 hover:to-orange-300 disabled:opacity-50 rounded-xl text-sm font-semibold text-white shadow-[0_0_20px_rgba(249,115,22,0.3)] hover:shadow-[0_0_30px_rgba(249,115,22,0.5)] transition-all duration-300 hover:-translate-y-0.5 active:translate-y-0 active:scale-95"
          >
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
