<script setup lang="ts">
import { computed, ref } from "vue";
import type { Lane, Point } from "../../types/timeline";
import { sampleCurve } from "../../composables/useInterpolation";

const props = defineProps<{
  lane: Lane;
  width: number;
  height: number;
  canvas: ReturnType<typeof import("../../composables/useTimelineCanvas").useTimelineCanvas>;
  selectedPointId: string | null;
  color: string;
}>();

const emit = defineEmits<{
  "select-point": [id: string];
  "add-point": [time: number, value: number];
  "remove-point": [id: string];
  wheel: [e: WheelEvent];
}>();

const hoveredPointId = ref<string | null>(null);
const dragPointId = ref<string | null>(null);
const dragHandleId = ref<string | null>(null);
const svgRef = ref<SVGSVGElement | null>(null);

// Grid lines for values 0, 0.25, 0.5, 0.75, 1.0
const gridLines = [0, 0.25, 0.5, 0.75, 1.0];

const curveSegments = computed(() => {
  const pts = props.lane.points;
  if (pts.length < 2) return [];

  const segments: {
    pathD: string;
    curveType: string;
  }[] = [];

  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i]!;
    const p1 = pts[i + 1]!;
    const x0 = props.canvas.timeToX(p0.time);
    const y0 = props.canvas.valueToY(p0.value);
    const x1 = props.canvas.timeToX(p1.time);
    const y1 = props.canvas.valueToY(p1.value);

    const ct = p1.curve_type;

    if (ct === "linear") {
      segments.push({ pathD: `M${x0},${y0} L${x1},${y1}`, curveType: ct });
    } else if (ct === "step") {
      segments.push({ pathD: `M${x0},${y0} H${x1} V${y1}`, curveType: ct });
    } else if (ct === "bezier" && p1.bezier_handles) {
      const h = p1.bezier_handles;
      const cp1x = x0 + (x1 - x0) * h.x1;
      const cp1y = y0 - (y0 - y1) * h.y1;
      const cp2x = x0 + (x1 - x0) * h.x2;
      const cp2y = y0 - (y0 - y1) * h.y2;
      segments.push({
        pathD: `M${x0},${y0} C${cp1x},${cp1y} ${cp2x},${cp2y} ${x1},${y1}`,
        curveType: ct,
      });
    } else {
      // Sample-based curves (ease-in, ease-out, etc.)
      const samples = sampleCurve(ct, p1.bezier_handles);
      let d = `M${x0},${y0}`;
      for (const [t, v] of samples) {
        const sx = x0 + (x1 - x0) * t;
        const sv = p0.value + (p1.value - p0.value) * v;
        const sy = props.canvas.valueToY(sv);
        d += ` L${sx},${sy}`;
      }
      segments.push({ pathD: d, curveType: ct });
    }
  }
  return segments;
});

function getPrevPoint(point: Point): Point | null {
  const idx = props.lane.points.indexOf(point);
  return idx > 0 ? props.lane.points[idx - 1]! : null;
}

const selectedBezierHandles = computed(() => {
  const point = props.lane.points.find((p) => p.id === props.selectedPointId);
  if (!point || point.curve_type !== "bezier" || !point.bezier_handles) return null;
  const prev = getPrevPoint(point);
  if (!prev) return null;

  const h = point.bezier_handles;
  const x0 = props.canvas.timeToX(prev.time);
  const y0 = props.canvas.valueToY(prev.value);
  const x1 = props.canvas.timeToX(point.time);
  const y1 = props.canvas.valueToY(point.value);

  return {
    pointId: point.id,
    prevX: x0,
    prevY: y0,
    currX: x1,
    currY: y1,
    cp1x: x0 + (x1 - x0) * h.x1,
    cp1y: y0 - (y0 - y1) * h.y1,
    cp2x: x0 + (x1 - x0) * h.x2,
    cp2y: y0 - (y0 - y1) * h.y2,
  };
});

