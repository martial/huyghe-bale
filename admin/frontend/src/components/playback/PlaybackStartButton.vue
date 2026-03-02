<script setup lang="ts">
import { ref } from "vue";
import { usePlaybackStore } from "../../stores/playbackStore";
import { useDeviceStore } from "../../stores/deviceStore";

const props = defineProps<{
  type: "timeline" | "orchestration";
  id: string;
}>();

const playback = usePlaybackStore();
const deviceStore = useDeviceStore();
const showDevicePicker = ref(false);
const selectedDeviceIds = ref<string[]>([]);

function toggleDevice(id: string) {
  const idx = selectedDeviceIds.value.indexOf(id);
  if (idx >= 0) selectedDeviceIds.value.splice(idx, 1);
  else selectedDeviceIds.value.push(id);
}

async function handleStart() {
  if (!deviceStore.list.length) {
    await deviceStore.fetchList();
  }
  if (!selectedDeviceIds.value.length && deviceStore.list.length) {
    // Auto-select all devices if none selected
    selectedDeviceIds.value = deviceStore.list.map((d) => d.id);
  }
  if (!selectedDeviceIds.value.length) {
    showDevicePicker.value = true;
    return;
  }
  await playback.start(props.type, props.id, selectedDeviceIds.value);
  showDevicePicker.value = false;
}
</script>

<template>
  <div class="relative">
    <button
      @click="handleStart"
      :disabled="playback.status.playing"
      class="px-4 py-1.5 bg-green-600 hover:bg-green-500 disabled:opacity-50 rounded text-sm font-medium transition-colors"
    >
      Play
    </button>

    <div
      v-if="showDevicePicker"
      class="absolute top-full mt-1 right-0 bg-zinc-800 rounded-lg border border-zinc-700 p-3 z-10 min-w-48"
    >
      <p class="text-xs text-zinc-400 mb-2">Select devices:</p>
      <label
        v-for="dev in deviceStore.list"
        :key="dev.id"
        class="flex items-center gap-2 py-1 text-sm cursor-pointer"
      >
        <input
          type="checkbox"
          :checked="selectedDeviceIds.includes(dev.id)"
          @change="toggleDevice(dev.id)"
          class="rounded"
        />
        {{ dev.name }}
      </label>
      <button
        @click="handleStart"
        :disabled="!selectedDeviceIds.length"
        class="mt-2 w-full px-3 py-1 bg-green-600 hover:bg-green-500 disabled:opacity-50 rounded text-xs font-medium"
      >
        Start
      </button>
    </div>
  </div>
</template>
