import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router";
import type { Orchestration, OrchestrationStep } from "../../types/orchestration";
import { useOrchestrationStore } from "../../stores/orchestration-store";
import { useNotificationStore } from "../../stores/notification-store";
import { useTimelineStore } from "../../stores/timeline-store";
import { useDeviceStore } from "../../stores/device-store";
import OrchestrationStepCard from "./OrchestrationStepCard";
import PlaybackStartButton from "../playback/PlaybackStartButton";

function generateId(): string {
  return "step_" + Math.random().toString(36).substring(2, 10);
}

export default function OrchestrationEditor({ orchestration }: { orchestration: Orchestration }) {
  const navigate = useNavigate();
  const orchStore = useOrchestrationStore();
  const notify = useNotificationStore((s) => s.notify);
  const timelines = useTimelineStore((s) => s.list);
  const fetchTimelines = useTimelineStore((s) => s.fetchList);
  const devices = useDeviceStore((s) => s.list);
  const fetchDevices = useDeviceStore((s) => s.fetchList);
  const ventsDevices = useMemo(
    () => devices.filter((d) => (d.type ?? "vents") === "vents"),
    [devices],
  );

  const [local, setLocal] = useState<Orchestration>(() => JSON.parse(JSON.stringify(orchestration)));

  useEffect(() => {
    fetchTimelines();
    fetchDevices();
  }, [fetchTimelines, fetchDevices]);

  function updateStep(updated: OrchestrationStep) {
    setLocal((prev) => ({
      ...prev,
      steps: prev.steps.map((s) => (s.id === updated.id ? updated : s)),
    }));
  }

  function addStep() {
    const step: OrchestrationStep = {
      id: generateId(),
      order: local.steps.length,
      timeline_id: "",
      device_ids: [],
      delay_before: 0,
      label: `Step ${local.steps.length + 1}`,
    };
    setLocal((prev) => ({ ...prev, steps: [...prev.steps, step] }));
  }

  function removeStep(id: string) {
    setLocal((prev) => {
      const steps = prev.steps
        .filter((s) => s.id !== id)
        .map((s, i) => ({ ...s, order: i }));
      return { ...prev, steps };
    });
  }

  function moveStep(id: string, direction: -1 | 1) {
    setLocal((prev) => {
      const steps = [...prev.steps];
      const idx = steps.findIndex((s) => s.id === id);
      const newIdx = idx + direction;
      if (newIdx < 0 || newIdx >= steps.length) return prev;
      [steps[idx], steps[newIdx]] = [steps[newIdx]!, steps[idx]!];
      return { ...prev, steps: steps.map((s, i) => ({ ...s, order: i })) };
    });
  }

  const totalDuration = useMemo(() => {
    let total = 0;
    for (const step of local.steps) {
      total += step.delay_before;
      const tl = timelines.find((t) => t.id === step.timeline_id);
      if (tl) total += tl.duration;
    }
    return total;
  }, [local.steps, timelines]);

  async function handleSave() {
    await orchStore.save(local);
    notify("success", "Orchestration saved successfully");
  }

  return (
    <div className="p-8">
      <div className="flex items-center gap-4 mb-6">
        <button onClick={() => navigate("/orchestrations")} className="text-zinc-500 hover:text-white text-sm transition-colors">
          &larr;
        </button>

        <input
          value={local.name}
          onChange={(e) => setLocal((prev) => ({ ...prev, name: e.target.value }))}
          className="bg-transparent border-b border-zinc-700 focus:border-orange-400 outline-none text-lg font-medium px-1 py-0.5 transition-colors"
        />

        <label className="flex items-center gap-2 text-sm text-zinc-400">
          <input
            type="checkbox"
            checked={local.loop}
            onChange={(e) => setLocal((prev) => ({ ...prev, loop: e.target.checked }))}
            className="rounded accent-orange-500"
          />
          Loop
        </label>

        <span className="text-xs text-zinc-500 font-mono">
          Total: {totalDuration.toFixed(1)}s
        </span>

        <div className="ml-auto flex gap-2">
          <PlaybackStartButton type="orchestration" id={local.id} />
          <a
            href={`/api/v1/export/orchestration/${local.id}`}
            download={`${local.name || local.id}.json`}
            className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm font-medium text-zinc-300 transition-all duration-200"
            title="Download orchestration JSON (timelines embedded)"
          >
            Export
          </a>
          <a
            href={`/api/v1/export/orchestration/${local.id}/sampled`}
            download={`${local.name || local.id}_sampled.json`}
            className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm font-medium text-zinc-300 transition-all duration-200"
            title="Download frame-by-frame rendered values for the full orchestration (uses app's configured FPS)"
          >
            Export sampled
          </a>
          <button
            onClick={handleSave}
            className="px-4 py-1.5 bg-orange-600 hover:bg-orange-500 rounded-lg text-sm font-medium transition-all duration-200"
          >
            Save
          </button>
        </div>
      </div>

      {/* Steps bar visualization */}
      {local.steps.length > 0 && (
        <div className="flex gap-1 mb-6 h-10 rounded-lg overflow-hidden">
          {local.steps.map((step) => (
            <div
              key={step.id}
              className="flex items-center justify-center text-xs font-medium bg-zinc-800/80 border border-zinc-700/50 rounded-lg px-2 min-w-16"
              style={{
                flex: (timelines.find((t) => t.id === step.timeline_id)?.duration || 10) + step.delay_before,
              }}
            >
              {step.label || "—"}
            </div>
          ))}
        </div>
      )}

      {/* Step list */}
      <div className="space-y-3">
        {local.steps.map((step) => (
          <OrchestrationStepCard
            key={step.id}
            step={step}
            timelines={timelines}
            devices={ventsDevices}
            isFirst={step.order === 0}
            isLast={step.order === local.steps.length - 1}
            onChange={updateStep}
            onMoveUp={() => moveStep(step.id, -1)}
            onMoveDown={() => moveStep(step.id, 1)}
            onRemove={() => removeStep(step.id)}
          />
        ))}
      </div>

      <button
        onClick={addStep}
        className="mt-4 w-full py-2.5 border border-dashed border-zinc-700/50 hover:border-zinc-500 rounded-xl text-sm text-zinc-400 hover:text-white transition-all duration-200"
      >
        + Add Step
      </button>
    </div>
  );
}
