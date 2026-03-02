<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useSettingsStore } from "../stores/settingsStore";

const store = useSettingsStore();
const frequency = ref(30);
const saving = ref(false);

onMounted(async () => {
  await store.fetch();
  frequency.value = store.settings.osc_frequency;
});

watch(() => store.settings.osc_frequency, (v) => {
  frequency.value = v;
});

async function save() {
  saving.value = true;
  try {
    await store.update({ osc_frequency: frequency.value });
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="p-6 max-w-xl">
    <h2 class="text-xl font-semibold mb-6">Settings</h2>

    <div class="space-y-6">
      <!-- OSC Frequency -->
      <div class="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
        <label class="block text-sm font-medium text-zinc-300 mb-1">
          OSC Send Frequency
        </label>
        <p class="text-xs text-zinc-500 mb-3">
          Rate at which values are sent to devices during playback (1–120 Hz).
        </p>
        <div class="flex items-center gap-3">
          <input
            v-model.number="frequency"
            type="number"
            min="1"
            max="120"
            step="1"
            class="w-24 bg-zinc-800 border border-zinc-700 rounded-md px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-orange-500"
          />
          <span class="text-sm text-zinc-400">Hz</span>
          <span class="text-xs text-zinc-600 ml-2">
            ({{ Math.round(1000 / frequency) }} ms between messages)
          </span>
        </div>
      </div>

      <button
        @click="save"
        :disabled="saving"
        class="px-4 py-2 bg-orange-600 hover:bg-orange-500 disabled:opacity-50 rounded-md text-sm font-medium transition-colors"
      >
        {{ saving ? "Saving..." : "Save" }}
      </button>
    </div>
  </div>
</template>
