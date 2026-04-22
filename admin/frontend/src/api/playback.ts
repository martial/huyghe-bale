import { get, post } from "./client";
import type { PlaybackStatus } from "../types/playback";

export function startPlayback(data: {
  type: "timeline" | "orchestration" | "trolley-timeline";
  id: string;
  device_ids: string[];
}) {
  return post<{ ok: boolean; message: string }>("/playback/start", data);
}

export function stopPlayback() {
  return post<{ ok: boolean; message: string }>("/playback/stop");
}

export function pausePlayback() {
  return post<{ ok: boolean }>("/playback/pause");
}

export function resumePlayback() {
  return post<{ ok: boolean }>("/playback/resume");
}

export function seekPlayback(elapsed: number) {
  return post<{ ok: boolean }>("/playback/seek", { elapsed });
}

export function getPlaybackStatus() {
  return get<PlaybackStatus>("/playback/status");
}
