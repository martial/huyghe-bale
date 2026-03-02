<script setup lang="ts">
import { ref } from "vue";
import { useDeviceStore } from "../../stores/deviceStore";

const emit = defineEmits<{ created: [] }>();
const store = useDeviceStore();

const name = ref("");
const ip_address = ref("");
const osc_port = ref(9000);

async function handleSubmit() {
  await store.create({ name: name.value, ip_address: ip_address.value, osc_port: osc_port.value });
  name.value = "";
  ip_address.value = "";
  osc_port.value = 9000;
  emit("created");
}
</script>

<template>
  <form @submit.prevent="handleSubmit" class="p-4 rounded-lg border border-zinc-700 bg-zinc-900/50 space-y-3">
    <div class="grid grid-cols-3 gap-3">
      <div>
        <label class="text-xs text-zinc-400 block mb-1">Name</label>
        <input v-model="name" required class="w-full bg-zinc-800 rounded px-3 py-1.5 text-sm" placeholder="Room 11" />
      </div>
      <div>
        <label class="text-xs text-zinc-400 block mb-1">IP Address</label>
        <input v-model="ip_address" required class="w-full bg-zinc-800 rounded px-3 py-1.5 text-sm font-mono" placeholder="192.168.1.101" />
      </div>
      <div>
        <label class="text-xs text-zinc-400 block mb-1">OSC Port</label>
        <input v-model.number="osc_port" type="number" class="w-full bg-zinc-800 rounded px-3 py-1.5 text-sm font-mono" />
      </div>
    </div>
    <button type="submit" class="px-4 py-1.5 bg-orange-600 hover:bg-orange-500 rounded text-sm font-medium transition-colors">
      Add Device
    </button>
  </form>
</template>
