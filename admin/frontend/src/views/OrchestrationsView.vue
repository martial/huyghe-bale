<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { useOrchestrationStore } from "../stores/orchestrationStore";

const router = useRouter();
const store = useOrchestrationStore();

onMounted(() => store.fetchList());

async function handleCreate() {
  const orch = await store.create({ name: "New Orchestration" });
  router.push(`/orchestrations/${orch.id}`);
}
</script>

<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-semibold">Orchestrations</h2>
      <button
        @click="handleCreate"
        class="px-4 py-2 bg-orange-600 hover:bg-orange-500 rounded-md text-sm font-medium transition-colors"
      >
        + New Orchestration
      </button>
    </div>

    <div class="space-y-2">
      <RouterLink
        v-for="orch in store.list"
        :key="orch.id"
        :to="`/orchestrations/${orch.id}`"
        class="block p-4 rounded-lg border border-zinc-800 hover:border-zinc-600 transition-colors"
      >
        <div class="flex items-center justify-between">
          <div>
            <p class="font-medium">{{ orch.name }}</p>
            <p class="text-xs text-zinc-500 mt-1">
              {{ orch.steps?.length || 0 }} step(s)
              <span v-if="orch.loop" class="ml-2 text-orange-400">looping</span>
            </p>
          </div>
          <span class="text-zinc-600 text-xs font-mono">{{ orch.id }}</span>
        </div>
      </RouterLink>
    </div>

    <p v-if="!store.list.length" class="text-zinc-500 text-sm mt-8 text-center">
      No orchestrations yet.
    </p>
  </div>
</template>
