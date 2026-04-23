export type CurveType =
  | "linear"
  | "step"
  | "ease-in"
  | "ease-out"
  | "ease-in-out"
  | "sine"
  | "exponential"
  | "bezier";

export interface BezierHandles {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface Point {
  id: string;
  time: number;
  value: number;
  curve_type: CurveType;
  bezier_handles: BezierHandles | null;
}

export interface Lane {
  label: string;
  points: Point[];
}

export interface Timeline {
  id: string;
  name: string;
  duration: number;
  created_at?: string;
  /** When true (default), playback wraps to t=0 after the last point.
   *  When false, playback stops cleanly once elapsed >= duration. */
  loop?: boolean;
  lanes: {
    a: Lane;
    b: Lane;
  };
}

export interface TimelineSummary {
  id: string;
  name: string;
  duration: number;
  lane_a_points: number;
  lane_b_points: number;
  created_at?: string;
}
