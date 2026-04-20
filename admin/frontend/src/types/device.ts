export type DeviceType = "vents" | "trolley";

export const DEVICE_TYPES: DeviceType[] = ["vents", "trolley"];

export interface Device {
  id: string;
  name: string;
  ip_address: string;
  osc_port: number;
  type: DeviceType;
  hardware_id?: string;
  needs_repair?: boolean;
  missing_fields?: string[];
}

export type DeviceStatus = "online" | "offline";

export interface DeviceVersion {
  version: string;
  version_date: string;
}

export interface DeviceSystemInfo {
  model: string;
  python_version: string;
  os: string;
  ip?: string;
  ram_total_mb: number;
  ram_available_mb: number;
  cpu_temp_c: number | null;
  disk_total_mb: number;
  disk_free_mb: number;
}

export interface LatestVersion {
  hash: string;
  date: string;
  message: string;
}

export interface UpdateResult {
  success: boolean;
  logs: string;
  new_version: string;
}

export interface DiscoveredHost {
  ip: string;
  osc_port: number;
  ssh: boolean;
  potential_pi: boolean;
  hostname: string;
}
