import { useEffect, useRef, useState } from "react";
import { usePlaybackStore } from "../../stores/playback-store";
import { useDeviceStore } from "../../stores/device-store";
import { getTrolleyTimeline } from "../../api/trolley";
import type { TrolleyEvent } from "../../types/trolley";

/** Client-only activity log — derives lines from playback-store changes.
 * No backend mods. When a trolley timeline is playing we fetch its event
 * list once so we can log each bang as the cursor crosses it. Vents
 * timelines just show state + A/B value drift. Capped at 50 FIFO. */

const MAX_ROWS = 50;
const VALUE_DELTA = 0.02; // log a lane value change only if >2% moved
const FORMAT_TIME = (t: number) => {
  const d = new Date(t);
  return (
    d.toLocaleTimeString(undefined, { hour12: false }) +
    "." +
    String(d.getMilliseconds()).padStart(3, "0")
  );
};

interface Entry {
  t: number;
  kind: "state" | "value" | "bang";
  text: string;
}

function formatTrolleyBang(ev: TrolleyEvent): string {
  const v = ev.value;
  switch (ev.command) {
    case "enable":   return `enable ${v === 1 ? "on" : "off"}`;
    case "dir":      return `dir ${v === 1 ? "forward" : "reverse"}`;
    case "speed":    return `speed ${typeof v === "number" ? v.toFixed(2) : "0"}`;
    case "position": return `position ${typeof v === "number" ? (v * 100).toFixed(1) + "%" : "0"}`;
    case "step":     return `step ${v ?? 0}`;
    case "stop":     return "stop";
    case "home":     return "home";
  }
}

