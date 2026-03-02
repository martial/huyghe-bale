import { get, post } from "./client";
import type { PlaybackStatus } from "../types/playback";

export function startPlayback(data: {
  type: "timeline" | "orchestration";
  id: string;
  device_ids: string[];
}) {
  return post<{ ok: boolean; message: string }>("/playback/start", data);
}

export function stopPlayback() {
  return post<{ ok: boolean; message: string }>("/playback/stop");
}

export function getPlaybackStatus() {
  return get<PlaybackStatus>("/playback/status");
}
