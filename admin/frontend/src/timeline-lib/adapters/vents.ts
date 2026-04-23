import type { Timeline } from "../../types/timeline";
import type {
  CurveTrack,
  UniversalTimeline,
  UniversalTimelineSummary,
} from "../types";
import { VENTS_TRACKS } from "../track-defs/vents";

/**
 * Convert the server's vents Timeline shape (lanes a + b) into the
 * universal two-curve-track shape. Non-destructive — returns a new
 * object.
 */
export function ventsTimelineToUniversal(tl: Timeline): UniversalTimeline {
  const fromLane = (laneIdx: 0 | 1): CurveTrack => {
    const laneKey = laneIdx === 0 ? "a" : "b";
    const lane = tl.lanes?.[laneKey] ?? { points: [] };
    const base = VENTS_TRACKS[laneIdx]!;
    return {
      ...base,
      points: lane.points.map((p) => ({
        id: p.id,
        time: p.time,
        value: p.value,
        curveType: p.curve_type,
        bezierHandles: p.bezier_handles,
      })),
    };
  };
  return {
    id: tl.id,
    name: tl.name,
    duration: tl.duration,
    kind: "vents",
    loop: tl.loop,
    created_at: tl.created_at,
    tracks: [fromLane(0), fromLane(1)],
  };
}

/** Inverse of ventsTimelineToUniversal — strips the universal wrapper
 *  back to the server's lane-based shape for save / duplicate. */
export function universalToVentsTimeline(tl: UniversalTimeline): Timeline {
  if (tl.kind !== "vents") {
    throw new Error(`expected vents kind, got ${tl.kind}`);
  }
  const track = (id: string) =>
    tl.tracks.find((t): t is CurveTrack => t.kind === "curve" && t.id === id) ??
    null;

  const fan1 = track("fan-1");
  const fan2 = track("fan-2");
  const lane = (t: CurveTrack | null) => ({
    label: t?.label ?? "",
    points:
      t?.points.map((p) => ({
        id: p.id,
        time: p.time,
        value: p.value,
        curve_type: p.curveType,
        bezier_handles: p.bezierHandles,
      })) ?? [],
  });
  return {
    id: tl.id,
    name: tl.name,
    duration: tl.duration,
    loop: tl.loop,
    created_at: tl.created_at,
    lanes: { a: lane(fan1), b: lane(fan2) },
  };
}

export interface VentsTimelineSummaryServer {
  id: string;
  name: string;
  duration: number;
  lane_a_points: number;
  lane_b_points: number;
  created_at?: string;
}

export function ventsSummaryToUniversal(
  s: VentsTimelineSummaryServer,
): UniversalTimelineSummary {
  return {
    id: s.id,
    name: s.name,
    duration: s.duration,
    kind: "vents",
    eventCount: (s.lane_a_points ?? 0) + (s.lane_b_points ?? 0),
    created_at: s.created_at,
  };
}
