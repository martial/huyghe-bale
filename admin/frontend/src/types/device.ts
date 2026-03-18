export interface Device {
  id: string;
  name: string;
  ip_address: string;
  osc_port: number;
}

export type DeviceStatus = "online" | "offline";

export interface DeviceVersion {
  version: string;
  version_date: string;
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
