/**
 * Universal timeline schema — device-agnostic. Both vents and trolley
 * timelines are expressed as this shape in the UI; the server shapes
 * are translated via adapters/ on read / write.
 */

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

export interface CurvePoint {
  id: string;
  time: number;
  value: number;
  curveType: CurveType;
  bezierHandles: BezierHandles | null;
}

export interface CurveTrack {
  id: string;
  kind: "curve";
  label: string;
  /** Accent colour (hex). */
  color: string;
  /** OSC address each tick is sent to. */
  oscAddress: string;
  /** Value range for the lane; default [0, 1]. */
  valueRange: [number, number];
  points: CurvePoint[];
}

export interface BangCommandDef {
  command: string;
  color: string;
  valueKind: "none" | "int" | "float" | "enum";
  valueRange?: [number, number];
  defaultValue?: number;
  enumOptions?: { label: string; value: number }[];
}

export interface BangEvent {
  id: string;
  time: number;
  command: string;
  value?: number;
}

export interface BangTrack {
  id: string;
  kind: "bang";
  label: string;
  color: string;
  /** Address prefix — actual OSC is `${oscAddress}/${command}`. */
  oscAddress: string;
  commands: BangCommandDef[];
  events: BangEvent[];
}

export type Track = CurveTrack | BangTrack;

export type TimelineKind = "vents" | "trolley";

export interface UniversalTimeline {
  id: string;
  name: string;
  duration: number;
  kind: TimelineKind;
  tracks: Track[];
  loop?: boolean;
  readonly?: boolean;
  created_at?: string;
}

export interface UniversalTimelineSummary {
  id: string;
  name: string;
  duration: number;
  kind: TimelineKind;
  /** Rough content-count (points + events across tracks). */
  eventCount: number;
  created_at?: string;
  readonly?: boolean;
}