function startHandleDrag(e: MouseEvent, point: Point, handleIndex: 1 | 2) {
  e.preventDefault();
  e.stopPropagation();
  dragHandleId.value = `${point.id}-cp${handleIndex}`;

  const svg = svgRef.value!;
  const prev = getPrevPoint(point);
  if (!prev || !point.bezier_handles) return;

  const onMove = (me: MouseEvent) => {
    const rect = svg.getBoundingClientRect();
    const mouseX = me.clientX - rect.left;
    const mouseY = me.clientY - rect.top;

    const x0 = props.canvas.timeToX(prev.time);
    const y0 = props.canvas.valueToY(prev.value);
    const x1 = props.canvas.timeToX(point.time);
    const y1 = props.canvas.valueToY(point.value);

    const dx = x1 - x0;
    const dy = y0 - y1;

    const h = point.bezier_handles!;
    if (handleIndex === 1) {
      h.x1 = dx !== 0 ? Math.max(0, Math.min(1, (mouseX - x0) / dx)) : 0;
      h.y1 = dy !== 0 ? (y0 - mouseY) / dy : 0;
    } else {
      h.x2 = dx !== 0 ? Math.max(0, Math.min(1, (mouseX - x0) / dx)) : 0;
      h.y2 = dy !== 0 ? (y0 - mouseY) / dy : 0;
    }
  };

  const onUp = () => {
    dragHandleId.value = null;
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
  };

  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
}

function handleSvgClick(e: MouseEvent) {
  if (dragPointId.value || dragHandleId.value) return;
  const svg = svgRef.value;
  if (!svg) return;
  const rect = svg.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;

  // Proximity guard: skip if click is within 12px of any existing point
  const minDist = 12;
  for (const pt of props.lane.points) {
    const px = props.canvas.timeToX(pt.time);
    const py = props.canvas.valueToY(pt.value);
    const dist = Math.sqrt((x - px) ** 2 + (y - py) ** 2);
    if (dist < minDist) return;
  }

  const time = props.canvas.xToTime(x);
  const value = props.canvas.yToValue(y);
  emit("add-point", time, value);
}

function handleContextMenu(e: MouseEvent, pointId: string) {
  e.preventDefault();
  emit("remove-point", pointId);
}

function startDrag(e: MouseEvent, point: Point) {
  e.preventDefault();
  e.stopPropagation();
  dragPointId.value = point.id;
  emit("select-point", point.id);

  const svg = svgRef.value!;

  const onMove = (me: MouseEvent) => {
    const rect = svg.getBoundingClientRect();
    const x = me.clientX - rect.left;
    const y = me.clientY - rect.top;
    let newTime = props.canvas.xToTime(x);
    const newValue = props.canvas.yToValue(y);

    // Constrain between adjacent points
    const idx = props.lane.points.findIndex((p) => p.id === point.id);
    const prev = idx > 0 ? props.lane.points[idx - 1]!.time : 0;
    const next =
      idx < props.lane.points.length - 1
        ? props.lane.points[idx + 1]!.time
        : props.canvas.xToTime(props.width);
    newTime = Math.max(prev, Math.min(next, newTime));

    point.time = Math.round(newTime * 100) / 100;
    point.value = Math.round(newValue * 1000) / 1000;
  };

  const onUp = () => {
    dragPointId.value = null;
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
  };

  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
}
</script>

