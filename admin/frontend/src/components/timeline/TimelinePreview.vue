<script setup lang="ts">
import { ref, onMounted, watch } from "vue";
import type { Timeline } from "../../types/timeline";
import { getTimeline } from "../../api/timelines";
import { sampleCurve } from "../../composables/useInterpolation";

const props = defineProps<{ timelineId: string }>();
const timeline = ref<Timeline | null>(null);

onMounted(load);
watch(() => props.timelineId, load);

async function load() {
  try {
    timeline.value = await getTimeline(props.timelineId);
  } catch {
    timeline.value = null;
  }
}

function buildPath(
  points: Timeline["lanes"]["a"]["points"],
  duration: number,
  width: number,
  height: number,
): string {
  if (points.length < 2) return "";
  let d = "";
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i]!;
    const p1 = points[i + 1]!;
    const x0 = (p0.time / duration) * width;
    const y0 = (1 - p0.value) * height;
    const x1 = (p1.time / duration) * width;
    const y1 = (1 - p1.value) * height;

    if (p1.curve_type === "linear" || p1.curve_type === "step") {
      if (i === 0) d += `M${x0},${y0}`;
      if (p1.curve_type === "step") {
        d += ` H${x1} V${y1}`;
      } else {
        d += ` L${x1},${y1}`;
      }
    } else {
      const samples = sampleCurve(p1.curve_type, p1.bezier_handles, 20);
      if (i === 0) d += `M${x0},${y0}`;
      for (const [t, v] of samples) {
        const sx = x0 + (x1 - x0) * t;
        const sv = p0.value + (p1.value - p0.value) * v;
        d += ` L${sx},${(1 - sv) * height}`;
      }
    }
  }
  return d;
}
</script>

<template>
  <svg viewBox="0 0 128 64" class="bg-zinc-900">
    <template v-if="timeline">
      <path
        :d="buildPath(timeline.lanes.a.points, timeline.duration, 128, 64)"
        fill="none"
        stroke="#f97316"
        stroke-width="1.5"
        opacity="0.7"
      />
      <path
        :d="buildPath(timeline.lanes.b.points, timeline.duration, 128, 64)"
        fill="none"
        stroke="#38bdf8"
        stroke-width="1.5"
        opacity="0.7"
      />
    </template>
  </svg>
</template>
