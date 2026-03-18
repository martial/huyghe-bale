export interface Device {
  id: string;
  name: string;
  ip_address: string;
  osc_port: number;
}

export type DeviceStatus = "online" | "offline";

export interface DiscoveredHost {
  ip: string;
  osc_port: number;
  ssh: boolean;
  potential_pi: boolean;
  hostname: string;
}
