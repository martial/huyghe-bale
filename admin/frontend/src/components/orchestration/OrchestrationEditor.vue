<script setup lang="ts">
import { reactive, onMounted, computed } from "vue";
import { useRouter } from "vue-router";
import type { Orchestration, OrchestrationStep } from "../../types/orchestration";
import { useOrchestrationStore } from "../../stores/orchestrationStore";
import { useTimelineStore } from "../../stores/timelineStore";
import { useDeviceStore } from "../../stores/deviceStore";
import OrchestrationStepCard from "./OrchestrationStepCard.vue";
import PlaybackStartButton from "../playback/PlaybackStartButton.vue";

const props = defineProps<{ orchestration: Orchestration }>();
const router = useRouter();
const orchStore = useOrchestrationStore();
const timelineStore = useTimelineStore();
const deviceStore = useDeviceStore();

const local = reactive<Orchestration>(JSON.parse(JSON.stringify(props.orchestration)));

onMounted(() => {
  timelineStore.fetchList();
  deviceStore.fetchList();
});

function generateId(): string {
  return "step_" + Math.random().toString(36).substring(2, 10);
}

function addStep() {
  const step: OrchestrationStep = {
    id: generateId(),
    order: local.steps.length,
    timeline_id: "",
    device_ids: [],
    delay_before: 0,
    label: `Step ${local.steps.length + 1}`,
  };
  local.steps.push(step);
}

function removeStep(id: string) {
  const idx = local.steps.findIndex((s) => s.id === id);
  if (idx >= 0) {
    local.steps.splice(idx, 1);
    // Re-order
    local.steps.forEach((s, i) => (s.order = i));
  }
}

function moveStep(id: string, direction: -1 | 1) {
  const idx = local.steps.findIndex((s) => s.id === id);
  const newIdx = idx + direction;
  if (newIdx < 0 || newIdx >= local.steps.length) return;
  const temp = local.steps[idx]!;
  local.steps[idx] = local.steps[newIdx]!;
  local.steps[newIdx] = temp;
  local.steps.forEach((s, i) => (s.order = i));
}

async function handleSave() {
  await orchStore.save(local as Orchestration);
}

const totalDuration = computed(() => {
  let total = 0;
  for (const step of local.steps) {
    total += step.delay_before;
    const tl = timelineStore.list.find((t) => t.id === step.timeline_id);
    if (tl) total += tl.duration;
  }
  return total;
});
</script>

<template>
  <div class="p-6">
    <div class="flex items-center gap-4 mb-6">
      <button @click="router.push('/orchestrations')" class="text-zinc-500 hover:text-white text-sm">
        &larr;
      </button>

      <input
        v-model="local.name"
        class="bg-transparent border-b border-zinc-700 focus:border-orange-400 outline-none text-lg font-medium px-1 py-0.5"
      />

      <label class="flex items-center gap-2 text-sm text-zinc-400">
        <input type="checkbox" v-model="local.loop" class="rounded" />
        Loop
      </label>

      <span class="text-xs text-zinc-500 font-mono">
        Total: {{ totalDuration.toFixed(1) }}s
      </span>

      <div class="ml-auto flex gap-2">
        <PlaybackStartButton type="orchestration" :id="local.id" />
        <button
          @click="handleSave"
          class="px-4 py-1.5 bg-orange-600 hover:bg-orange-500 rounded text-sm font-medium transition-colors"
        >
          Save
        </button>
      </div>
    </div>

    <!-- Steps bar visualization -->
    <div v-if="local.steps.length" class="flex gap-1 mb-6 h-10 rounded overflow-hidden">
      <div
        v-for="step in local.steps"
        :key="step.id"
        class="flex items-center justify-center text-xs font-medium bg-zinc-800 border border-zinc-700 rounded px-2 min-w-16"
        :style="{
          flex: (timelineStore.list.find(t => t.id === step.timeline_id)?.duration || 10) + step.delay_before,
        }"
      >
        {{ step.label || "—" }}
      </div>
    </div>

    <!-- Step list -->
    <div class="space-y-3">
      <OrchestrationStepCard
        v-for="step in local.steps"
        :key="step.id"
        :step="step"
        :timelines="timelineStore.list"
        :devices="deviceStore.list"
        :is-first="step.order === 0"
        :is-last="step.order === local.steps.length - 1"
        @move-up="moveStep(step.id, -1)"
        @move-down="moveStep(step.id, 1)"
        @remove="removeStep(step.id)"
      />
    </div>

    <button
      @click="addStep"
      class="mt-4 w-full py-2 border border-dashed border-zinc-700 hover:border-zinc-500 rounded-lg text-sm text-zinc-400 hover:text-white transition-colors"
    >
      + Add Step
    </button>
  </div>
</template>
