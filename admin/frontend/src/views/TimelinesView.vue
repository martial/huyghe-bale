<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { useTimelineStore } from "../stores/timelineStore";
import TimelineList from "../components/timeline/TimelineList.vue";

const router = useRouter();
const store = useTimelineStore();

onMounted(() => store.fetchList());

async function handleCreate() {
  const tl = await store.create({ name: "New Timeline", duration: 60 });
  router.push(`/timelines/${tl.id}`);
}
</script>

<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-semibold">Timelines</h2>
      <button
        @click="handleCreate"
        class="px-4 py-2 bg-orange-600 hover:bg-orange-500 rounded-md text-sm font-medium transition-colors"
      >
        + New Timeline
      </button>
    </div>
    <TimelineList />
  </div>
</template>
