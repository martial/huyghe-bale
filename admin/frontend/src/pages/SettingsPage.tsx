import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useSettingsStore } from "../stores/settings-store";
import { useNotificationStore } from "../stores/notification-store";
import type { BridgeRouting, Settings } from "../api/settings";
import RoutingHelp from "../components/bridge/RoutingHelp";

function SectionHeader({
  icon, title, subtitle,
}: { icon: ReactNode; title: string; subtitle: string }) {
  return (
    <div className="flex items-center gap-3 mb-4">
      <div className="w-9 h-9 rounded-xl bg-zinc-800/70 border border-white/5 flex items-center justify-center text-zinc-300">
        {icon}
      </div>
      <div>
        <h3 className="text-base font-medium text-white tracking-tight leading-tight">{title}</h3>
        <p className="text-xs text-zinc-500 leading-tight">{subtitle}</p>
      </div>
    </div>
  );
}

function Section({ children }: { children: ReactNode }) {
  return (
    <section className="bg-zinc-900/40 backdrop-blur-sm border border-white/5 rounded-2xl p-6 shadow-lg">
      {children}
    </section>
  );
}

function Field({
  label, hint, children, accent = "orange",
}: {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
  accent?: "orange" | "sky";
}) {
  const ring = accent === "sky" ? "focus-within:ring-sky-500/30" : "focus-within:ring-orange-500/30";
  return (
    <div className={`group rounded-xl border border-white/5 bg-zinc-900/40 px-4 py-3 transition-all focus-within:border-white/15 focus-within:ring-2 ${ring}`}>
      <div className="flex items-center justify-between gap-4">
        <label className="text-[13px] font-medium text-zinc-200">{label}</label>
        <div className="flex items-center gap-2">{children}</div>
      </div>
      {hint && <p className="text-[11px] text-zinc-500 mt-2 leading-snug">{hint}</p>}
    </div>
  );
}

