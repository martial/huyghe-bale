import { useEffect, useRef, useState } from "react";
import type { Device, DeviceType } from "../../types/device";
import { useDeviceStore } from "../../stores/device-store";

interface Props {
  /** Device type this selector should list. */
  type: DeviceType;
  selected: string[];
  onChange: (ids: string[]) => void;
  /** Optional label prefix, e.g. "Targets". */
  label?: string;
}

/**
 * Small toolbar control: a button showing "N / M selected", that opens a
 * floating checkbox list of every device of the given type. All selected
 * by default so existing "Play sends to all" behaviour is preserved.
 */
export default function DeviceMultiSelect({ type, selected, onChange, label }: Props) {
  const devices = useDeviceStore((s) => s.list);
  const statuses = useDeviceStore((s) => s.deviceStatuses);
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const eligible = devices.filter((d) => (d.type ?? "vents") === type);
  const selectedCount = eligible.filter((d) => selected.includes(d.id)).length;
  const allSelected = selectedCount === eligible.length && eligible.length > 0;

  useEffect(() => {
    if (!open) return;
    function onDocMouseDown(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    window.addEventListener("mousedown", onDocMouseDown);
    return () => window.removeEventListener("mousedown", onDocMouseDown);
  }, [open]);

  function toggle(id: string) {
    onChange(
      selected.includes(id)
        ? selected.filter((x) => x !== id)
        : [...selected, id],
    );
  }

  function setAll(on: boolean) {
    onChange(on ? eligible.map((d) => d.id) : []);
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((s) => !s)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-200 transition-colors"
        title={`${selectedCount} of ${eligible.length} ${type} device(s) will receive playback OSC`}
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z" />
        </svg>
        <span className="text-xs text-zinc-500">{label ?? "Targets"}</span>
        <span className="font-mono text-xs">
          {selectedCount}
          <span className="text-zinc-500"> / {eligible.length}</span>
        </span>
        <svg className={`w-3 h-3 text-zinc-500 transition-transform ${open ? "rotate-180" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 z-30 w-64 rounded-lg border border-white/10 bg-zinc-950/95 backdrop-blur shadow-xl overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2 border-b border-white/5 bg-white/[0.02]">
            <span className="text-[10px] uppercase tracking-wider text-zinc-500">
              {type} devices
            </span>
            <button
              onClick={() => setAll(!allSelected)}
              className="text-[10px] text-zinc-400 hover:text-white transition-colors"
            >
              {allSelected ? "Deselect all" : "Select all"}
            </button>
          </div>
          <div className="max-h-64 overflow-y-auto">
            {eligible.length === 0 ? (
              <div className="px-3 py-4 text-[11px] text-zinc-500 text-center">
                No {type} devices.
              </div>
            ) : (
              eligible.map((d: Device) => {
                const checked = selected.includes(d.id);
                const online = statuses[d.id] === "online";
                return (
                  <label
                    key={d.id}
                    className="flex items-center gap-2 px-3 py-1.5 text-xs text-zinc-300 hover:bg-white/5 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggle(d.id)}
                      className="accent-orange-500"
                    />
                    <span
                      className={`w-1.5 h-1.5 rounded-full ${online ? "bg-green-400" : "bg-zinc-600"}`}
                      title={online ? "online" : "offline"}
                    />
                    <span className="flex-1 truncate">
                      {d.name || "(unnamed)"}
                    </span>
                    <span className="text-[10px] text-zinc-500 font-mono truncate">
                      {d.ip_address || "—"}
                    </span>
                  </label>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
