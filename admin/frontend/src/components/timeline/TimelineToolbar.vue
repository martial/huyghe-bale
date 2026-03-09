<script setup lang="ts">
import { useRouter } from "vue-router";
import type { Timeline, Point, CurveType } from "../../types/timeline";

const props = defineProps<{
  timeline: Timeline;
  selectedPoint: Point | null;
}>();

const emit = defineEmits<{
  "update:name": [name: string];
  "update:duration": [duration: number];
  "update:curve-type": [curveType: CurveType];
  save: [];
}>();

const router = useRouter();

const curveTypes: CurveType[] = [
  "linear",
  "step",
  "ease-in",
  "ease-out",
  "ease-in-out",
  "sine",
  "exponential",
  "bezier",
];
</script>

<template>
  <div class="flex items-center gap-4 px-4 py-2 border-b border-zinc-800 bg-zinc-900/50">
    <button @click="router.push('/timelines')" class="text-zinc-500 hover:text-white text-sm">
      &larr;
    </button>

    <input
      :value="timeline.name"
      @input="emit('update:name', ($event.target as HTMLInputElement).value)"
      class="bg-transparent border-b border-zinc-700 focus:border-orange-400 outline-none text-sm font-medium px-1 py-0.5 w-48"
    />

    <label class="flex items-center gap-1 text-xs text-zinc-500">
      Duration
      <input
        :value="timeline.duration"
        @change="emit('update:duration', Number(($event.target as HTMLInputElement).value))"
        type="number"
        min="1"
        step="1"
        class="bg-zinc-800 rounded px-2 py-0.5 w-16 text-sm text-zinc-200 font-mono"
      />
      <span>s</span>
    </label>

    <div v-if="selectedPoint" class="flex items-center gap-2 ml-4 pl-4 border-l border-zinc-800">
      <span class="text-xs text-zinc-500">Curve:</span>
      <select
        :value="selectedPoint.curve_type"
        @change="emit('update:curve-type', ($event.target as HTMLSelectElement).value as CurveType)"
        class="bg-zinc-800 rounded px-2 py-0.5 text-xs text-zinc-200"
      >
        <option v-for="ct in curveTypes" :key="ct" :value="ct">{{ ct === 'bezier' ? 'custom' : ct }}</option>
      </select>
      <span class="text-xs text-zinc-600 font-mono">
        t={{ selectedPoint.time.toFixed(1) }}s v={{ selectedPoint.value.toFixed(3) }}
      </span>
    </div>

    <div class="ml-auto">
      <button
        @click="emit('save')"
        class="px-4 py-1.5 bg-orange-600 hover:bg-orange-500 rounded text-sm font-medium transition-colors"
      >
        Save
      </button>
    </div>
  </div>
</template>
