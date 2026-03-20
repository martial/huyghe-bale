import { useEffect } from "react";
import { useNavigate } from "react-router";
import { useTimelineStore } from "../stores/timeline-store";
import TimelineList from "../components/timeline/TimelineList";

export default function TimelinesPage() {
  const navigate = useNavigate();
  const fetchList = useTimelineStore((s) => s.fetchList);
  const createTimeline = useTimelineStore((s) => s.createTimeline);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  async function handleCreate() {
    const tl = await createTimeline({ name: "New Timeline", duration: 60 });
    navigate(`/timelines/${tl.id}`);
  }

  return (
    <div className="p-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="flex items-center justify-between mb-10 pb-4 border-b border-white/10">
        <div>
          <h2 className="text-3xl font-light tracking-tight text-white mb-1">Timelines</h2>
          <p className="text-zinc-400 text-sm">Manage the scheduling and sequencing of events</p>
        </div>
        <button
          onClick={handleCreate}
          className="px-5 py-2.5 bg-gradient-to-r from-orange-500 to-orange-400 hover:from-orange-400 hover:to-orange-300 rounded-xl text-sm font-semibold text-white shadow-[0_0_20px_rgba(249,115,22,0.3)] hover:shadow-[0_0_30px_rgba(249,115,22,0.5)] transition-all duration-300 hover:-translate-y-0.5 active:translate-y-0 active:scale-95"
        >
          <span className="flex items-center gap-2">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
            New Timeline
          </span>
        </button>
      </div>
      <TimelineList />
    </div>
  );
}
