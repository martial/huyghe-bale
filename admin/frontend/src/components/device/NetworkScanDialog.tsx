import { useState, useEffect } from "react";
import { useDeviceStore } from "../../stores/device-store";

interface ScanRow {
  ip: string;
  osc_port: number;
  ssh: boolean;
  potential_pi: boolean;
  hostname: string;
  selected: boolean;
}

function deviceName(row: ScanRow): string {
  if (row.hostname) return row.hostname;
  return row.potential_pi
    ? `RPi ${row.ip.split(".").pop()}`
    : `Host ${row.ip.split(".").pop()}`;
}

export default function NetworkScanDialog({ onClose }: { onClose: () => void }) {
  const scanning = useDeviceStore((s) => s.scanning);
  const scanResults = useDeviceStore((s) => s.scanResults);
  const scanError = useDeviceStore((s) => s.scanError);
  const scan = useDeviceStore((s) => s.scan);
  const addDiscovered = useDeviceStore((s) => s.addDiscovered);
  const clearScanResults = useDeviceStore((s) => s.clearScanResults);

  const [rows, setRows] = useState<ScanRow[]>([]);

  useEffect(() => {
    scan();
  }, [scan]);

  // Sync scanResults to local rows
  useEffect(() => {
    setRows((prev) => {
      const next = [...prev];
      for (const h of scanResults) {
        const existing = next.find((r) => r.ip === h.ip);
        if (existing) {
          existing.ssh = h.ssh;
          existing.potential_pi = h.potential_pi;
          if (h.hostname && !existing.hostname) {
            existing.hostname = h.hostname;
          }
        } else {
          next.push({
            ip: h.ip,
            osc_port: h.osc_port,
            ssh: h.ssh,
            potential_pi: h.potential_pi,
            hostname: h.hostname,
            selected: false,
          });
        }
      }
      return next;
    });
  }, [scanResults]);

  const selectedCount = rows.filter((r) => r.selected).length;

  function selectAll(val: boolean) {
    setRows((prev) => prev.map((r) => ({ ...r, selected: val })));
  }

  function toggleRow(ip: string) {
    setRows((prev) => prev.map((r) => (r.ip === ip ? { ...r, selected: !r.selected } : r)));
  }

  async function addSelected() {
    const hosts = rows
      .filter((r) => r.selected)
      .map((r) => ({ ip: r.ip, osc_port: r.osc_port, name: deviceName(r) }));
    if (!hosts.length) return;
    await addDiscovered(hosts);
    clearScanResults();
    onClose();
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="bg-zinc-900 border border-zinc-700/50 rounded-2xl w-full max-w-lg mx-4 shadow-2xl">
        <div className="flex items-center justify-between p-5 border-b border-zinc-800/60">
          <h3 className="text-sm font-semibold text-zinc-200">Scan Local Network</h3>
          <button onClick={onClose} className="text-zinc-500 hover:text-white text-lg leading-none transition-colors">&times;</button>
        </div>

        <div className="p-5 space-y-4">
          {scanning && (
            <div className="flex items-center gap-2 text-xs text-zinc-400">
              <span className="inline-block animate-spin">&#9696;</span>
              <span>Scanning... {rows.length} host{rows.length !== 1 ? "s" : ""} found</span>
            </div>
          )}

          {scanError && <p className="text-xs text-red-400">{scanError}</p>}

          {rows.length > 0 && (
            <>
              <div className="flex items-center justify-between text-xs text-zinc-400">
                <span>{rows.length} host{rows.length !== 1 ? "s" : ""} found</span>
                <span className="flex gap-2">
                  <button onClick={() => selectAll(true)} className="hover:text-white transition-colors">Select all</button>
                  <button onClick={() => selectAll(false)} className="hover:text-white transition-colors">Select none</button>
                </span>
              </div>

              <div className="max-h-60 overflow-y-auto space-y-1">
                {rows.map((row) => (
                  <label
                    key={row.ip}
                    className="flex items-center gap-3 p-2 rounded-lg hover:bg-zinc-800/50 cursor-pointer transition-colors"
                  >
                    <input
                      type="checkbox"
                      checked={row.selected}
                      onChange={() => toggleRow(row.ip)}
                      className="accent-orange-500"
                    />
                    <div className="flex-1 min-w-0">
                      <span className="font-mono text-sm text-zinc-300 block">{row.ip}:{row.osc_port}</span>
                      {row.hostname && (
                        <span className="text-[11px] text-zinc-500 block truncate">{row.hostname}</span>
                      )}
                    </div>
                    {row.potential_pi && (
                      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-emerald-900/60 text-emerald-400 shrink-0">
                        Potential Pi
                      </span>
                    )}
                  </label>
                ))}
              </div>

              <button
                onClick={addSelected}
                disabled={!selectedCount}
                className="w-full px-4 py-2 bg-orange-600 hover:bg-orange-500 disabled:opacity-40 rounded-lg text-sm font-medium transition-all duration-200"
              >
                Add Selected ({selectedCount})
              </button>
            </>
          )}

          {!scanning && !rows.length && !scanError && (
            <p className="text-xs text-zinc-500 text-center py-4">
              No hosts found on the local network.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
