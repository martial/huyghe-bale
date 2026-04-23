import type { CurveTrack } from "../types";

export const VENTS_TRACKS: CurveTrack[] = [
  {
    id: "fan-1",
    kind: "curve",
    label: "Fan 1 (cold)",
    color: "#f97316",
    oscAddress: "/vents/fan/1",
    valueRange: [0, 1],
    points: [],
  },
  {
    id: "fan-2",
    kind: "curve",
    label: "Fan 2 (hot)",
    color: "#38bdf8",
    oscAddress: "/vents/fan/2",
    valueRange: [0, 1],
    points: [],
  },
];