function NumInput({
  value, onChange, min, max, step, width = "w-24", accent = "orange", suffix,
}: {
  value: number;
  onChange: (n: number) => void;
  min: number;
  max: number;
  step: number;
  width?: string;
  accent?: "orange" | "sky";
  suffix?: string;
}) {
  const focus = accent === "sky" ? "focus:border-sky-500/50" : "focus:border-orange-500/50";
  return (
    <>
      <input
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        type="number"
        min={min}
        max={max}
        step={step}
        className={`${width} bg-zinc-800 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-zinc-100 tabular-nums text-right focus:outline-none ${focus} transition-colors`}
      />
      {suffix && <span className="text-xs text-zinc-500 w-8">{suffix}</span>}
    </>
  );
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (b: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`relative w-10 h-6 rounded-full transition-colors ${checked ? "bg-sky-500" : "bg-zinc-700"}`}
      aria-pressed={checked}
    >
      <span
        className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${checked ? "translate-x-4" : ""}`}
      />
    </button>
  );
}

// Icons (inline SVG keeps the bundle small).
const IconPlayback = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="5 3 19 12 5 21 5 3" /></svg>
);
const IconShield = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
);
const IconBridge = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 17h18M5 17V8a3 3 0 0 1 6 0M13 8a3 3 0 0 1 6 0v9"/></svg>
);

export default function SettingsPage() {
  const settings = useSettingsStore((s) => s.settings);
  const loading = useSettingsStore((s) => s.loading);
  const fetchSettings = useSettingsStore((s) => s.fetchSettings);
  const updateSettings = useSettingsStore((s) => s.updateSettings);
  const notify = useNotificationStore((s) => s.notify);

  const [frequency, setFrequency] = useState(30);
  const [bridgeEnabled, setBridgeEnabled] = useState(false);
  const [bridgePort, setBridgePort] = useState(9002);
  const [bridgeRouting, setBridgeRouting] = useState<BridgeRouting>("type-match");
  const [ventsMaxTemp, setVentsMaxTemp] = useState(80);
  const [ventsMinFanPct, setVentsMinFanPct] = useState(20);
  const [ventsMaxFanPct, setVentsMaxFanPct] = useState(100);
  const [ventsMinRpmAlarm, setVentsMinRpmAlarm] = useState(500);
  const [ventsOverTempFanPct, setVentsOverTempFanPct] = useState(100);
  const [saving, setSaving] = useState(false);

  useEffect(() => { fetchSettings(); }, [fetchSettings]);

  useEffect(() => { setFrequency(settings.osc_frequency); }, [settings.osc_frequency]);
  useEffect(() => {
    setBridgeEnabled(settings.bridge_enabled);
    setBridgePort(settings.bridge_port);
    setBridgeRouting(settings.bridge_routing);
    setVentsMaxTemp(settings.vents_max_temp_c ?? 80);
    setVentsMinFanPct(settings.vents_min_fan_pct ?? 20);
    setVentsMaxFanPct(settings.vents_max_fan_pct ?? 100);
    setVentsMinRpmAlarm(settings.vents_min_rpm_alarm ?? 500);
    setVentsOverTempFanPct(settings.vents_over_temp_fan_pct ?? 100);
  }, [
    settings.bridge_enabled, settings.bridge_port, settings.bridge_routing,
    settings.vents_max_temp_c, settings.vents_min_fan_pct, settings.vents_max_fan_pct,
    settings.vents_min_rpm_alarm, settings.vents_over_temp_fan_pct,
  ]);

  const draft: Partial<Settings> = useMemo(() => ({
    osc_frequency: frequency,
    bridge_enabled: bridgeEnabled,
    bridge_port: bridgePort,
    bridge_routing: bridgeRouting,
    vents_max_temp_c: ventsMaxTemp,
    vents_min_fan_pct: ventsMinFanPct,
    vents_max_fan_pct: ventsMaxFanPct,
    vents_min_rpm_alarm: ventsMinRpmAlarm,
    vents_over_temp_fan_pct: ventsOverTempFanPct,
  }), [
    frequency, bridgeEnabled, bridgePort, bridgeRouting,
    ventsMaxTemp, ventsMinFanPct, ventsMaxFanPct, ventsMinRpmAlarm, ventsOverTempFanPct,
  ]);

  const dirty = useMemo(
    () => (Object.keys(draft) as (keyof Settings)[]).some((k) => settings[k] !== draft[k]),
    [draft, settings],
  );

  async function handleSave() {
    setSaving(true);
    try {
      await updateSettings(draft);
      notify("success", "Settings saved");
    } finally {
      setSaving(false);
    }
  }

  function handleReset() {
    setFrequency(settings.osc_frequency);
    setBridgeEnabled(settings.bridge_enabled);
    setBridgePort(settings.bridge_port);
    setBridgeRouting(settings.bridge_routing);
    setVentsMaxTemp(settings.vents_max_temp_c ?? 80);
    setVentsMinFanPct(settings.vents_min_fan_pct ?? 20);
    setVentsMaxFanPct(settings.vents_max_fan_pct ?? 100);
    setVentsMinRpmAlarm(settings.vents_min_rpm_alarm ?? 500);
    setVentsOverTempFanPct(settings.vents_over_temp_fan_pct ?? 100);
  }

  if (loading) return null;

  return (
    <div className="p-10 pb-32 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <header className="flex items-center justify-between mb-10 pb-4 border-b border-white/10">
        <div>
          <h2 className="text-3xl font-light tracking-tight text-white mb-1">Settings</h2>
          <p className="text-zinc-400 text-sm">
            Global parameters applied to playback, the OSC bridge, and every vents device.
          </p>
        </div>
      </header>

      <div className="space-y-6">
            {/* ── Playback ─────────────────────────────────────── */}
            <Section>
              <SectionHeader
                icon={IconPlayback}
                title="Playback"
                subtitle="How fast and how hard the engine drives devices."
              />
              <div className="space-y-2">
                <Field
                  label="OSC send frequency"
                  hint={`Rate at which values are sent during playback — currently ${Math.round(1000 / frequency)} ms between messages.`}
                >
                  <NumInput value={frequency} onChange={setFrequency} min={1} max={120} step={1} suffix="Hz" />
                </Field>
              </div>
            </Section>

            {/* ── Vents safety ─────────────────────────────────── */}
            <Section>
              <SectionHeader
                icon={IconShield}
                title="Vents safety"
                subtitle="Limits applied on every vents Pi. Saved to vents_prefs.json on each device."
              />
              <div className="space-y-2">
                <Field
                  label="Max temperature"
                  hint={
                    <>
                      Per-sensor safety ceiling. If <strong>any probe</strong> exceeds this, the Pi cuts all Peltiers
                      and pins both fans to the over-temp fan PWM below.
                    </>
                  }
                >
                  <NumInput value={ventsMaxTemp} onChange={setVentsMaxTemp} min={-55} max={125} step={0.1} width="w-24" suffix="°C" />
                </Field>
                <Field
                  label="Minimum fan PWM"
                  hint="Floor enforced on every fan command above zero. Keeps ventilation always on. Explicit 0% still passes through."
                >
                  <NumInput value={ventsMinFanPct} onChange={setVentsMinFanPct} min={0} max={100} step={1} suffix="%" />
                </Field>
                <Field
                  label="Maximum fan PWM"
                  hint={
                    <>
                      Scale applied to every fan command on the Pi. Effective output is{" "}
                      <span className="font-mono">command × max ÷ 100</span> — at 80, a 100% lane sends 80% and a 50%
                      lane sends 40%. Pushed to every vents Pi on Save.
                    </>
                  }
                >
                  <NumInput value={ventsMaxFanPct} onChange={setVentsMaxFanPct} min={0} max={100} step={1} suffix="%" />
                </Field>
                <Field
                  label="Over-temperature fan PWM"
                  hint="Forced on both fans whenever any probe exceeds max temperature."
                >
                  <NumInput value={ventsOverTempFanPct} onChange={setVentsOverTempFanPct} min={0} max={100} step={1} suffix="%" />
                </Field>
                <Field
                  label="RPM alarm threshold"
                  hint="Admin watches each fan tach at 5 Hz. Below this for ≥ 3 s while commanded > 0% raises an alarm badge. 0 disables."
                >
                  <NumInput value={ventsMinRpmAlarm} onChange={setVentsMinRpmAlarm} min={0} max={10000} step={50} width="w-24" suffix="RPM" />
                </Field>
              </div>
            </Section>

            {/* ── OSC Bridge ───────────────────────────────────── */}
            <Section>
              <SectionHeader
                icon={IconBridge}
                title="OSC Bridge"
                subtitle="Listen on a UDP port and rebroadcast to devices."
              />
              <div className="space-y-2">
                <Field label="Enabled" hint="Live feed and traffic preview on the /bridge page.">
                  <Toggle checked={bridgeEnabled} onChange={setBridgeEnabled} />
                </Field>
                <Field label="Port" accent="sky">
                  <NumInput
                    value={bridgePort}
                    onChange={setBridgePort}
                    min={1024}
                    max={65535}
                    step={1}
                    width="w-28"
                    accent="sky"
                  />
                </Field>
                <Field
                  label={"Routing"}
                  hint={
                    <span className="inline-flex items-center gap-1.5">
                      How incoming addresses fan out to devices <RoutingHelp />
                    </span>
                  }
                  accent="sky"
                >
                  <select
                    value={bridgeRouting}
                    onChange={(e) => setBridgeRouting(e.target.value as BridgeRouting)}
                    className="bg-zinc-800 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-zinc-100 focus:outline-none focus:border-sky-500/50 max-w-[260px] truncate"
                  >
                    <option value="type-match">type-match</option>
                    <option value="passthrough">passthrough</option>
                    <option value="none">none — tap only</option>
                  </select>
                </Field>
              </div>
            </Section>
      </div>

      {/* Sticky save bar */}
      <div className="fixed bottom-0 left-0 right-0 z-30 border-t border-white/10 bg-zinc-950/80 backdrop-blur-md">
        <div className="px-10 py-3 flex items-center justify-between">
          <span className={`text-xs ${dirty ? "text-orange-300" : "text-zinc-500"}`}>
            {dirty ? "Unsaved changes" : "Up to date"}
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={handleReset}
              disabled={!dirty || saving}
              className="px-4 py-2 text-sm text-zinc-300 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              Reset
            </button>
            <button
              onClick={handleSave}
              disabled={!dirty || saving}
              className="px-5 py-2 bg-gradient-to-r from-orange-500 to-orange-400 hover:from-orange-400 hover:to-orange-300 disabled:opacity-40 disabled:cursor-not-allowed rounded-xl text-sm font-semibold text-white shadow-[0_0_20px_rgba(249,115,22,0.3)] hover:shadow-[0_0_30px_rgba(249,115,22,0.5)] transition-all duration-300"
            >
              {saving ? "Saving…" : "Save changes"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