<template>
  <svg
    ref="svgRef"
    :width="width"
    :height="height"
    class="bg-zinc-950 cursor-crosshair select-none"
    @click="handleSvgClick"
    @wheel.prevent="$emit('wheel', $event)"
  >
    <!-- Grid lines -->
    <line
      v-for="val in gridLines"
      :key="val"
      :x1="48"
      :y1="canvas.valueToY(val)"
      :x2="width - 16"
      :y2="canvas.valueToY(val)"
      stroke="#27272a"
      stroke-width="1"
    />
    <!-- Grid labels -->
    <text
      v-for="val in gridLines"
      :key="'label-' + val"
      :x="40"
      :y="canvas.valueToY(val) + 4"
      fill="#52525b"
      font-size="9"
      text-anchor="end"
    >
      {{ val.toFixed(2) }}
    </text>

    <!-- Curve segments -->
    <path
      v-for="(seg, i) in curveSegments"
      :key="i"
      :d="seg.pathD"
      fill="none"
      :stroke="color"
      stroke-width="2"
      stroke-linecap="round"
      :opacity="0.8"
    />

    <!-- Control points -->
    <g v-for="point in lane.points" :key="point.id">
      <!-- Outer ring for selected -->
      <circle
        v-if="selectedPointId === point.id"
        :cx="canvas.timeToX(point.time)"
        :cy="canvas.valueToY(point.value)"
        r="8"
        fill="none"
        :stroke="color"
        stroke-width="1.5"
        opacity="0.4"
        @click.stop
      />
      <!-- Point circle -->
      <circle
        :cx="canvas.timeToX(point.time)"
        :cy="canvas.valueToY(point.value)"
        r="5"
        :fill="selectedPointId === point.id ? color : '#18181b'"
        :stroke="color"
        stroke-width="2"
        class="cursor-grab"
        :class="{ 'cursor-grabbing': dragPointId === point.id }"
        @click.stop
        @mousedown="startDrag($event, point)"
        @contextmenu="handleContextMenu($event, point.id)"
        @mouseenter="hoveredPointId = point.id"
        @mouseleave="hoveredPointId = null"
      />
      <!-- Tooltip -->
      <g v-if="hoveredPointId === point.id || dragPointId === point.id">
        <rect
          :x="canvas.timeToX(point.time) - 36"
          :y="canvas.valueToY(point.value) - 28"
          width="72"
          height="18"
          rx="3"
          fill="#27272a"
          opacity="0.9"
        />
        <text
          :x="canvas.timeToX(point.time)"
          :y="canvas.valueToY(point.value) - 15"
          fill="#e4e4e7"
          font-size="9"
          text-anchor="middle"
          font-family="monospace"
        >
          {{ point.time.toFixed(1) }}s · {{ point.value.toFixed(3) }}
        </text>
      </g>

      <!-- Bezier handles -->
      <template v-if="selectedBezierHandles && selectedBezierHandles.pointId === point.id">
        <g>
          <line
            :x1="selectedBezierHandles.prevX"
            :y1="selectedBezierHandles.prevY"
            :x2="selectedBezierHandles.cp1x"
            :y2="selectedBezierHandles.cp1y"
            stroke="#a1a1aa"
            stroke-width="1"
            stroke-dasharray="4 3"
            opacity="0.6"
          />
          <line
            :x1="selectedBezierHandles.currX"
            :y1="selectedBezierHandles.currY"
            :x2="selectedBezierHandles.cp2x"
            :y2="selectedBezierHandles.cp2y"
            stroke="#a1a1aa"
            stroke-width="1"
            stroke-dasharray="4 3"
            opacity="0.6"
          />
          <circle
            :cx="selectedBezierHandles.cp1x"
            :cy="selectedBezierHandles.cp1y"
            r="4"
            fill="#f59e0b"
            stroke="#fbbf24"
            stroke-width="1.5"
            class="cursor-grab"
            :class="{ 'cursor-grabbing': dragHandleId === point.id + '-cp1' }"
            @click.stop
            @mousedown="startHandleDrag($event, point, 1)"
          />
          <circle
            :cx="selectedBezierHandles.cp2x"
            :cy="selectedBezierHandles.cp2y"
            r="4"
            fill="#f59e0b"
            stroke="#fbbf24"
            stroke-width="1.5"
            class="cursor-grab"
            :class="{ 'cursor-grabbing': dragHandleId === point.id + '-cp2' }"
            @click.stop
            @mousedown="startHandleDrag($event, point, 2)"
          />
        </g>
      </template>
    </g>
    <!-- Info overlay (bottom-right) -->
    <g>
      <rect
        :x="width - 130"
        :y="height - 24"
        width="122"
        height="18"
        rx="3"
        fill="#18181b"
        opacity="0.8"
      />
      <text
        :x="width - 125"
        :y="height - 11"
        fill="#71717a"
        font-size="9"
        font-family="monospace"
      >
        {{ lane.points.length }} pts · {{ Math.round(canvas.zoom.value * 100) }}%
      </text>
    </g>
  </svg>
</template>