export default function OscActivityBar() {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<Entry[]>([]);
  const prev = useRef<{ playing: boolean; paused: boolean; id: string | null; elapsed: number; a: number; b: number }>(
    { playing: false, paused: false, id: null, elapsed: 0, a: 0, b: 0 },
  );
  // Cached trolley event list sorted by time, for the currently playing
  // trolley timeline. Fetched on id change; cleared when playback stops.
  const trolleyEvents = useRef<TrolleyEvent[] | null>(null);

  useEffect(() => {
    const push = (kind: Entry["kind"], text: string) => {
      setEntries((rows) => {
        const next: Entry[] = [{ t: Date.now(), kind, text }, ...rows];
        return next.length > MAX_ROWS ? next.slice(0, MAX_ROWS) : next;
      });
    };

    const unsubscribe = usePlaybackStore.subscribe((state) => {
      const s = state.status;
      const p = prev.current;

      // Resolve target device_ids → "name (ip)" for the log.
      const formatTargets = (): string => {
        const ids = state.lastDeviceIds;
        if (!ids || ids.length === 0) return "";
        const devices = useDeviceStore.getState().list;
        const parts = ids
          .map((id) => devices.find((d) => d.id === id))
          .filter((d): d is NonNullable<typeof d> => !!d)
          .map((d) => `${d.name || d.id} (${d.ip_address || "—"})`);
        return parts.length ? ` → ${parts.join(", ")}` : "";
      };

      // State transitions
      if (s.id !== p.id) {
        if (s.id) {
          push("state", `▶ ${s.type ?? "playback"} · ${s.id}${formatTargets()}`);
          // Pull the trolley event list so we can log each bang client-side.
          if (s.type === "trolley-timeline") {
            trolleyEvents.current = null;
            getTrolleyTimeline(s.id)
              .then((tl) => {
                trolleyEvents.current = [...tl.events].sort((x, y) => x.time - y.time);
              })
              .catch(() => {
                trolleyEvents.current = null;
              });
          } else {
            trolleyEvents.current = null;
          }
        } else {
          push("state", `◼ stopped`);
          trolleyEvents.current = null;
        }
      } else if (s.playing && !s.paused && (!p.playing || p.paused)) {
        push("state", `▶ resume`);
      } else if (s.playing && s.paused && !p.paused) {
        push("state", `⏸ pause @ ${s.elapsed.toFixed(2)}s`);
      } else if (!s.playing && p.playing) {
        push("state", `◼ stop @ ${s.elapsed.toFixed(2)}s`);
        trolleyEvents.current = null;
      }

      // Trolley bangs — any event whose time falls in (prev_elapsed, cur_elapsed].
      // Handles loop wrap (cur < prev) by firing from prev→end then 0→cur.
      if (s.playing && !s.paused && trolleyEvents.current && s.elapsed !== p.elapsed) {
        const list = trolleyEvents.current;
        const fireRange = (lo: number, hi: number) => {
          for (const ev of list) {
            if (ev.time > lo && ev.time <= hi) {
              push("bang", `@ ${ev.time.toFixed(2)}s  ${formatTrolleyBang(ev)}`);
            }
          }
        };
        if (s.elapsed >= p.elapsed) {
          fireRange(p.elapsed, s.elapsed);
        } else {
          // loop wrap or seek backwards — log the remainder of last lap + start of new.
          fireRange(p.elapsed, Number.POSITIVE_INFINITY);
          fireRange(-1, s.elapsed);
        }
      }

      // Vents value drift (only while playing, only for non-trolley timelines)
      if (s.playing && !s.paused && s.type !== "trolley-timeline") {
        const a = s.current_values.a;
        const b = s.current_values.b;
        if (Math.abs(a - p.a) >= VALUE_DELTA || Math.abs(b - p.b) >= VALUE_DELTA) {
          push(
            "value",
            `@ ${s.elapsed.toFixed(2)}s  A=${(a * 100).toFixed(0)}%  B=${(b * 100).toFixed(0)}%`,
          );
          prev.current.a = a;
          prev.current.b = b;
        }
      }

      prev.current.playing = s.playing;
      prev.current.paused = s.paused;
      prev.current.id = s.id;
      prev.current.elapsed = s.elapsed;
    });
    return unsubscribe;
  }, []);

  function handleClear() {
    setEntries([]);
  }

  return (
    <div className="fixed bottom-0 left-64 right-0 z-50 bg-zinc-950/95 backdrop-blur border-t border-white/10 text-zinc-300">
      <button
        onClick={() => setOpen((s) => !s)}
        className="w-full flex items-center gap-3 px-4 py-1.5 hover:bg-white/5 transition-colors text-left"
      >
        <span
          className={`w-2 h-2 rounded-full ${entries.length > 0 && Date.now() - entries[0].t < 2000 ? "bg-orange-400 shadow-[0_0_6px_rgba(251,146,60,0.6)]" : "bg-zinc-600"}`}
        />
        <span className="text-[11px] uppercase tracking-wider font-semibold text-zinc-400">
          Activity
        </span>
        <span className="text-[10px] font-mono text-zinc-500">
          <span className="text-zinc-300">{entries.length}</span> / {MAX_ROWS}
        </span>
        {!open && entries[0] && (
          <span className="ml-2 truncate text-[10px] font-mono text-zinc-500 max-w-[60%]">
            {entries[0].text}
          </span>
        )}
        <svg
          className={`ml-auto w-3.5 h-3.5 text-zinc-500 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M5 15l7-7 7 7" />
        </svg>
      </button>

      {open && (
        <div className="border-t border-white/5">
          <div className="flex items-center justify-between px-4 py-1 bg-black/40 border-b border-white/5">
            <span className="text-[10px] uppercase tracking-wider text-zinc-500 font-mono">
              last {MAX_ROWS} events (client-derived from playback state)
            </span>
            <button
              onClick={handleClear}
              className="text-[10px] text-zinc-400 hover:text-white transition-colors"
            >
              clear
            </button>
          </div>
          <div className="max-h-[30vh] overflow-y-auto font-mono">
            {entries.length === 0 ? (
              <div className="px-4 py-6 text-center text-[11px] text-zinc-500">
                Waiting — press Play on a timeline.
              </div>
            ) : (
              entries.map((e, i) => (
                <div
                  key={`${e.t}-${i}`}
                  className="grid grid-cols-[110px_60px_1fr] gap-3 px-4 py-1 text-[11px] border-b border-white/5 last:border-b-0 hover:bg-white/[0.02]"
                >
                  <span className="text-zinc-500">{FORMAT_TIME(e.t)}</span>
                  <span
                    className={
                      "uppercase tracking-wider text-[10px] " +
                      (e.kind === "state"
                        ? "text-sky-300/80"
                        : e.kind === "bang"
                        ? "text-emerald-300/80"
                        : "text-zinc-500")
                    }
                  >
                    {e.kind}
                  </span>
                  <span className="text-zinc-200 truncate">{e.text}</span>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
