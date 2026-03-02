<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue";
import { useDeviceStore } from "../../stores/deviceStore";

const emit = defineEmits<{ close: [] }>();
const store = useDeviceStore();

interface ScanRow {
  ip: string;
  osc_port: number;
  ssh: boolean;
  potential_pi: boolean;
  hostname: string;
  selected: boolean;
}

const rows = ref<ScanRow[]>([]);

const selectedCount = computed(() => rows.value.filter((r) => r.selected).length);

// Watch scanResults for real-time updates
watch(
  () => store.scanResults,
  (results) => {
    for (const h of results) {
      const existing = rows.value.find((r) => r.ip === h.ip);
      if (existing) {
        existing.ssh = h.ssh;
        existing.potential_pi = h.potential_pi;
        if (h.hostname && !existing.hostname) {
          existing.hostname = h.hostname;
        }
      } else {
        rows.value.push({
          ip: h.ip,
          osc_port: h.osc_port,
          ssh: h.ssh,
          potential_pi: h.potential_pi,
          hostname: h.hostname,
          selected: false,
        });
      }
    }
  },
  { deep: true },
);

function deviceName(row: ScanRow): string {
  if (row.hostname) return row.hostname;
  return row.potential_pi
    ? `RPi ${row.ip.split(".").pop()}`
    : `Host ${row.ip.split(".").pop()}`;
}

// Auto-start scan on mount
onMounted(() => {
  rows.value = [];
  store.scan();
});

function selectAll(val: boolean) {
  rows.value.forEach((r) => (r.selected = val));
}

async function addSelected() {
  const hosts = rows.value
    .filter((r) => r.selected)
    .map((r) => ({ ip: r.ip, osc_port: r.osc_port, name: deviceName(r) }));
  if (!hosts.length) return;
  await store.addDiscovered(hosts);
  store.clearScanResults();
  emit("close");
}
</script>

<template>
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="emit('close')">
    <div class="bg-zinc-900 border border-zinc-700 rounded-lg w-full max-w-lg mx-4 shadow-xl">
      <div class="flex items-center justify-between p-4 border-b border-zinc-800">
        <h3 class="text-sm font-semibold">Scan Local Network</h3>
        <button @click="emit('close')" class="text-zinc-500 hover:text-white text-lg leading-none">&times;</button>
      </div>

      <div class="p-4 space-y-4">
        <!-- Scanning indicator -->
        <div v-if="store.scanning" class="flex items-center gap-2 text-xs text-zinc-400">
          <span class="inline-block animate-spin">&#9696;</span>
          <span>Scanning... {{ rows.length }} host{{ rows.length !== 1 ? "s" : "" }} found</span>
        </div>

        <!-- Error -->
        <p v-if="store.scanError" class="text-xs text-red-400">{{ store.scanError }}</p>

        <!-- Results -->
        <template v-if="rows.length">
          <div class="flex items-center justify-between text-xs text-zinc-400">
            <span>{{ rows.length }} host{{ rows.length !== 1 ? "s" : "" }} found</span>
            <span class="flex gap-2">
              <button @click="selectAll(true)" class="hover:text-white transition-colors">Select all</button>
              <button @click="selectAll(false)" class="hover:text-white transition-colors">Select none</button>
            </span>
          </div>

          <div class="max-h-60 overflow-y-auto space-y-1">
            <label
              v-for="row in rows"
              :key="row.ip"
              class="flex items-center gap-3 p-2 rounded hover:bg-zinc-800/50 cursor-pointer"
            >
              <input type="checkbox" v-model="row.selected" class="accent-orange-500" />
              <div class="flex-1 min-w-0">
                <span class="font-mono text-sm text-zinc-300 block">{{ row.ip }}:{{ row.osc_port }}</span>
                <span v-if="row.hostname" class="text-[11px] text-zinc-500 block truncate">{{ row.hostname }}</span>
              </div>
              <span
                v-if="row.potential_pi"
                class="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-emerald-900/60 text-emerald-400 shrink-0"
              >
                Potential Pi
              </span>
            </label>
          </div>

          <button
            @click="addSelected"
            :disabled="!selectedCount"
            class="w-full px-4 py-2 bg-orange-600 hover:bg-orange-500 disabled:opacity-40 rounded text-sm font-medium transition-colors"
          >
            Add Selected ({{ selectedCount }})
          </button>
        </template>

        <!-- Empty state -->
        <p
          v-if="!store.scanning && !rows.length && !store.scanError"
          class="text-xs text-zinc-500 text-center py-4"
        >
          No hosts found on the local network.
        </p>
      </div>
    </div>
  </div>
</template>
