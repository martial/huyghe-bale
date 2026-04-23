import { useEffect, useRef, useState } from "react";
import { usePlaybackStore } from "../../stores/playback-store";

/** Client-only activity log — derives lines from playback-store changes.
 * No backend. Useful as a light telemetry strip: play/pause/seek, lane
 * value drifts, and timeline-switch events. Capped at 50 FIFO. */

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
  kind: "state" | "value";
  text: string;
}

export default function OscActivityBar() {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<Entry[]>([]);
  const prev = useRef<{ playing: boolean; paused: boolean; id: string | null; a: number; b: number }>(
    { playing: false, paused: false, id: null, a: 0, b: 0 },
  );

  useEffect(() => {
    const unsubscribe = usePlaybackStore.subscribe((state) => {
      const s = state.status;
      const p = prev.current;
      const push = (kind: Entry["kind"], text: string) => {
        setEntries((rows) => {
          const next: Entry[] = [{ t: Date.now(), kind, text }, ...rows];
          return next.length > MAX_ROWS ? next.slice(0, MAX_ROWS) : next;
        });
      };

      // State transitions
      if (s.id !== p.id) {
        if (s.id) push("state", `▶ ${s.type ?? "playback"} · ${s.id}`);
        else push("state", `◼ stopped`);
      } else if (s.playing && !s.paused && (!p.playing || p.paused)) {
        push("state", `▶ resume`);
      } else if (s.playing && s.paused && !p.paused) {
        push("state", `⏸ pause @ ${s.elapsed.toFixed(2)}s`);
      } else if (!s.playing && p.playing) {
        push("state", `◼ stop @ ${s.elapsed.toFixed(2)}s`);
      }

      // Value drift (only while playing)
      if (s.playing && !s.paused) {
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
                      e.kind === "state"
                        ? "text-sky-300/80 uppercase tracking-wider text-[10px]"
                        : "text-zinc-500 uppercase tracking-wider text-[10px]"
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
