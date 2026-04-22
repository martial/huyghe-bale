import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { useTrolleyStore } from "../stores/trolley-store";
import { useDeviceStore } from "../stores/device-store";
import TrolleyTimelineList from "../components/trolley/TrolleyTimelineList";
import TrolleyTestPanel from "../components/trolley/TrolleyTestPanel";

type Tab = "panel" | "timelines";

export default function TrolleysPage() {
  const navigate = useNavigate();
  const fetchTimelines = useTrolleyStore((s) => s.fetchList);
  const createTrolleyTimeline = useTrolleyStore((s) => s.createTrolleyTimeline);
  const devices = useDeviceStore((s) => s.list);
  const fetchDevices = useDeviceStore((s) => s.fetchList);
  const [tab, setTab] = useState<Tab>("panel");

  useEffect(() => {
    fetchTimelines();
    fetchDevices();
  }, [fetchTimelines, fetchDevices]);

  const trolleys = devices.filter((d) => d.type === "trolley");

  async function handleCreate() {
    const tl = await createTrolleyTimeline({ name: "New Trolley Timeline", duration: 60 });
    navigate(`/trolleys/${tl.id}`);
  }

  return (
    <div className="p-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="flex items-center justify-between mb-8 pb-4 border-b border-white/10">
        <div>
          <h2 className="text-3xl font-light tracking-tight text-white mb-1">Trolleys</h2>
          <p className="text-zinc-400 text-sm">Test panel &amp; position timelines for trolley devices</p>
        </div>
        {tab === "timelines" && (
          <button
            onClick={handleCreate}
            className="px-5 py-2.5 bg-gradient-to-r from-sky-500 to-sky-400 hover:from-sky-400 hover:to-sky-300 rounded-xl text-sm font-semibold text-white shadow-[0_0_20px_rgba(56,189,248,0.3)] hover:shadow-[0_0_30px_rgba(56,189,248,0.5)] transition-all duration-300 hover:-translate-y-0.5 active:translate-y-0 active:scale-95"
          >
            <span className="flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              New Timeline
            </span>
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6">
        <button
          onClick={() => setTab("panel")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            tab === "panel"
              ? "bg-sky-600 text-white"
              : "bg-zinc-800/60 hover:bg-zinc-700/60 text-zinc-300"
          }`}
        >
          Test panel
        </button>
        <button
          onClick={() => setTab("timelines")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            tab === "timelines"
              ? "bg-sky-600 text-white"
              : "bg-zinc-800/60 hover:bg-zinc-700/60 text-zinc-300"
          }`}
        >
          Timelines
        </button>
      </div>

      {tab === "panel" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {trolleys.length === 0 && (
            <div className="col-span-full flex flex-col items-center justify-center p-16 border border-white/5 border-dashed rounded-3xl bg-zinc-900/20">
              <p className="text-zinc-300 text-lg font-medium">No trolley devices yet</p>
              <p className="text-zinc-500 text-sm mt-2">
                Add a device of type <span className="font-mono">trolley</span> on the Devices page.
              </p>
            </div>
          )}
          {trolleys.map((d) => (
            <TrolleyTestPanel key={d.id} device={d} />
          ))}
        </div>
      )}

      {tab === "timelines" && <TrolleyTimelineList />}
    </div>
  );
}
