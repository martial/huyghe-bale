import { useEffect, useState } from "react";
import { useSettingsStore } from "../stores/settings-store";
import { useNotificationStore } from "../stores/notification-store";

export default function SettingsPage() {
  const settings = useSettingsStore((s) => s.settings);
  const loading = useSettingsStore((s) => s.loading);
  const fetchSettings = useSettingsStore((s) => s.fetchSettings);
  const updateSettings = useSettingsStore((s) => s.updateSettings);
  const notify = useNotificationStore((s) => s.notify);

  const [frequency, setFrequency] = useState(30);
  const [cap, setCap] = useState(100);
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

  async function handleSave() {
    setSaving(true);
    try {
      await updateSettings({ osc_frequency: frequency, output_cap: cap });
      notify("success", "Settings saved successfully");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return null;

  return (
    <div className="p-8 max-w-xl">
      <h2 className="text-xl font-semibold text-zinc-100 mb-6">Settings</h2>

      <div className="space-y-6">
        {/* OSC Frequency */}
        <div className="bg-zinc-900/80 border border-zinc-800/50 rounded-xl p-6 shadow-sm">
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
              className="w-24 bg-zinc-800 border border-zinc-700/50 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-orange-500/50 transition-colors"
            />
            <span className="text-sm text-zinc-400">Hz</span>
            <span className="text-xs text-zinc-600 ml-2">
              ({Math.round(1000 / frequency)} ms between messages)
            </span>
          </div>
        </div>

        {/* Output Cap */}
        <div className="bg-zinc-900/80 border border-zinc-800/50 rounded-xl p-6 shadow-sm">
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
              className="w-24 bg-zinc-800 border border-zinc-700/50 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-orange-500/50 transition-colors"
            />
            <span className="text-sm text-zinc-400">%</span>
          </div>
        </div>

        <button
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-2 bg-orange-600 hover:bg-orange-500 disabled:opacity-50 rounded-lg text-sm font-medium transition-all duration-200"
        >
          {saving ? "Saving..." : "Save"}
        </button>
      </div>
    </div>
  );
}
