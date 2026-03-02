<script setup lang="ts">
import { ref } from "vue";
import type { Device } from "../../types/device";
import { useDeviceStore } from "../../stores/deviceStore";

const props = defineProps<{ device: Device }>();
const store = useDeviceStore();
const pingStatus = ref<"idle" | "ok" | "error">("idle");
const editing = ref(false);
const form = ref({ ...props.device });

async function handlePing() {
  try {
    pingStatus.value = "idle";
    const result = await store.ping(props.device.id);
    pingStatus.value = result.ok ? "ok" : "error";
  } catch {
    pingStatus.value = "error";
  }
  setTimeout(() => (pingStatus.value = "idle"), 3000);
}

async function handleSave() {
  await store.update(form.value as Device);
  editing.value = false;
}

async function handleDelete() {
  await store.remove(props.device.id);
}
</script>

<template>
  <div class="p-4 rounded-lg border border-zinc-800 bg-zinc-900/50">
    <template v-if="!editing">
      <div class="flex items-start justify-between">
        <div>
          <p class="font-medium">{{ device.name }}</p>
          <p class="text-xs text-zinc-500 font-mono mt-1">
            {{ device.ip_address }}:{{ device.osc_port }}
          </p>
        </div>
        <div class="flex items-center gap-1">
          <div
            class="w-2 h-2 rounded-full transition-colors"
            :class="{
              'bg-zinc-600': pingStatus === 'idle',
              'bg-green-400': pingStatus === 'ok',
              'bg-red-400': pingStatus === 'error',
            }"
          />
        </div>
      </div>
      <div class="flex gap-2 mt-3">
        <button @click="handlePing" class="text-xs text-zinc-400 hover:text-white transition-colors">
          Ping
        </button>
        <button @click="editing = true; form = { ...device }" class="text-xs text-zinc-400 hover:text-white transition-colors">
          Edit
        </button>
        <button @click="handleDelete" class="text-xs text-red-400/60 hover:text-red-400 transition-colors">
          Delete
        </button>
      </div>
    </template>

    <template v-else>
      <div class="space-y-2">
        <input v-model="form.name" class="w-full bg-zinc-800 rounded px-2 py-1 text-sm" placeholder="Name" />
        <input v-model="form.ip_address" class="w-full bg-zinc-800 rounded px-2 py-1 text-sm font-mono" placeholder="IP Address" />
        <input v-model.number="form.osc_port" type="number" class="w-full bg-zinc-800 rounded px-2 py-1 text-sm font-mono" placeholder="Port" />
        <div class="flex gap-2">
          <button @click="handleSave" class="text-xs text-orange-400 hover:text-orange-300">Save</button>
          <button @click="editing = false" class="text-xs text-zinc-400 hover:text-white">Cancel</button>
        </div>
      </div>
    </template>
  </div>
</template>
