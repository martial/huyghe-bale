export interface OrchestrationStep {
  id: string;
  order: number;
  timeline_id: string;
  device_ids: string[];
  delay_before: number;
  label: string;
}

export interface Orchestration {
  id: string;
  name: string;
  loop: boolean;
  steps: OrchestrationStep[];
}
