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
}
