export interface CanvasState {
  width: number;
  height: number;
  duration: number;
  zoom: number;
  panX: number;
  paddingLeft: number;
  paddingRight: number;
  paddingTop: number;
  paddingBottom: number;
}

export function plotWidth(s: CanvasState): number {
  return (s.width - s.paddingLeft - s.paddingRight) * s.zoom;
}

export function plotHeight(s: CanvasState): number {
  return s.height - s.paddingTop - s.paddingBottom;
}

export function timeToX(s: CanvasState, time: number): number {
  const ratio = time / s.duration;
  return s.paddingLeft + ratio * plotWidth(s) + s.panX;
}

export function valueToY(s: CanvasState, value: number): number {
  return s.paddingTop + (1 - value) * plotHeight(s);
}

export function xToTime(s: CanvasState, x: number): number {
  const pw = plotWidth(s);
  const ratio = (x - s.paddingLeft - s.panX) / pw;
  return Math.max(0, Math.min(s.duration, ratio * s.duration));
}

export function yToValue(s: CanvasState, y: number): number {
  const ratio = 1 - (y - s.paddingTop) / plotHeight(s);
  return Math.max(0, Math.min(1, ratio));
}

export function handleWheel(
  s: CanvasState,
  e: { deltaX: number; deltaY: number; offsetX: number },
): { zoom: number; panX: number } {
  let newZoom = s.zoom;
  let newPanX = s.panX;

  if (e.deltaY !== 0) {
    const factor = e.deltaY > 0 ? 0.9 : 1.1;
    newZoom = Math.max(1, Math.min(20, s.zoom * factor));
    const pw = plotWidth(s);
    const mouseRatio = (e.offsetX - s.paddingLeft - s.panX) / pw;
    const newPw = (s.width - s.paddingLeft - s.paddingRight) * newZoom;
    newPanX = s.panX - (newPw - pw) * mouseRatio;
  }
  if (e.deltaX !== 0) {
    newPanX -= e.deltaX;
  }

  const pw = (s.width - s.paddingLeft - s.paddingRight) * newZoom;
  const maxPan = 0;
  const minPan = -(pw - (s.width - s.paddingLeft - s.paddingRight));
  newPanX = Math.max(minPan, Math.min(maxPan, newPanX));

  return { zoom: newZoom, panX: newPanX };
}
