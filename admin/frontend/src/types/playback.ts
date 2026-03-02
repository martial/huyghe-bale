export interface PlaybackStatus {
  playing: boolean;
  elapsed: number;
  total_duration: number;
  current_values: {
    a: number;
    b: number;
  };
  type: string | null;
  id: string | null;
}
