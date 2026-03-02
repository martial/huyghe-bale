<script setup lang="ts">
import { computed } from "vue";
import type { PlaybackStatus } from "../../types/playback";

const props = defineProps<{ status: PlaybackStatus }>();

const progress = computed(() => {
  if (props.status.total_duration === 0) return 0;
  return (props.status.elapsed / props.status.total_duration) * 100;
});

function formatTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}
</script>

<template>
  <div class="space-y-2">
    <!-- Progress bar -->
    <div class="h-1 bg-zinc-800 rounded-full overflow-hidden">
      <div
        class="h-full bg-orange-500 transition-all duration-300"
        :style="{ width: `${progress}%` }"
      />
    </div>

    <!-- Time -->
    <div class="flex justify-between text-[10px] text-zinc-500 font-mono">
      <span>{{ formatTime(status.elapsed) }}</span>
      <span>{{ formatTime(status.total_duration) }}</span>
    </div>

    <!-- Value bars -->
    <div class="space-y-1">
      <div class="flex items-center gap-2">
        <span class="text-[10px] text-orange-400/70 w-3">A</span>
        <div class="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
          <div
            class="h-full bg-orange-500/60 transition-all duration-200"
            :style="{ width: `${status.current_values.a * 100}%` }"
          />
        </div>
        <span class="text-[10px] text-zinc-500 font-mono w-8 text-right">
          {{ (status.current_values.a * 100).toFixed(0) }}%
        </span>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-[10px] text-sky-400/70 w-3">B</span>
        <div class="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
          <div
            class="h-full bg-sky-500/60 transition-all duration-200"
            :style="{ width: `${status.current_values.b * 100}%` }"
          />
        </div>
        <span class="text-[10px] text-zinc-500 font-mono w-8 text-right">
          {{ (status.current_values.b * 100).toFixed(0) }}%
        </span>
      </div>
    </div>
  </div>
</template>
