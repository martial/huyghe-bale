import type { TrolleyTimeline } from "../../types/trolley";
import type {
  BangTrack,
  UniversalTimeline,
  UniversalTimelineSummary,
} from "../types";
import { TROLLEY_TRACKS } from "../track-defs/trolley";

/** Server trolley timeline (events list) → universal single-bang-track. */
export function trolleyTimelineToUniversal(
  tl: TrolleyTimeline,
): UniversalTimeline {
  const base = TROLLEY_TRACKS[0]!;
  const track: BangTrack = {
    ...base,
    events: tl.events.map((e) => ({
      id: e.id,
      time: e.time,
      command: e.command,
      value: e.value,
    })),
  };
  return {
    id: tl.id,
    name: tl.name,
    duration: tl.duration,
    kind: "trolley",
    loop: (tl as unknown as { loop?: boolean }).loop,
    readonly: tl.readonly,
    created_at: tl.created_at,
    tracks: [track],
  };
}

export function universalToTrolleyTimeline(
  tl: UniversalTimeline,
): TrolleyTimeline {
  if (tl.kind !== "trolley") {
    throw new Error(`expected trolley kind, got ${tl.kind}`);
  }
  const track = tl.tracks.find((t): t is BangTrack => t.kind === "bang");
  return {
    id: tl.id,
    name: tl.name,
    duration: tl.duration,
    created_at: tl.created_at,
    readonly: tl.readonly,
    events:
      track?.events.map((e) => ({
        id: e.id,
        time: e.time,
        // Cast back to the enumerated TrolleyCommand — the universal
        // BangEvent stores command as string; valid values are the
        // ones defined in track-defs/trolley.ts.
        command: e.command as TrolleyTimeline["events"][number]["command"],
        value: e.value,
      })) ?? [],
  };
}

export interface TrolleyTimelineSummaryServer {
  id: string;
  name: string;
  duration: number;
  events: number;
  created_at?: string;
  readonly?: boolean;
}

export function trolleySummaryToUniversal(
  s: TrolleyTimelineSummaryServer,
): UniversalTimelineSummary {
  return {
    id: s.id,
    name: s.name,
    duration: s.duration,
    kind: "trolley",
    eventCount: s.events,
    created_at: s.created_at,
    readonly: s.readonly,
  };
}
