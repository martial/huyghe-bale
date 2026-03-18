<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import { useDeviceStore } from "../../stores/deviceStore";
import { usePlaybackStore } from "../../stores/playbackStore";

const deviceStore = useDeviceStore();
const playbackStore = usePlaybackStore();

const heartbeats = ref<Record<string, { ok: boolean; rx: boolean }>>({});
let interval: number;
let lastOscMap: Record<string, number> = {};

async function pollHeartbeats() {
  for (const device of deviceStore.list) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 800);
      const res = await fetch(`http://${device.ip_address}:9001/status`, { signal: controller.signal });
      clearTimeout(timeoutId);
      
      if (res.ok) {
        const data = await res.json();
        const prevOsc = lastOscMap[device.id] || 0;
        const currentOsc = data.last_osc || 0;
        let receivedRecent = heartbeats.value[device.id]?.rx || false;
        if (currentOsc > prevOsc) {
          receivedRecent = true;
          setTimeout(() => { if (heartbeats.value[device.id] !== undefined) heartbeats.value[device.id]!.rx = false; }, 800);
        }
        
        heartbeats.value[device.id] = { ok: true, rx: receivedRecent };
        lastOscMap[device.id] = currentOsc;
      } else {
        heartbeats.value[device.id] = { ok: false, rx: false };
      }
    } catch {
      heartbeats.value[device.id] = { ok: false, rx: false };
    }
  }
}

onMounted(() => {
  deviceStore.fetchList();
  interval = setInterval(pollHeartbeats, 500); // Fast poll for immediate RX visual feedback
});

onUnmounted(() => {
  clearInterval(interval);
});
</script>

<template>
  <div class="flex flex-col gap-1.5 mb-2">
    <div v-if="deviceStore.list.length === 0" class="text-[10px] text-zinc-600 px-3">
      No devices found
    </div>
    <div 
      v-for="device in deviceStore.list" 
      :key="device.id" 
      class="flex flex-col gap-1 px-3 py-1.5 rounded-md transition-colors border border-zinc-800/50 bg-zinc-900/30"
      :title="`${device.name} (${device.ip_address})`"
    >
      <div class="flex justify-between items-center">
        <span class="text-xs text-zinc-400 font-mono truncate">{{ device.name }}</span>
        
        <div class="flex items-center gap-1.5">
          <!-- TX (Sent) -->
          <div 
            class="w-2 h-2 rounded-full transition-all duration-75"
            :class="playbackStore.status.playing ? 'bg-orange-400 shadow-[0_0_5px_rgba(249,115,22,0.6)]' : 'bg-zinc-700'"
            title="TX: Signal Envoyé (Playing)"
          />
          <!-- Line connector -->
          <div class="w-2 h-px bg-zinc-700"></div>
          <!-- RX (Received) -->
          <div 
            class="w-2 h-2 rounded-full transition-all duration-75"
            :class="heartbeats[device.id]?.rx ? 'bg-green-400 shadow-[0_0_5px_rgba(74,222,128,0.6)]' : (heartbeats[device.id]?.ok ? 'bg-zinc-500' : 'bg-red-500/80')"
            title="RX: Signal Reçu par le Pi (Vert = Reçu, Gris = Connecté, Rouge = Hors-ligne)"
          />
        </div>
      </div>
      
      <div class="flex justify-between text-[8px] uppercase tracking-wider font-semibold text-zinc-600">
        <span>TX</span>
        <span :class="!heartbeats[device.id]?.ok ? 'text-red-500/80' : ''">
          {{ heartbeats[device.id]?.ok ? 'RX' : 'OFFLINE' }}
        </span>
      </div>
    </div>
  </div>
</template>
