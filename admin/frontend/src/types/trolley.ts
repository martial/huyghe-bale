export type TrolleyCommand =
  | "enable"
  | "dir"
  | "speed"
  | "step"
  | "stop"
  | "home"
  | "position";

export interface TrolleyEvent {
  id: string;
  time: number;
  command: TrolleyCommand;
  value?: number;
}

export interface TrolleyTimeline {
  id: string;
  name: string;
  duration: number;
  created_at?: string;
  events: TrolleyEvent[];
}

export interface TrolleyTimelineSummary {
  id: string;
  name: string;
  duration: number;
  events: number;
  created_at?: string;
}

export interface TrolleyStatus {
  position: number;
  limit: number;
  homed: number;
  timestamp?: number;
  online: boolean;
}
