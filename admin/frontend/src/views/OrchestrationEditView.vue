<script setup lang="ts">
import { onMounted, watch } from "vue";
import { useOrchestrationStore } from "../stores/orchestrationStore";
import OrchestrationEditor from "../components/orchestration/OrchestrationEditor.vue";

const props = defineProps<{ id: string }>();
const store = useOrchestrationStore();

onMounted(() => store.fetchOne(props.id));
watch(() => props.id, (id) => store.fetchOne(id));
</script>

<template>
  <div class="h-full">
    <div v-if="store.loading" class="flex items-center justify-center h-full text-zinc-500">
      Loading...
    </div>
    <OrchestrationEditor v-else-if="store.current" :orchestration="store.current" />
    <div v-else class="flex items-center justify-center h-full text-zinc-500">
      Orchestration not found
    </div>
  </div>
</template>
