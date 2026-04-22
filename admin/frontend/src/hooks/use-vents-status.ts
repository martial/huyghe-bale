import { fetchVentsStatus } from "../api/vents";
import { usePolledStatus } from "./use-polled-status";
import type { VentsStatus } from "../types/vents";

export const useVentsStatus = (deviceId: string) =>
  usePolledStatus<VentsStatus>(deviceId, fetchVentsStatus);
