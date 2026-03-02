<script setup lang="ts">
import type { OrchestrationStep } from "../../types/orchestration";
import type { TimelineSummary } from "../../types/timeline";
import type { Device } from "../../types/device";

const props = defineProps<{
  step: OrchestrationStep;
  timelines: TimelineSummary[];
  devices: Device[];
  isFirst: boolean;
  isLast: boolean;
}>();

const emit = defineEmits<{
  "move-up": [];
  "move-down": [];
  remove: [];
}>();

function toggleDevice(id: string) {
  const idx = props.step.device_ids.indexOf(id);
  if (idx >= 0) props.step.device_ids.splice(idx, 1);
  else props.step.device_ids.push(id);
}
</script>

<template>
  <div class="p-4 rounded-lg border border-zinc-800 bg-zinc-900/50">
    <div class="flex items-start gap-4">
      <!-- Order controls -->
      <div class="flex flex-col gap-0.5 pt-1">
        <button
          @click="emit('move-up')"
          :disabled="isFirst"
          class="text-zinc-500 hover:text-white disabled:opacity-20 text-xs"
        >
          &uarr;
        </button>
        <span class="text-xs text-zinc-600 text-center">{{ step.order + 1 }}</span>
        <button
          @click="emit('move-down')"
          :disabled="isLast"
          class="text-zinc-500 hover:text-white disabled:opacity-20 text-xs"
        >
          &darr;
        </button>
      </div>

      <div class="flex-1 grid grid-cols-4 gap-3">
        <!-- Label -->
        <div>
          <label class="text-xs text-zinc-500 block mb-1">Label</label>
          <input
            v-model="step.label"
            class="w-full bg-zinc-800 rounded px-2 py-1 text-sm"
            placeholder="Step name"
          />
        </div>

        <!-- Timeline -->
        <div>
          <label class="text-xs text-zinc-500 block mb-1">Timeline</label>
          <select
            v-model="step.timeline_id"
            class="w-full bg-zinc-800 rounded px-2 py-1 text-sm"
          >
            <option value="">— Select —</option>
            <option v-for="tl in timelines" :key="tl.id" :value="tl.id">
              {{ tl.name }} ({{ tl.duration }}s)
            </option>
          </select>
        </div>

        <!-- Delay -->
        <div>
          <label class="text-xs text-zinc-500 block mb-1">Delay before (s)</label>
          <input
            v-model.number="step.delay_before"
            type="number"
            min="0"
            step="0.5"
            class="w-full bg-zinc-800 rounded px-2 py-1 text-sm font-mono"
          />
        </div>

        <!-- Devices -->
        <div>
          <label class="text-xs text-zinc-500 block mb-1">Devices</label>
          <div class="flex flex-wrap gap-1">
            <label
              v-for="dev in devices"
              :key="dev.id"
              class="flex items-center gap-1 text-xs cursor-pointer"
            >
              <input
                type="checkbox"
                :checked="step.device_ids.includes(dev.id)"
                @change="toggleDevice(dev.id)"
                class="rounded"
              />
              {{ dev.name }}
            </label>
          </div>
        </div>
      </div>

      <button @click="emit('remove')" class="text-red-400/60 hover:text-red-400 text-xs pt-1">
        Remove
      </button>
    </div>
  </div>
</template>
