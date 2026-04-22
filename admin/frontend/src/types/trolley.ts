import type { Point } from "./timeline";

export interface TrolleyLane {
  label: string;
  points: Point[];
}

export interface TrolleyTimeline {
  id: string;
  name: string;
  duration: number;
  created_at?: string;
  lane: TrolleyLane;
}

export interface TrolleyTimelineSummary {
  id: string;
  name: string;
  duration: number;
  points: number;
  created_at?: string;
}

export type TrolleyCommand =
  | "enable"
  | "dir"
  | "speed"
  | "step"
  | "stop"
  | "home"
  | "position";

export interface TrolleyStatus {
  position: number;
  limit: number;
  homed: number;
  timestamp?: number;
  online: boolean;
}
