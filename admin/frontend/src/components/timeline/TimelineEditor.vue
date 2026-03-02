<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted } from "vue";
import type { Timeline, Point, CurveType, Lane } from "../../types/timeline";
import { useTimelineStore } from "../../stores/timelineStore";
import { useTimelineCanvas } from "../../composables/useTimelineCanvas";
import TimelineLane from "./TimelineLane.vue";
import TimelineRuler from "./TimelineRuler.vue";
import TimelineToolbar from "./TimelineToolbar.vue";

const props = defineProps<{ timeline: Timeline }>();
const store = useTimelineStore();

// Local editable copy
const local = reactive<Timeline>(JSON.parse(JSON.stringify(props.timeline)));
watch(
  () => props.timeline,
  (tl) => Object.assign(local, JSON.parse(JSON.stringify(tl))),
  { deep: true },
);

const containerRef = ref<HTMLElement | null>(null);
const svgWidth = ref(900);
const svgHeight = ref(200);
const rulerHeight = 32;
const selectedPointId = ref<string | null>(null);

const selectedPoint = computed(() => {
  if (!selectedPointId.value) return null;
  for (const lane of [local.lanes.a, local.lanes.b]) {
    const pt = lane.points.find((p) => p.id === selectedPointId.value);
    if (pt) return pt;
  }
  return null;
});

const canvasA = useTimelineCanvas({
  width: svgWidth,
  height: svgHeight,
  duration: computed(() => local.duration),
  paddingLeft: 48,
  paddingRight: 16,
  paddingTop: 12,
  paddingBottom: 12,
});

const canvasB = useTimelineCanvas({
  width: svgWidth,
  height: svgHeight,
  duration: computed(() => local.duration),
  paddingLeft: 48,
  paddingRight: 16,
  paddingTop: 12,
  paddingBottom: 12,
});

// Sync zoom/pan between lanes
watch([canvasA.zoom, canvasA.panX], () => {
  canvasB.zoom.value = canvasA.zoom.value;
  canvasB.panX.value = canvasA.panX.value;
});

onMounted(() => {
  if (containerRef.value) {
    const rect = containerRef.value.getBoundingClientRect();
    svgWidth.value = rect.width;
  }
  window.addEventListener("keydown", handleKeydown);
});
onUnmounted(() => {
  window.removeEventListener("keydown", handleKeydown);
});

function generateId(): string {
  return "pt_" + Math.random().toString(36).substring(2, 10);
}

function addPoint(lane: Lane, time: number, value: number) {
  const pt: Point = {
    id: generateId(),
    time: Math.round(time * 100) / 100,
    value: Math.round(value * 1000) / 1000,
    curve_type: "linear",
    bezier_handles: null,
  };
  lane.points.push(pt);
  lane.points.sort((a, b) => a.time - b.time);
  selectedPointId.value = pt.id;
}

function removePoint(lane: Lane, pointId: string) {
  const idx = lane.points.findIndex((p) => p.id === pointId);
  if (idx >= 0) {
    lane.points.splice(idx, 1);
    if (selectedPointId.value === pointId) selectedPointId.value = null;
  }
}

function updatePointCurveType(curveType: CurveType) {
  if (!selectedPoint.value) return;
  selectedPoint.value.curve_type = curveType;
  if (curveType === "bezier" && !selectedPoint.value.bezier_handles) {
    selectedPoint.value.bezier_handles = { x1: 0.25, y1: 0.0, x2: 0.75, y2: 1.0 };
  }
}

async function handleSave() {
  await store.save(local as Timeline);
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") {
    selectedPointId.value = null;
    return;
  }
  const isDelete =
    (e.shiftKey && e.key === "D") ||
    e.key === "Delete" ||
    e.key === "Backspace";
  if (isDelete && selectedPointId.value) {
    e.preventDefault();
    for (const lane of [local.lanes.a, local.lanes.b]) {
      const idx = lane.points.findIndex((p) => p.id === selectedPointId.value);
      if (idx >= 0) {
        removePoint(lane, selectedPointId.value!);
        break;
      }
    }
  }
}

</script>

<template>
  <div class="flex flex-col h-full" ref="containerRef">
    <TimelineToolbar
      :timeline="local"
      :selected-point="selectedPoint"
      @update:name="local.name = $event"
      @update:duration="local.duration = $event"
      @update:curve-type="updatePointCurveType"
      @save="handleSave"
    />

    <!-- Ruler -->
    <TimelineRuler
      :width="svgWidth"
      :height="rulerHeight"
      :duration="local.duration"
      :canvas="canvasA"
    />

    <!-- Lane A -->
    <div class="border-b border-zinc-800">
      <div class="flex items-center px-2 py-1 text-xs text-zinc-500 bg-zinc-900/50">
        <span class="w-10 text-center font-medium text-orange-400/70">A</span>
        <span>{{ local.lanes.a.label }}</span>
      </div>
      <TimelineLane
        :lane="local.lanes.a"
        :width="svgWidth"
        :height="svgHeight"
        :canvas="canvasA"
        :selected-point-id="selectedPointId"
        color="#f97316"
        @select-point="selectedPointId = $event"
        @add-point="(t, v) => addPoint(local.lanes.a, t, v)"
        @remove-point="(id) => removePoint(local.lanes.a, id)"
        @wheel="canvasA.handleWheel"
      />
    </div>

    <!-- Lane B -->
    <div class="border-b border-zinc-800">
      <div class="flex items-center px-2 py-1 text-xs text-zinc-500 bg-zinc-900/50">
        <span class="w-10 text-center font-medium text-sky-400/70">B</span>
        <span>{{ local.lanes.b.label }}</span>
      </div>
      <TimelineLane
        :lane="local.lanes.b"
        :width="svgWidth"
        :height="svgHeight"
        :canvas="canvasB"
        :selected-point-id="selectedPointId"
        color="#38bdf8"
        @select-point="selectedPointId = $event"
        @add-point="(t, v) => addPoint(local.lanes.b, t, v)"
        @remove-point="(id) => removePoint(local.lanes.b, id)"
        @wheel="canvasB.handleWheel"
      />
    </div>

    <!-- Keyboard shortcuts hint -->
    <div class="px-3 py-1.5 text-[10px] text-zinc-600 bg-zinc-900/50 border-t border-zinc-800 font-mono">
      Click = add point · Shift+D / Del = delete · Scroll = zoom · Esc = deselect · Right-click = delete
    </div>
  </div>
</template>
