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
  /** Built-in example — API rejects PUT/DELETE. Edit via Duplicate. */
  readonly?: boolean;
}

export interface TrolleyTimelineSummary {
  id: string;
  name: string;
  duration: number;
  events: number;
  created_at?: string;
  readonly?: boolean;
}

export interface TrolleyStatus {
  position: number;
  limit: number;
  homed: number;
  timestamp?: number;
  online: boolean;
}
