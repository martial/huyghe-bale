/**
 * TypeScript mirror of backend interpolation.py
 * MUST produce identical results for consistent frontend preview.
 */

import type { CurveType, BezierHandles } from "../types/timeline";

function linear(t: number): number {
  return t;
}

function step(t: number): number {
  return t < 1.0 ? 0.0 : 1.0;
}

function easeIn(t: number): number {
  return t * t;
}

function easeOut(t: number): number {
  return 1.0 - (1.0 - t) ** 2;
}

function easeInOut(t: number): number {
  return t < 0.5 ? 4.0 * t * t * t : 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0;
}

function sine(t: number): number {
  return (1.0 - Math.cos(t * Math.PI)) / 2.0;
}

function exponential(t: number): number {
  if (t === 0.0) return 0.0;
  if (t === 1.0) return 1.0;
  return Math.pow(2.0, 10.0 * (t - 1.0));
}

function bezier(t: number, handles?: BezierHandles | null): number {
  if (!handles) return t;

  const { x1, y1, x2, y2 } = handles;

  // Newton's method to find t_bezier such that bezier_x(t_bezier) = t
  let tb = t;
  for (let i = 0; i < 8; i++) {
    const x =
      3.0 * (1 - tb) ** 2 * tb * x1 +
      3.0 * (1 - tb) * tb ** 2 * x2 +
      tb ** 3;
    if (Math.abs(x - t) < 1e-7) break;
    const dx =
      3.0 * (1 - tb) ** 2 * x1 +
      6.0 * (1 - tb) * tb * (x2 - x1) +
      3.0 * tb ** 2 * (1 - x2);
    if (Math.abs(dx) < 1e-7) break;
    tb -= (x - t) / dx;
  }

  tb = Math.max(0, Math.min(1, tb));
  return (
    3.0 * (1 - tb) ** 2 * tb * y1 +
    3.0 * (1 - tb) * tb ** 2 * y2 +
    tb ** 3
  );
}

const INTERPOLATORS: Record<string, (t: number, handles?: BezierHandles | null) => number> = {
  linear,
  step,
  "ease-in": easeIn,
  "ease-out": easeOut,
  "ease-in-out": easeInOut,
  sine,
  exponential,
  bezier,
};

export function interpolate(
  t: number,
  curveType: CurveType,
  bezierHandles?: BezierHandles | null,
): number {
  t = Math.max(0, Math.min(1, t));
  const fn = INTERPOLATORS[curveType] || linear;
  if (curveType === "bezier") {
    return fn(t, bezierHandles);
  }
  return fn(t);
}

export function evaluateLane(
  points: { time: number; value: number; curve_type: CurveType; bezier_handles?: BezierHandles | null }[],
  currentTime: number,
): number {
  if (!points.length) return 0;

  const last = points[points.length - 1]!;
  const first = points[0]!;
  if (currentTime >= last.time) return last.value;
  if (currentTime <= first.time) return first.value;

  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i]!;
    const p1 = points[i + 1]!;
    if (p0.time <= currentTime && currentTime <= p1.time) {
      const segDuration = p1.time - p0.time;
      if (segDuration === 0) return p1.value;
      const t = (currentTime - p0.time) / segDuration;
      const eased = interpolate(t, p1.curve_type, p1.bezier_handles);
      return p0.value + (p1.value - p0.value) * eased;
    }
  }
  return last.value;
}

/**
 * Generate polyline points for a curve segment between two control points.
 * Returns array of [x, y] in normalized coordinates (0-1 for both axes within segment).
 */
export function sampleCurve(
  curveType: CurveType,
  bezierHandles?: BezierHandles | null,
  numSamples: number = 50,
): [number, number][] {
  const points: [number, number][] = [];
  for (let i = 0; i <= numSamples; i++) {
    const t = i / numSamples;
    const v = interpolate(t, curveType, bezierHandles);
    points.push([t, v]);
  }
  return points;
}
