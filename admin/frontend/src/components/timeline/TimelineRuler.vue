<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  width: number;
  height: number;
  duration: number;
  canvas: ReturnType<typeof import("../../composables/useTimelineCanvas").useTimelineCanvas>;
}>();

const ticks = computed(() => {
  const result: { x: number; label: string; major: boolean }[] = [];
  // Compute appropriate tick interval based on zoom
  const pixelsPerSecond = props.canvas.plotWidth.value / props.duration;
  let interval = 1;
  if (pixelsPerSecond < 5) interval = 30;
  else if (pixelsPerSecond < 10) interval = 15;
  else if (pixelsPerSecond < 20) interval = 10;
  else if (pixelsPerSecond < 50) interval = 5;
  else interval = 1;

  for (let t = 0; t <= props.duration; t += interval) {
    const x = props.canvas.timeToX(t);
    if (x < 48 || x > props.width - 16) continue;
    const minutes = Math.floor(t / 60);
    const seconds = t % 60;
    const label = minutes > 0 ? `${minutes}:${seconds.toString().padStart(2, "0")}` : `${seconds}s`;
    result.push({ x, label, major: t % (interval * 5) === 0 || t === 0 });
  }
  return result;
});
</script>

<template>
  <svg :width="width" :height="height" class="bg-zinc-900/30 border-b border-zinc-800">
    <g v-for="tick in ticks" :key="tick.x">
      <line
        :x1="tick.x"
        :y1="tick.major ? 14 : 20"
        :x2="tick.x"
        :y2="height"
        stroke="#3f3f46"
        stroke-width="1"
      />
      <text
        v-if="tick.major"
        :x="tick.x"
        :y="12"
        fill="#71717a"
        font-size="9"
        text-anchor="middle"
        font-family="monospace"
      >
        {{ tick.label }}
      </text>
    </g>
  </svg>
</template>
