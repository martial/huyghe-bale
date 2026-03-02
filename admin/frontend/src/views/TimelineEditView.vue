<script setup lang="ts">
import { onMounted, watch } from "vue";
import { useTimelineStore } from "../stores/timelineStore";
import TimelineEditor from "../components/timeline/TimelineEditor.vue";

const props = defineProps<{ id: string }>();
const store = useTimelineStore();

onMounted(() => store.fetchOne(props.id));
watch(() => props.id, (id) => store.fetchOne(id));
</script>

<template>
  <div class="h-full flex flex-col">
    <div v-if="store.loading" class="flex-1 flex items-center justify-center text-zinc-500">
      Loading...
    </div>
    <TimelineEditor v-else-if="store.current" :timeline="store.current" />
    <div v-else class="flex-1 flex items-center justify-center text-zinc-500">
      Timeline not found
    </div>
  </div>
</template>
