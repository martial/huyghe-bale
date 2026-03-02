<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useDeviceStore } from "../stores/deviceStore";
import DeviceCard from "../components/device/DeviceCard.vue";
import DeviceForm from "../components/device/DeviceForm.vue";
import NetworkScanModal from "../components/device/NetworkScanModal.vue";

const store = useDeviceStore();
const showForm = ref(false);
const showScan = ref(false);

onMounted(() => store.fetchList());
</script>

<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-semibold">Devices</h2>
      <div class="flex gap-2">
        <button
          @click="showScan = true"
          class="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 rounded-md text-sm font-medium transition-colors"
        >
          Scan Network
        </button>
        <button
          @click="showForm = !showForm"
          class="px-4 py-2 bg-orange-600 hover:bg-orange-500 rounded-md text-sm font-medium transition-colors"
        >
          {{ showForm ? "Cancel" : "+ Add Device" }}
        </button>
      </div>
    </div>

    <DeviceForm v-if="showForm" @created="showForm = false" />

    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-4">
      <DeviceCard v-for="device in store.list" :key="device.id" :device="device" />
    </div>

    <p v-if="!store.list.length && !showForm" class="text-zinc-500 text-sm mt-8 text-center">
      No devices configured yet. Add one to get started.
    </p>

    <NetworkScanModal v-if="showScan" @close="showScan = false" />
  </div>
</template>
