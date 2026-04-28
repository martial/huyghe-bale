import { create } from "zustand";
import * as api from "../api/settings";
import type { Settings } from "../api/settings";

interface SettingsState {
  settings: Settings;
  loading: boolean;
  fetchSettings: () => Promise<void>;
  updateSettings: (data: Partial<Settings>) => Promise<void>;
}

export const useSettingsStore = create<SettingsState>((set) => ({
  settings: {
    osc_frequency: 30,
    bridge_enabled: false,
    bridge_port: 9002,
    bridge_routing: "type-match",
    vents_max_temp_c: 80,
    vents_min_fan_pct: 20,
    vents_max_fan_pct: 100,
    vents_min_rpm_alarm: 500,
    vents_over_temp_fan_pct: 100,
  },
  loading: false,

  async fetchSettings() {
    set({ loading: true });
    try {
      const settings = await api.getSettings();
      set({ settings });
    } finally {
      set({ loading: false });
    }
  },

  async updateSettings(data: Partial<Settings>) {
    const settings = await api.updateSettings(data);
    set({ settings });
  },
}));
