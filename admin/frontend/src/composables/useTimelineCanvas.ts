import { ref, computed, type Ref } from "vue";

export interface CanvasConfig {
  width: Ref<number>;
  height: Ref<number>;
  duration: Ref<number>;
  paddingLeft: number;
  paddingRight: number;
  paddingTop: number;
  paddingBottom: number;
}

export function useTimelineCanvas(config: CanvasConfig) {
  const zoom = ref(1);
  const panX = ref(0);

  const plotWidth = computed(
    () => (config.width.value - config.paddingLeft - config.paddingRight) * zoom.value,
  );
  const plotHeight = computed(
    () => config.height.value - config.paddingTop - config.paddingBottom,
  );

  /** Convert timeline time (seconds) to screen X */
  function timeToX(time: number): number {
    const ratio = time / config.duration.value;
    return config.paddingLeft + ratio * plotWidth.value + panX.value;
  }

  /** Convert value (0-1) to screen Y (inverted: 0=bottom, 1=top) */
  function valueToY(value: number): number {
    return config.paddingTop + (1 - value) * plotHeight.value;
  }

  /** Convert screen X to timeline time */
  function xToTime(x: number): number {
    const ratio = (x - config.paddingLeft - panX.value) / plotWidth.value;
    return Math.max(0, Math.min(config.duration.value, ratio * config.duration.value));
  }

  /** Convert screen Y to value (0-1) */
  function yToValue(y: number): number {
    const ratio = 1 - (y - config.paddingTop) / plotHeight.value;
    return Math.max(0, Math.min(1, ratio));
  }

  function handleWheel(e: WheelEvent) {
    // Vertical scroll (deltaY) = zoom, horizontal scroll (deltaX) = pan
    if (e.deltaY !== 0) {
      // Zoom
      const factor = e.deltaY > 0 ? 0.9 : 1.1;
      const newZoom = Math.max(1, Math.min(20, zoom.value * factor));
      // Zoom towards mouse position
      const mouseRatio = (e.offsetX - config.paddingLeft - panX.value) / plotWidth.value;
      const newPlotWidth = (config.width.value - config.paddingLeft - config.paddingRight) * newZoom;
      panX.value = panX.value - (newPlotWidth - plotWidth.value) * mouseRatio;
      zoom.value = newZoom;
    }
    if (e.deltaX !== 0) {
      // Pan
      panX.value -= e.deltaX;
    }
    // Clamp pan
    const maxPan = 0;
    const minPan = -(plotWidth.value - (config.width.value - config.paddingLeft - config.paddingRight));
    panX.value = Math.max(minPan, Math.min(maxPan, panX.value));
  }

  return {
    zoom,
    panX,
    plotWidth,
    plotHeight,
    timeToX,
    valueToY,
    xToTime,
    yToValue,
    handleWheel,
  };
}
