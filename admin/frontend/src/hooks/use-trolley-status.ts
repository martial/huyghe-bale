import { fetchTrolleyStatus } from "../api/trolley";
import { usePolledStatus } from "./use-polled-status";
import type { TrolleyStatus } from "../types/trolley";

export const useTrolleyStatus = (deviceId: string) =>
  usePolledStatus<TrolleyStatus>(deviceId, fetchTrolleyStatus);
