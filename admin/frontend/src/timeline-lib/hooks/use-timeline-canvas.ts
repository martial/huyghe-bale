import { useState, useCallback, useMemo } from "react";
import * as tc from "../lib/canvas-math";
import type { CanvasState } from "../lib/canvas-math";

export function useTimelineCanvas(
  width: number,
  height: number,
  duration: number,
) {
  const [zoom, setZoom] = useState(1);
  const [panX, setPanX] = useState(0);

  const padding = useMemo(
    () => ({ paddingLeft: 48, paddingRight: 16, paddingTop: 12, paddingBottom: 12 }),
    [],
  );

  const state: CanvasState = useMemo(
    () => ({ width, height, duration, zoom, panX, ...padding }),
    [width, height, duration, zoom, panX, padding],
  );

  const timeToX = useCallback((time: number) => tc.timeToX(state, time), [state]);
  const valueToY = useCallback((value: number) => tc.valueToY(state, value), [state]);
  const xToTime = useCallback((x: number) => tc.xToTime(state, x), [state]);
  const yToValue = useCallback((y: number) => tc.yToValue(state, y), [state]);

  const onWheel = useCallback(
    (e: React.WheelEvent) => {
      e.preventDefault();
      const { zoom: z, panX: p } = tc.handleWheel(state, {
        deltaX: e.deltaX,
        deltaY: e.deltaY,
        offsetX: e.nativeEvent.offsetX,
      });
      setZoom(z);
      setPanX(p);
    },
    [state],
  );

  const pw = tc.plotWidth(state);

  return {
    zoom,
    panX,
    setZoom,
    setPanX,
    plotWidth: pw,
    plotHeight: tc.plotHeight(state),
    timeToX,
    valueToY,
    xToTime,
    yToValue,
    onWheel,
    state,
  };
}
