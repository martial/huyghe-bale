import type { BangTrack } from "../types";

export const TROLLEY_TRACKS: BangTrack[] = [
  {
    id: "trolley-control",
    kind: "bang",
    label: "Trolley",
    color: "#38bdf8",
    oscAddress: "/trolley",
    commands: [
      {
        command: "enable",
        color: "#10b981",
        valueKind: "enum",
        enumOptions: [
          { label: "on", value: 1 },
          { label: "off", value: 0 },
        ],
        defaultValue: 1,
      },
      {
        command: "dir",
        color: "#f59e0b",
        valueKind: "enum",
        enumOptions: [
          { label: "fwd", value: 1 },
          { label: "rev", value: 0 },
        ],
        defaultValue: 1,
      },
      {
        command: "speed",
        color: "#f97316",
        valueKind: "float",
        valueRange: [0, 1],
        defaultValue: 0.5,
      },
      {
        command: "step",
        color: "#a78bfa",
        valueKind: "int",
        valueRange: [1, 100000],
        defaultValue: 1000,
      },
      {
        command: "position",
        color: "#38bdf8",
        valueKind: "float",
        valueRange: [0, 1],
        defaultValue: 0.5,
      },
      {
        command: "stop",
        color: "#ef4444",
        valueKind: "none",
      },
      {
        command: "home",
        color: "#e5e7eb",
        valueKind: "none",
      },
    ],
    events: [],
  },
];
